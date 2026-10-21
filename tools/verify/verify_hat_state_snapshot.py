#!/usr/bin/env python3
"""Paired actual DSP proof for frozen Hat snapshots in scheduled readback.

PKFM11's unchanged ColdFire image supplies ordinary source packets. The new
and old DSP programs receive identical packets, except the old partner has the
new request bit clear. No target synthesis state is copied or repaired.
"""
import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys

import verify_perky_hybrid_runtime as rt

ROOT = rt.ROOT
sys.path[:0] = [str(ROOT / p) for p in ('tools', 'tools/build')]
import ab_records as A

BASE, WORDS, CURSOR = 0x7a5, 190, 0x863
U16, U32, I32 = C.c_uint16, C.c_uint32, C.c_int32


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build_bridge(out):
    vendor = ROOT / 'vendor/dsp56300'
    original = ROOT / 'tools/harness/perky_cf/full_map_dsp_bridge.cpp'
    memory = vendor / 'source/dsp56kEmu/memory.cpp'
    text = memory.read_text()
    marker = 'TWord Memory::get( EMemArea _area, TWord _offset ) const\n\t{'
    assert text.count(marker) == 1
    text = 'extern "C" void fm_snapshot_read_hook(unsigned,unsigned);\n' + text.replace(
        marker, marker + '\n        fm_snapshot_read_hook(unsigned(_area), _offset);')
    staged_memory = out / 'memory.cpp'
    staged_memory.write_text(text)
    bridge = out / 'bridge.cpp'
    bridge_source = original.read_text()
    marker = 'if(dsp.getPC().toWord()==0x426)'
    assert bridge_source.count(marker) == 1
    # Plain CF PCM/import packets return to the harness caller; resident Hat
    # source packets resume at the stock source continuation instead.
    bridge_source = bridge_source.replace(marker, 'if(dsp.getPC().toWord()==0x426||dsp.getPC().toWord()==0x5002)')
    bridge.write_text(bridge_source + '\n' + r'''
#include <array>
#include <map>
struct SnapshotAudit {
 std::array<unsigned,191> reads{},writes{};bool sealed=false;
};
static std::map<FMBridge*,SnapshotAudit> snapshot_audit;
static FMBridge* snapshot_active=nullptr;
extern "C" void fm_snapshot_read_hook(unsigned area,unsigned at){
 if(snapshot_active&&area==unsigned(MemArea_Y)&&at>=0x7a5&&at<=0x863)
  snapshot_audit.at(snapshot_active).reads[at-0x7a5]++;
}
extern "C" void* fm_snapshot_open(const char*c,const char*d,unsigned entry){
 auto*p=static_cast<FMBridge*>(fm_dsp_open(c,d,entry));if(!p)return nullptr;
 snapshot_audit.emplace(p,SnapshotAudit{});
 p->mem.setWriteHook([p](EMemArea area,TWord at,TWord){
  if(snapshot_active==p&&area==MemArea_Y&&at>=0x7a5&&at<=0x863)
   snapshot_audit.at(p).writes[at-0x7a5]++;
 });return p;
}
extern "C" int fm_snapshot_step(void*p,const uint16_t*packet,unsigned n,int32_t*pcm,uint16_t*state,uint16_t*side,uint32_t*clock,uint16_t*mail){
 auto*b=static_cast<FMBridge*>(p);snapshot_audit.at(b).sealed=true;snapshot_active=b;
 int result=fm_dsp_step(p,packet,n,pcm,state,side,clock,mail);snapshot_active=nullptr;return result;
}
extern "C" unsigned fm_snapshot_peek(void*p,unsigned area,unsigned at){
 return static_cast<FMBridge*>(p)->mem.get(EMemArea(area),at);
}
extern "C" unsigned fm_snapshot_return_pc(void*p){
 return static_cast<FMBridge*>(p)->dsp.getPC().toWord();
}
extern "C" int fm_snapshot_poke_before_execution(void*p,unsigned area,unsigned at,unsigned value){
 auto*b=static_cast<FMBridge*>(p);if(snapshot_audit.at(b).sealed)return 0;
 b->mem.set(EMemArea(area),at,value);return 1;
}
extern "C" void fm_snapshot_counts(void*p,unsigned*reads,unsigned*writes){
 auto&a=snapshot_audit.at(static_cast<FMBridge*>(p));
 std::copy(a.reads.begin(),a.reads.end(),reads);std::copy(a.writes.begin(),a.writes.end(),writes);
}
extern "C" void fm_snapshot_reset_counts(void*p){
 auto&a=snapshot_audit.at(static_cast<FMBridge*>(p));a.reads.fill(0);a.writes.fill(0);
}
extern "C" void fm_snapshot_probe_read(void*p){
 auto*b=static_cast<FMBridge*>(p);snapshot_audit.at(b).sealed=true;snapshot_active=b;
 b->dsp.setPC(0x5010);b->dsp.execInterpreter();snapshot_active=nullptr;
}
extern "C" void fm_snapshot_close(void*p){
 auto*b=static_cast<FMBridge*>(p);b->mem.setWriteHook({});snapshot_audit.erase(b);fm_dsp_close(p);
}
''')
    dll = out / 'snapshot.dylib'
    command = ['c++', '-O3', '-shared', '-fPIC', '-DNDEBUG', '-std=gnu++17',
               '-DASMJIT_STATIC', '-DDSP56300_DEBUGGER=0',
               '-I' + str(vendor / 'source'), '-I' + str(vendor / 'source/dsp56kEmu'),
               '-I' + str(vendor / 'source/asmjit/src'), str(bridge), str(staged_memory),
               *[str(vendor / ('build/source/' + name)) for name in (
                   'dsp56kEmu/libdsp56kEmu.a', 'dsp56kBase/libdsp56kBase.a', 'asmjit/libasmjit.a')],
               '-lpthread', '-o', str(dll)]
    with (out / 'compile.log').open('w') as log:
        subprocess.run(command, check=True, stdout=log, stderr=subprocess.STDOUT)
    return dll, command, (original, memory, bridge, staged_memory)


def flatten(build, directory):
    blob = (build / 'dsp-A.upload.bin').read_bytes()
    records, _ = A.records(blob, A.BASE, len(blob))
    flat = [0] * 0x40000
    data = []
    for space, at, n, offset in records:
        words = [A.rd(blob, offset + 3 * i) for i in range(n)]
        if space == 0:
            flat[at:at + n] = words
        else:
            data.append(('X' if space == 1 else 'Y') + f' {at:x} ' +
                        ' '.join(f'{value:x}' for value in words) + '\n')
    code, initial = directory / 'code.bin', directory / 'initial.data'
    code.write_bytes(b''.join(value.to_bytes(3, 'little') for value in flat))
    initial.write_text(''.join(data))
    return code, initial


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--producer', type=Path, default=ROOT / 'out/perky/hybrid/full-map-budget-v5')
    parser.add_argument('--frames', type=int, default=400)
    args = parser.parse_args()
    assert args.frames >= 400
    build, producer = args.build.resolve(), args.producer.resolve()
    out = build / 'snapshot-gate'
    out.mkdir(exist_ok=True)
    dll, command, bridge_sources = build_bridge(out)
    lib = C.CDLL(str(dll))
    lib.fm_snapshot_open.argtypes = [C.c_char_p, C.c_char_p, U32]
    lib.fm_snapshot_open.restype = C.c_void_p
    lib.fm_snapshot_step.argtypes = [C.c_void_p, C.POINTER(U16), U32, C.POINTER(I32),
                                     C.POINTER(U16), C.POINTER(U16), C.POINTER(U32), C.POINTER(U16)]
    lib.fm_snapshot_peek.argtypes = [C.c_void_p, U32, U32]
    lib.fm_snapshot_peek.restype = U32
    lib.fm_snapshot_return_pc.argtypes = [C.c_void_p]
    lib.fm_snapshot_return_pc.restype = U32
    lib.fm_snapshot_poke_before_execution.argtypes = [C.c_void_p, U32, U32, U32]
    lib.fm_snapshot_poke_before_execution.restype = C.c_int
    lib.fm_snapshot_counts.argtypes = [C.c_void_p, C.POINTER(U32), C.POINTER(U32)]
    lib.fm_snapshot_reset_counts.argtypes = [C.c_void_p]
    lib.fm_snapshot_probe_read.argtypes = [C.c_void_p]
    lib.fm_snapshot_close.argtypes = [C.c_void_p]
    lib.fm_dsp_error.restype = C.c_char_p
    code, initial = flatten(build, out)
    entry = json.loads((build / 'program/resident-symbols.json').read_text())['source_entry']
    old_entry = json.loads((producer / 'program/resident-symbols.json').read_text())['source_entry']
    old_code, old_initial = producer / 'import-gate/code.bin', producer / 'import-gate/initial.data'
    handles = []

    def opened(c, d, e):
        handle = lib.fm_snapshot_open(str(c).encode(), str(d).encode(), e)
        assert handle, lib.fm_dsp_error()
        handles.append(handle)
        return handle

    def counts(handle):
        read, written = (U32 * 191)(), (U32 * 191)()
        lib.fm_snapshot_counts(handle, read, written)
        return list(read), list(written)

    try:
        # Calibrate the read watch with an actual DSP load on a separate target.
        probe = opened(code, initial, entry)
        probe_source, probe_binary = out / 'read-probe.asm', out / 'read-probe.bin'
        probe_source.write_text(' move y:>$7a5,a\n')
        asm = ROOT / 'vendor/dsp56300/build/source/dsp_host/dsp_asm'
        asm_command = [str(asm), '-in', str(probe_source), '-org', '5010', '-out', str(probe_binary), '-list']
        listing = subprocess.run(asm_command, check=True, capture_output=True, text=True)
        (out / 'read-probe.list').write_text(listing.stdout + listing.stderr)
        disassembler = ROOT / 'vendor/dsp56300/build/source/disassemble/dsp56kDisassemble'
        dis = subprocess.run([str(disassembler), '-in', str(probe_binary), '-pc', '5010', '-le'],
                             check=True, capture_output=True, text=True)
        (out / 'read-probe.dis').write_text(dis.stdout)
        assert 'y:' in dis.stdout.lower() and '7a5' in dis.stdout.lower()
        for i in range(len(probe_binary.read_bytes()) // 3):
            value = int.from_bytes(probe_binary.read_bytes()[3 * i:3 * i + 3], 'little')
            assert lib.fm_snapshot_poke_before_execution(probe, 0, 0x5010 + i, value)
        lib.fm_snapshot_reset_counts(probe)
        lib.fm_snapshot_probe_read(probe)
        assert counts(probe)[0][0] == 1, 'DSP Y read watch is structurally blind'

        current, old = opened(code, initial, entry), opened(old_code, old_initial, old_entry)
        poison = [((i * 0x39e71) ^ 0xa55aff) & 0xffffff for i in range(WORDS)]
        for i, value in enumerate(poison):
            assert lib.fm_snapshot_poke_before_execution(current, 2, BASE + i, value)
        boot = rt.g.emu.boot
        rt.g.emu.boot = lambda image: boot(image, count=200000000)
        version = json.loads((producer / 'BUILD.json').read_text())['version']
        image = producer / 'probe' / f'mainos_{version}.bin'
        machine, symbols = rt.machine(image, producer / 'probe/platform/runtime.elf', True)
        u = machine.uc
        if not any(lo <= 0x48000000 and hi >= 0x480fffff for lo, hi, _ in u.mem_regions()):
            u.mem_map(0x48000000, 0x100000)
        packet_at = 0x48010000
        pending, stream, frozen = [], None, poison.copy()
        captures, complete, canceled, ring_words = [], [], [], 0
        significant = [0, 0, 0]
        positive = [0, 0, 0]
        negative = [0, 0, 0]
        requests = {64, 200, 260, 300}
        last_writes = [0] * 191
        for frame in range(args.frames):
            if len(pending) >= 3:
                u.mem_write(symbols['pk_nhr_mail'], pending.pop(0))
            generation = 1 if frame < 250 else 2
            rt.w32(u, symbols['pk_prod_generation'], generation)
            mode = ((frame // 16) % 3 if frame < 64 else
                    0 if frame < 200 else 1 if frame < 250 else
                    2 if frame < 286 else (frame // 3) % 3)
            control = [5, mode, 96 + frame % 32, frame * 7 % 128,
                       frame * 13 % 128, frame * 19 % 128, 255, 45, 0, int(frame % 7 == 0)]
            u.mem_write(symbols['placement_inputs'] + 120, struct.pack('>10I', *control))
            rt.g.emu._call(u, symbols['pk_nhr_frame'], (0, packet_at))
            packet = list(struct.unpack('>168H', u.mem_read(packet_at, 336)))
            assert packet[0] == 0x4e54 and packet[2] & 31 == 0
            second = 5 + 2 * packet[4]
            assert second < 168 and not packet[second] & 0x800
            if frame in requests:
                assert stream is None
                packet[second] |= 0x800
            responses = []
            for handle, wire in ((current, packet), (old, [v & ~0x800 if i == second else v for i, v in enumerate(packet)])):
                pcm, state, side, clock, mail = (I32 * 16)(), (U16 * 180)(), (U16 * 6)(), (U32 * 3)(), (U16 * 24)()
                assert lib.fm_snapshot_step(handle, (U16 * 168)(*wire), 168, pcm, state, side, clock, mail), lib.fm_dsp_error()
                assert lib.fm_snapshot_return_pc(handle) == 0x426, (frame, 'resident source did not render')
                responses.append((list(pcm), list(state), list(side), list(clock), list(mail)))
            now, reference = responses
            assert now[:4] == reference[:4], (frame, 'PCM/state/side/clock')
            significant[mode] += sum(abs(value) > 64 for value in now[0])
            positive[mode] += sum(value > 64 for value in now[0])
            negative[mode] += sum(value < -64 for value in now[0])
            n = now[4][2]
            assert now[4][:3] == reference[4][:3] and n <= 20
            assert now[4][4:4 + n] == reference[4][4:4 + n], (frame, 'ring feedback')
            ring_words += n
            reads, writes = counts(current)
            payload = [lib.fm_snapshot_peek(current, 2, BASE + i) for i in range(WORDS)]
            if frame in requests:
                semantic = [now[4][1], *now[1], *now[2], *[value & 65535 for value in now[3]]]
                assert [value & 65535 for value in payload] == semantic, (frame, 'capture state coherence')
                frozen = payload
                assert all(writes[i] - last_writes[i] == 1 for i in range(WORDS)), (frame, 'capture writes')
                stream = dict(frame=frame, sequence=now[4][1], offset=0)
                captures.append(dict(frame=frame, sequence=stream['sequence'], mode=mode, generation=generation))
            else:
                assert payload == frozen, (frame, 'frozen snapshot changed')
                assert writes[:WORDS] == last_writes[:WORDS], (frame, 'unexpected snapshot writes')
            if frame < 64:
                assert sum(reads[:WORDS]) == sum(writes[:WORDS]) == 0, (frame, 'retired Y region used by synthesis')
            if frame == 250:
                assert stream is not None and 0 < stream['offset'] < WORDS
                canceled.append(stream.copy())
                stream = None
                assert now[4][3] == 0 and lib.fm_snapshot_peek(current, 2, CURSOR) == WORDS
            elif stream is not None:
                available = min(20 - n, WORDS - stream['offset'])
                if available:
                    assert now[4][3] == (0x8000 | stream['offset']), (frame, 'snapshot offset')
                    assert now[4][4 + n:4 + n + available] == [value & 65535 for value in frozen[stream['offset']:stream['offset'] + available]]
                    stream['offset'] += available
                    if stream['offset'] == WORDS:
                        complete.append(dict(stream, end_frame=frame))
                        stream = None
                else:
                    assert now[4][3] == 0
            else:
                assert now[4][3] == 0, (frame, 'unexpected snapshot carrier')
            last_writes = writes
            pending.append(struct.pack('>24H', *reference[4]))
            rt.g.emu._call(u, symbols['pk_nhb_work'], ())
            assert rt.word(u, symbols['pk_nhr_failures']) == 0
        assert len(captures) == 4 and len(complete) == 3 and len(canceled) == 1 and stream is None
        assert ring_words > 0
        assert all(value > 64 for value in significant), ('inactive source mode', significant)
        assert all(value > 0 for value in positive + negative), ('missing bipolar source', positive, negative)
        assert all(value == 4 for value in counts(current)[1][:WORDS])
        candidate_version = json.loads((build / 'BUILD.json').read_text())['version']
        candidate_image = build / 'probe' / f'mainos_{candidate_version}.bin'
        result = dict(status='PASS_FROZEN_DSP_SNAPSHOT_AUDIO_STATE_AND_RING_FEEDBACK',
                      frames=args.frames, captures=captures, completed=complete, canceled=canceled,
                      ring_feedback_words_checked=ring_words, snapshot_payload_words=WORDS,
                      mode_source_significant=significant, mode_source_positive=positive,
                      mode_source_negative=negative,
                      snapshot_payload_address=BASE, snapshot_cursor_address=CURSOR,
                      payload_writes_per_word=4, read_watch_positive_control=True,
                      retired_Y_payload_reads_before_request=0,
                      retired_Y_payload_writes_before_request=0,
                      image_sha256=sha(candidate_image),
                      producer_image_sha256=sha(image),
                      source_sha256={str(p.relative_to(ROOT)): sha(p) for p in (Path(__file__).resolve(), *bridge_sources)},
                      inputs={str(p): sha(p) for p in (build / 'dsp-A.upload.bin', code, initial, old_code, old_initial, dll)},
                      commands=[command, asm_command],
                      limits=['Direct interpreted DSP proof; whole-machine timing and CF snapshot catch-up/handoffs are separate.',
                              'Only ordinary source packets change the two DSP states after initialization; the separate read-watch calibration uses its own target instance.',
                              'Paired PKFM11 DSP is the preserved binary reference; the full production source gates additionally compare independent original algorithm streams.'])
        (build / 'SNAPSHOT_DSP_GATE.json').write_text(json.dumps(result, indent=2) + '\n')
        print(result['status'], args.frames, 'frames', ring_words, 'ring feedback words')
    finally:
        for handle in handles:
            lib.fm_snapshot_close(handle)


if __name__ == '__main__':
    main()

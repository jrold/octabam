#!/usr/bin/env python3
"""Execute hybrid boot readiness, event reset, bit identity and profile export."""
import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/verify'))
import verify_perky_hybrid_probe_gates as g
from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE


def sizes(elf):
    import subprocess
    rows = subprocess.check_output(['m68k-elf-nm', '-S', str(elf)], text=True)
    return {f[3]: int(f[1], 16) for line in rows.splitlines() if len(f := line.split()) == 4}


def w32(u, a, v): u.mem_write(a, (v & 0xffffffff).to_bytes(4, 'big'))
def word(u, a): return int.from_bytes(u.mem_read(a, 4), 'big')
def digest(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def machine(image, elf, require_boot_ready=False):
    r = g.emu.boot(str(image)); assert r.clean, (r.stopped, r.error)
    g.emu._prime_part(r); syms = g.load_elf_symbols(elf); u = r.uc
    if require_boot_ready:
        assert word(u, syms['pk_hybrid_pcm_cookie']) == 0x504b5052
        assert word(u, syms['pk_hybrid_rt_cookie']) == 0x504b4852
    g.emu._call(u, syms['pk_ui_tick'])
    part = word(u, g.emu.PART_PTR) + 0x8ed80
    for part_index in range(4):
        for track in (1, 5):
            u.mem_write(part + part_index * 0x18b2 + 0x22 + track, b'\x01')
            u.mem_write(part + part_index * 0x18b2 + 60 + 30 * track, b'PK\x01')
    w32(u, 0x800062a8, 0x80008000)
    w32(u, syms['pk_hybrid_profiler_enable'], 0)
    return r, syms


def args_for(u, track, frame, split, syms):
    vals = (24 + frame % 80, 80 + frame % 48, (frame // 17 + track) % 3,
            frame * 13 % 128, frame * 19 % 128, frame // 11 % 3)
    for k, v in enumerate(vals): u.mem_write(0x80008000 + 2*k, (v << 8).to_bytes(2, 'big'))
    w32(u, 0x80001c80, 0x80010000)
    u.mem_write(0x46104d0c + track, bytes([16 if frame % 3 == 0 else 0]))
    g.emu._call(u, syms['pk_render'], (track, 0, 0, split))
    u.mem_write(0x46104d0c + track, b'\0')
    g.emu._call(u, syms['pk_render'], (track, 1, split, 16))
    return bytes(u.mem_read(0x80001c90 + 0xa80 + 336*track, 160))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--work', type=Path, default=ROOT/'out/perky/hybrid')
    ap.add_argument('--reference', type=Path, default=ROOT/'out/perky/hybrid/resume-fixes/before')
    ap.add_argument('--frames', type=int, default=256)
    a = ap.parse_args(); p = a.work.resolve()/'probe'; out = a.work.resolve()/'resume-fixes'
    out.mkdir(exist_ok=True)
    r, syms = machine(p/'mainos_PKHYB2P.bin', p/'platform/runtime.elf', True); u = r.uc
    sz = sizes(p/'platform/runtime.elf')
    assert word(u, syms['pk_hybrid_pcm_cookie']) == 0x504b5052
    assert word(u, syms['pk_hybrid_rt_cookie']) == 0x504b4852
    assert word(u, syms['pk_hybrid_prof_cookie']) == 0x504b5452
    result = {'status': 'RUNNING', 'boot_ready_before_UI_or_audio': True}

    # Compiler inserts aggregate tail bytes on m68k: require a complete,
    # deterministic initializer even with dirty destinations.
    initial_pcm = bytes(u.mem_read(syms['pk_pcm_wt_base'], 4096)) + bytes(
        u.mem_read(syms['pk_pcm_wt_bank'], 196608))
    for name in ('pk_hybrid_voices', 'pk_hybrid_pristine'):
        u.mem_write(syms[name], b'\xa5' * sz[name])
    g.emu._call(u, syms['pk_hybrid_boot_init'])
    assert u.reg_read(g.emu.UC_M68K_REG_D0) == 1
    n = sz['pk_hybrid_pristine']; virgin = bytes(u.mem_read(syms['pk_hybrid_pristine'], n))
    assert bytes(u.mem_read(syms['pk_hybrid_voices'], 2*n)) == virgin*2
    reinitialized_pcm = bytes(u.mem_read(syms['pk_pcm_wt_base'], 4096)) + bytes(
        u.mem_read(syms['pk_pcm_wt_bank'], 196608))
    assert reinitialized_pcm == initial_pcm, 'BSS scrub invalidated PCM behind a READY cookie'
    result['reinitialized_PCM_equal'] = {'bytes': len(initial_pcm),
        'sha256': hashlib.sha256(reinitialized_pcm).hexdigest()}
    result['poisoned_voice_initialization'] = {'bytes': 3*n, 'template_bytes': n}

    # Neither callbacks nor UI may decode or mutate waveform assets.
    asset_writes = []
    hooks = [u.hook_add(UC_HOOK_MEM_WRITE,
              lambda mu, k, addr, size, v, d: asset_writes.append((addr, size)),
              begin=syms[name], end=syms[name]+sz_bytes-1)
             for name, sz_bytes in [('pk_pcm_wt_base', 4096), ('pk_pcm_wt_bank', 196608)]]
    old, old_syms = machine(a.reference/'mainos_PKHYB2P.bin', a.reference/'platform/runtime.elf')
    state_hash = hashlib.sha256(); audio_hash = hashlib.sha256()
    for f in range(a.frames):
        for t in (1, 5):
            now = args_for(u, t, f, f % 16, syms)
            reference = args_for(old.uc, t, f, f % 16, old_syms)
            assert now == reference, ('record PCM changed', f, t)
            audio_hash.update(now)
        state = bytes(u.mem_read(syms['pk_hybrid_voices'], sz['pk_hybrid_voices']))
        assert state == bytes(old.uc.mem_read(old_syms['pk_hybrid_voices'], sz['pk_hybrid_voices'])), ('state/RNG changed', f)
        state_hash.update(state)
    result['bit_exact_reference'] = {'frames': a.frames, 'split_offsets': 16,
        'stereo_source_records': a.frames*2, 'PCM_sha256': audio_hash.hexdigest(),
        'state_RNG_sha256': state_hash.hexdigest(), 'reference_image_sha256': digest(a.reference/'mainos_PKHYB2P.bin')}

    # Exact fallback for out-of-range state: public knobs remain 7-bit,
    # but deliberately corrupt old smoothers to exercise the guarded path.
    saved = bytes(u.mem_read(syms['pk_hybrid_voices'], sz['pk_hybrid_voices']))
    for case in range(8):
        for mu, symbols in ((u, syms), (old.uc, old_syms)):
            obj = symbols['pk_hybrid_voices'] + 2*0x150 + (0x1d4 if case & 1 else 0)
            for k, value in enumerate((0xfffffffe,0x80000000,0x12345678,0xf00f0123)):
                mu.mem_write(obj+0x1c+4*k, value.to_bytes(4,'little'))
            g.emu._call(mu, symbols['pk_hybrid_cf_prepare_event'],
                        (0,127,case*13,23,101,case & 1,2,255,45,case & 1))
        assert bytes(u.mem_read(syms['pk_hybrid_voices'],len(saved))) == bytes(old.uc.mem_read(old_syms['pk_hybrid_voices'],len(saved)))
    for mu, symbols in ((u,syms),(old.uc,old_syms)):
        mu.mem_write(symbols['pk_hybrid_voices'],saved)
    result['out_of_range_smoother_reference_cases'] = 8

    # UI ticks never reset live audio state, even after a Part index changes.
    state = bytes(u.mem_read(syms['pk_hybrid_voices'], sz['pk_hybrid_voices']))
    u.mem_write(0x100b14cf, b'\x01')
    g.emu._call(u, syms['pk_ui_tick'])
    assert state == bytes(u.mem_read(syms['pk_hybrid_voices'], len(state)))
    args_for(u, 1, a.frames, 7, syms)
    assert word(u, syms['pk_hybrid_prof'] + 67*4 + 369*4) > 0 # v2 reset_count
    assert not asset_writes, asset_writes[:5]
    for h in hooks: u.hook_del(h)
    result['no_realtime_asset_writes_or_UI_state_reset'] = 'PASS'

    # Explicit fault injection: a corrupted COLD cookie delegates to stock;
    # it may not execute the decoder or hide a missing boot initialization.
    cold_calls = []
    def stock(mu, pc, size, data):
        cold_calls.append(pc); sp = mu.reg_read(g.emu.UC_M68K_REG_A7)
        mu.reg_write(g.emu.UC_M68K_REG_D0, 0)
        mu.reg_write(g.emu.UC_M68K_REG_PC, word(mu, sp))
        mu.reg_write(g.emu.UC_M68K_REG_A7, sp+4)
    hook = u.hook_add(UC_HOOK_CODE, stock, begin=0x40004008, end=0x40004008); u.ctl_flush_tb()
    w32(u, syms['pk_hybrid_pcm_cookie'], 0x504b5043)
    g.emu._call(u, syms['pk_render'], (1, 0, 0, 16))
    assert len(cold_calls) == 1
    w32(u, syms['pk_hybrid_pcm_cookie'], 0x504b5052); u.hook_del(hook)
    result['cold_cookie_fault_delegates_without_decode'] = 'PASS'

    # Snapshot collision must be detected without spinning or publishing torn data.
    # Continuous debug snapshots are now an explicit opt-in; keep this test.
    w32(u, syms['pk_hybrid_live_snapshot'], 1)
    w32(u, syms['pk_hybrid_profiler_enable'], 1)
    w32(u, syms['pk_hybrid_prof_seq'], 0)
    before = word(u, syms['pk_hybrid_export_seq']); collision = []
    def interrupt(mu, kind, addr, size, value, data):
        if not collision:
            collision.append(True); w32(mu, syms['pk_hybrid_prof_seq'], 2)
    h = u.hook_add(UC_HOOK_MEM_WRITE, interrupt, begin=syms['pk_hybrid_snapshot'], end=syms['pk_hybrid_snapshot']+sz['pk_hybrid_snapshot']-1)
    g.emu._call(u, syms['pk_ui_tick']); u.hook_del(h)
    assert collision and word(u, syms['pk_hybrid_export_seq']) == before
    g.emu._call(u, syms['pk_ui_tick'])
    assert word(u, syms['pk_hybrid_export_seq']) == before+2
    result['snapshot_collision_detected_without_spin'] = 'PASS'
    w32(u, syms['pk_hybrid_live_snapshot'], 0)

    # One frame count for many split callbacks, with unsigned timer wrap.
    u.mem_unmap(0xfc000000, 0x100000)
    u.mem_map(0xfc000000, 0x100000) # direct-call wrap fixture, no RTOS/peripherals running
    w32(u, 0xfc07c00c, 0x30)
    g.emu._call(u, syms['pk_hybrid_reset_profiler'])
    w32(u, syms['pk_hybrid_isr_enter_ticks'], 0xfffffff0)
    g.emu._call(u, syms['pk_hybrid_frame_begin'])
    for tr in (1, 5): args_for(u, tr, 8, 7, syms)
    g.emu._call(u, syms['pk_hybrid_frame_end'])
    assert word(u, syms['pk_hybrid_prof'] + 6*4) == 1
    assert word(u, syms['pk_hybrid_prof'] + 18*4) == 64
    assert word(u, syms['pk_hybrid_prof'] + 11*4) == 2
    result['frame_count_and_timer_wrap'] = {'frames': 1, 'split_callbacks': 4, 'elapsed_ticks': 64}

    # Hardware file-writer ABI: only UI after stop, no overwrite of an existing
    # diagnostic, exact payload/header/source identity and valid decoder input.
    fs_calls = []; payloads = []
    def fs(mu, pc, size, data):
        sp = mu.reg_read(g.emu.UC_M68K_REG_A7)
        args = [word(mu, sp+4+4*i) for i in range(5)]
        if pc == 0x40016864:
            path = bytes(mu.mem_read(args[1], 13)).split(b'\0')[0].decode()
            mode = bytes(mu.mem_read(args[2], 2)).split(b'\0')[0].decode()
            ret = -1 if mode == 'r' else 0
            fs_calls.append(('open', path, mode))
        elif pc == 0x400166b8:
            payloads.append(bytes(mu.mem_read(args[1], args[2]))); ret = 1
            fs_calls.append(('write', args[2]))
        else: ret = 0; fs_calls.append(('close',))
        mu.reg_write(g.emu.UC_M68K_REG_D0, ret & 0xffffffff)
        mu.reg_write(g.emu.UC_M68K_REG_PC, word(mu, sp)); mu.reg_write(g.emu.UC_M68K_REG_A7, sp+4)
    hs = [u.hook_add(UC_HOOK_CODE, fs, begin=pc, end=pc) for pc in (0x40016864,0x400166b8,0x4001677c)]
    u.ctl_flush_tb(); w32(u, 0x800065b8, 1); g.emu._call(u, syms['pk_ui_tick'])
    assert not fs_calls
    w32(u, 0x800065b8, 2); g.emu._call(u, syms['pk_ui_tick'])
    assert len(payloads) == 1 and word(u, syms['pk_hybrid_export_status']) == 1
    g.emu._call(u, syms['pk_ui_tick']); assert len(payloads) == 1
    for h in hs: u.hook_del(h)
    export = out/'ABI_PROFILE.PRF'; export.write_bytes(payloads[0])
    sys.path.insert(0, str(ROOT/'tools/perky')); from read_hybrid_profile import read_export
    decoded = read_export(export, json.loads((p/'BUILD.json').read_text()))
    result['UI_stop_file_ABI'] = {'calls': fs_calls, 'bytes': len(payloads[0]),
        'source_id': decoded['source_id'], 'one_export_per_stop': True}
    result.update(status='PASS', image_sha256=digest(p/'mainos_PKHYB2P.bin'),
                  runtime_elf_sha256=digest(p/'platform/runtime.elf'))
    (out/'RUNTIME.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__': main()

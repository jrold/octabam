#!/usr/bin/env python3
"""Actual placed Complex renderer against original ARM/native PCM and state.

Raw native seam only: clock, gain, control producer and stock continuation
require separate gates. No reference expected values come from DSP output.
"""
import json
import os
import random
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'tools/verify'),str(ROOT/'tools/perky'),str(ROOT/'modules/perky')]
import verify_perky_three_audio as address
import verify_perky_complex_drum_exec as native
import verify_perky_cf_complex_drum_dsp as evidence
import build_four_payload as production
import complex_drum_compact as oracle
import complex_drum_production as geometry
c = address.c


def main():
    tag = address.TAG
    c.OUT = ROOT/f'out/perky/four-renderer-{tag}'
    c.OUT.mkdir(parents=True,exist_ok=True)
    c.HOST.parent.mkdir(parents=True,exist_ok=True)
    c.build_host(); c.CYCLE_METER = True
    source,_ = production.build(c.OUT/'payload')
    tables = c.words(c.OUT/'payload/tables.words')
    initial = c.words(c.OUT/'payload/state_init.words')
    digest,count = evidence.capture_digest(native.FIX)
    assert digest == evidence.CAPTURE_SET_SHA256, ('ARM capture drift',digest)
    wrapper = '''pk_controlled_voice_exec:
        move #>$200,r6
        move #>$3900,r5
        move #>$ffffff,m0
        move #>$ffffff,m1
        move #>$ffffff,m2
        move #>$ffffff,m3
        move #>$ffffff,m4
        move #>$ffffff,m5
        move #>$ffffff,m6
        jsrl pk_simple_base
        move #$0,r0
        jsrl pk_complex_production_voice
        move #>$38e8,r1
        move #>$23a,r2
        do #>4,p4raw_rng
        move x:(r1)+,a
        move a1,x:(r2)+
p4raw_rng:
        nop
        rts
'''
    binary,entry = address.at_production_addresses(wrapper+source.replace('@CONT@','$000400'))
    def data(path,state,table):
        path.write_text('X 200 '+' '.join(f'{v:06x}' for v in state)+'\n'
                        +'X 3900 '+' '.join(['000000']*118)+'\n'
                        +'X 3964 00ffff '+' '.join(['000000']*16)+'\n'
                        +'X 383a '+' '.join(f'{v:06x}' for v in initial[58:230])+'\n'
                        +'X 38e8 001234 005678 009abc 00def0\n'
                        +'Y 7a5 '+' '.join(f'{v:06x}' for v in table)+'\n')
        return []
    c.write_data = data
    waves = {a:(native.ASSET/f'wave_{a:08x}.bin').read_bytes()
             for a in (0x080222a0,0x080224a0,0x080226a0,0x080228a0)}
    pitch,e1,e2 = [(native.ASSET/n).read_bytes() for n in ('pitch.bin','envelope1.bin','envelope2.bin')]
    cases = []; captures = []
    for mode in range(1,4):
        for corner in range(3):
            p = native.FIX/f'engine-6-mode-{mode}-corner-{corner}'
            for before,audio,after in (
                ('wrapper-window-before.bin','arm-pcm.bin','wrapper-window-after.bin'),
                ('wrapper-window-after.bin','arm-pcm-continuation.bin','wrapper-window-continuation-after.bin'),
                ('wrapper-window-retrigger-before.bin','arm-pcm-retrigger.bin','wrapper-window-retrigger-after.bin')):
                raw = (p/before).read_bytes()[0x1f8:0x338]
                captures.append((list(struct.unpack('<256h',(p/audio).read_bytes())),
                                 oracle.CompactComplexDrum.from_arm((p/after).read_bytes()[0x1f8:0x338]).words))
                cases.append(raw)
    r = random.Random(0x5045524b)
    for i in range(128):
        raw = cases[i%27]
        v = oracle.CompactComplexDrum.from_arm(raw)
        v.words[0] = r.randrange(1,256); v.words[1] = int(i%17==0)
        v.words[40] = r.randrange(4096); v.words[41] = r.randrange(4096)
        for base in (2,10):
            v.set_u32(base,r.randrange(0x100001))
            v.set_u32(base+4,r.choice(tuple(waves)))
            v.set_u32(base+6,r.choice(tuple(waves)))
        cases.append(v.apply_to_arm(raw))
    cpp = c.OUT/'native.cpp'; exe = c.OUT/'native'
    cpp.write_text(native.RUNNER)
    subprocess.run(['c++','-std=c++20','-O2','-I'+str(native.NATIVE),str(cpp),
                    str(native.NATIVE/'NativeV121ComplexDrum.cpp'),'-o',str(exe)],check=True)
    inp = c.OUT/'native-input.bin'; out = c.OUT/'native-output.bin'
    inp.write_bytes(b''.join(cases))
    subprocess.run([str(exe),str(native.ASSET),str(native.ASSET),str(inp),str(out)],check=True)
    blob = out.read_bytes(); stride = 512+0x140; meters=[]
    for i,raw in enumerate(cases):
        voice = oracle.CompactComplexDrum.from_arm(raw)
        want_pcm = list(struct.unpack('<256h',blob[i*stride:i*stride+512]))
        want_state = oracle.CompactComplexDrum.from_arm(blob[i*stride+512:(i+1)*stride]).words
        if i < len(captures):
            assert (want_pcm,want_state) == captures[i], (i,'native/ARM')
        audio,states,_ = c.run(binary,entry,f'case-{i:03d}',geometry.from_original(voice.words)+[0]*22,
                              tables,[(tuple([0]*12),-1)]*16)
        assert c.flatten(audio) == want_pcm, (tag,i,'DSP/native PCM',
            [(n,a,b) for n,(a,b) in enumerate(zip(c.flatten(audio),want_pcm)) if a!=b][:8])
        for block,row in enumerate(states):
            pcm = oracle.render_block(voice,16,waves,pitch,e1,e2)
            assert pcm == audio[block], (tag,i,block,'independent per-block PCM')
            assert geometry.to_original(row) == voice.words, (tag,i,block,'42-word state',
                [(n,a,b) for n,(a,b) in enumerate(zip(geometry.to_original(row),voice.words)) if a!=b])
            assert row[58:62]==[0x1234,0x5678,0x9abc,0xdef0], (tag,i,block,'Complex changed reference RNG')
        assert voice.words == want_state, (i,'compact/native persistent state')
        assert voice.apply_to_arm(raw)==blob[i*stride+512:(i+1)*stride], (i,'complete ARM object including unchanged note/config')
        meters += list(map(int,(c.OUT/f'case-{i:03d}.meter').read_text().split()))
    report = {'core':tag,'cases':len(cases),'blocks':len(cases)*16,'original_ARM_blocks':27*16,
              'randomized_native_blocks':128*16,'worst_raw_modeled_cycles':max(meters),
              'capture_sha256':digest,'capture_files':count,
              'status':'raw renderer only; integrated clock/control/stock continuation not qualified'}
    (c.OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(f'[PASS] PERKY4/{tag} raw Complex: {report}')


if __name__ == '__main__': main()

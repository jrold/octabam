#!/usr/bin/env python3
"""Probe production WT preparation against the original V1/V2 capture corpus.

This is a host correctness test, not a ColdFire cost measurement. It reuses
pk4_init/prepare_event/render. The original constructor/update/render isolated
object probe proves owned state ends at 0x12c. V1's parameter array begins there;
it is adjacent wrapper memory, not WT state. Compare every owned state byte
after the identity header (0x1c..0x12b), including the first smoother word.
"""
import argparse
from collections import Counter
import ctypes
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'tools/perky'), str(ROOT / 'tools/verify')]
import generate_cf_final_fixtures as fixtures
import verify_perky_cf_wavetable_dsp as reference

BRIDGE = r'''
#include <string.h>
#include "cf_perky4.h"
static pk4_engine e;
static pk4_assets a;
void begin(const unsigned char **p) {
    memset(&a,0,sizeof(a));
    a.pitch=p[0]; a.chromatic=p[1]; a.envelope1=p[2]; a.envelope2=p[3];
    a.m1_wave=p[4]; a.m1_wave_address=0x080310e0u;
    a.res_interp_a=p[5]; a.res_interp_b=p[6];
    a.wt_base=p[7]; a.wt_bank=p[8];
    for(unsigned i=0;i<4;i++){
        a.waves[i].address=0x080222a0u+i*0x200u; a.waves[i].table=p[9+i];
    }
    pk4_init(&e,&a);
}
int prepare(unsigned tr,unsigned mode,unsigned raw,int trig) {
    return pk4_prepare_event(&e,tr,raw,raw,raw,raw,mode,
                            PK4_ALGO_WAVETABLE,255,trig?45:63,trig);
}
int render(unsigned tr,short *pcm) {
    for(unsigned i=0;i<16;i++) if(!pk4_render(&e,tr,pcm+16*i,16))return 0;
    return 1;
}
void state(unsigned tr,unsigned char *s){memcpy(s,e.tracks[tr].wt,PK_CF_WT_STATE_BYTES);}
'''


def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--firmware', type=Path, required=True)
    ap.add_argument('--fixtures', type=Path, default=ROOT/'out/perky/engine-fixtures')
    ap.add_argument('--work', type=Path, required=True)
    args = ap.parse_args()
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    assert digest(args.firmware) == reference.FIRMWARE_SHA256, 'firmware identity'
    capture_hash, count = reference.capture_digest(args.fixtures)
    assert capture_hash == reference.CAPTURE_SET_SHA256, 'capture identity'
    assets = fixtures.write_assets(args.firmware.resolve(), work/'fixtures')
    bridge = work/'bridge.c'
    bridge.write_text(BRIDGE)
    names = ['cf_fold','cf_karplus','cf_noise_tone','cf_perky4','cf_resonant',
             'cf_noise_hat','cf_simple_drum','cf_complex_drum','cf_slap','cf_wavetable']
    argv = ['gcc','-std=c11','-O2','-Wall','-Wextra','-Werror','-shared','-fPIC',
            '-I',str(ROOT/'modules/perky'),str(bridge)]
    argv += [str(ROOT/'modules/perky'/f'{n}.c') for n in names]
    argv += ['-o',str(work/'probe.dylib')]
    subprocess.run(argv, cwd=ROOT, check=True)
    lib = ctypes.CDLL(str(work/'probe.dylib'))
    byte = ctypes.c_ubyte
    ptr = ctypes.POINTER(byte)
    lib.begin.argtypes = [ctypes.POINTER(ptr)]
    lib.prepare.argtypes = [ctypes.c_uint]*3+[ctypes.c_int]
    lib.render.argtypes = [ctypes.c_uint,ctypes.POINTER(ctypes.c_short)]
    lib.state.argtypes = [ctypes.c_uint,ptr]
    files = ['pitch','chromatic','envelope1','envelope2','m1','interp_a','interp_b',
             'wt_base','wt_bank','w0','w1','w2','w3']
    buffers = [(byte*len(data)).from_buffer_copy(data)
               for data in [(assets/f'{n}.bin').read_bytes() for n in files]]
    pointers = (ptr*len(buffers))(*[ctypes.cast(b,ptr) for b in buffers])
    mismatches, comparisons, captures = [], 0, {}
    for original, offset in [(2,0x2e8),(5,0x31c)]:
        for logical in (0,1):
            for mode in range(3):
                for corner,raw in enumerate((0,64,127)):
                    case = args.fixtures/f'engine-{original}-mode-{mode+1}-corner-{corner}'
                    lib.begin(pointers)
                    pcm = (ctypes.c_short*256)()
                    def compare(name, pcm_name=None):
                        nonlocal comparisons
                        path = case/name
                        captures[str(path.resolve())] = digest(path)
                        want = path.read_bytes()[offset:offset+0x150]
                        state = (byte*0x150)()
                        lib.state(logical,state)
                        got = bytes(state)
                        different = [i for i in range(0x1c,0x12c) if got[i]!=want[i]]
                        if different:
                            i = different[0]
                            mismatches.append({'original_engine':original,'logical_instance':logical,
                                'mode':mode,'raw':raw,'stage':name,'kind':'state',
                                'different_bytes':len(different),'first_offset':i,
                                'got_window':got[max(0x1c,i-4):i+8].hex(),
                                'want_window':want[max(0x1c,i-4):i+8].hex()})
                        if pcm_name:
                            p = case/pcm_name
                            captures[str(p.resolve())] = digest(p)
                            if bytes(pcm)!=p.read_bytes():
                                expected = (ctypes.c_short*256).from_buffer_copy(p.read_bytes())
                                i = next(i for i in range(256) if pcm[i]!=expected[i])
                                mismatches.append({'original_engine':original,'logical_instance':logical,
                                    'mode':mode,'raw':raw,'stage':pcm_name,'kind':'PCM',
                                    'first_sample':i,'got':pcm[i],'want':expected[i]})
                        comparisons += 1
                    assert lib.prepare(logical,mode,raw,0)
                    compare('wrapper-window-pre-trigger.bin')
                    assert lib.prepare(logical,mode,raw,1)
                    compare('wrapper-window-before.bin')
                    assert lib.render(logical,pcm)
                    compare('wrapper-window-after.bin','arm-pcm.bin')
                    assert lib.render(logical,pcm)
                    compare('wrapper-window-continuation-after.bin','arm-pcm-continuation.bin')
                    assert lib.prepare(logical,mode,raw,1)
                    compare('wrapper-window-retrigger-before.bin')
                    assert lib.render(logical,pcm)
                    compare('wrapper-window-retrigger-after.bin','arm-pcm-retrigger.bin')
    result = {'status':'FAIL' if mismatches else 'PASS','scope':'three captured control corners; not exhaustive profiles',
              'compile_argv':argv,'capture_set_sha256':capture_hash,'capture_files':count,
              'fixture_hashes':captures,'comparisons':comparisons,'mismatch_count':len(mismatches),
              'bounded_mismatches':mismatches[:24],
              'mismatch_distribution':dict(Counter(f"engine-{m['original_engine']}/{m['kind']}" for m in mismatches)),
              'full_mismatch_records_sha256':hashlib.sha256(json.dumps(mismatches,sort_keys=True).encode()).hexdigest(),
              'limits':['logical instances tested separately, simultaneous independence unproved',
                        'no release, long-tail, boundary sweep or original dirty-control trajectory proof']}
    (work/'report.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('fixture_hashes','compile_argv')},indent=2))
    return 1 if mismatches else 0


if __name__ == '__main__':
    raise SystemExit(main())

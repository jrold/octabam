#!/usr/bin/env python3
"""Compare actual final-state-only adapter with the existing full converter."""
import ctypes as C,hashlib,json,random,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
W=ROOT/'out/perky/hybrid/noise-hat-handoff/clock-gate'
def main():
 W.mkdir(exist_ok=True);s=W/'clock.c';s.write_text('#include "noise_hat_handoff_clock.h"\nvoid full(pk_cf_native_clock*c,const int16_t*p,unsigned n){int32_t out[16];pk_cf_native_convert(c,p,n,out);}\nvoid shadow(pk_cf_native_clock*c,const int16_t*p,unsigned n){pk_nhb_advance_clock(c,p,n);}\n')
 cmd=['cc','-O3','-shared','-fPIC','-I'+str(ROOT/'modules/perky'),str(s),'-o',str(W/'clock.dylib')];subprocess.run(cmd,check=True)
 class Clock(C.Structure):_fields_=[('phase',C.c_uint32),('have',C.c_uint32),('carry',C.c_int32)]
 lib=C.CDLL(str(W/'clock.dylib'));rng=random.Random(0x160147);cases=0
 for phase in range(147):
  for n in range(17):
   for carry in (-32768,-1,0,32767):
    a=Clock(phase,int(phase>=13),carry);b=Clock(phase,int(phase>=13),carry);pcm=(C.c_int16*20)(*[rng.randrange(-32768,32768) for _ in range(20)])
    for f in (lib.full,lib.shadow):f.argtypes=[C.POINTER(Clock),C.POINTER(C.c_int16),C.c_uint]
    lib.full(C.byref(a),pcm,n);lib.shadow(C.byref(b),pcm,n);assert bytes(a)==bytes(b),(phase,n,carry);cases+=1
 report=dict(status='PASS_EXACT_PHASE_HAVE_CARRY',cases=cases,command=cmd,source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__),ROOT/'modules/perky/noise_hat_handoff_clock.h',ROOT/'modules/perky/cf_native_clock.h')})
 (W.parent/'CLOCK_GATE.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':main()

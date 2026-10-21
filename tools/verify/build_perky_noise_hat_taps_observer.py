#!/usr/bin/env python3
"""Current DSP source / delayed ring commit witness, using the original C body."""
from pathlib import Path
import json,subprocess
import build_perky_noise_hat_observer as base
ROOT=Path(__file__).resolve().parents[2];WORK=ROOT/'out/perky/hybrid/noise-hat-taps'
HEADER=ROOT/'tools/harness/perky_cf/noise_hat_taps_observer.h'
def build():
 def transform(s):
  s=s.replace('namespace ot\n{','#include "'+str(HEADER)+'"\nnamespace ot\n{',1)
  marker='\t\tconst auto pc = c.dsp->getPC().toWord();\n\t\tc.pcRing';assert marker in s
  return s.replace(marker,'\t\tconst auto pc = c.dsp->getPC().toWord();\n        if(i==0)noise_hat_exact::observer.dsp(*c.mem,pc);\n\t\tc.pcRing',1)
 out=WORK/'observer';base.build(out,transform,HEADER)
 oracle='#include <string.h>\n'+(ROOT/'tools/harness/perky_cf/noise_hat_resident_oracle.c').read_text()
 oracle=oracle.replace('    uint16_t old[121]={0},next[121]={0};','''    if(mode<2){
        if(init && !(initialized&3u))memcpy(s,controls,0x2dd8);
        memcpy(s+0x3e4,controls+0x3e4,20);
        memcpy(s+0x2dd4,controls+0x2dd4,2);
    }
    uint16_t old[121]={0},next[121]={0};''')
 oracle+='\nunsigned pk_nht_ring(uint16_t*out){for(unsigned i=0;i<4805;i++)out[i]=r16(resident_classic,0x3f8+2*i);return r16(resident_classic,0x2982);}\n'
 (out/'taps-oracle.c').write_text(oracle)
 subprocess.run(['cc','-std=c11','-O3','-fPIC','-shared','-I'+str(ROOT/'modules/perky'),str(out/'taps-oracle.c'),'-o',str(out/'resident-oracle.dylib')],check=True)
 r=json.loads((out/'OBSERVER_BUILD.json').read_text());r['complete_oracle_sha256']=base.sha(out/'resident-oracle.dylib');r['scope']='Current DSP source, resident state, rational clock, feedback and committed CF ring; original complete CF renderer. No target-time renderer added.'
 (out/'OBSERVER_BUILD.json').write_text(json.dumps(r,indent=2)+'\n')
if __name__=='__main__':build()

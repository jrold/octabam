#!/usr/bin/env python3
"""Read-only resident-state / PCM witness using the original CF arithmetic."""
from pathlib import Path
import subprocess,json,hashlib
import build_perky_noise_hat_observer as base
ROOT=Path(__file__).resolve().parents[2];WORK=ROOT/'out/perky/hybrid/noise-hat-resident'
HEADER=ROOT/'tools/harness/perky_cf/noise_hat_resident_observer.h'
def transform(s):
    s=s.replace('namespace ot\n{','#include "'+str(HEADER)+'"\nnamespace ot\n{',1)
    marker='\t\tconst auto pc = c.dsp->getPC().toWord();\n\t\tc.pcRing';assert marker in s
    return s.replace(marker,'\t\tconst auto pc = c.dsp->getPC().toWord();\n        if(i==0)noise_hat_exact::observer.dsp(*c.mem,pc);\n\t\tc.pcRing',1)
def build():
    base.build(WORK/'observer',transform,HEADER)
    out=WORK/'observer'
    src=(ROOT/'modules/perky/cf_noise_hat.c').read_text()
    needle='dst[i]=s16((uint16_t)nh_delay_step(s,&dly,inner));';assert src.count(needle)==2
    src=src.replace(needle,'dst[i]=(int16_t)inner;')
    (out/'inner.c').write_text(src)
    codec=(ROOT/'modules/perky/cf_noise_hat_offload.c').read_text().replace('#include "cf_noise_hat.c"','#include "'+str(out/'inner.c')+'"')
    (out/'codec.c').write_text(codec)
    oracle=(ROOT/'tools/harness/perky_cf/noise_hat_resident_oracle.c').read_text().replace('#include "cf_noise_hat_offload.c"','#include "'+str(out/'codec.c')+'"')
    (out/'oracle.c').write_text(oracle)
    subprocess.run(['cc','-std=c11','-O3','-fPIC','-shared','-I'+str(ROOT/'modules/perky'),str(out/'oracle.c'),'-o',str(out/'resident-oracle.dylib')],check=True)
    r=json.loads((out/'OBSERVER_BUILD.json').read_text());r['resident_oracle_sha256']=base.sha(out/'resident-oracle.dylib')
    r['oracle_transform']='Only remove the two classic wrapper-delay calls; pulse renderer unchanged. Original control shadow with evolving state retained independently.'
    (out/'OBSERVER_BUILD.json').write_text(json.dumps(r,indent=2)+'\n')
if __name__=='__main__':build()

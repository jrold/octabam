#!/usr/bin/env python3
"""Separate complete-renderer/clock witness; never replaces the timing observer."""
from pathlib import Path
import json,subprocess
import build_perky_noise_hat_observer as base
ROOT=Path(__file__).resolve().parents[2];WORK=ROOT/'out/perky/hybrid/noise-hat-resident-full'
def build():
    out=WORK/'observer';out.mkdir(parents=True,exist_ok=True)
    inner=ROOT/'tools/harness/perky_cf/noise_hat_resident_observer.h'
    full=ROOT/'tools/harness/perky_cf/noise_hat_resident_full_observer.h'
    source=inner.read_text().replace('namespace noise_hat_exact {','namespace nhr_inner_base {').replace('inline Observer observer;','')
    combined=out/'combined-observer.h'
    combined.write_text(full.read_text().replace('#include "noise_hat_resident_observer.h"',source))
    def transform(s):
        s=s.replace('namespace ot\n{','#include "'+str(combined)+'"\nnamespace ot\n{',1)
        marker='\t\tconst auto pc = c.dsp->getPC().toWord();\n\t\tc.pcRing';assert marker in s
        return s.replace(marker,'\t\tconst auto pc = c.dsp->getPC().toWord();\n        if(i==0)noise_hat_exact::observer.dsp(*c.mem,pc);\n\t\tc.pcRing',1)
    base.build(out,transform,combined)
    # Reuse the exact inner oracle from the primary campaign as a separate TU.
    primary=ROOT/'out/perky/hybrid/noise-hat-resident/observer'
    oracle=(ROOT/'tools/harness/perky_cf/noise_hat_resident_oracle.c').read_text()
    include='#include "cf_noise_hat_offload.c"'
    original=ROOT/'modules/perky/cf_noise_hat.c'
    prefix='#include <string.h>\n#define pk_cf_nh_render pk_nhr_full_renderer\n#include "'+str(original)+'"\nextern void pk_nha_codec(uint8_t*,unsigned,uint16_t*,int);\n#define pk_nha_unused_renderer pk_nhr_full_renderer\n'
    complete=oracle.replace(include,prefix).replace('int pk_nhr_oracle(', 'int pk_nhr_full_oracle(')
    complete=complete.replace('    uint16_t old[121]={0},next[121]={0};', '''    if(mode<2){
        if(init && !(initialized&3u))memcpy(s,controls,0x2dd8);
        memcpy(s+0x3e4,controls+0x3e4,20);
        memcpy(s+0x2dd4,controls+0x2dd4,2);
    }
    uint16_t old[121]={0},next[121]={0};''')
    (out/'full-oracle.c').write_text(complete)
    subprocess.run(['cc','-std=c11','-O3','-fPIC','-shared','-I'+str(ROOT/'modules/perky'),
        str(primary/'oracle.c'),str(out/'full-oracle.c'),'-o',str(out/'resident-oracle.dylib')],check=True)
    r=json.loads((out/'OBSERVER_BUILD.json').read_text());r.update(complete_oracle_sha256=base.sha(out/'resident-oracle.dylib'),
        inner_header_sha256=base.sha(inner),full_header_sha256=base.sha(full),full_renderer_sha256=base.sha(original),
        scope='Original complete CF renderer plus independent rational clock compared to delayed target source PCM; no target-time renderer added.')
    (out/'OBSERVER_BUILD.json').write_text(json.dumps(r,indent=2)+'\n')
    primary_work=primary.parent
    for name in ('probe','program','dsp-A.upload.bin','dsp-B.upload.bin'):
        target=WORK/name
        if not target.exists():target.symlink_to(primary_work/name,target_is_directory=(primary_work/name).is_dir())
if __name__=='__main__':build()

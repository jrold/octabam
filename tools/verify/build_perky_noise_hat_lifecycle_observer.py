#!/usr/bin/env python3
"""Build an isolated lifecycle witness; no target or shipping-image changes."""
import json,subprocess
from pathlib import Path
import build_perky_noise_hat_taps_observer as b
ROOT=Path(__file__).resolve().parents[2]
WORK=ROOT/'out/perky/hybrid/noise-hat-lifecycle'
def build():
 WORK.mkdir(parents=True,exist_ok=True)
 source=ROOT/'tools/harness/perky_cf/noise_hat_taps_observer.h'
 controls=ROOT/'tools/harness/perky_cf/noise_hat_controls_observer.h'
 extension=ROOT/'tools/harness/perky_cf/noise_hat_lifecycle_observer.h'
 combined=WORK/'lifecycle-observer.h'
 base=source.read_text().replace('namespace noise_hat_exact {','namespace nht_lifecycle_base {').replace('inline Observer observer;','')
 base=base.replace('struct Observer{','struct Observer{\n bool lifecycle_allow=true;').replace('if(!ref)return;auto sp=','if(!ref||!lifecycle_allow)return;auto sp=').replace('if(!ref||pc!=commit)return;','if(!ref||!lifecycle_allow||pc!=commit)return;')
 # Wire IDs are 16-bit; the host's bounded frame map uses the full producer
 # sequence. Bank-change waits can cross the first wrap with requests pending.
 base=base.replace('bool lifecycle_allow=true;','bool lifecycle_allow=true;\n unsigned unwrap(unsigned wire)const{unsigned n=(seq&~65535u)|(wire&65535u);return n>seq?n-65536u:n;}')
 assert base.count('auto found=frames.find(number);')==base.count('auto it=frames.find(number);')==1
 base=base.replace('auto found=frames.find(number);','number=unwrap(number);auto found=frames.find(number);').replace('auto it=frames.find(number);','number=unwrap(number);auto it=frames.find(number);')
 combined.write_text(base+'\n'+
  controls.read_text().replace('namespace noise_hat_exact {','namespace nhl_control_base {').replace('nht_control_base','nht_lifecycle_base').replace('inline Observer observer;','')+'\n#include "'+str(extension)+'"\n')
 b.WORK=WORK;b.HEADER=combined;b.build()
 out=WORK/'observer';oracle=ROOT/'tools/harness/perky_cf/noise_hat_controls_oracle.c'
 original=out/'taps-oracle.c'
 original.write_text(original.read_text()+'''\nint nhl_native_reference(const uint8_t*raw,unsigned n,unsigned mode,const pk_cf_nh_tables*t,const pk_cf_nh_rng*rng,const uint16_t*hold,int16_t*out){uint8_t s[0x2dd8];pk_cf_nh_rng r=*rng;uint16_t h[2]={hold[0],hold[1]};memcpy(s,raw,mode==2?0x160:0x2dd8);return pk_nha_unused_renderer(s,out,n,mode,t,&r,h);}\n''')
 # m68k structures align 32-bit members to two bytes. This helper only
 # describes bytes in the target; host renderer/control TUs retain their ABI.
 offsets=WORK/'offsets.c';offsets.write_text('#include <stddef.h>\n#pragma pack(push,2)\n#include "cf_perky4.h"\n#pragma pack(pop)\nconst unsigned*nhl_offsets(void){static const unsigned o[]={sizeof(pk4_track),offsetof(pk4_track,nh),offsetof(pk4_track,rng_low),offsetof(pk4_track,active_algo),offsetof(pk4_track,active_mode),offsetof(pk4_engine,nh_hold)};return o;}\n')
 subprocess.run(['cc','-O3','-std=c11','-shared','-fPIC','-I'+str(ROOT/'modules/perky'),str(out/'taps-oracle.c'),str(oracle),str(offsets),str(ROOT/'out/perky/hybrid/cf-placement/native.dylib'),'-o',str(out/'resident-oracle.dylib')],check=True)
 receipt=json.loads((out/'OBSERVER_BUILD.json').read_text())
 receipt.update(complete_oracle_sha256=b.base.sha(out/'resident-oracle.dylib'),source_sha256={str(p.relative_to(ROOT)):b.base.sha(p) for p in (Path(__file__),source,controls,extension,oracle)})
 (out/'OBSERVER_BUILD.json').write_text(json.dumps(receipt,indent=2)+'\n')
if __name__=='__main__':build()

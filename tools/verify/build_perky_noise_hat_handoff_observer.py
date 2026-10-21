#!/usr/bin/env python3
"""Build an isolated lifecycle witness; no target or shipping-image changes."""
import json,subprocess
from pathlib import Path
import build_perky_noise_hat_taps_observer as b
ROOT=Path(__file__).resolve().parents[2]
WORK=ROOT/'out/perky/hybrid/noise-hat-handoff'
def build(profile=False):
 WORK.mkdir(parents=True,exist_ok=True)
 source=ROOT/'tools/harness/perky_cf/noise_hat_taps_observer.h'
 controls=ROOT/'tools/harness/perky_cf/noise_hat_controls_observer.h'
 extension=ROOT/'tools/harness/perky_cf/noise_hat_handoff_observer.h'
 combined=WORK/'lifecycle-observer.h'
 base=source.read_text().replace('namespace noise_hat_exact {','namespace nht_lifecycle_base {').replace('inline Observer observer;','')
 base=base.replace('struct Observer{','struct Observer{\n bool lifecycle_allow=true;').replace('if(!ref)return;auto sp=','if(!ref||!lifecycle_allow)return;auto sp=').replace('if(!ref||pc!=commit)return;','if(!ref||!lifecycle_allow||pc!=commit)return;')
 # Wire IDs are 16-bit; the host's bounded frame map uses the full producer
 # sequence. Bank-change waits can cross the first wrap with requests pending.
 base=base.replace('bool lifecycle_allow=true;','bool lifecycle_allow=true;\n unsigned unwrap(unsigned wire)const{unsigned n=(seq&~65535u)|(wire&65535u);return n>seq?n-65536u:n;}')
 assert base.count('auto found=frames.find(number);')==base.count('auto it=frames.find(number);')==1
 base=base.replace('auto found=frames.find(number);','number=unwrap(number);auto found=frames.find(number);').replace('auto it=frames.find(number);','number=unwrap(number);auto it=frames.find(number);')
 combined_text=base+'\n'+controls.read_text().replace('namespace noise_hat_exact {','namespace nhb_control_base {').replace('nht_control_base','nht_lifecycle_base').replace('inline Observer observer;','')+'\n'
 if profile:
  combined_text='#include "'+str(b.base.BASE/'observer.h')+'"\n'+combined_text
  combined_text+=extension.read_text().replace('#include "cf_synthesis_observer.h"','#include "'+str(ROOT/'tools/harness/perky_cf/cf_synthesis_observer.h')+'"').replace('namespace noise_hat_exact {','namespace nhb_profile_base {').replace('inline Observer observer;','')+'\n#include "'+str(ROOT/'tools/harness/perky_cf/noise_hat_handoff_profile.h')+'"\n'
 else:combined_text+='#include "'+str(extension)+'"\n'
 combined.write_text(combined_text)
 b.WORK=WORK;b.HEADER=combined;b.build()
 out=WORK/'observer';oracle=ROOT/'tools/harness/perky_cf/noise_hat_controls_oracle.c'
 original=out/'taps-oracle.c'
 original.write_text(original.read_text()+'''\nint nhl_native_reference(const uint8_t*raw,unsigned n,unsigned mode,const pk_cf_nh_tables*t,const pk_cf_nh_rng*rng,const uint16_t*hold,int16_t*out){uint8_t s[0x2dd8];pk_cf_nh_rng r=*rng;uint16_t h[2]={hold[0],hold[1]};memcpy(s,raw,mode==2?0x160:0x2dd8);return pk_nha_unused_renderer(s,out,n,mode,t,&r,h);}\n''')
 # m68k structures align 32-bit members to two bytes. This helper only
 # describes bytes in the target; host renderer/control TUs retain their ABI.
 offsets=WORK/'offsets.c';offsets.write_text('#include <stddef.h>\n#pragma pack(push,2)\n#include "cf_perky4.h"\n#pragma pack(pop)\nconst unsigned*nhl_offsets(void){static const unsigned o[]={sizeof(pk4_track),offsetof(pk4_track,nh),offsetof(pk4_track,rng_low),offsetof(pk4_track,active_algo),offsetof(pk4_track,active_mode),offsetof(pk4_engine,nh_hold),offsetof(pk4_track,nh_ctl)};return o;}\n')
 subprocess.run(['cc','-O3','-std=c11','-shared','-fPIC','-I'+str(ROOT/'modules/perky'),str(out/'taps-oracle.c'),str(ROOT/'tools/harness/perky_cf/noise_hat_handoff_oracle.c'),str(offsets),str(ROOT/'out/perky/hybrid/cf-placement/native.dylib'),'-o',str(out/'resident-oracle.dylib')],check=True)
 # Main's idle loop now has real work. Idle-skipping may only bypass it
 # while its published queue is empty. All worker instructions execute on CF;
 # the host adds no target calls, writes, time or completion notifications.
 import shlex
 path=ROOT/'tools/emu/ot_emu/rtos.cpp';rtos=path.read_text()
 needle='if(_s.idleSkip && atSpin(pc) && !anyPending())'
 assert rtos.count(needle)==1
 rtos=rtos.replace(needle,needle[:-1]+' && (!std::getenv("NHB_PRODUCED") || m_machine.peek32(std::strtoul(std::getenv("NHB_PRODUCED"),nullptr,0)) == m_machine.peek32(std::strtoul(std::getenv("NHB_COMPLETED"),nullptr,0))))')
 (out/'rtos.cpp').write_text(rtos)
 flags=(ROOT/'out/emu/CMakeFiles/ot_machine.dir/flags.make').read_text();options=[]
 for key in ('CXX_DEFINES','CXX_INCLUDES','CXX_FLAGS'):
  options+=shlex.split(next(line.split(' = ',1)[1] for line in flags.splitlines() if line.startswith(key+' = ')))
 compile=['/usr/bin/c++',*options,'-I'+str(path.parent),'-c',str(out/'rtos.cpp'),'-o',str(out/'rtos.o')]
 subprocess.run(compile,check=True)
 receipt=json.loads((out/'OBSERVER_BUILD.json').read_text())
 link=list(receipt['commands'][-1]);link.insert(link.index('-o'),str(out/'rtos.o'));subprocess.run(link,check=True)
 receipt['commands'] += [compile,link]
 receipt['cycle_profile_enabled']=profile
 receipt['idle_skip_scope']='Skip worker idle loop only when the actual target publication queue is empty; execute all CF worker code with ordinary IRQ scheduling.'
 receipt['binary_sha256']=b.base.sha(out/'ot_emu_safety')

 receipt.update(complete_oracle_sha256=b.base.sha(out/'resident-oracle.dylib'),source_sha256={str(p.relative_to(ROOT)):b.base.sha(p) for p in (Path(__file__),source,controls,extension,ROOT/'tools/harness/perky_cf/cf_synthesis_observer.h',ROOT/'modules/perky/cf_slap.c',oracle,ROOT/'tools/harness/perky_cf/noise_hat_handoff_oracle.c')})
 if profile:receipt['source_sha256']['tools/harness/perky_cf/noise_hat_handoff_profile.h']=b.base.sha(ROOT/'tools/harness/perky_cf/noise_hat_handoff_profile.h')
 (out/'OBSERVER_BUILD.json').write_text(json.dumps(receipt,indent=2)+'\n')
if __name__=='__main__':build()

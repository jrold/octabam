#!/usr/bin/env python3
"""Rapid ownership handoffs while production MODE locks cycle all Hat limbs."""
import hashlib,inspect,json
from pathlib import Path
import qualify_perky_noise_hat_production as p
q=p.q;ROOT=p.ROOT;SOURCE=p.SOURCE;WORK=SOURCE/'switching'
def sha(x):return hashlib.sha256(x.read_bytes()).hexdigest()
def stage(*a,**kw):
 otp=q.c.workload.otp;previous=otp._bank_write
 def write(directory,bank,mutate,guard=True):
  def cycling(data):
   mutate(data)
   for pattern in range(4):
    at=otp.trac_off(pattern,5)+0x59
    for step in range(64):data[at+32*step+5]=step%3
  return previous(directory,bank,cycling,guard=guard)
 otp._bank_write=write
 try:return p.stage(*a,**kw)
 finally:otp._bank_write=previous

def main():
 WORK.mkdir(exist_ok=True)
 for name in ('probe','program','dsp-A.upload.bin','dsp-B.upload.bin','observer'):
  dest=WORK/name
  if not dest.exists():dest.symlink_to(SOURCE/name,target_is_directory=(SOURCE/name).is_dir())
 q.WORK=WORK;q.SOURCE=SOURCE;q.c.stage_fixture=stage
 env=q.environment
 def production_env(directory,syms):
  r=env(directory,syms)
  for key,name in (('NHP_EVENT','placement_production_event'),('NHP_VOICES','pk_prod_voice_generation'),('NHP_GENERATION','pk_prod_generation')):r[key]=hex(syms[name])
  r['NHP_REPORT']=str(directory/'production-resets.json');return r
 q.environment=production_env
 source=inspect.getsource(q.run)
 # Production supplies MODE from staged lock data on every source callback;
 # remove diagnostic downstream pokes, which production would overwrite.
 source=source.replace("p.poke(syms['placement_inputs']+124,mode.to_bytes(4,'big'));",'')
 source=source.replace("p.poke(syms['placement_inputs']+124,i.to_bytes(4,'big'));",'')
 source=source.replace("p.poke(syms['placement_inputs']+124,(i%3).to_bytes(4,'big'));",'')
 driver=WORK/'executed-driver.py';driver.write_text(source);exec(compile(source,str(driver),'exec'),q.__dict__)
 result=q.run('backend')
 modes={str(owner):sorted({r['mode'] for r in result['events'] if r['counts']['pk_nhb_owner']==owner}) for owner in (0,1)}
 result.update(actual_modes_by_backend=modes,production_resets=json.loads((WORK/'backend/production-resets.json').read_text()),source_sha256={str(x.relative_to(ROOT)):sha(x) for x in (Path(__file__).resolve(),Path(p.__file__).resolve(),Path(q.__file__).resolve(),driver)},limits=['Production ALGO/MODE staging; MODE locks cycle 0/1/2 in the project. Only backend-enable is poked. No production Part change in this focused switching row.','Local cycle-model and original Hat/Slap exactness scope; hardware and V4 alternative source dispatch unqualified.'])
 result['status']='PASS_PRODUCTION_SWITCHING_MODE_LOCKS' if not any(result['errors'].values()) and modes=={'0':[0,1,2],'1':[0,1,2]} and result['lifecycle']['ownership_transitions']==18 else 'FAILED_PRODUCTION_SWITCHING'
 (WORK/'SWITCHING_RESULT.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps(dict(status=result['status'],modes=modes,errors=result['errors'],ISR=result['full_ISR'],transitions=result['lifecycle']['ownership_transitions'])),flush=True)
if __name__=='__main__':main()

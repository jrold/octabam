#!/usr/bin/env python3
"""Run real panel generations through the candidate's production integration.

Failures are qualification findings. F7 is retained separately; this driver
never repairs state or forces an observer reference from post-reset state.
"""
import argparse,hashlib,inspect,json,os,shutil
from pathlib import Path
import qualify_perky_noise_hat_handoff as q
ROOT=q.ROOT;SOURCE=ROOT/'out/perky/hybrid/noise-hat-production'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def stage(project,directory,kind,algos,modes,mask):
 otp=q.c.workload.otp;previous=otp._bank_write
 def write(pdir,banknum,mutate,guard=True):
  def production(data):
   mutate(data)
   for part in range(otp.NPARTS_ALL):
    live=otp.PART_BASE+part*otp.PART_STRIDE+9
    for voice,track in enumerate((0,1,4,5)):
     at=live+48+30*track
     data[at+2]=(1,1,1,0)[voice]
     data[at+5]=(voice+part+banknum-1)%3
   for pattern in range(4):
    for track in (0,1,4,5):
     at=otp.trac_off(pattern,track)+0x59
     for step in range(64):
      data[at+32*step+2]=255;data[at+32*step+5]=255
  return previous(pdir,banknum,production,guard=guard)
 otp._bank_write=write
 try:return ORIGINAL_STAGE(project,directory,kind,algos,modes,mask)
 finally:otp._bank_write=previous
ORIGINAL_STAGE=q.c.stage_fixture

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--backend',choices=('cf','dsp'),required=True);a=p.parse_args()
 w=SOURCE/('production-'+a.backend);w.mkdir(exist_ok=True)
 for name in ('probe','program','dsp-A.upload.bin','dsp-B.upload.bin','observer'):
  dest=w/name
  if not dest.exists():dest.symlink_to(SOURCE/name,target_is_directory=(SOURCE/name).is_dir())
 q.WORK=w;q.SOURCE=SOURCE;q.c.stage_fixture=stage;q.NHP_FORCE_CF=a.backend=='cf'
 environment=q.environment
 def env(directory,syms):
  r=environment(directory,syms)
  for key,name in (('NHP_EVENT','placement_production_event'),('NHP_VOICES','pk_prod_voice_generation'),('NHP_GENERATION','pk_prod_generation')):r[key]=hex(syms[name])
  r['NHP_REPORT']=str(directory/'production-resets.json');return r
 q.environment=env
 source=inspect.getsource(q.run)
 source=source.replace("if case=='cf-calibration':poke32(syms['pk_nhr_enabled'],0)","if NHP_FORCE_CF:poke32(syms['pk_nhr_enabled'],0)")
 source=source.replace(' def backend(p,wanted,label):',' def backend(p,wanted,label):\n  if NHP_FORCE_CF:wanted=0')
 marker="  rows.append(row);"
 addition='''  live=row['bank_pointer']+0x8ed80+row['part']*0x18b2
  row['stored_controls']=[list(p.peek(live+48+30*t,6)) for t in (0,1,4,5)]
  row['production_generation']=p.long(syms['pk_prod_generation'])
  row['production_voice_generations']=[p.long(syms['pk_prod_voice_generation']+4*i) for i in range(4)]
  row['production_resets']=[p.long(syms['pk_prod_resets']+4*i) for i in range(4)]
  row['actual_algorithms']=[p.long(syms['pk_prod_algorithms']+4*i) for i in range(4)]
  row['actual_modes']=[p.long(syms['pk_prod_modes']+4*i) for i in range(4)]
'''
 assert source.count(marker)==1;source=source.replace(marker,addition+marker)
 # Archive the exact generated driver before execution, including the original
 # function body and every integration substitution above.
 driver=w/'executed-driver.py';driver.write_text(source)
 exec(compile(source,str(driver),'exec'),q.__dict__)
 result=q.run('panel')
 result.update(production_backend=a.backend,source_sha256={str(p.relative_to(ROOT)):sha(p) for p in (Path(__file__).resolve(),Path(q.__file__).resolve(),ROOT/'tools/harness/perky_cf/production_lifecycle.h',ROOT/'tools/harness/perky_cf/production_lifecycle_observer.h',driver)},production_resets=json.loads((w/'panel/production-resets.json').read_text()))
 result['production_selector_errors']=sum(e['actual_algorithms']!=[9,9,8,5] or e['actual_modes']!=[s[5] for s in e['stored_controls']] for e in result['events'])
 result['production_status']='PASS_PRODUCTION_MODEL_SCOPE' if not any(result['errors'].values()) and not result['production_selector_errors'] else 'FAILED_PRODUCTION_QUALIFICATION'
 result['limits']=['Current WT/WT/Slap/Hat selection only; V4 Noise Tone dispatch is not integrated into the resident Hat protocol.','Resident state, ordered shadow resets and feedback retirement are generation-aware; the independent witness checks old-epoch feedback before retirement.','Physical timing and power-loss persistence remain unqualified.']
 (w/'PRODUCTION_RESULT.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps(dict(status=result['production_status'],backend=a.backend,errors=result['errors'],selector_errors=result['production_selector_errors'],resets=result['production_resets'],ISR=result['full_ISR'])),flush=True)
if __name__=='__main__':main()

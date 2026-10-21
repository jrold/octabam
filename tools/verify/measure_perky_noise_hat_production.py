#!/usr/bin/env python3
"""Sustained eight-track/FX rows through the production control adapter."""
import sys
from pathlib import Path
import qualify_perky_noise_hat_production as p
import measure_perky_noise_hat_handoff as m
import qualify_perky_noise_hat_handoff as q
ROOT=p.ROOT;W=p.SOURCE
original_stage=p.stage
# Keep all ordinary four-parameter locks and the stock workload. Only ALGO and
# MODE locks are removed so each row exercises its declared persisted choice.
def stage(project,directory,kind,algos,modes,mask):
 otp=q.c.workload.otp;previous=otp._bank_write
 def write(pdir,banknum,mutate,guard=True):
  def production(data):
   mutate(data)
   for part in range(otp.NPARTS_ALL):
    live=otp.PART_BASE+part*otp.PART_STRIDE+9
    for voice,track in enumerate((0,1,4,5)):
     data[live+48+30*track+2]=(1,1,1,0)[voice]
     data[live+48+30*track+5]=modes[voice]
   for pattern in range(4):
    for track in (0,1,4,5):
     at=otp.trac_off(pattern,track)+0x59
     for step in range(64):
      data[at+32*step+2]=255;data[at+32*step+5]=255
  return previous(pdir,banknum,production,guard=guard)
 otp._bank_write=write
 try:return p.ORIGINAL_STAGE(project,directory,kind,algos,modes,mask)
 finally:otp._bank_write=previous

def main():
 m.WORK=W;q.WORK=q.SOURCE=W;q.c.stage_fixture=stage
 env=q.environment
 def production_env(directory,syms):
  r=env(directory,syms)
  for key,name in (('NHP_EVENT','placement_production_event'),('NHP_VOICES','pk_prod_voice_generation'),('NHP_GENERATION','pk_prod_generation')):r[key]=hex(syms[name])
  r['NHP_REPORT']=str(directory/'production-resets.json');return r
 q.environment=production_env
 run=m.c.run
 def candidate(*a,**kw):kw['image_name']='PKNHG3';return run(*a,**kw)
 m.c.run=candidate
 m.main()
if __name__=='__main__':main()

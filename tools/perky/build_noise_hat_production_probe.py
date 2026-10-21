#!/usr/bin/env python3
"""Integrate production selector/generation paths into the four-voice candidate.

This is an admission experiment. BUILT is not qualification. In particular,
resident DSP epochs and source-prefix retirement need their own witness.
"""
import hashlib,json,dataclasses
import perky_noise_hat_production as production
from pathlib import Path
import build_noise_hat_handoff_probe as h
ROOT=h.ROOT
WORK=ROOT/'out/perky/hybrid/noise-hat-production'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 h.WORK=WORK;h.VERSION='PKNHG3'
 h.N.build_program=production.build_program
 linked=h.Linked
 def unit(name,path,**kw):
  if name=='pknhbclock':path='modules/perky/production_resample.s'
  return linked(name,path,**kw)
 h.Linked=unit
 original_module=h.CF.base.build_hybrid_module
 def module(*a,**kw):
  r=original_module(*a,**kw)
  return dataclasses.replace(r,linked=r.linked+(h.Linked('pkprod','modules/perky/production_copy.s',dram=True),h.Linked('pkprzero','modules/perky/production_sparse.s',dram=True),h.Linked('pkprpub','modules/perky/production_publish.s',dram=True),))
 h.CF.base.build_hybrid_module=module
 extend=h.P.extend_upload
 def upload(img,tag,y,x=None,extra=None,extra_y=None,p_records=None):
  if tag=='A' and x is not None and extra and any(at==0x3a23 for at,_ in extra):
   values=[(i<<16)|v for i,v in enumerate(x[:180]) if v]
   assert len(values)==47
   values += [0]*4
   extra=list(extra)+[(production.RESET_TABLE+i,values[i:i+17]) for i in range(0,51,17)]
  return extend(img,tag,y,x,extra,extra_y,p_records)
 h.P.extend_upload=upload
 original=h.CF.build
 def build(work,**kw):
  previous=kw['control_transform']
  def control(text):
   text=previous(text)
   marker='    if(end<start||end>16u)return 0;'
   assert text.count(marker)==1
   text=text.replace(marker,marker+'\n    pk_hybrid_observe_generation();\n    placement_production_observe(pk_hybrid_generation);')
   marker='        p[2]=(uint8_t)(fp[DECAY_SLOT]>>8);'
   assert text.count(marker)==1
   text=text.replace(marker,'        p[0]=pk4_voice_engine(voice,(uint8_t)(fp[ALGO_SLOT]>>8));\n        p[1]=(uint8_t)(fp[MODE_SLOT_FINAL]>>8);if(p[1]>2)p[1]=2;\n'+marker)
   marker='static uint32_t placement_trigger[4];'
   text=text.replace(marker,marker+'\nextern void placement_production_observe(unsigned);')
   start=text.index('    uint32_t algo_max = track == 5u ? 1u :')
   end=text.index('    put32(desc + 0xd2',start)
   text=text[:start]+'    unsigned voice=track==0?0:track==1?1:track==4?2:3;\n    uint32_t algo_max=pk4_voice_len(voice);\n'+text[end:]
   old='placement_pack(voice,start);\n        pk_hybrid_commit_longs(pk_hybrid_fixed_slot(track,ping),placement_packets[voice],40u);'
   assert text.count(old)==1
   text=text.replace(old,'pk_prod_pack(pk_hybrid_fixed_slot(track,ping),placement_output[voice],start);')
   old='    for(unsigned i=0;i<words;i++)cursor[i]=0;\n    U32(0x80001c80u)=(uint32_t)(uintptr_t)(cursor+words);'
   assert text.count(old)==1
   text=text.replace(old,'    U32(0x80001c80u)=(uint32_t)(uintptr_t)pk_prod_clear(cursor,words);')
   text='#include <stdint.h>\nextern void pk_prod_pack(volatile uint32_t*,const int32_t*,unsigned);\nextern volatile uint32_t*pk_prod_clear(volatile uint32_t*,unsigned);\n'+text
   return text
  kw['control_transform']=control
  src=kw['placement_source'];text=src.read_text().replace('noise_hat_handoff_engine.c','production_handoff_engine.c')
  kw['build_number']=29
  text='void placement_production_init(void);\n'+text
  marker='placement_status=1;pk_nhb_reset();'
  assert text.count(marker)==1
  text=text.replace(marker,marker+'placement_production_init();')
  marker='int placement_prepare(unsigned tr,const uint32_t *input,int trig)'
  assert text.count(marker)==1
  text=text.replace(marker,'#include "'+str(ROOT/'tools/harness/perky_cf/production_lifecycle.h')+'"\n'+marker)
  marker='    if(algo>10||mode>2||tr>3)return 0;'
  text=text.replace(marker,marker+'\n    placement_production_event(tr,algo);\n    pk_prod_algorithms[tr]=algo;pk_prod_modes[tr]=mode;')
  src.write_text(text)
  return original(work,**kw)
 h.CF.build=build
 try:h.build()
 finally:
  h.CF.build=original;h.CF.base.build_hybrid_module=original_module;h.P.extend_upload=extend;h.Linked=linked
 p=WORK/'BUILD.json';r=json.loads(p.read_text());r['status']='BUILT_PRODUCTION_PATHS_NOT_QUALIFIED'
 r['source_sha256'].update({str(p.relative_to(ROOT)):sha(p) for p in (Path(__file__).resolve(),ROOT/'tools/harness/perky_cf/production_lifecycle.h',ROOT/'tools/harness/perky_cf/production_handoff_engine.c',ROOT/'tools/harness/perky_cf/production_handoff_shadow.h',ROOT/'tools/perky/perky_noise_hat_production.py',ROOT/'modules/perky/production_copy.s',ROOT/'modules/perky/production_sparse.s',ROOT/'modules/perky/production_publish.s',ROOT/'modules/perky/production_resample.s',ROOT/'tools/harness/perky_cf/production_sparse.h')})
 r['integration_scope']='Production selectors and Bank/Part generation; scheduled resident DSP epoch reset; generation-tagged feedback retirement; ordered shadow reset; lazy CF assembly restores with pristine first adoption.'
 m=r['memory'];m['A_private_X'].append(['packed original initializer',production.RESET_TABLE,production.RESET_TABLE+51]);m['A_private_X_words']+=51
 assert m['A_private_X_words']<=m['A_private_X_capacity']
 (WORK/'MEMORY.json').write_text(json.dumps(m,indent=2)+'\n')
 p.write_text(json.dumps(r,indent=2)+'\n')
if __name__=='__main__':main()

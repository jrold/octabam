#!/usr/bin/env python3
"""Build all twelve logical PERKONS choices from the qualified G3 base."""
import dataclasses,hashlib,json
from pathlib import Path
import build_noise_hat_production_probe as G
import perky_full_map as F
import generate_full_map_transport as T
import full_map_project as project
ROOT=G.ROOT;WORK=ROOT/'out/perky/hybrid/full-map'
VERSION='PKFM2'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 WORK.mkdir(parents=True,exist_ok=True)
 transport=T.generate(WORK)
 abi=project.generate(WORK)
 old_module=G.h.CF.base.build_hybrid_module
 def module(*a,**kw):
  r=old_module(*a,**kw)
  return dataclasses.replace(r,linked=tuple(dataclasses.replace(u,source=str((abi/'machine.s').relative_to(ROOT))) if u.label=='pkmachine' else u for u in r.linked))
 original=G.h.CF.build;program=G.production.build_program;hbuild=G.h.build
 def build(work,**kw):
  src=kw['placement_source'];text=src.read_text()
  text=T.once(text,str(ROOT/'tools/harness/perky_cf/production_handoff_engine.c'),str(transport))
  # Leave the generic production family map untouched for existing images.
  marker='#define pk4_encode_stock_segment placement_unused_stock_encoder'
  text=T.once(text,marker,'''#define pk4_voice_len fm_base_voice_len
#define pk4_voice_engine fm_base_voice_engine
'''+marker)
  marker='#undef pk4_encode_stock_segment'
  text=T.once(text,marker,marker+'''
#undef pk4_voice_len
#undef pk4_voice_engine
unsigned fm_voice_len(unsigned v){return v<4?3:1;}
uint8_t fm_voice_engine(unsigned v,unsigned local){if(v==3&&local>=2)return 10;return fm_base_voice_engine(v,local);}
''')
  marker='static pk4_engine placement_pristine;'
  # The production reset source is included, so extend it in this candidate.
  lifecycle=(ROOT/'tools/harness/perky_cf/production_lifecycle.h').read_text()
  lifecycle=T.once(lifecycle,marker,marker+'\nstatic uint8_t fm_ah_pristine[PK_CF_AH_STATE_BYTES];')
  lifecycle=T.once(lifecycle,' for(unsigned i=0;i<4;i++){',' for(unsigned i=0;i<PK_CF_AH_STATE_BYTES;i++)fm_ah_pristine[i]=placement_ah_state[i];\n for(unsigned i=0;i<4;i++){')
  lifecycle=T.once(lifecycle,' if(algo==PK4_ALGO_WAVETABLE){',' if(algo==10){prod_copy(placement_ah_state,fm_ah_pristine,sizeof(fm_ah_pristine));for(unsigned i=0;i<sizeof(placement_ah_control);i++)((uint8_t*)&placement_ah_control)[i]=0;placement_ah_hold=0;}\n else if(algo==PK4_ALGO_WAVETABLE){')
  lp=WORK/'full-map-lifecycle.h';lp.write_text(lifecycle)
  text=T.once(text,str(ROOT/'tools/harness/perky_cf/production_lifecycle.h'),str(lp));src.write_text(text)
  previous=kw['control_transform']
  def controls(s):
   s=previous(s)
   s=T.once(s,'#include "control_four_candidate.c"','#include "'+str(abi/'control_four_candidate.c')+'"')
   return s.replace('pk4_voice_engine(voice,','fm_voice_engine(voice,').replace('pk4_voice_len(voice)','fm_voice_len(voice)').replace('#include <stdint.h>','#include <stdint.h>\nextern unsigned fm_voice_len(unsigned);\nextern uint8_t fm_voice_engine(unsigned,unsigned);',1)
  kw['control_transform']=controls;kw['build_number']=30
  return original(work,**kw)
 def fullbuild():
  G.h.VERSION=VERSION;return hbuild()
 G.WORK=WORK;G.h.CF.build=build;G.production.build_program=F.build_program;G.h.build=fullbuild;G.h.CF.base.build_hybrid_module=module
 try:G.main()
 finally:G.h.CF.build=original;G.production.build_program=program;G.h.build=hbuild;G.h.CF.base.build_hybrid_module=old_module
 p=WORK/'BUILD.json';r=json.loads(p.read_text());r['status']='BUILT_FULL_MAP_NOT_QUALIFIED'
 paths=[Path(__file__).resolve(),ROOT/'tools/perky/perky_full_map.py',ROOT/'tools/perky/generate_full_map_transport.py',ROOT/'tools/perky/full_map_project.py',ROOT/'tools/harness/perky_cf/full_map_rng.h',transport,WORK/'full-map-shadow.h',WORK/'full-map-lifecycle.h',*sorted(abi.iterdir())]
 r['project_signature_version']=project.SIGNATURE_VERSION;r['version']=VERSION
 r['source_sha256'].update({str(p.relative_to(ROOT)):sha(p) for p in paths});p.write_text(json.dumps(r,indent=2)+'\n')
if __name__=='__main__':main()

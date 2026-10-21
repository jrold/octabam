#!/usr/bin/env python3
"""Fourteen stock effects and original B source: exact live-upload bytes."""
import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/p) for p in ('tools/verify','tools/perky','tools/build','tools')]
import measure_perky_full_map as f
import ab_records as A
import perky_image as P
from remix import registry,stock
W=f.W
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def words(blob,span):
 rows,_=A.records(blob,*span)
 return {(space,at+i):A.rd(blob,off+3*i) for space,at,n,off in rows for i in range(n)}
def main():
 pristine=(ROOT/'out/raw/section_3_MAIN_OS.bin').read_bytes();cases={}
 for tag in ('A','B'):
  old=words(pristine,P.PAY[tag]['payload']);path=W/f'dsp-{tag}.upload.bin';blob=path.read_bytes();new=words(blob,(A.BASE,len(blob)))
  allowed=set(range(0x40,0x4a if tag=='A' else 0x4b))
  if tag=='A':allowed|={0x39c,0x39d,0x53e,0x53f}
  assert {at for space,at in new if space==0 and at<0x2000}=={at for space,at in old if space==0 and at<0x2000},'private program tail appended'
  for (space,at),value in old.items():
   if space==0 and at in allowed:continue
   assert new[space,at]==value,(tag,'stock word changed',space,hex(at))
  effects={}
  for name,(start,count) in stock.p_spans(tag).items():
   effect_id=registry.modules()[name].menu.fx2_id
   assert all(new[0,at]==old[0,at] for at in range(start,start+count)),(tag,name,'code')
   assert all(new[1,base+effect_id]==old[1,base+effect_id] for base in (0x215,0x235)),(tag,name,'dispatch')
   effects[name]=dict(start=start,words=count,FX1_and_FX2_dispatch_exact=True)
  # DELAY is outside stock.p_spans' thirteen ordinary effect spans. The
  # complete private-program identity above covers its stock implementation.
  effect_id=registry.modules()['DELAY'].menu.fx2_id
  assert all(new[1,base+effect_id]==old[1,base+effect_id] for base in (0x215,0x235))
  effects['DELAY']=dict(code_identity='covered by complete stock program comparison',FX1_and_FX2_dispatch_exact=True)
  assert len(effects)==14
  if tag=='B':assert all(new[0,at]==old[0,at] for at in (0x1a2,0x1a3))
  shared={at for space,at in new if space==0 and at>=0x30000}
  inherited={at for space,at in old if space==0 and at>=0x30000}
  added=shared-inherited;assert len(added)==2220,(tag,len(added))
  cases[tag]=dict(effects=effects,ordinary_P_tail_added=False,stock_existing_X_Y_exact=True,added_shared_words=len(added),inherited_shared_words=len(inherited),upload_sha256=sha(path))
 result=dict(status='PASS_ALL_FOURTEEN_FX_CODE_BOTH_DISPATCHES_STOCK_DATA_AND_B_SOURCE',cases=cases,inputs={str(p):sha(p) for p in (ROOT/'out/raw/section_3_MAIN_OS.bin',W/'dsp-A.upload.bin',W/'dsp-B.upload.bin')},source_sha256={str(Path(__file__).relative_to(ROOT)):sha(Path(__file__))},limits=['Upload-byte and memory proof. Actual FX execution, buffer guards, timing and physical qualification remain separate.'])
 (W/'STOCK_FX_GATE.json').write_text(json.dumps(result,indent=2)+'\n');print(result['status'])
if __name__=='__main__':main()

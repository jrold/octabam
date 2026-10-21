#!/usr/bin/env python3
"""Complete map with all fourteen stock FX and no private-P donor/tail use."""
import json
import build_perky_full_map as b
import perky_full_map_all_fx as fx
ROOT=b.ROOT;W=ROOT/'out/perky/hybrid/full-map-all-fx'
def main():
 W.mkdir(parents=True,exist_ok=True);b.WORK=W;b.VERSION='PKFM3';fx.ACTIVE_WORK=W;fx.READY=False
 program=b.F.build_program;extend=b.G.h.P.extend_upload
 b.F.build_program=fx.build_program
 def upload(*args,**kw):return fx.restored_upload(extend,*args,**kw)
 b.G.h.P.extend_upload=upload
 try:b.main()
 finally:b.F.build_program=program;b.G.h.P.extend_upload=extend
 p=W/'BUILD.json';r=json.loads(p.read_text());m=r['memory'];m['private_P_used']={'A':0,'B':0};m['retained_FX']='all fourteen original stock effect code/dispatch words preserved';m['notes']=['A service and shared math/clear helpers occupy shared executable tails only.','No Plate/Compressor donor code or candidate private-P upper tails used.','B retains its original stock source path; four logical voices use CF except resident Hat segments on A.','Full fourteen-effect execution, scheduling and physical qualification are separate gates.']
 r['source_sha256'].update({str(p.relative_to(ROOT)):b.sha(p) for p in (ROOT/'tools/perky/perky_full_map_all_fx.py',ROOT/'tools/perky/build_perky_full_map_all_fx.py')});r['status']='BUILT_ALL_FOURTEEN_FX_NOT_QUALIFIED'
 (W/'MEMORY.json').write_text(json.dumps(m,indent=2)+'\n');p.write_text(json.dumps(r,indent=2)+'\n');print(r['status'],m['shared_words'],m['shared_capacity'])
if __name__=='__main__':main()

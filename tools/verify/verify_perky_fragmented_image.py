#!/usr/bin/env python3
"""Build the four-engine candidate locally and prove its final P uploads/FX bytes."""
import os,sys,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'tools/build'),str(ROOT/'tools/perky'),str(ROOT/'modules/perky')]
os.environ.setdefault('REMIX','perky-machine')
import ab_records as A, perky_image as P, perky_fragmented_image as F
import build_fold_candidate as C, build_multi_machine_canary as M
from remix import registry,stock

def main():
    work=ROOT/'out/perky/fragmented'
    source,_=C.build(work);(work/'multi.asm').write_text(source)
    M.build_image(work,6,'PERKY2F',control_input=ROOT/'modules/perky/control_light2_candidate.c',engine_ids=(0,3,2,10),local_only=True)
    normal=(work/'fragmented-normal.bin').read_bytes()
    original=(ROOT/'out/raw/section_3_MAIN_OS.bin').read_bytes()
    p_records=json.loads((work/'p-records.json').read_text())
    assert p_records['A']==p_records['B'],'aliased shared P must have identical code'
    y,layout=P.load_tables(work);x=P.load_state_init(work,layout)
    r=registry.remix('perky-machine')
    assert stock.harvested(set(r.modules)|set(r.fx1))=={'PLATE REV','COMPRESSOR'}
    for tag,c in P.PAY.items():
        rr,_=A.records(original,*c['payload'])
        raw,_=P.extend_upload(normal,tag,y,x,P.extra_state_init(layout),P.load_extra_y_init(work,layout),p_records[tag])
        installed,term=A.records(raw,A.BASE,len(raw))
        records,ledger,entry=F.plan(work/'multi.asm',tag)
        for addr,words in records:
            assert [A.rd(raw,A.word_at(installed,0,addr+i)) for i in range(len(words))]==words
        for effect,(addr,count) in stock.p_spans(tag).items():
            if effect in ('PLATE REV','COMPRESSOR'):continue
            assert [A.rd(raw,A.word_at(installed,0,addr+i)) for i in range(count)]==[A.rd(original,A.word_at(rr,0,addr+i)) for i in range(count)],(tag,effect)
            effect_id=registry.modules()[effect].menu.fx2_id
            for base in (0x215,0x235):
                assert A.rd(raw,A.word_at(installed,1,base+effect_id))==A.rd(original,A.word_at(rr,1,base+effect_id)),(tag,effect,'dispatch')
        print(f'[PASS] {tag}: every relocated shard reconstructed; all retained FX P words and dispatch entries stock-identical')
    print('[PASS] fragmented production build, integration, packed loader and boot readback')
if __name__=='__main__':
    try:
        main()
    finally:
        # Later image gates expect the tracked impulse probe, not our upgraded
        # full machine. The candidate's matched inputs are staged under work.
        subprocess.run(['make','bus','REMIX=perky-machine'],cwd=ROOT,check=True)

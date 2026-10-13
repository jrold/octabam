#!/usr/bin/env python3
"""Check the built three-engine image's physical aliases, every shard and stock FX."""
import argparse, json, os, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'tools/build'),str(ROOT/'tools/perky'),str(ROOT/'modules/perky')]
os.environ.setdefault('REMIX','perky-machine')
import ab_records as A, perky_image as P, perky_fragmented_image as F
from remix import registry, stock


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--build',type=Path,default=ROOT/'out/perky/three')
    work=ap.parse_args().build
    original=(ROOT/'out/raw/section_3_MAIN_OS.bin').read_bytes()
    normal=(work/'fragmented-normal.bin').read_bytes()
    p_records=json.loads((work/'p-records.json').read_text())
    assert p_records['A']==p_records['B'],'physical shared P upload differs between cores'
    spans=sorted((start,start+len(words)) for start,words in p_records['A'])
    assert all(a[1]<=b[0] for a,b in zip(spans,spans[1:])),'physical shared P overlap'
    y,layout=P.load_tables(work);x=P.load_state_init(work,layout)
    assert layout['source_clock']['native_rate']==48000 and layout['source_clock']['output_rate']==44100
    for tag,c in P.PAY.items():
        rr,_=A.records(original,*c['payload'])
        raw,_=P.extend_upload(normal,tag,y,x,P.extra_state_init(layout),P.load_extra_y_init(work,layout),p_records[tag])
        installed,_=A.records(raw,A.BASE,len(raw))
        records,ledger,entry=F.plan(work/'multi.asm',tag)
        for addr,words in records:
            assert [A.rd(raw,A.word_at(installed,0,addr+i)) for i in range(len(words))]==words,(tag,hex(addr),'actual program shard')
        for effect,(addr,count) in stock.p_spans(tag).items():
            if effect in ('PLATE REV','COMPRESSOR'):continue
            assert [A.rd(raw,A.word_at(installed,0,addr+i)) for i in range(count)]==[A.rd(original,A.word_at(rr,0,addr+i)) for i in range(count)],(tag,effect,'stock P bytes')
            effect_id=registry.modules()[effect].menu.fx2_id
            for base in (0x215,0x235):
                assert A.rd(raw,A.word_at(installed,1,base+effect_id))==A.rd(original,A.word_at(rr,1,base+effect_id)),(tag,effect,'stock dispatch')
        print(f'[PASS] {tag}: every final P shard; all retained stock FX program bytes and dispatch entries identical')
    memory=json.loads((work/'memory.json').read_text())
    assert memory['physical_shared_p']['free']>=0 and all(c['p_free']>=0 for c in memory['cores'].values())
    assert all('noise_tone_voice' not in s['name'] for c in memory['cores'].values() for s in c['p_shards'])
    print('[PASS] physical shared P union is nonoverlapping and identical in both uploads; native clock initialized; Noise/Tone renderer absent')


if __name__=='__main__':main()

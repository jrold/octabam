#!/usr/bin/env python3
"""Run retained-FX gates using the actual diagnostic image's DSP placement.

The original gate's assembler-derived expectations remain its default. This
adapter reads private words from the generated normal image and shared upload
words from its union records, so alternative physical placements are observed.
"""
import json, os, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'tools/verify'),str(ROOT/'tools/build')]
import verify_perky_four_fx as fx
import ab_records as A

def main():
    build=Path(os.environ['PERKY_FRAGMENT_BUILD'])
    image=(build/'fragmented-normal.bin').read_bytes()
    ledger=json.loads((build/'memory.json').read_text())
    shared=json.loads((build/'p-records.json').read_text())
    def actual_plan(_asm,tag):
        va,length={'A':A.PAYLOAD_A,'B':A.PAYLOAD_B}[tag]
        stock,_=A.records(image,va,length)
        rows=ledger['cores'][tag]['p_shards']; result=[]
        for row in rows:
            address,count=row['start'],row['length']
            if address<0x30000:
                words=[A.rd(image,A.word_at(stock,0,address+i)) for i in range(count)]
            else:
                words=next(words[address-start:address-start+count] for start,words in shared[tag] if start<=address and address+count<=start+len(words))
            result.append((address,words))
        return result,rows,next(row['start'] for row in rows if row['name']=='synth_seam_glue.asm')
    fx.F.plan=actual_plan
    fx.main()

if __name__=='__main__':main()

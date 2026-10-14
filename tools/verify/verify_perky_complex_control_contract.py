#!/usr/bin/env python3
"""Constrain the entire Complex producer record with original ARM note-45 state.

The AU/native full-decay gate independently proves the desired renderer path.
This gate checks 512 authentic trigger/update cases, never a self-derived law.
"""
import json, struct, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'tools/verify'),str(ROOT/'modules/perky')]
import verify_perky_light2_src_page as g
import simple_drum_control as law
OUT=ROOT/'out/perky/au-regression/control-contract'

def main():
 OUT.mkdir(parents=True,exist_ok=True)
 source=ROOT/'out/perky/au/control-sweep.bin'
 assert source.stat().st_size==512*0x6000,'regenerate authenticated note-45 ARM control sweep'
 cases=[]
 for ctrl in range(4):
  for knob in range(128):
   k=[64]*4;k[ctrl]=knob;i=len(cases)
   cases.append(g.Case(f'arm{i}',track=(0,4)[i%2],part=i%4,ping=0,trig=1,algo=3,mode=0,knobs=tuple(k),dirty=125,hidden=10))
 g.CONTROL=ROOT/'modules/perky/control_four_candidate.c';g.WORK=OUT;g.ALGO_COUNT=4;g.ALGO_ENGINE=(0,3,2,5)
 data=g.execute(cases);capture=source.read_bytes()
 for i,case in enumerate(cases):
  s=capture[i*0x6000+0x1f8:i*0x6000+0x338];assert s[7]==45
  at=lambda off:struct.unpack_from('<H',s,off)[0]
  want=[at(0xba),at(0x96),at(0x11a),at(0x120)]
  rows=g.record_words(data['rows'],i,case)
  assert rows[4:8]==[g.pair(v) for v in want],(i,'actual ARM controls',rows[4:8],want)
  assert (rows[8]>>16)==(0x80 if s[0x7b] else 0),(i,'actual ARM sustain')
  frequency=(rows[8]&255)<<3
  assert frequency*0x57619f1//(1<<22)==struct.unpack_from('<I',s,0xcc)[0],(i,'actual ARM modulation increment')
 (OUT/'report.json').write_text(json.dumps({'cases':512,'note':45,'all_control_axes':128,'status':'exact executed ColdFire-C records versus independent ARM controls'},indent=2)+'\n')
 print('[PASS] Complex producer: 512 independent ARM control/trigger cases, note 45; raw pitch, both envelopes, PAR2, sustain and modulation increment exact')
if __name__=='__main__':main()

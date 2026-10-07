#!/usr/bin/env python3
"""Execute the evidence-derived Fold Drum 2 trigger plan on DSP56300.

The firmware-derived contract/plan remain local under ``out/``.  Assembly is
emitted through ``tools/perky/fold2_trigger_plan_source.py`` — the same tracked
translation layer used by the hidden production candidate — so qualification
cannot silently test a different interpretation of the ARM trigger law.
"""
from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'out/perky/fold2-trigger-exec';CONTRACT=ROOT/'out/perky/fold2-trigger-contract.json';PLAN=ROOT/'out/perky/fold2-trigger-plan.json'
sys.path[:0]=[str(ROOT/'tools/verify'),str(ROOT/'tools/perky')]
import verify_perky_controlled_voice_exec as c
import fold2_trigger_plan_source as trigger
WORDS=trigger.WORDS;VISIBLE=64;VOICE_X=0x200;SNAPSHOT_X=0x300;PHASES=('first_trigger','active_retrigger')

def fail(m):raise AssertionError('Fold2 trigger DSP gate: '+m)

def cases(contract,ops,control):
 assert contract.get('schema')==trigger.CONTRACT_SCHEMA and contract.get('compact_words')==WORDS and contract.get('engine_zero_based')==3
 out=[];dests={o['dst'] for o in ops}
 for phase in PHASES:
  rows=contract[phase]['cases'];assert len(rows)==9
  for n,row in enumerate(rows):
   pre=row['pre'];post=row['post'];assert len(pre)==len(post)==WORDS
   want=list(pre)
   for d in dests:want[d]=post[d]
   got=trigger.apply_plan(pre,ops)
   if got!=want:fail(f'{phase}[{n}]: plan/ARM mismatch')
   if any(want[d]!=pre[d] for d in control):fail(f'{phase}[{n}]: trigger overlaps control state')
   out.append((f"{phase}-{n}-{row.get('case','case')}",pre,want))
 return out

def main():
 if not PLAN.exists() or not CONTRACT.exists():
  print('Fold2 trigger DSP gate: SKIP (run tools/perky/qualify_fold2_trigger.py first)',file=sys.stderr);raise SystemExit(2)
 plan,ops=trigger.load_plan(PLAN);contract=json.loads(CONTRACT.read_text());rows=cases(contract,ops,set(plan['control_owned_words']))
 c.OUT=OUT;OUT.mkdir(parents=True,exist_ok=True);c.HOST.parent.mkdir(parents=True,exist_ok=True);c.build_host()
 source='pk_controlled_voice_exec:\n'+f'        move #>${VOICE_X:06x},r6\n'+trigger.emit_routine(ops,label='pk_fold2_trigger',snapshot_reg='r5',snapshot_address=SNAPSHOT_X)+'pk_fold2_entry:\n        jsr pk_fold2_trigger\n        rts\n'
 # The assembler entry is the first label; make that wrapper actually call the shared routine.
 source=source.replace('pk_controlled_voice_exec:\n        move #>$000200,r6\npk_fold2_trigger:', 'pk_controlled_voice_exec:\n        move #>$000200,r6\n        jsr pk_fold2_trigger\n        rts\npk_fold2_trigger:',1)
 binary,entry=c.assemble(c.source_builder.force_long_local_jsr(c.source_builder.relativize_local_conditionals(source)))
 def write_data(path,state_words,_tables):
  if len(state_words)!=VISIBLE:fail('bad visible state size')
  path.write_text('X 100 '+' '.join(['000000']*13)+'\n'+f'X {VOICE_X:x} '+' '.join(f'{v&0xffff:06x}' for v in state_words)+'\n'+f'X {SNAPSHOT_X:x} '+' '.join(['000000']*100)+'\n');return []
 c.write_data=write_data;record=tuple([0]*12)
 for tag,pre,want in rows:
  tag=tag.replace("/", "-")
  initial=list(pre)+[0]*(VISIBLE-WORDS);_a,states,_r=c.run(binary,entry,tag,initial,[],[(record,-1)]);got=states[0][:WORDS]
  if got!=want:fail(f'{tag}: executable state mismatch')
  if states[0][WORDS:VISIBLE]!=[0]*(VISIBLE-WORDS):fail(f'{tag}: write escaped Fold2 allocation')
 print(f'Fold Drum 2 trigger DSP executable gate: PASS ({len(rows)} ARM observations; {len(ops)} trigger operations; shared emitter)')
if __name__=='__main__':main()

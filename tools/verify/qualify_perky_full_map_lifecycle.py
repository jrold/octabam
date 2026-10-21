#!/usr/bin/env python3
"""Full-map lifecycle, actual Part/Bank selectors and diagnostic handoffs."""
import json,os,shutil
from pathlib import Path
import measure_perky_full_map as f
import stems_panel as panel
ROOT=f.ROOT;W=f.W
COUNTS=('pk_nhr_failures','pk_nhb_overflows','pk_nhb_clock_errors','pk_nhb_produced','pk_nhb_completed','pk_nhb_owner','pk_nhb_switches','pk_nhb_deferred','pk_nhb_queue_peak','pk_prod_generation')
def stage(project,d):
 otp=f.c.workload.otp;previous=otp._bank_write
 def write(pdir,banknum,mutate,guard=True):
  def parts(data):
   mutate(data)
   for part in range(otp.NPARTS_ALL):
    live=otp.PART_BASE+part*otp.PART_STRIDE+9
    for voice,track in enumerate((0,1,4,5)):
     at=live+48+30*track
     data[at+2]=(1,1,(0 if banknum==2 else (1,0,2,1)[part%4]),(2 if banknum==2 else (0,2,1,0)[part%4]))[voice]
     data[at+5]=(voice+part+banknum-1)%3
   for pattern in range(4):
    at=otp.trac_off(pattern,5)+0x59
    for step in range(64):data[at+32*step+5]=step%3
  return previous(pdir,banknum,parts,guard=guard)
 otp._bank_write=write
 try:return f.stage(project,d,'static',[9,9,8,5],[1,2,0,0],15)
 finally:otp._bank_write=previous
def main():
 d=W/'lifecycle';d.mkdir(exist_ok=True)
 for name in ('port.log','stack.json','private.json','full-map-exact.json','RESULT.json'):
  p=d/name
  if p.exists():p.unlink()
 syms=f.c.private.symbols(W/'probe/platform/runtime.elf');project=Path(json.loads((ROOT/'modules/perky/hybrid/BASELINE.json').read_text())['project']['root'])
 card=stage(project,d);image=W/'probe'/f'mainos_{f.image_name()}.bin';peeks,expected=f.program_checks()
 env=f.c.private.environment(W,'full-map-lifecycle');env.update(f.environment(d,syms));env.update(HYBRID_SAFETY_REPORT=str(d/'stack.json'),HYBRID_PRIVATE_REPORT=str(d/'private.json'))
 initial={k:os.environ.get(k) for k in env};os.environ.update(env);panel.PORT_BIN=W/'observer/ot_emu_safety';proc=None;events=[]
 inputs={str(p):f.c.sha(p) for p in (image,W/'probe/platform/runtime.elf',panel.PORT_BIN,W/'observer/full-map-oracle.dylib',Path(__file__),card)}
 def snap(m,label):
  row=dict(label=label,part=m.peek(0x100b14cf,1)[0],bank=m.peek(0x800065bd,1)[0],latched_bank=m.peek(0x46c7ff40,1)[0],transport=m.long(0x800065b8),counts={n:m.long(syms[n]) for n in COUNTS},algorithms=[m.long(syms['pk_prod_algorithms']+4*i) for i in range(4)],modes=[m.long(syms['pk_prod_modes']+4*i) for i in range(4)],resets=[m.long(syms['pk_prod_resets']+4*i) for i in range(4)],status=m.proc.command('status','status'))
  events.append(row);(d/'EVENTS.json').write_text(json.dumps(events,indent=2)+'\n');print(json.dumps(row),flush=True)
  assert not any(row['counts'][k] for k in ('pk_nhr_failures','pk_nhb_overflows','pk_nhb_clock_errors')),row
  return row
 def backend(m,wanted):
  m.poke(syms['pk_nhr_enabled'],wanted.to_bytes(4,'big'))
  for _ in range(30):
   m.run(20)
   if m.long(syms['pk_nhb_owner'])==wanted:break
  row=snap(m,'backend-'+str(wanted));assert row['counts']['pk_nhb_owner']==wanted,row
 def part(m,wanted,key):
  m.press('part',hold=20,settle=40);m.press(key,hold=20,settle=30);m.press('yes',hold=20,settle=160)
  row=snap(m,'part-'+str(wanted));assert row['part']==wanted,row
  expected_algos=[9,9,(8,4,2,8)[wanted],(5,10,3,5)[wanted]]
  assert row['algorithms']==expected_algos,(row,expected_algos)
 try:
  with panel.MenuPort(image,card,'OCTABAM','RIG',True,log_path=d/'port.log',extra=('--load-ms','90000','--sequencer','--frames','1','--bank','0','--dsp-dirty','123','--pit-clock-hz','132000000','--cf-cycles-clock','1.0','--cf-cycles-clock-before-transport','--block-dump',str(d/'blocks.bin'),'--dsp-peek',';'.join(peeks))) as m:
   proc=m.proc;(d/'startup.log').write_text('\n'.join(proc.log)+'\n');assert 'cycle clock: startup/pre-roll/transport use' in '\n'.join(proc.log)
   m.settle();snap(m,'loaded')
   for i in range(3):
    backend(m,int(i!=1));m.press('stop',hold=20,settle=80);off=snap(m,'stop-'+str(i));m.press('play',hold=20,settle=160);on=snap(m,'start-'+str(i));assert off['transport']!=on['transport']
   backend(m,1)
   for wanted,key in ((2,'down'),(0,'up')):part(m,wanted,key)
   # Repeat generation changes while CF owns Hat; switch back only after
   # the return to Hat, exercising pending retirement and lazy first use.
   backend(m,0)
   part(m,2,'down')
   m.press('t6',hold=20,settle=30);m.press('pg_playback',hold=20,settle=30)
   # First Hat use after a generation began on NT, while CF owns the voice.
   # Real encoder publication must restore/export every inactive Hat limb.
   m.rt.uart64.rx.extend([0x32,192]);m.run(160)
   row=snap(m,'fresh-CF-Hat-within-generation');assert row['algorithms'][3]==5,row
   backend(m,1)
   for mode in (0,1,2):
    for _ in range(40):
     if m.long(syms['pk_prod_modes']+12)==mode:break
     m.run(25)
    row=snap(m,'sequencer-mode-'+str(mode));assert row['modes'][3]==mode,row
    backend(m,0);m.run(40);backend(m,1)
   part(m,0,'up')
   backend(m,1)
   for _ in range(20):
    if m.long(0x40218856)==0:break
    m.run(500)
   assert m.long(0x40218856)==0
   for bank in (1,0):
    m.chord('bank',f'trig{bank+1}',settle=60);m.press('trig1',hold=20,settle=80)
    for _ in range(25):
     if m.peek(0x800065bd,1)[0]==bank and m.peek(0x46c7ff40,1)[0]==bank:break
     m.run(500)
    m.run(160);row=snap(m,'bank-'+str(bank));assert row['bank']==row['latched_bank']==bank
   for i in range(6):backend(m,0);m.run(1);backend(m,1)
   m.run(500);snap(m,'end')
   loaded=f.live_program(m,expected)
  assert proc.proc.wait(timeout=60)==0
  stdout='\n'.join(proc.log);(d/'stdout.log').write_text(stdout+'\n')
  exact=json.loads((d/'full-map-exact.json').read_text());stack=json.loads((d/'stack.json').read_text());private=json.loads((d/'private.json').read_text());classes=f.c.blockdump.classes(f.c.blockdump.read(d/'blocks.bin'))
  audio={str(t):sum(abs(v)>64 for v in f.c.recloop.readback_audio(classes,t)) for t in range(1,9)}
  assert loaded
  passed=f.exact(exact) and stack['ISR_duration_misses']==stack['DMA_read_write_overlaps']==stack['DMA_active_restarts']==stack['guard_writes_after_dispatch']==private['ownership_register_frame_or_mask_violations']==private['fence_writes']==0 and all(v>64 for v in audio.values()) and all(not s['outside_extent'] for s in stack['stacks'])
  result=dict(status='PASS_FULL_MAP_LIFECYCLE_MODEL_SCOPE' if passed else 'FAILED_FULL_MAP_LIFECYCLE',inputs=inputs,events=events,independent_source=exact,safety=stack,private=private,loaded_program_words_checked=loaded,post_FX_significant=audio,full_ISR=dict(frames=stack['frames'],returns=stack['frame_returns'],max_cycles=stack['full_ISR_max_cycles'],max_us=stack['full_ISR_max_cycles']/264,deadline_misses=stack['ISR_duration_misses']),final_card_sha256=f.c.sha(card),limits=['Actual STOP/START, Part and Bank panel changes with production generation resets; backend enable is a diagnostic callback-boundary flag.','Independent reference streams; no target state repair. Physical cache/bus/DMA timing remains hardware work.'])
  assert all(f.c.sha(Path(p))==h for p,h in inputs.items() if Path(p)!=card)
  (d/'RESULT.json').write_text(json.dumps(result,indent=2)+'\n');print(result['status'],result['full_ISR'],exact,flush=True);assert passed,result
 finally:
  if proc and proc.alive():
   try:proc.proc.wait(timeout=60)
   except Exception:proc.kill()
  for k,v in initial.items():
   if v is None:os.environ.pop(k,None)
   else:os.environ[k]=v
  for name in ('card.img','blocks.bin'):
   p=d/name
   if p.exists():p.unlink()
  for name in ('tree','project'):
   if (d/name).exists():shutil.rmtree(d/name)
if __name__=='__main__':main()

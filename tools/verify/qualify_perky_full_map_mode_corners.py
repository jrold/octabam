#!/usr/bin/env python3
"""Cartesian modes on four demanding combinations, with real sequencer locks."""
import argparse,json,os,shutil
from pathlib import Path
import measure_perky_full_map as f
import stems_panel as panel
ROOT=f.ROOT;W=f.W
def choices():
 # Full Cartesian modes for combinations whose simultaneous CPU cost or
 # split DSP transport matters most. The general 81-layout gate is separate.
 import itertools
 result=[]
 for algos in ((9,9,8,5),(0,1,4,5),(9,9,8,10),(9,9,4,3)):
  local=[f.FAMILY[i].index(a) for i,a in enumerate(algos)]
  for modes in itertools.product(range(3),repeat=4):result.append((local,list(modes)))
 return result
def key(local,modes):return ':'.join(str(f.FAMILY[i][local[i]]) for i in range(4))+'/'+':'.join(map(str,modes))
def stage(project,directory):
 otp=f.c.workload.otp;previous=otp._bank_write;rows=choices()
 def write(pdir,banknum,mutate,guard=True):
  def locked(data):
   mutate(data)
   for pattern in (4,5):
    for track in range(8):
     src=otp.trac_off(0,track)-9;dst=otp.trac_off(pattern,track)-9
     data[dst:dst+otp.TRAC_FSTRIDE]=data[src:src+otp.TRAC_FSTRIDE]
   for pattern in range(6):
    tail=otp.PTRN0+pattern*otp.PTRN_FSTRIDE+otp.PTRN_FSTRIDE-11;data[tail+2]=64;data[tail+3]=2
    for voice,track in enumerate((0,1,4,5)):
     at=otp.trac_off(pattern,track);data[at:at+8]=b'\xff'*8;data[at+0x50:at+0x52]=bytes((64,2))
     for step in range(64):
      local,modes=rows[min(pattern*64+step,len(rows)-1)]
      data[at+0x59+32*step:at+0x59+32*step+6]=bytes((64,108,local[voice],64,64,modes[voice]))
  return previous(pdir,banknum,locked,guard=guard)
 otp._bank_write=write
 try:return f.stage(project,directory,'static',[9,9,8,5],[1,2,0,0],15)
 finally:otp._bank_write=previous
def main():
 p=argparse.ArgumentParser();p.add_argument('--patterns',type=int,choices=(6,),default=6);a=p.parse_args()
 d=W/'mode-matrix';d.mkdir(exist_ok=True);syms=f.c.private.symbols(W/'probe/platform/runtime.elf');project=Path(json.loads((ROOT/'modules/perky/hybrid/BASELINE.json').read_text())['project']['root'])
 card=stage(project,d);image=W/'probe'/f'mainos_{f.image_name()}.bin';env=f.c.private.environment(W,'mode-matrix');env.update(f.environment(d,syms));env.update(HYBRID_SAFETY_REPORT=str(d/'stack.json'),HYBRID_PRIVATE_REPORT=str(d/'private.json'))
 initial={k:os.environ.get(k) for k in env};os.environ.update(env);panel.PORT_BIN=W/'observer/ot_emu_safety';port=None;events=[]
 inputs={str(p):f.c.sha(p) for p in (image,W/'probe/platform/runtime.elf',panel.PORT_BIN,W/'observer/full-map-oracle.dylib',Path(__file__).resolve(),card)}
 try:
  with panel.MenuPort(image,card,'OCTABAM','RIG',True,log_path=d/'port.log',extra=('--load-ms','90000','--sequencer','--frames','1','--bank','0','--dsp-dirty','123','--pit-clock-hz','132000000','--cf-cycles-clock','1.0','--cf-cycles-clock-before-transport')) as m:
   port=m.proc;(d/'startup.log').write_text('\n'.join(port.log)+'\n');assert 'cycle clock: startup/pre-roll/transport use' in '\n'.join(port.log);m.settle()
   for pattern in range(a.patterns):
    if pattern:
     m.chord('pattern',f'trig{pattern+1}',settle=100)
     for _ in range(20):
      if m.peek(0x800065be,1)[0]==pattern:break
      m.run(500)
    assert m.peek(0x800065be,1)[0]==pattern,('pattern selection failed',pattern)
    for _ in range(17):m.run(500)
    event=dict(pattern=pattern,actual_pattern=m.peek(0x800065be,1)[0],counts={n:m.long(syms[n]) for n in ('pk_nhr_failures','pk_nhb_overflows','pk_nhb_clock_errors','pk_nhb_produced','pk_nhb_completed')},status=m.proc.command('status','status'))
    events.append(event);(d/'EVENTS.json').write_text(json.dumps(events,indent=2)+'\n');print(json.dumps(event),flush=True)
    assert not any(event['counts'][k] for k in ('pk_nhr_failures','pk_nhb_overflows','pk_nhb_clock_errors')),event
  assert port.proc.wait(timeout=60)==0
  exact=json.loads((d/'full-map-exact.json').read_text());stack=json.loads((d/'stack.json').read_text());private=json.loads((d/'private.json').read_text())
  expected={key(*row) for row in choices()[:64*a.patterns]};missing=sorted(expected-set(exact['combinations']))
  passed=f.exact(exact) and not missing and stack['ISR_duration_misses']==0 and private['ownership_register_frame_or_mask_violations']==private['fence_writes']==0 and events[-1]['counts']['pk_nhb_completed']>0
  result=dict(status=('PASS_FULL_MAP_MODE_CORNERS_MODEL_SCOPE' if a.patterns==6 else 'PASS_PARTIAL_MATRIX_DIAGNOSTIC') if passed else 'FAILED_FULL_MAP_MATRIX',inputs=inputs,observer_environment=f.environment(d,syms),patterns=a.patterns,expected_tuples=len(expected),missing_tuples=missing,events=events,independent_source=exact,safety=stack,private=private,full_ISR=dict(frames=stack['frames'],returns=stack['frame_returns'],max_cycles=stack['full_ISR_max_cycles'],max_us=stack['full_ISR_max_cycles']/264,deadline_misses=stack['ISR_duration_misses']),limits=['Actual sequencer ALGO/MODE and four parameter locks; actual panel pattern changes. All sources have independent original-reference streams.','Local instruction/cycle model; no physical timing qualification.'])
  assert all(f.c.sha(Path(p))==h for p,h in inputs.items());(W/'MODE_MATRIX.json').write_text(json.dumps(result,indent=2)+'\n');print(result['status'],result['full_ISR'],'missing',len(missing),flush=True);assert passed,result
 finally:
  if port and port.alive():
   try:port.proc.wait(timeout=60)
   except Exception:port.kill()
  for k,v in initial.items():
   if v is None:os.environ.pop(k,None)
   else:os.environ[k]=v
  if card.exists():card.unlink()
  for name in ('tree','project'):
   if (d/name).exists():shutil.rmtree(d/name)
if __name__=='__main__':main()

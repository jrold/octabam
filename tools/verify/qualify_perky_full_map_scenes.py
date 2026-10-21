#!/usr/bin/env python3
"""Actual stock scene/fader delivery with independent full-map audio."""
import json,os,shutil
from pathlib import Path
import measure_perky_full_map as f
import stems_panel as panel
import emu_card
ROOT=f.ROOT;W=f.W
def main():
 d=W/'scenes';d.mkdir(exist_ok=True);project=Path(json.loads((ROOT/'modules/perky/hybrid/BASELINE.json').read_text())['project']['root'])
 card=f.stage(project,d,'static',[9,9,8,5],[1,2,0,1],15);tree=d/'scene-tree';tree.mkdir(exist_ok=True)
 a=(24,56,32,48);b=(104,112,96,120);otp=f.c.workload.otp
 for name,blob in emu_card.extract_image(card.read_bytes()).items():
  p=tree/name;p.parent.mkdir(parents=True,exist_ok=True)
  if p.stem.startswith('bank') and p.suffix in ('.work','.strd'):
   data=bytearray(blob)
   for part in range(otp.NPARTS_ALL):
    base=otp.PART_BASE+part*otp.PART_STRIDE+9;data[base+0x10:base+0x12]=bytes((0,1))
    for track in (0,1,4,5):
     data[base+0x11a+24*track+3:base+0x11a+24*track+6]=bytes(3)
     for scene,values in enumerate((a,b)):
      at=base+0x662+(scene*8+track)*32;data[at:at+32]=bytes([255])*32
      for index,value in zip((0,1,3,4),values):data[at+index]=value
   for pattern in range(4):
    for track in (0,1,4,5):
     at=otp.trac_off(pattern,track)+0x59;data[at:at+64*32]=bytes([255])*(64*32)
   data[-2:]=(sum(data[0x10:-2])&65535).to_bytes(2,'big');blob=bytes(data)
  p.write_bytes(blob)
 card.write_bytes(emu_card.build_image(tree));shutil.rmtree(tree)
 syms=f.c.private.symbols(W/'probe/platform/runtime.elf');image=W/'probe'/f'mainos_{f.image_name()}.bin';peeks,expected=f.program_checks()
 env=f.c.private.environment(W,'full-map-scenes');env.update(f.environment(d,syms));env.update(HYBRID_SAFETY_REPORT=str(d/'stack.json'),HYBRID_PRIVATE_REPORT=str(d/'private.json'))
 old={k:os.environ.get(k) for k in env};os.environ.update(env);panel.PORT_BIN=W/'observer/ot_emu_safety';proc=None;events=[]
 inputs={str(p):f.c.sha(p) for p in (image,W/'probe/platform/runtime.elf',panel.PORT_BIN,W/'observer/full-map-oracle.dylib',Path(__file__),card)}
 try:
  with panel.MenuPort(image,card,'OCTABAM','RIG',True,log_path=d/'port.log',extra=('--load-ms','90000','--sequencer','--frames','1','--bank','0','--dsp-dirty','123','--pit-clock-hz','132000000','--cf-cycles-clock','1.0','--cf-cycles-clock-before-transport','--block-dump',str(d/'blocks.bin'),'--dsp-peek',';'.join(peeks))) as m:
   proc=m.proc;m.settle()
   for key,flag in (('scene_a',0x80000006),('scene_b',0x80000007)):
    if m.peek(flag,1)[0]:m.chord('func',key,settle=60)
    assert m.peek(flag,1)==b'\x00'
   for pos in (0,32,64,96,127,96,64,32,0):
    m.rt.uart64.rx.extend([0x40,2*(127-pos)+1]);m.run(100)
    xf=m.long(0x460d16c8);assert xf==127-pos
    raw=[[m.long(syms['placement_inputs']+40*v+4*i) for i in (3,2,4,5)] for v in range(4)]
    if pos in (0,127):assert raw==[list(a if pos==0 else b)]*4,(pos,raw)
    events.append(dict(position=pos,stock_fader=xf,controls=raw))
   m.run(500)
   loaded=f.live_program(m,expected)
  assert proc.proc.wait(timeout=60)==0
  stdout='\n'.join(proc.log);(d/'stdout.log').write_text(stdout+'\n')
  exact=json.loads((d/'full-map-exact.json').read_text());stack=json.loads((d/'stack.json').read_text());private=json.loads((d/'private.json').read_text());classes=f.c.blockdump.classes(f.c.blockdump.read(d/'blocks.bin'))
  audio={str(t):sum(abs(v)>64 for v in f.c.recloop.readback_audio(classes,t)) for t in range(1,9)}
  passed=f.exact(exact) and stack['ISR_duration_misses']==stack['DMA_read_write_overlaps']==stack['guard_writes_after_dispatch']==private['ownership_register_frame_or_mask_violations']==private['fence_writes']==0 and all(v>64 for v in audio.values())
  result=dict(status='PASS_FULL_MAP_SCENE_FADER_MODEL_SCOPE' if passed else 'FAILED_FULL_MAP_SCENE_FADER',inputs=inputs,events=events,independent_source=exact,loaded_program_words_checked=loaded,safety=stack,private=private,post_FX_significant=audio,full_ISR=dict(frames=stack['frames'],max_cycles=stack['full_ISR_max_cycles'],max_us=stack['full_ISR_max_cycles']/264,deadline_misses=stack['ISR_duration_misses']),limits=['Actual enabled scene endpoints and stock UART fader input. LFOs and p-locks disabled here to isolate scene delivery; matrix covers those paths.','Local model; physical UI responsiveness remains unqualified.'])
  assert all(f.c.sha(Path(p))==h for p,h in inputs.items() if Path(p)!=card)
  (W/'SCENES.json').write_text(json.dumps(result,indent=2)+'\n');print(result['status'],result['full_ISR'],flush=True);assert passed,result
 finally:
  if proc and proc.alive():
   try:proc.proc.wait(timeout=60)
   except Exception:proc.kill()
  for k,v in old.items():
   if v is None:os.environ.pop(k,None)
   else:os.environ[k]=v
  for name in ('card.img','blocks.bin'):
   p=d/name
   if p.exists():p.unlink()
  for name in ('tree','project','scene-tree'):
   if (d/name).exists():shutil.rmtree(d/name)
if __name__=='__main__':main()

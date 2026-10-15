import sys,json,shutil
from pathlib import Path
root=Path.cwd();sys.path.insert(0,str(root/'tools/verify'));import stems_panel as s
w=root/'out/perky/hybrid/ipl3/bank-panel';w.mkdir(exist_ok=True);shutil.copyfile(root/'out/perky/hybrid/ipl3/dense/card.img',w/'card.img')
s.PORT_BIN=root/'out/perky/hybrid/safety-final/final-observer/ot_emu_safety'
import os
os.environ['HYBRID_SAFETY_REPORT']=str(w/'stack.json')
with s.MenuPort(root/'out/perky/hybrid/ipl3/trial-mainos.bin',w/'card.img','OCTABAM','RIG',True,log_path=w/'port.log',extra=('--load-ms','90000','--pit-clock-hz','132000000','--cf-cycles-clock','1.0','--block-dump',str(w/'blocks.bin'))) as p:
 def state(label):
  d={'label':label,'A_unavailable':p.long(0x4017d516),'B_unavailable':p.long(0x40218856),'ui':list(p.peek(0x100b14cc,4)),'working':list(p.peek(0x80000002,3)),'playing':list(p.peek(0x800065bd,6))};print(d,flush=True);return d
 state('loaded')
 for i in range(15):
  if p.long(0x40218856)==0:break
  p.run(1000)
 ready=state('background_wait_done');assert ready['B_unavailable']==0,ready
 p.settle();p.press('play',hold=20,settle=100);state('play')
 for bank in [1,0]:
  p.chord('bank',f'trig{bank+1}',settle=60);p.png(w/f'bank-{bank}-selected.png');state('bankselected')
  p.press('trig1',hold=20,settle=80)
  for i in range(10):
   if p.peek(0x800065bd,1)[0]==bank:break
   p.run(400)
  row=state('switch_done');p.png(w/f'bank-{bank}-done.png');assert row['playing'][0]==bank,row
 p.press('stop');state('stop')

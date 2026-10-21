#!/usr/bin/env python3
"""Attribute IRQ and background work, requiring a matching observer control."""
import argparse,json,os,shlex,subprocess
from pathlib import Path
import calibrate_perky_hybrid_budget as c
ROOT=c.ROOT
def build(work):
 out=work/'observer';out.mkdir(parents=True,exist_ok=True)
 base=c.DEFAULT_WORK/'observer';receipt=json.loads((base/'BUILD.json').read_text())
 assert c.sha(base/'ot_emu_safety')==receipt['binary_sha256']
 text=(base/'machine.cpp').read_text();header=ROOT/'tools/harness/perky_cf/full_map_cost_observer.h'
 needle='#include "'+str(base/'observer.h')+'"';assert text.count(needle)==1
 text=text.replace(needle,needle+'\n#include "'+str(header)+'"')
 for expression in ('pc()','pcFast()','p'):
  marker=f'noise_hat_exact::observer.step(*this, {expression});';assert text.count(marker)==1
  text=text.replace(marker,marker+f'\n full_map_cost::observer.step(*this, {expression});')
 path=out/'machine.cpp';path.write_text(text)
 command=list(receipt['commands'][0]);command[command.index('-c')+1]=str(path);command[command.index('-o')+1]=str(out/'machine.o')
 subprocess.run(command,check=True)
 link=list(receipt['commands'][-1]);link[link.index(str(base/'machine.o'))]=str(out/'machine.o');link[link.index('-o')+1]=str(out/'ot_emu_safety')
 subprocess.run(link,check=True)
 c.save(out/'BUILD.json',dict(binary_sha256=c.sha(out/'ot_emu_safety'),commands=[command,link],parent_sha256=c.sha(base/'ot_emu_safety'),header_sha256=c.sha(header)))
def main():
 p=argparse.ArgumentParser();p.add_argument('--work',type=Path,default=ROOT/'out/perky/hybrid/full-map-cost');p.add_argument('--frames',type=int,default=4096);p.add_argument('--case',default='F6-WTWT-Slap-5-M1-shared12');p.add_argument('--candidate',type=Path);p.add_argument('--control-row',type=Path);a=p.parse_args();w=a.work.resolve();w.mkdir(parents=True,exist_ok=True)
 control=(a.control_row or c.DEFAULT_WORK/a.case/'ROW.json').resolve()
 assert control.is_file(),'A matching unprofiled ROW.json is required'
 old=json.loads(control.read_text())
 if a.candidate:
  c.CURRENT=a.candidate.resolve();version=old['configuration']['version'];image=c.CURRENT/'probe'/f'mainos_{version}.bin'
  assert c.sha(image)==old['image_sha256'] and old['case']==a.case
  c.PINNED[version]=old['image_sha256'];c.cases=lambda:{a.case:old['configuration']}
 build(w)
 elf=c.CURRENT/'probe/platform/runtime.elf'
 lines=subprocess.check_output(['m68k-elf-nm','-n','-S',str(elf)],text=True)
 symbols=w/'symbols.txt';symbols.write_text(''.join(f'{int(v[0],16):x} {int(v[0],16)+int(v[1],16):x} {v[3]}\n' for line in lines.splitlines() if len(v:=line.split())==4 and v[2] in ('t','T')))
 os.environ.update(CF_COST_SYMBOLS=str(symbols),CF_COST_REPORT=str(w/'cost.json'))
 row=c.run(w,a.case,a.frames)
 assert old['frames']==row['frames'] and old['image_sha256']==row['image_sha256']
 for k in ('full_ISR','comparison_dumps','whole_CPU','stock_audio'):assert old[k]==row[k],('profile observer perturbed execution',k)
 prof=json.loads((w/'cost.json').read_text());n=prof['completed_ISR']-512
 top={k:sorted(((name,cycles/n/264) for name,cycles in prof[k].items()),key=lambda p:p[1],reverse=True)[:24] for k in ('ISR','background')}
 c.save(w/'PROFILE.json',dict(status='PASS_UNCHANGED_AUDIO_AND_CYCLES',control_receipt=str(control),control_sha256=c.sha(control),row=row,profile=prof,per_frame_us=top,source_sha256={str(p):c.sha(p) for p in (Path(__file__),ROOT/'tools/harness/perky_cf/full_map_cost_observer.h')}))
 print(json.dumps(top,indent=2))
if __name__=='__main__':main()

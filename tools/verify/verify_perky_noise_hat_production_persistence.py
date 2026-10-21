#!/usr/bin/env python3
"""Actual encoder ALGO/MODE edits, stock SAVE PROJECT and cold card reload."""
import hashlib,json,os,re,shutil,subprocess
from pathlib import Path
import qualify_perky_noise_hat_production as p
ROOT=p.ROOT;W=p.SOURCE/'persistence'
def sha(x):return hashlib.sha256(x.read_bytes()).hexdigest()
def main():
 p.q.WORK=p.q.SOURCE=p.SOURCE
 W.mkdir(exist_ok=True);syms=p.q.c.private.symbols(p.SOURCE/'probe/platform/runtime.elf')
 project=Path(json.loads((ROOT/'modules/perky/hybrid/BASELINE.json').read_text())['project']['root'])
 card=p.stage(project,W,'static',[9,9,8,5],[1,2,0,0],15)
 script=W/'save.txt';s=(ROOT/'tools/harness/perky_hybrid_safety/save.txt').read_text()
 s=s.replace('500 key','300 enc 2 -64\n380 enc 5 64\n500 key',1);script.write_text(s)
 import emu_card
 otp=p.q.c.workload.otp;initial=emu_card.extract_image(card.read_bytes())
 at=otp.PART_BASE+9+48+30
 key='OCTABAM/RIG/bank01.work';before=initial[key][at:at+6]
 expected=bytes((before[0]+7,before[1],before[2]-1,before[3],before[4],min(before[5]+1,2)))
 image=p.SOURCE/'probe/mainos_PKNHG3.bin';elf=p.SOURCE/'probe/platform/runtime.elf';emu=p.SOURCE/'observer/ot_emu_safety';saved=W/'saved-card.img'
 inputs={str(x):sha(x) for x in (image,elf,emu,script,card,Path(__file__).resolve(),ROOT/'tools/harness/perky_hybrid_safety/save.txt')}
 result=dict(status='RUNNING',inputs=inputs,expected_T2_controls=list(expected),hardware_validated=False,commands=[])
 base=[str(emu),'--image',str(image),'--set','OCTABAM','--project','RIG','--load-ms','90000','--dsp','--dsp-dirty','123','--mkii','--pit-clock-hz','132000000','--cf-cycles-clock','1.0','--cf-cycles-clock-before-transport']
 def run(cmd,label):
  directory=W/label;directory.mkdir(exist_ok=True)
  env=p.q.environment(directory,syms)
  for k,n in (('NHP_EVENT','placement_production_event'),('NHP_VOICES','pk_prod_voice_generation'),('NHP_GENERATION','pk_prod_generation')):env[k]=hex(syms[n])
  env['NHP_REPORT']=str(directory/'production-resets.json')
  with (directory/'port.log').open('w') as log:r=subprocess.run(cmd,cwd=ROOT,env={**os.environ,**env},stdout=log,stderr=subprocess.STDOUT,timeout=600)
  result['commands'].append(dict(command=cmd,exit_status=r.returncode,log_sha256=sha(directory/'port.log')))
  assert r.returncode==0,(label,r.returncode)
  return (directory/'port.log').read_text()
 try:
  log=run([*base,'--card',str(card),'--live-script',str(script),'--card-out',str(saved)],'save')
  assert 'on quit' in log and 'FAULT:' not in log and 'ILLEGAL' not in log
  files=emu_card.extract_image(saved.read_bytes());selected={}
  for suffix in ('work','strd'):
   name='OCTABAM/RIG/bank01.'+suffix;selected[suffix]=list(files[name][at:at+6]);assert files[name][at:at+6]==expected,('saved controls',suffix,selected[suffix],list(expected))
  result['saved_controls']=selected;result['saved_card_sha256']=sha(saved)
  # A new process loads the SAVED card; no selector or state pokes are used.
  controls=W/'reload-controls.bin';dump=W/'reload-blocks.bin'
  log=run([*base,'--card',str(saved),'--sequencer','--internal-clock','--bank','0','--frames','512','--block-dump',str(dump),'--mem-dump',f'{0x400e21e0+0x8ed80+48+30:#x},6={controls}'],'reload')
  assert re.search(r'frames run\s*:\s*512 .*REACHED',log) and 'FAULT:' not in log and 'ILLEGAL' not in log
  assert controls.read_bytes()==expected,('cold reload controls',list(controls.read_bytes()),list(expected))
  classes=p.q.c.blockdump.classes(p.q.c.blockdump.read(dump));audio={}
  for tr in range(1,9):
   values=p.q.c.recloop.readback_audio(classes,tr);audio[str(tr)]=sum(abs(x)>64 for x in values)
  result['cold_reload_post_FX_significant']=audio;assert all(x>64 for x in audio.values())
  result['status']='PASS_ENCODER_SAVE_COLD_RELOAD_CONTROLS_AND_ACTIVE_AUDIO'
  result['limits']=['A valid family-local ALGO and MODE on T2 edited by real encoders. All six saved controls compared in work/strd and after a fresh process.','No power-loss atomicity claim. This is selection persistence, not a pass for generation reset PCM or V4 Noise Tone rendering.']
 except Exception as e:result['status']='FAILED_PERSISTENCE_QUALIFICATION';result['failure']=str(e)
 result['source_sha256']={str(x.relative_to(ROOT)):sha(x) for x in (Path(__file__).resolve(),Path(p.__file__).resolve())}
 (W/'RESULT.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
 # Preserve the exact saved fixture as evidence. Drop the disposable input and
 # block recording, retaining the hashes and decoded assertions above.
 for x in (card,W/'reload-blocks.bin'):
  if x.exists():x.unlink()
 for name in ('project','tree'):
  if (W/name).exists():shutil.rmtree(W/name)
if __name__=='__main__':main()

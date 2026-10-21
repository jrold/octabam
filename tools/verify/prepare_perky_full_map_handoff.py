#!/usr/bin/env python3
"""Fresh isolated demo SET, then play it through the actual final candidate."""
import json,shutil
from pathlib import Path
import measure_perky_full_map as f
import qualify_perky_full_map_matrix as matrix
import emu_card
ROOT=f.ROOT;W=f.W
def main():
 d=W/'handoff';d.mkdir(exist_ok=True);tree=d/'CARD_CONTENTS';assert not tree.exists(),'handoff tree already exists'
 project=Path(json.loads((ROOT/'modules/perky/hybrid/BASELINE.json').read_text())['project']['root']);card=f.stage(project,d,'static',[9,9,8,5],[1,2,0,1],15);otp=f.c.workload.otp
 rows=matrix.choices()
 for name,blob in emu_card.extract_image(card.read_bytes()).items():
  parts=Path(name).parts;name=str(Path('PERKYF6',*parts[1:])) if parts[0]=='OCTABAM' else name
  p=tree/name;p.parent.mkdir(parents=True,exist_ok=True)
  if p.suffix in ('.work','.strd'):
   blob=blob.replace(b'OCTABAM',b'PERKYF6')
   if p.stem.startswith('bank'):
    data=bytearray(blob);bank=int(p.stem[4:])
    # Part 3 changes V4 to NT, giving one simple generation-reset check.
    live=otp.PART_BASE+2*otp.PART_STRIDE+9;data[live+48+30*5+2]=1
    for pattern in range(4):
     tail=otp.PTRN0+pattern*otp.PTRN_FSTRIDE+otp.PTRN_FSTRIDE-11;data[tail+2]=64;data[tail+3]=2
     for track in range(8):
      at=otp.trac_off(pattern,track);data[at+0x50:at+0x52]=bytes((64,2))
     if bank==2:
      for voice,track in enumerate((0,1,4,5)):
       at=otp.trac_off(pattern,track);data[at:at+8]=b'\xff'*8
       for step in range(64):
        local,modes=rows[min(pattern*64+step,len(rows)-1)]
        data[at+0x59+32*step:at+0x59+32*step+6]=bytes((64,108,local[voice],64,64,modes[voice]))
     elif bank==1 and pattern:
      local,modes=(([1,1,1,1],[1,2,0,0]),([1,1,1,2],[1,2,0,1]),([0,0,0,0],[2,1,0,1]))[pattern-1]
      for voice,track in enumerate((0,1,4,5)):
       at=otp.trac_off(pattern,track)+0x59
       for step in range(64):data[at+32*step+2]=local[voice];data[at+32*step+5]=modes[voice]
    data[-2:]=(sum(data[0x10:-2])&65535).to_bytes(2,'big');blob=bytes(data)
  p.write_bytes(blob)
 card.write_bytes(emu_card.build_image(tree))
 manifest={str(p.relative_to(tree)):f.c.sha(p) for p in sorted(tree.rglob('*')) if p.is_file()};(d/'PROJECT_FILES.json').write_text(json.dumps(manifest,indent=2)+'\n')
 name='HANDOFF-DEMO';f.c.SCENARIOS[name]=([9,9,8,5],[1,2,0,1],15)
 original_stage=f.c.stage_fixture;original_run=f.c.subprocess.run
 f.c.stage_fixture=lambda *a,**kw:card
 def run(command,*a,**kw):
  if '--set' in command:command[command.index('--set')+1]='PERKYF6'
  return original_run(command,*a,**kw)
 f.c.subprocess.run=run;directory=W/'integrated-results/HANDOFF-DEMO-static';syms=f.c.private.symbols(W/'probe/platform/runtime.elf');peeks,expected=f.program_checks()
 try:
  row=f.c.run(W,name,'static',512,image_name=f.image_name(),extra_env=f.environment(directory,syms),extra_dumps=[(n,4) for n in ('pk_nhr_failures','pk_nhb_overflows','pk_nhb_clock_errors','pk_nhb_produced','pk_nhb_completed','fma_ready','fma_status')]+[(f'pk_placement_{n}',size) for n,size in (('closed',20202),('open',172800),('ride',259106))],extra_port_args=('--dsp-peek',';'.join(peeks)),retain_audio_failure=True)
  f.finish_row(row,directory,expected,syms)
 finally:f.c.stage_fixture=original_stage;f.c.subprocess.run=original_run
 result=dict(status='PASS_FRESH_HANDOFF_SET_PLAYBACK_AND_ASSET_BYTES',set='PERKYF6',project='RIG',project_files=manifest,playback_receipt=str(directory/'FULL_ROW.json'),playback_receipt_sha256=f.c.sha(directory/'FULL_ROW.json'),patterns={'A1':'WT/WT/Slap/metallic Hat, dense controls/LFOs and all 14 FX','A2':'WT/WT/Slap/Noise-Tone','A3':'WT/WT/Slap/Acoustic Hats','A4':'Fold1/Fold2/Resonant/metallic Hat','B1-B4':'243 algorithm/mode tuples; play one complete 64-step cycle of each'},source_sha256=f.c.sha(Path(__file__)),limits=['Only A1 playback of this exported SET is independently checked here. Equivalent B1-B4 matrix fixtures have a separate full automated qualification.','Copy the supplied new SET as a whole; no existing project is migrated or overwritten.'])
 (W/'HANDOFF_PROJECT.json').write_text(json.dumps(result,indent=2)+'\n');print(result['status'])
if __name__=='__main__':main()

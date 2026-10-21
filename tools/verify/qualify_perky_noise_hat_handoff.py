#!/usr/bin/env python3
"""Actual panel lifecycle and diagnostic mode/backend transition qualification.

Findings are retained, including failed qualification. No target state is
repaired by the observer. Fixed-selector workload rows are separate evidence.
"""
import argparse,json,os,re,shutil,subprocess,sys
from pathlib import Path
import measure_perky_cf_placement_integrated as c
import stems_panel as panel
ROOT=Path(__file__).resolve().parents[2]
WORK=ROOT/'out/perky/hybrid/noise-hat-handoff'
SOURCE=ROOT/'out/perky/hybrid/noise-hat-handoff'
COUNTS=('pk_nhr_sequence','pk_nhr_consumed','pk_nhr_failures','pk_nhr_dma_reads','pk_nhr_dma_done',
        'pk_nhr_lag_min','pk_nhr_lag_max','pk_nht_pending_max','pk_nhr_enabled','pk_nhf_batches','placement_status','pk_nhb_owner','pk_nhb_produced','pk_nhb_completed','pk_nhb_switches','pk_nhb_deferred','pk_nhb_queue_peak','pk_nhb_imports','pk_nhb_overflows','pk_nhb_clock_errors')
def setup():
 WORK.mkdir(parents=True,exist_ok=True)
 for name in ('probe','program','dsp-A.upload.bin','dsp-B.upload.bin'):
  path=WORK/name
  if not path.exists():path.symlink_to(SOURCE/name,target_is_directory=(SOURCE/name).is_dir())
def environment(directory,syms):
 env=c.private.environment(WORK,'lifecycle')
 dsp=json.loads((WORK/'program/resident-symbols.json').read_text())
 env.update(HYBRID_SAFETY_REPORT=str(directory/'stack.json'),HYBRID_PRIVATE_REPORT=str(directory/'private.json'),
  NHR_EXACT_LIBRARY=str(WORK/'observer/resident-oracle.dylib'),NHR_DSP_COMMIT=hex(dsp['commit']),NHR_EXACT_REPORT=str(directory/'exact.json'))
 for key,name in dict(NHR_EXPECT='pk_nhr_expect',NHR_ACCEPT='pk_nhr_accept',NHR_FRAME='pk_nhr_frame',NHR_MAIL='pk_nhr_mail',NHF_PREPARE='prepare_nh',
  NHL_ENABLED='pk_nhr_enabled',NHL_RENDER='pk4_render',NHL_ENGINE='placement_engine',NHL_ASSETS='placement_assets',NHL_LAYOUT='placement_layout',NHL_SEGMENT='placement_segment').items():env[key]=hex(syms[name])
 for key,name in dict(NHB_OWNER='pk_nhb_owner',NHB_INPUTS='placement_inputs',NHB_SEQUENCE='pk_nhr_sequence',NHB_OUTPUT='placement_output',NHB_PRODUCED='pk_nhb_produced',NHB_COMPLETED='pk_nhb_completed',NHB_BLOCKING='nha_port',NHB_WORK='pk_nhb_work').items():
  env[key]=hex(syms[name]+(120 if key=='NHB_INPUTS' else 192 if key=='NHB_OUTPUT' else 0))
 if 'stems_ata_first' in syms:env['NHB_ATA_FIX']=hex(syms['stems_ata_first'])
 env.update(CFS_SLAP_RENDER=hex(syms['pk_cf_slap_render']),CFS_SLAP_LIBRARY=str(ROOT/'out/perky/hybrid/cf-placement/native.dylib'),CFS_REPORT=str(directory/'synthesis.json'))
 env['NHB_CLOCK']=hex(syms['placement_clocks']+36)
 env['NHL_CLOCK']=hex(syms['placement_clocks']+36)
 return env
def run(case):
 setup();directory=WORK/case;directory.mkdir(exist_ok=True)
 # Replace reproducible run outputs, without touching source assets or other
 # cases. MenuPort appends stderr, so an old port.log must not survive a run.
 disposable={'port.log','startup.log','SNAPSHOTS.json','RESULT.json','stack.json','private.json',
             'synthesis.json','exact.json','exact.json.controls.json','exact.json.lifecycle.json','exact.json.stream.json'}
 for p in directory.iterdir():
  if p.is_file() and not p.is_symlink() and (p.name in disposable or p.suffix=='.png'):p.unlink()
 syms=c.private.symbols(WORK/'probe/platform/runtime.elf')
 project=Path(json.loads((ROOT/'modules/perky/hybrid/BASELINE.json').read_text())['project']['root'])
 card=c.stage_fixture(project,directory,'static',[9,9,8,5],[1,2,0,0],15)
 wanted=json.loads((SOURCE/'BUILD.json').read_text())['main_sha256']
 images=[p for p in (WORK/'probe').glob('mainos_PK*.bin') if c.sha(p)==wanted]
 assert len(images)==1,('candidate image is ambiguous',images)
 image=images[0]
 instrument=directory/'instrument';instrument.mkdir(exist_ok=True)
 receipt=json.loads((WORK/'observer/OBSERVER_BUILD.json').read_text())
 archive={}
 for p in dict.fromkeys([WORK/'observer/ot_emu_safety',WORK/'observer/resident-oracle.dylib',WORK/'observer/OBSERVER_BUILD.json',Path(__file__),*[ROOT/p for p in receipt['source_sha256']]]):
  dest=instrument/p.name;shutil.copy2(p,dest);archive[str(p)]=str(dest)
 (directory/'INPUT_ARCHIVE.json').write_text(json.dumps(archive,indent=2)+'\n')
 emu=instrument/'ot_emu_safety'
 inputs={str(p):c.sha(p) for p in (image,WORK/'probe/platform/runtime.elf',card,emu,instrument/'resident-oracle.dylib',instrument/'OBSERVER_BUILD.json',instrument/Path(__file__).name,ROOT/'out/perky/hybrid/cf-placement/native.dylib')}
 pokes=[]
 def poke32(address,value):pokes.extend(f'{address+i:#x}={v:#x}' for i,v in enumerate(value.to_bytes(4,'big')))
 poke32(syms['placement_mask'],15)
 if case=='cf-calibration':poke32(syms['pk_nhr_enabled'],0)
 for i,(algo,mode) in enumerate(zip([9,9,8,5],[1,2,0,0])):
  poke32(syms['placement_inputs']+40*i,algo);poke32(syms['placement_inputs']+40*i+4,mode)
 env=environment(directory,syms);env['NHR_EXACT_LIBRARY']=str(instrument/'resident-oracle.dylib')
 previous={k:os.environ.get(k) for k in env};os.environ.update(env)
 panel.PORT_BIN=emu;rows=[];port=None
 def snapshot(p,label):
  row=dict(label=label,counts={n:p.long(syms[n]) for n in COUNTS},part=p.peek(0x100b14cf,1)[0],
   bank_pointer=p.long(0x46c82456),working_bank=p.peek(0x80000002,1)[0],playing_bank=p.peek(0x800065bd,1)[0],
   latched_bank=p.peek(0x46c7ff40,1)[0],track_banks=list(p.peek(0x8000182a,8)),
   transport=p.long(0x800065b8),mode=p.long(syms['placement_inputs']+124),B_unavailable=p.long(0x40218856),status=p.proc.command('status','status'),cf_status=p.proc.command('cfstatus','cfstatus'),dma_status=p.proc.command('edmastatus','edmastatus'),card_status=p.proc.command('card status','card'),card_count=p.peek(0x46c8c592,1)[0],card_state=p.long(0x46c8c58a),card_UDMA=p.peek(0x46c85c8c,1)[0])
  rows.append(row);(directory/'SNAPSHOTS.json').write_text(json.dumps(rows,indent=2)+'\n');print(json.dumps(row),flush=True);return row
 def backend(p,wanted,label):
  p.poke(syms['pk_nhr_enabled'],wanted.to_bytes(4,'big'))
  for _ in range(20):
   p.run(20)
   if p.long(syms['pk_nhb_owner'])==wanted:break
  row=snapshot(p,label);assert row['counts']['pk_nhb_owner']==wanted,('handoff did not complete',row)
  return row
 try:
  with panel.MenuPort(image,card,'OCTABAM','RIG',True,log_path=directory/'port.log',extra=(
   '--load-ms','90000','--sequencer','--frames','1','--bank','0','--dsp-dirty','123','--pit-clock-hz','132000000',
   '--cf-cycles-clock','1.0','--cf-cycles-clock-before-transport','--poke-before-play',';'.join(pokes),
   '--block-dump',str(directory/'blocks.bin'))) as p:
   port=p.proc
   startup='\n'.join(port.log);(directory/'startup.log').write_text(startup+'\n')
   assert 'cycle clock: startup/pre-roll/transport use' in startup,'interactive clock inactive'
   p.settle();snapshot(p,'loaded-playing')
   if case=='cf-calibration':
    p.run(150);snapshot(p,'CF-continuous')
    for mode in (1,2,0):
     p.poke(syms['placement_inputs']+124,mode.to_bytes(4,'big'));p.run(100);snapshot(p,f'CF-mode-{mode}')
   elif case=='panel':
    for i in range(3):
     backend(p,i!=1,f'stop-backend-{i}')
     p.press('stop',hold=20,settle=80);off=snapshot(p,f'stop-{i}')
     p.press('play',hold=20,settle=100);on=snapshot(p,f'start-{i}')
     if off['transport']==on['transport']:
      p.png(directory/f'failed-start-{i}.png')
      for j in range(3):p.run(100);snapshot(p,f'failed-start-{i}-followup-{j}')
     assert off['transport']!=on['transport'],('transport did not change',off,on)
    # Bounded two-Part navigation. Verify actual target Part after each key.
    for wanted,keys in ((2,('down',)),(0,('up',))):
     backend(p,int(wanted==0),f'part-backend-{wanted}')
     p.press('part',hold=20,settle=40)
     for key in keys:p.press(key,hold=20,settle=30)
     p.press('yes',hold=20,settle=100)
     row=snapshot(p,f'part-{wanted}');p.png(directory/f'part-{wanted}.png');assert row['part']==wanted,row
    for _ in range(16):
     if p.long(0x40218856)==0:break
     p.run(1000)
    ready=snapshot(p,'background-bank-ready');assert ready['B_unavailable']==0,ready
    for bank in (1,0):
     backend(p,int(bank==0),f'bank-backend-{bank}')
     p.chord('bank',f'trig{bank+1}',settle=60);p.press('trig1',hold=20,settle=80)
     for _ in range(13):
      if p.peek(0x800065bd,1)[0]==bank and p.peek(0x46c7ff40,1)[0]==bank:break
      p.run(1000)
     p.run(40) # let the frame ISR apply the separately latched playing bank
     row=snapshot(p,f'bank-{bank}');assert row['playing_bank']==row['latched_bank']==bank,row
   else:
    # All six directed panel-mode pairs; each limb is warm before fallback.
    for i,mode in enumerate((1,2,0,2,1,0)):
     p.poke(syms['placement_inputs']+124,mode.to_bytes(4,'big'));p.run(100);snapshot(p,f'mode-{i}-{mode}')
    if case=='backend':
     for i in range(3):
      p.poke(syms['placement_inputs']+124,i.to_bytes(4,'big'));p.run(100);snapshot(p,f'DSP-mode-{i}')
      backend(p,0,f'CF-enter-{i}');p.run(80);snapshot(p,f'CF-{i}')
      backend(p,1,f'DSP-enter-{i}');p.run(100);snapshot(p,f'DSP-{i}')
     for i in range(6):
      backend(p,0,f'rapid-CF-{i}')
      p.poke(syms['placement_inputs']+124,(i%3).to_bytes(4,'big'));p.run(1)
      backend(p,1,f'rapid-DSP-{i}')
   p.run(100);snapshot(p,'end')
  # quit acknowledges before static destructors write the exact/stack reports.
  assert port.proc.wait(timeout=60)==0
  exact=json.loads((directory/'exact.json').read_text());controls=json.loads((directory/'exact.json.controls.json').read_text());lifecycle=json.loads((directory/'exact.json.stream.json').read_text())
  synthesis=json.loads((directory/'synthesis.json').read_text());assert synthesis['Slap_calls'] and synthesis['Slap_native_samples']
  stack=json.loads((directory/'stack.json').read_text());private=json.loads((directory/'private.json').read_text())
  classes=c.blockdump.classes(c.blockdump.read(directory/'blocks.bin'));audio={}
  for tr in range(1,9):
   src=c.recloop.track_audio(classes,tr);post=c.recloop.readback_audio(classes,tr)
   audio[f'T{tr}']=dict(source_significant=sum(abs(v)>64 for v in src),post_FX_significant=sum(abs(v)>64 for v in post))
  if case!='cf-calibration':audio['T6']['source_significant']=max(exact['source_significant'],audio['T6']['source_significant']);audio['T6']['source_kind']='DSP source PCM witnessed before AMP; controls in DMA records'
  errors={k:exact[k] for k in ('source_PCM_mismatches','state_mismatches','feedback_mismatches','clock_mismatches','ring_mismatches')}
  errors.update(stream_PCM_mismatches=lifecycle['PCM_mismatches'],stream_state_mismatches=lifecycle['state_mismatches'],stream_clock_mismatches=lifecycle['clock_mismatches'],stream_ring_mismatches=lifecycle['ring_mismatches'],stream_feedback_mismatches=lifecycle['feedback_mismatches'],blocking_RPC_calls=lifecycle['blocking_RPC_calls'],control_mismatches=controls['mismatches'],transport_failures=rows[-1]['counts']['pk_nhr_failures'])
  errors.update({k:v for k,v in synthesis.items() if k.endswith('_mismatches')})
  errors['card_write_errors']=int(re.search(r'errors=(\d+)',rows[-1]['card_status']).group(1))
  errors.update(deadline_misses=stack['ISR_duration_misses'],DMA_overlaps=stack['DMA_read_write_overlaps'],DMA_restarts=stack['DMA_active_restarts'],
   guard_writes=stack['guard_writes_after_dispatch'],stack_extent_errors=sum(t['outside_extent'] for t in stack['stacks']),
   private_ownership_errors=private['ownership_register_frame_or_mask_violations']+private['fence_writes'],
   inactive_tracks=sum(a['source_significant']<=64 or a['post_FX_significant']<=64 for a in audio.values()))
  assert 0<=stack['frames']-stack['frame_returns']<=1,'unbounded unfinished ISR'
  report=dict(schema='perky-noise-hat-lifecycle-v1',case=case,status='PASS_MODEL_SCOPE' if not any(errors.values()) else 'FAILED_QUALIFICATION',
   inputs=inputs,events=rows,exact=exact,controls=controls,lifecycle=lifecycle,synthesis=synthesis,errors=errors,audio=audio,
   full_ISR=dict(frames=stack['frames'],returns=stack['frame_returns'],max_cycles=stack['full_ISR_max_cycles'],max_us=stack['full_ISR_max_cycles']/264,deadline_misses=stack['ISR_duration_misses']),
   safety=stack,private=private,hardware_validated=False,
   limits=['Diagnostic fixed algorithm selectors persist across real Part/Bank changes; this does not qualify shipping ALGO/MODE persistence or generation reset.',
    'Mode/backend selector pokes take effect at callback boundaries; these are probe controls, not product UI knobs.',
    'One persistent original-author stream is seeded once before the first source frame; subsequent state and clock evolve independently across both backends.',
    'Lockstep instruction scheduler and CF cycle model; no physical cache/card arbitration qualification.'])
  assert all(c.sha(Path(p))==h for p,h in inputs.items() if Path(p)!=card),'inputs changed'
  report['final_card_sha256']=c.sha(card) # panel actions may legitimately save working data
  report['outputs']={p.name:c.sha(p) for p in directory.iterdir() if p.is_file() and p.name not in ('card.img','blocks.bin','RESULT.json')}
  (directory/'RESULT.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(case=case,status=report['status'],errors=errors,full_ISR=report['full_ISR'])),flush=True)
  return report
 finally:
  if port and port.alive():
   try:port.proc.wait(timeout=60)
   except subprocess.TimeoutExpired:port.kill()
  for k,v in previous.items():
   if v is None:os.environ.pop(k,None)
   else:os.environ[k]=v
  # Generated cards/blocks can be reproduced; source assets remain untouched.
  for name in ('card.img','blocks.bin'):
   path=directory/name
   if path.exists():path.unlink()
  for name in ('project','tree'):
   if (directory/name).exists():shutil.rmtree(directory/name)
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--case',choices=('panel','modes','backend','cf-calibration'),action='append');a=p.parse_args()
 for case in a.case or ('cf-calibration','panel','modes','backend'):run(case)
if __name__=='__main__':main()

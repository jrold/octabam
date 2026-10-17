#!/usr/bin/env python3
"""Measure first T6 admission through the stock chooser while T2 continues.

Uses three unchanged STATIC sources, the original panel path, coherent PERKY
profiler snapshots and an existing calibrated private-stack observer. Natural
pattern/UI phase differs between windows; the matched stock matrix and native
activation probe separately isolate marginal execution work.
"""
from pathlib import Path
import argparse
import os,sys,json,struct,subprocess,shutil,hashlib,time,collections
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'tools/verify'),str(ROOT/'tools/emu'),str(ROOT/'tools/perky'),str(ROOT/'tools/harness')]
import verify_perky_hybrid_workload as workload
import verify_perky_hybrid_private_stack as private
import perky_hybrid_voice_layout as layout
import stems_panel as panel
import emu_card,blockdump,recloop
from hybrid_profile import decode_profiler_dump


def run(PROBE,observer,OUT,pairs,validate_only=False):
    OUT.mkdir(parents=True,exist_ok=True)
    image=PROBE/'mainos_PKHYB2P.bin';elf=PROBE/'platform/runtime.elf';syms=private.symbols(elf);geometry=layout.layout(PROBE);panel.PORT_BIN=observer
    OriginalPort=panel.PortProc
    class FullLogPort(OriginalPort):
     def __init__(self,*args,**kwargs):
      super().__init__(*args,**kwargs);self.log=collections.deque(maxlen=10000)
    panel.PortProc=FullLogPort
    project=Path(json.loads((ROOT/'modules/perky/hybrid/BASELINE.json').read_text())['project']['root']);rows=[]
    inputs={str(p):private.sha(p) for p in [image,elf,observer,Path(__file__),Path(workload.__file__),Path(panel.__file__)]}
    for left,right in pairs:
     name=left+'-'+right;work=OUT/name;work.mkdir(exist_ok=True);
     capture_files=['stopped.prof.bin','SNAPSHOTS.json','INITIAL_CARD.json','PORT_COMMAND.json','stdout-boot-and-noise.log','executed-stack.json','private-stack.json','blocks.bin']
     resumed=all((work/n).exists() for n in capture_files)
     if resumed and not validate_only:raise AssertionError('completed capture exists; use --validate-only')
     if not resumed and validate_only:raise AssertionError('missing completed capture: '+str(work))
     if not resumed:
      shutil.copyfile(__file__,work/'capture_driver.py')
      (work/'CAPTURE_SOURCE.json').write_text(json.dumps(dict(path=str(work/'capture_driver.py'),sha256=private.sha(work/'capture_driver.py'),recorded_after_capture=False),indent=2)+'\n')
      tone=work/'tone.wav';workload.make_tone(tone)
      card=workload.stage_integrated_fixture(project,work/'fixture',left,right,tone_path=tone,allow_family_transitions=False,sampler_kind='static',sampler_tracks=(2,3,6))
      tree=work/'tree';tree.mkdir()
      for name,data in emu_card.extract_image(card.read_bytes()).items():
       p=tree/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
      project_dir=next(tree.rglob('bank01.work')).parent
      for bank in project_dir.glob('bank*.work'):
       def disable_t6(data):
        for part in range(workload.otp.NPARTS_ALL):
         live=workload.otp.PART_BASE+part*workload.otp.PART_STRIDE+9
         data[live+60+30*5:live+63+30*5]=bytes(3)
       workload.otp._bank_write(project_dir,int(bank.stem[4:]),disable_t6,guard=False)
      card.write_bytes(emu_card.build_image(tree));shutil.rmtree(tree)
      shutil.copyfile(card,work/'initial-card.img')
      capture_files=[image,elf,PROBE/'BUILD.json',observer,work/'capture_driver.py',work/'initial-card.img']
      if (PROBE/'VOICE_LAYOUT.json').exists():capture_files.append(PROBE/'VOICE_LAYOUT.json')
      (work/'CAPTURE_INPUTS.json').write_text(json.dumps(dict(recorded_after_capture=False,inputs={str(f):private.sha(f) for f in capture_files}),indent=2)+'\n')
      initial_card_sha=private.sha(card);(work/'INITIAL_CARD.json').write_text(json.dumps(dict(path=str(card),immutable_archive=str(work/'initial-card.img'),sha256=initial_card_sha),indent=2)+'\n');env=private.environment(PROBE.parent,'panel-second-'+left+'-'+right)
      env['HYBRID_SAFETY_REPORT']=str(work/'executed-stack.json');env['HYBRID_PRIVATE_REPORT']=str(work/'private-stack.json');os.environ.update(env)
      snaps=[]
      def snapshot(p,label):
       for attempt in range(100):
        seq=p.long(syms['pk_hybrid_prof_seq'])
        if seq&1:p.run(1);continue
        raw=p.peek(syms['pk_hybrid_prof'],1780)
        if p.long(syms['pk_hybrid_prof_seq'])==seq:break
       else:raise AssertionError('no coherent profile snapshot')
       values=struct.unpack('>445I',raw);profile=decode_profiler_dump(raw);assert profile['magic']=='0x504b4850' and profile['extension']['full_frame_window']
       bank=p.long(0x46c82456);part=p.peek(0x100b14cf,1)[0];live=bank+0x8ed80+part*0x18b2
       native=[list(p.peek(syms['pk_hybrid_voices']+i*geometry['stride']+geometry['active_algo_offset'],2)) for i in (0,1)]
       n=min(values[6],64);start=(values[48]-n)%64;ring=[dict(frame=values[6]-n+j+1,full=values[49+(start+j)%64],cf=values[113+(start+j)%64],control=values[177+(start+j)%64],render=values[241+(start+j)%64],pack=values[305+(start+j)%64]) for j in range(n)]
       path=work/(label+'.prof.bin');path.write_bytes(raw)
       row=dict(label=label,profiler_sequence=seq,frame_count=values[6],inst_calls=list(values[36:38]),full_sum_ticks=values[24]+(values[25]<<32),cf_sum_ticks=values[26]+(values[27]<<32),control_sum_ticks=values[28]+(values[29]<<32),render_sum_ticks=values[30]+(values[31]<<32),pack_sum_ticks=values[32]+(values[33]<<32),reset_count=values[436],reset_max_ticks=values[435],generation=values[14],deadline_misses=values[16],margin_misses=values[17],native_algorithms_modes=native,signatures={str(t):p.peek(live+60+30*t,3).hex() for t in (0,1,4,5)},stock_machine_types={str(t):p.peek(live+0x22+t,1)[0] for t in (2,3,6)},recent_ring_ticks=ring,raw_path=str(path),raw_sha256=private.sha(path))
       snaps.append(row);(work/'SNAPSHOTS.json').write_text(json.dumps(snaps,indent=2)+'\n');return row
      with panel.MenuPort(image,card,'OCTABAM','RIG',True,log_path=work/'port.log',extra=('--load-ms','90000','--dsp-dirty','123','--pit-clock-hz','132000000','--cf-cycles-clock','1.0','--cf-cycles-clock-before-transport','--sequencer','--frames','1','--block-dump',str(work/'blocks.bin'))) as p:
       (work/'PORT_COMMAND.json').write_text(json.dumps(p.proc.argv,indent=2)+'\n')
       p.settle();p.poke(0x46c00010,b'\x01');loaded=snapshot(p,'loaded')
       assert loaded['inst_calls'][0]>0 and loaded['inst_calls'][1]==0 and loaded['signatures']['5']=='000000', 'T6 must never have synthesized before activation'
       assert p.long(0x800065b8)==1,'transport not playing'
       single_start=snapshot(p,'single_start');p.run(1000);single_end=snapshot(p,'single_end')
       p.press('t6',hold=20,settle=50);p.chord('func','pg_playback',settle=60);assert p.long(0x460d5c30)==1
       for _ in range(4):p.press('down',hold=15,settle=25)
       assert p.long(0x460d5c30)==5;before=snapshot(p,'before_yes')
       assert before['inst_calls'][1]==0
       p.press('yes',hold=20,settle=0);after=snapshot(p,'after_yes20')
       for i in range(20):
        if after['signatures']['5']=='504b01':break
        p.run(5);after=snapshot(p,'after_yes_retry'+str(i))
       assert after['signatures']['5']=='504b01'
       bank=p.long(0x46c82456);part=p.peek(0x100b14cf,1)[0];live=bank+0x8ed80+part*0x18b2
       algo,mode,tune,decay,p1,p2=workload.CF_SPEC[right];controls=bytes((tune,decay,algo,p1,p2,mode))
       p.poke(live+48+30*5,controls);p.poke(0x100a4ece+part*0x18b2+48+30*5,controls)
       snapshot(p,'PERKY_T6_parameters_restored_after_stock_chooser_defaults')
       for i in range(4):p.run(10);snapshot(p,'after_activation_'+str(10*(i+1)))
       p.press('no',hold=20,settle=50);p.run(700);dual_start=snapshot(p,'dual_start')
       expected=[list(workload.CF_SPEC[k][:2]) for k in (left,right)]
       assert dual_start['native_algorithms_modes']==expected
       for i in range(10):
        p.run(100);dual_end=snapshot(p,'dual_steady_'+str(i));assert dual_end['native_algorithms_modes']==expected
       assert dual_end['native_algorithms_modes']==expected,(dual_end['native_algorithms_modes'],expected)
       assert all(s['signatures']['1']=='504b01' and s['stock_machine_types']=={'2':0,'3':0,'6':0} for s in snaps)
       assert dual_end['generation']==single_end['generation'] and dual_end['reset_count']==single_end['reset_count']+1
       assert dual_end['inst_calls'][0]>before['inst_calls'][0] and dual_end['inst_calls'][1]>0
       p.press('stop',hold=20,settle=60);snapshot(p,'stopped')
      assert p.proc.proc.wait(timeout=120)==0, 'port child failed at shutdown'
      log='\n'.join(p.proc.log);(work/'stdout-boot-and-noise.log').write_text(log+'\n');assert 'startup/pre-roll/transport use x1.00' in log
     else:
      snaps=json.loads((work/'SNAPSHOTS.json').read_text());bylabel={s['label']:s for s in snaps}
      assert snaps[-1]['label']=='stopped'
      single_start,single_end,before,dual_start,dual_end=(bylabel[n] for n in ['single_start','single_end','before_yes','dual_start','dual_steady_9'])
      initial_card_sha=json.loads((work/'INITIAL_CARD.json').read_text())['sha256']
      assert 'startup/pre-roll/transport use x1.00' in (work/'stdout-boot-and-noise.log').read_text()
      for snapshot in snaps:assert private.sha(snapshot['raw_path'])==snapshot['raw_sha256']
     capture_pins=json.loads((work/'CAPTURE_INPUTS.json').read_text())
     assert capture_pins['inputs'][str(image)]==private.sha(image)
     assert capture_pins['inputs'][str(elf)]==private.sha(elf)
     assert capture_pins['inputs'][str(observer)]==private.sha(observer)
     for filename,digest in capture_pins['inputs'].items():assert private.sha(filename)==digest,'capture input drift: '+filename
     capture_source=json.loads((work/'CAPTURE_SOURCE.json').read_text());assert private.sha(capture_source['path'])==capture_source['sha256']
     command=json.loads((work/'PORT_COMMAND.json').read_text());assert private.sha(command[command.index('--image')+1])==private.sha(image)
     initial=json.loads((work/'INITIAL_CARD.json').read_text())
     if initial.get('immutable_archive'):assert private.sha(initial['immutable_archive'])==initial['sha256']
     stack,own=(private.read(work/n) for n in ['executed-stack.json','private-stack.json']);assert stack['frames']==stack['frame_returns']==own['switched']==own['restored']>0
     assert stack['ISR_duration_misses']==stack['DMA_read_write_overlaps']==stack['guard_writes_after_dispatch']==0
     assert own['ownership_register_frame_or_mask_violations']==own['fence_writes']==0 and not any(t['outside_extent'] for t in stack['stacks'])
     def window(a,b):
      n=b['frame_count']-a['frame_count'];assert n>0
      return dict(frames=n,simulated_audio_seconds=n*16/44100,mean_full_ISR_elapsed_us=(b['full_sum_ticks']-a['full_sum_ticks'])/n/132,mean_CF_callback_us=(b['cf_sum_ticks']-a['cf_sum_ticks'])/n/132,CF_calls=[b['inst_calls'][i]-a['inst_calls'][i] for i in (0,1)],hard_miss_delta=b['deadline_misses']-a['deadline_misses'],margin_miss_delta=b['margin_misses']-a['margin_misses'])
     single,dual=window(single_start,single_end),window(dual_start,dual_end)
     assert single['CF_calls'][0]>0 and single['CF_calls'][1]==0 and all(c>0 for c in dual['CF_calls'])
     classes=blockdump.classes(blockdump.read(work/'blocks.bin'));audio={}
     for track in (1,2,3,4,5,6,7):
      chain=recloop.readback_audio(classes,track)
      audio[str(track)]=dict(chain_significant=sum(abs(v)>64 for v in chain),chain_samples=len(chain));assert audio[str(track)]['chain_significant']>64,(track,audio[str(track)])
      if track not in (1,5):
       pcm=recloop.track_audio(classes,track);audio[str(track)].update(source_significant=sum(abs(v)>64 for v in pcm),source_samples=len(pcm));assert audio[str(track)]['source_significant']>64,(track,audio[str(track)])
     row=dict(pair=[left,right],capture_source=capture_source,capture_inputs=capture_pins,reused_completed_capture=validate_only,initial_fixture_archive_available=bool(initial.get('immutable_archive')),status='PASS_ACTUAL_PANEL_FIRST_T6_ACTIVATION_WITH_T2_CONTINUOUS_AND_THREE_STATIC',single_window=single,dual_window=dual,added_T6_mean_elapsed_us=dual['mean_full_ISR_elapsed_us']-single['mean_full_ISR_elapsed_us'],activation_window_max_last64_us=max(r['full'] for s in snaps if s['label'].startswith('after_') for r in s['recent_ring_ticks'])/132,source_audio=audio,fixture_before_run_sha256=initial_card_sha,snapshots=str(work/'SNAPSHOTS.json'),snapshots_sha256=private.sha(work/'SNAPSHOTS.json'),observer_reports={str(work/n):private.sha(work/n) for n in ['executed-stack.json','private-stack.json']})
     rows.append(row);assert inputs=={p:private.sha(p) for p in inputs}
     (OUT/('PANEL_VALIDATION.json' if validate_only else 'PANEL_ACTIVATION.json')).write_text(json.dumps(dict(status='PASS' if len(rows)==len(pairs) else 'RUNNING',inputs=inputs,rows=rows,scope='True first T6 PERKY admission through original chooser while T2 keeps synthesizing. Three stock STATIC tracks unchanged. Pattern trigs/locks exist on initially unsigned silent donor T6. Pre-interactive one-frame batch explicitly enables cycle clock. Elapsed-timer windows include differing natural pattern phase and UI activity; paired native sweep separates callback work. No silicon cache/card latency or physical UI latency is modeled.'),indent=2)+'\n');print(left,right,'PASS',flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--probe',type=Path,required=True)
    ap.add_argument('--observer',type=Path,required=True)
    ap.add_argument('--work',type=Path,required=True)
    ap.add_argument('--pair',action='append',help='Ordered T2/T6 algorithm pair')
    ap.add_argument('--validate-only',action='store_true',help='Validate complete saved captures without executing firmware again')
    a=ap.parse_args();pairs=[tuple(p.split('/')) for p in (a.pair or ['snare/snare','snare/bass','bass/bass'])]
    assert all(len(p)==2 and all(k in workload.CF_SPEC for k in p) for p in pairs)
    run(a.probe.resolve(),a.observer.resolve(),a.work.resolve(),pairs,a.validate_only)

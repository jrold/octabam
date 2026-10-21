#!/usr/bin/env python3
"""Bind live handoff/lifecycle and sustained full-workload evidence to one image."""
import hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/build'))
import ab_records as A
W=ROOT/'out/perky/hybrid/noise-hat-handoff'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):return json.loads(p.read_text())
def check_sources(receipt):
 for name,h in receipt.get('source_sha256',{}).items():assert sha(ROOT/name)==h,('source drift',name)
def main():
 build=load(W/'BUILD.json');image=W/'probe/mainos_PKNHF7.bin';elf=W/'probe/platform/runtime.elf'
 assert sha(image)==build['main_sha256'] and sha(elf)==build['runtime_sha256'];check_sources(build)
 assert build['boot_status'].startswith('PASS_EXACT_RUNTIME')
 observer=load(W/'observer/OBSERVER_BUILD.json');check_sources(observer)
 assert observer['binary_sha256']==sha(W/'observer/ot_emu_safety')
 assert observer['complete_oracle_sha256']==sha(W/'observer/resident-oracle.dylib')
 cases={}
 for case in ('cf-calibration','backend','panel'):
  d=W/case;r=load(d/'RESULT.json');assert r['status']=='PASS_MODEL_SCOPE',(case,r['errors'])
  assert not any(r['errors'].values()),(case,r['errors'])
  assert r['inputs'][str(image)]==sha(image) and r['inputs'][str(elf)]==sha(elf)
  archive=load(d/'INPUT_ARCHIVE.json')
  for name,h in r['inputs'].items():
   if name.endswith('card.img'):continue # mutable working project, initial+final hashes retained
   p=Path(name);assert p.exists() and sha(p)==h,('executed input drift',case,name)
  executed=load(d/'instrument/OBSERVER_BUILD.json')
  for name,h in executed['source_sha256'].items():
   assert sha(Path(archive[str(ROOT/name)]))==h,('executed source archive',case,name)
  assert 'cycle clock: startup/pre-roll/transport use' in (d/'startup.log').read_text()
  assert r['full_ISR']['max_us']<16e6/44100 and 0<=r['full_ISR']['frames']-r['full_ISR']['returns']<=1
  syn=r['synthesis'];assert syn['Slap_calls'] and syn['Slap_native_samples'] and not any(v for k,v in syn.items() if k.endswith('_mismatches'))
  stream=r['lifecycle'];assert stream['CF_frames'] and stream['worker_calls']
  if case!='cf-calibration':assert stream['DSP_frames'] and stream['ownership_transitions']>0 and stream['retired_feedback_jobs']>0
  assert stream['maximum_feedback_age_frames']<=3
  assert not stream['blocking_RPC_calls']
  end=r['events'][-1]['counts'];assert end['pk_nhb_overflows']==end['pk_nhb_clock_errors']==0
  assert end['pk_nhb_queue_peak']<1024
  cases[case]=r
 assert cases['backend']['lifecycle']['ownership_transitions']==18,cases['backend']['lifecycle']
 # Takeover is deliberately nonblocking: its first snapshot may retain old
 # feedback (observed age is independently bounded to three source frames).
 # Demand complete retirement at each later 80 ms CF dwell, not at takeover.
 cf_enter=[e for e in cases['backend']['events'] if e['label'].startswith('CF-enter-')]
 cf_events=[e for e in cases['backend']['events'] if e['label'] in ('CF-0','CF-1','CF-2')]
 assert len(cf_enter)==len(cf_events)==3
 assert all(e['counts']['pk_nhb_owner']==0 and 0<=e['counts']['pk_nhr_sequence']-e['counts']['pk_nhr_consumed']<=3 for e in cf_enter)
 assert all(e['counts']['pk_nhb_owner']==0 and e['counts']['pk_nhr_sequence']==e['counts']['pk_nhr_consumed'] for e in cf_events)
 panel=cases['panel']['events'];labels={e['label'] for e in panel}
 for e in panel:
  if e['label'] in ('bank-1','bank-0'):assert e['playing_bank']==e['latched_bank']==int(e['label'][-1])
 assert {'stop-0','start-0','stop-1','start-1','stop-2','start-2','part-2','part-0','bank-1','bank-0'}<=labels
 rows=[]
 for mode in (1,2,3):
  d=W/'integrated-results'/f'WTWT-SLAP-HAT-HANDOFF-OPT-M{mode}-static';r=load(d/'FAST_ROW.json')
  assert r['status']=='FUNCTIONAL_MODEL_ROW' and r['full_ISR']['frames']>=16384
  assert r['inputs'][str(image)]==sha(image) and r['inputs'][str(elf)]==sha(elf)
  assert r['driver_sha256']==sha(ROOT/'tools/verify/measure_perky_noise_hat_handoff.py')
  for name,h in r['inputs'].items():
   if not name.endswith('card.img'):assert sha(Path(name))==h
  assert r['full_ISR']['max_us']<16e6/44100 and not r['full_ISR']['deadline_misses']
  assert r['program_ownership'].startswith('all loaded private/shared P exact')
  syn=r['synthesis'];assert syn['Slap_calls'] and syn['Slap_native_samples'] and not any(v for k,v in syn.items() if k.endswith('_mismatches'))
  s=r['stream_exact'];assert s['DSP_frames']>=16384
  assert all(s[k]==0 for k in ('PCM_mismatches','state_mismatches','clock_mismatches','ring_mismatches','feedback_mismatches','blocking_RPC_calls'))
  assert r['control_exact']['calls'] and not r['control_exact']['mismatches']
  assert not r['audio_failures'] and r['playback_card_reads']>0
  c=r['transport_counts'];assert c['pk_nhr_failures']==0 and c['pk_nhb_queue_peak']<1024
  # A steady growing backlog would invalidate an otherwise timely audio ISR.
  assert c['pk_nhb_produced']-c['pk_nhb_completed']<128,('worker failed to keep up',mode,c)
  rows.append(r)
 gates={}
 for name in ('PERSISTENT_GATE','IMPORT_GATE','CLOCK_GATE','INNER_GATE','RESAMPLE_GATE','RENDERER_GATE','ATA_GATE'):
  r=load(W/(name+'.json'));assert r['status'].startswith('PASS');gates[name]=r
 for name in ('IMPORT_GATE','CLOCK_GATE','INNER_GATE','RESAMPLE_GATE','RENDERER_GATE','ATA_GATE'):check_sources(gates[name])
 assert gates['RESAMPLE_GATE']['division_cases']==306279667 and gates['RESAMPLE_GATE']['source_clock_frames']==145504
 assert gates['RESAMPLE_GATE']['table_sha256']==sha(W/'noise-hat-clock-table.h')
 assert gates['RENDERER_GATE']['calls']==1440 and gates['RENDERER_GATE']['native_samples']==17649
 for name,h in gates['RENDERER_GATE']['input_sha256'].items():assert sha(Path(name))==h
 asm_work=ROOT/'out/perky/hybrid/noise-hat-asm';assembly=load(asm_work/'RESULT.json')
 assert assembly['status']=='PASS_TARGET_ASSEMBLY_CLOCK_PCM_ABI_AND_COMBINED_SOURCE' and assembly['clock']['cases']==39984
 for name,h in assembly['input_sha256'].items():assert sha(Path(name))==h,('assembly proof input drift',name)
 assert sha(asm_work/'resample.h')==sha(ROOT/'modules/perky/noise_hat_handoff_resample.h')
 assert sha(asm_work/'table.h')==sha(W/'noise-hat-clock-table.h')
 gates['ASSEMBLY_GATE']=assembly
 synthesis_work=ROOT/'out/perky/hybrid/cf-synthesis-asm';synthesis=load(synthesis_work/'RESULT.json')
 assert synthesis['status']=='PASS_EXACT_DELAY_AND_COMBINED_RENDERERS'
 for name,h in synthesis['input_sha256'].items():assert sha(Path(name))==h,('synthesis proof drift',name)
 for variant in ('baseline','assembly'):
  v=synthesis['results'][variant];assert v['delay']['cases']==96880 and v['execution']['frames']==13824 and v['execution']['state_snapshots']==9288
  assert v['elf_sha256']==sha(synthesis_work/variant/'target.elf')
 assert synthesis['results']['assembly']['delay']['fast_entries']>5000
 assert synthesis['results']['assembly']['delay']['generic_entries']==24220
 # Prove the exact position-independent assembly bodies tested in isolation
 # are also the bodies linked into the full candidate.
 sys.path.insert(0,str(ROOT/'tools/perky'))
 import perky_noise_hat_ata as ata_bytes
 def body(path,name):
  base,blob=ata_bytes.text_bytes(path)
  rows=subprocess.check_output(['m68k-elf-nm','-S',str(path)],text=True).splitlines()
  row=next(line.split() for line in rows if len(line.split())==4 and line.split()[3]==name)
  at,n=int(row[0],16),int(row[1],16);return blob[at-base:at-base+n]
 for name in ('pk_cf_nh_delay_i16','pk_cf_slap_delay_block'):
  assert body(elf,name)==body(synthesis_work/'assembly/target.elf',name),('untested linked synthesis body',name)
 gates['SYNTHESIS_GATE']=synthesis
 ata=gates['ATA_GATE'];assert ata['candidate_elf_sha256']==sha(elf)
 assert ata['reference']['function_length']==52 and ata['reference']['length']==54
 assert sha(W/'ata-author/runtime.elf')==ata['reference']['elf_sha256']
 assert sha(W/'ata-author/mainos_stems.bin')==ata['reference']['image_sha256']
 assert cases['panel']['lifecycle']['PIO_first_sector_calls']>0
 assert cases['panel']['events'][-1]['card_UDMA']==255 and not cases['panel']['errors']['card_write_errors']
 for name,h in gates['PERSISTENT_GATE']['candidate_source_sha256'].items():assert sha(ROOT/name)==h
 for name,h in gates['IMPORT_GATE']['input_sha256'].items():assert sha(ROOT/name)==h
 program_blob=(W/'persistent-gate/program.bin').read_bytes()
 assert sha(W/'persistent-gate/program.bin')==gates['PERSISTENT_GATE']['program_sha256']
 upload=(W/'dsp-A.upload.bin').read_bytes();records,_=A.records(upload,A.BASE,len(upload))
 actual={a+i:A.rd(upload,o+3*i) for sp,a,n,o in records if sp==0 for i in range(n)}
 for row in load(W/'MEMORY.json')['A_program']:
  for at in range(row['start'],row['start']+row['length']):
   assert actual[at]==int.from_bytes(program_blob[3*at:3*at+3],'little'),('gate program is not uploaded program',row['name'],hex(at))
 assert gates['PERSISTENT_GATE']['frames']==720 and gates['PERSISTENT_GATE']['arithmetic_vectors']==2560
 assert gates['IMPORT_GATE']['cases']==768 and gates['CLOCK_GATE']['cases']==9996
 assert gates['INNER_GATE']['native_samples']==7633 and gates['INNER_GATE']['arithmetic_vectors']==8192
 # The new parser may move A shards, but B's qualified oscillator words must
 # remain unchanged. Other new shared records contain A-only code.
 def program(p):
  blob=p.read_bytes();rr,_=A.records(blob,A.BASE,len(blob));return {a+i:A.rd(blob,o+3*i) for sp,a,n,o in rr if sp==0 for i in range(n)}
 current=program(W/'dsp-B.upload.bin');prior=program(ROOT/'out/perky/hybrid/noise-hat-fast/dsp-B.upload.bin');memory=load(W/'MEMORY.json');bwords=0
 for row in memory['B_program']:
  for at in range(row['start'],row['start']+row['length']):assert current[at]==prior[at];bwords+=1
 assert memory['shared_free']>=0 and memory['private_P_used']['A']<=774 and memory['A_private_X_words']<=616 and memory['A_low_Y_words']<=2139
 check=(ROOT/'out/perky/hybrid/noise-hat-handoff-make-check.log').read_text();assert 'module gates (shared isolated, perky-machine): 84 run, 0 failed' in check and 'module gates (image): 4 run, 0 failed' in check
 refhash=ROOT/'out/perky/hybrid/noise-hat-handoff-refhash.log';assert 'ALL 24 CASES BIT-IDENTICAL' in refhash.read_text()
 assert sha(ROOT/'out/mainos_bus.bin')=='354bdac8f2fe79696b3156a034894b1bd0d5f757ce76657ca608851089268a58'
 def size(p):
  f=subprocess.check_output(['m68k-elf-size',str(p)],text=True).splitlines()[1].split()
  return dict(zip(('text','data','BSS'),map(int,f[:3])))
 current_size=size(elf);prior_size=size(ROOT/'out/perky/hybrid/noise-hat-fast/probe/platform/runtime.elf')
 cf_footprint=dict(linked=current_size,PKNHE1=prior_size,delta={k:current_size[k]-prior_size[k] for k in current_size},zero_bound_bytes=0x200000)
 assert current_size['BSS']<cf_footprint['zero_bound_bytes']
 sources=[Path(__file__),ROOT/'tools/harness/perky_cf/noise_hat_handoff_oracle.c',ROOT/'tools/harness/perky_cf/noise_hat_handoff_observer.h',ROOT/'tools/verify/qualify_perky_noise_hat_handoff.py',ROOT/'tools/verify/measure_perky_noise_hat_handoff.py',ROOT/'tools/verify/verify_perky_noise_hat_handoff_dsp.py',ROOT/'tools/verify/verify_perky_noise_hat_handoff_renderer.py',ROOT/'tools/verify/verify_perky_noise_hat_handoff_resample.py',ROOT/'tools/verify/verify_perky_noise_hat_handoff_asm.py',ROOT/'tools/verify/profile_perky_noise_hat_handoff.py',ROOT/'tools/verify/verify_perky_cf_synthesis_asm.py',ROOT/'tools/perky/generate_cf_synthesis_asm.py',ROOT/'modules/perky/cf_synthesis_delay.s',ROOT/'modules/perky/noise_hat_delay_i16.s',ROOT/'tools/harness/perky_cf/noise_hat_handoff_profile.h',ROOT/'tools/harness/perky_cf/cf_synthesis_observer.h',W/'observer/rtos.cpp',W/'observer/machine.cpp',W/'lifecycle-observer.h']
 report=dict(schema='perky-noise-hat-handoff-v1',status='PASS_SWITCH_REGRESSION_FIXED_MODEL_SCOPE',hardware_validated=False,
  build=build,observer=observer,cases=cases,rows=rows,gates=gates,memory=memory,CF_footprint=cf_footprint,B_qualified_words_unchanged=bwords,
  deadline_us=16e6/44100,CF_clock_hz=264000000,PIT_clock_hz=132000000,
  validation=dict(module_shared_gates=84,module_image_gates=4,refhash_cases=24,refhash_log_sha256=sha(refhash),make_check_log_sha256=sha(ROOT/'out/perky/hybrid/noise-hat-handoff-make-check.log')),
  source_sha256={str(p.relative_to(ROOT)):sha(p) for p in sources},
  scope=['Exact Slap native PCM, full raw object including the ring, and RNG at every actual renderer call against the unchanged original C given its entry state.',
   'Exact Noise Hat source PCM, resident state, phase/carry and feedback against one persistent original-author stream; state is seeded once before the first source frame and never reseeded at a switch.',
   'Actual STOP/START, Part 1/3 and Bank A/B changes with both backends; diagnostic fixed algorithm/mode selectors retain their placement. Production Part/generation reset semantics are not qualified.',
   'All eight tracks active with the fixture stock workload; twelve retained FX code/dispatch bytes exact. Whole-project post-FX PCM equivalence is not asserted.',
   'Instruction-scheduled DSP and native CF cycle model; physical cache/card arbitration and B private-tail hardware fit remain unqualified. No flash release.'])
 # Bind the read-only profiles to the actual executed inputs. Attribution
 # must reproduce every completed frame/cycle total of the normal witness.
 profiles={}
 for label,directory in (('PKNHF6_switch','noise-hat-switch-before'),('qualified','noise-hat-switch-qualified')):
  directory=ROOT/'out/perky/hybrid'/directory;profile=load(directory/'PROFILE.json');runtime=profile['result'];attribution=profile['profile']
  check_sources(profile['observer'])
  assert runtime['status']=='PASS_MODEL_SCOPE' and not any(runtime['errors'].values())
  assert attribution['returns']==runtime['full_ISR']['returns'] and attribution['top'][0]['cycles']==runtime['full_ISR']['max_cycles']
  assert attribution['sum_cycles']==runtime['safety']['full_ISR_sum_cycles']
  for name,h in runtime['inputs'].items():
   if not name.endswith('card.img'):assert sha(Path(name))==h,('profile input drift',label,name)
  for row in attribution['top']:assert sum(row['buckets'].values())==row['cycles']
  if label=='qualified':
   assert profile['source_image_sha256']==sha(image) and profile['source_elf_sha256']==sha(elf)
   assert profile['driver_sha256']==sha(ROOT/'tools/verify/profile_perky_noise_hat_handoff.py')
   assert runtime['full_ISR']==cases['backend']['full_ISR'],'profile changed target timing'
   assert runtime['safety']['full_ISR_sum_cycles']==cases['backend']['safety']['full_ISR_sum_cycles']
   assert attribution['aggregate']['pk_nhb_native_convert_fast']>0
   assert attribution['aggregate']['pk_cf_slap_delay_block']>0
   assert attribution['top'][0]['panel_mode'] in (0,1,2)
  else:
   assert profile['source_image_sha256']=='3da11d00a10a6bf813592e6a54fb2c5d237ee31489afc3b46bc8f3d6b46e328a'
   prior_switch=load(ROOT/'out/perky/hybrid/noise-hat-switch-before-normal/backend/RESULT.json')
   historic=load(ROOT/'out/perky/hybrid/noise-hat-handoff-f6/backend/RESULT.json')
   assert not any(prior_switch['errors'].values()) and prior_switch['status']=='PASS_MODEL_SCOPE'
   assert prior_switch['full_ISR']==historic['full_ISR']
   for name,h in prior_switch['inputs'].items():
    if not name.endswith('card.img'):assert sha(Path(name))==h,('F6 normal input drift',name)
   profiles['PKNHF6_switch_normal']=prior_switch
   profiles['PKNHF6_historical_sum_cycles']=historic['safety']['full_ISR_sum_cycles']
   assert runtime['full_ISR']==prior_switch['full_ISR']
   assert attribution['sum_cycles']==prior_switch['safety']['full_ISR_sum_cycles']
   assert runtime['full_ISR']['max_cycles']==89715
   assert profile['driver_sha256']==sha(ROOT/'tools/verify/profile_perky_noise_hat_handoff.py')
  profiles[label]=profile
 previous=load(ROOT/'out/perky/hybrid/noise-hat-synthesis-before/PROFILE.json')
 assert previous['source_image_sha256']=='179cdc293a27b45466efcd68d1efd1e4092db3b38cb6afcf5292993c89ac7e99'
 prior_case=load(ROOT/'out/perky/hybrid/noise-hat-handoff-f5/cf-calibration/RESULT.json')
 assert previous['result']['full_ISR']==prior_case['full_ISR'] and previous['profile']['sum_cycles']==prior_case['safety']['full_ISR_sum_cycles']
 for name,h in previous['result']['inputs'].items():
  if not name.endswith('card.img'):assert sha(Path(name))==h,('F5 profile input drift',name)
 profiles['PKNHF5_CF_calibration']=previous
 qualified_cf=load(ROOT/'out/perky/hybrid/noise-hat-switch-cf-qualified/PROFILE.json')
 assert qualified_cf['source_image_sha256']==sha(image) and qualified_cf['source_elf_sha256']==sha(elf)
 assert qualified_cf['result']['full_ISR']==cases['cf-calibration']['full_ISR']
 assert qualified_cf['profile']['sum_cycles']==cases['cf-calibration']['safety']['full_ISR_sum_cycles']
 assert qualified_cf['profile']['aggregate']['pk_cf_nh_delay_i16']>0 and qualified_cf['profile']['aggregate']['pk_cf_slap_delay_block']>0
 for name,h in qualified_cf['result']['inputs'].items():
  if not name.endswith('card.img'):assert sha(Path(name))==h,('CF profile input drift',name)
 profiles['qualified_CF_calibration']=qualified_cf
 maximum=max([r['full_ISR']['max_cycles'] for r in cases.values()]+[r['full_ISR']['max_cycles'] for r in rows])
 reserve=264000000*16/44100-maximum
 assert cases['backend']['full_ISR']['max_cycles']<=88270,('backend regression persists',cases['backend']['full_ISR'])
 assert maximum<91744,('no improvement over qualified PKNHF5',maximum)
 assert reserve>=2640,('less than 10 us modeled reserve',reserve/264)
 headroom=dict(worst_full_ISR_cycles=maximum,worst_full_ISR_us=maximum/264,reserve_cycles=reserve,reserve_us=reserve/264,minimum_required_model_reserve_us=10,deadline_fraction_free=reserve/(264000000*16/44100),baseline_switch_peak_cycles=95780,baseline_switch_reserve_cycles=264000000*16/44100-95780,PKNHF6_switch_cycles=89715,PKNHF5_switch_cycles=88270,switch_cycles_saved_from_PKNHF6=89715-cases['backend']['full_ISR']['max_cycles'],PKNHF6_worst_cycles=91152,PKNHF5_worst_cycles=91744,cycles_saved_from_PKNHF5_worst=91744-maximum)
 baseline=ROOT/'out/perky/hybrid/noise-hat-handoff-baseline'
 for core in ('A','B'):assert sha(W/f'dsp-{core}.upload.bin')==sha(baseline/f'dsp-{core}.upload.bin'),('DSP upload changed',core)
 baseline_size=size(baseline/'probe/platform/runtime.elf')
 cf_footprint.update(PKNHF1=baseline_size,delta_from_PKNHF1={k:current_size[k]-baseline_size[k] for k in current_size})
 totals=dict(source_frames=sum(r['lifecycle']['CF_frames']+r['lifecycle']['DSP_frames'] for r in cases.values())+sum(r['stream_exact']['CF_frames']+r['stream_exact']['DSP_frames'] for r in rows),
  original_control_calls=sum(r['controls']['calls'] for r in cases.values())+sum(r['control_exact']['calls'] for r in rows),
  Slap_calls=sum(r['synthesis']['Slap_calls'] for r in cases.values())+sum(r['synthesis']['Slap_calls'] for r in rows),Slap_native_samples=sum(r['synthesis']['Slap_native_samples'] for r in cases.values())+sum(r['synthesis']['Slap_native_samples'] for r in rows))
 f5size=size(ROOT/'out/perky/hybrid/noise-hat-handoff-f5/probe/platform/runtime.elf');cf_footprint.update(PKNHF5=f5size,delta_from_PKNHF5={k:current_size[k]-f5size[k] for k in current_size})
 f6size=size(ROOT/'out/perky/hybrid/noise-hat-handoff-f6/probe/platform/runtime.elf');cf_footprint.update(PKNHF6=f6size,delta_from_PKNHF6={k:current_size[k]-f6size[k] for k in current_size})
 assert body(elf,'pk_cf_slap_delay_block')==body(ROOT/'out/perky/hybrid/noise-hat-handoff-f6/probe/platform/runtime.elf','pk_cf_slap_delay_block'),'Slap assembly changed'
 report.update(profiles=profiles,headroom=headroom,totals=totals,DSP_uploads_identical_to_PKNHF1=True)
 destination=ROOT/'modules/perky/hybrid/NOISE_HAT_HANDOFF.json';destination.write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(dict(status=report['status'],image_sha256=sha(image),headroom=headroom,lifecycle={k:dict(frames=v['full_ISR']['frames'],peak_us=v['full_ISR']['max_us'],transitions=v['lifecycle']['ownership_transitions']) for k,v in cases.items()},workload=[dict(mode=r['panel_mode'],frames=r['full_ISR']['frames'],peak_us=r['full_ISR']['max_us']) for r in rows]),indent=2))
if __name__=='__main__':main()

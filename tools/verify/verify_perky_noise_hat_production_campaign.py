#!/usr/bin/env python3
"""Admit production reset scope only from exact current-image receipts."""
import hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];W=ROOT/'out/perky/hybrid/noise-hat-production'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):return json.loads(p.read_text())
def sources(r):
 for name,h in r.get('source_sha256',{}).items():assert sha(ROOT/name)==h,('source drift',name)
def inputs(r):
 for name,h in r.get('inputs',{}).items():
  if name.endswith('card.img'):continue # disposable initial card; saved result separately retained
  assert sha(Path(name))==h,('executed input drift',name)
def main():
 build=load(W/'BUILD.json');image=W/'probe/mainos_PKNHG3.bin';elf=W/'probe/platform/runtime.elf'
 assert sha(image)==build['main_sha256'] and sha(elf)==build['runtime_sha256'];sources(build)
 observer=load(W/'observer/OBSERVER_BUILD.json');sources(observer)
 assert sha(W/'observer/ot_emu_safety')==observer['binary_sha256']
 assert sha(W/'observer/resident-oracle.dylib')==observer['complete_oracle_sha256']
 selection=load(W/'SELECTION.json');sources(selection)
 assert selection['status']=='PASS_LINKED_SIGNATURE_VALIDATION_AND_UI_SCOPES' and len(selection['cases'])==32
 assert selection['image_sha256']==sha(image) and selection['elf_sha256']==sha(elf)
 persistence=load(W/'persistence/RESULT.json');sources(persistence);inputs(persistence)
 assert persistence['status']=='PASS_ENCODER_SAVE_COLD_RELOAD_CONTROLS_AND_ACTIVE_AUDIO'
 assert persistence['saved_controls']['work']==persistence['saved_controls']['strd']==persistence['expected_T2_controls']
 assert list((W/'persistence/reload-controls.bin').read_bytes())==persistence['expected_T2_controls']
 assert sha(W/'persistence/saved-card.img')==persistence['saved_card_sha256']
 reload_stream=load(W/'persistence/reload/exact.json.stream.json');reload_synthesis=load(W/'persistence/reload/synthesis.json');reload_stack=load(W/'persistence/reload/stack.json')
 assert reload_stream['DSP_frames']>=500 and not any(reload_stream[k] for k in ('PCM_mismatches','state_mismatches','ring_mismatches','clock_mismatches','feedback_mismatches'))
 assert reload_synthesis['Slap_native_samples']>8000 and not any(v for k,v in reload_synthesis.items() if k.endswith('_mismatches'))
 assert reload_stack['ISR_duration_misses']==0
 for row,label in zip(persistence['commands'],('save','reload')):
  assert row['exit_status']==0 and row['log_sha256']==sha(W/'persistence'/label/'port.log')
 cases={}
 for backend in ('cf','dsp'):
  r=load(W/f'production-{backend}/PRODUCTION_RESULT.json');sources(r);inputs(r)
  assert r['production_status']=='PASS_PRODUCTION_MODEL_SCOPE'
  assert r['production_selector_errors']==0 and r['production_resets']['original_initializer_resets']==5
  assert r['events'][-1]['production_resets']==[5]*4
  assert r['events'][-1]['production_voice_generations']==[5]*4
  assert 'cycle clock: startup/pre-roll/transport use' in (W/f'production-{backend}/panel/startup.log').read_text()
  assert r['inputs'][str(W/f'production-{backend}/probe/mainos_PKNHG3.bin')]==sha(image)
  assert not any(r['errors'].values()),(backend,r['errors'])
  cases[backend]=r
 switching=load(W/'switching/SWITCHING_RESULT.json');sources(switching);inputs(switching)
 assert switching['status']=='PASS_PRODUCTION_SWITCHING_MODE_LOCKS' and not any(switching['errors'].values())
 assert switching['inputs'][str(W/'switching/probe/mainos_PKNHG3.bin')]==sha(image)
 assert switching['actual_modes_by_backend']=={'0':[0,1,2],'1':[0,1,2]}
 assert switching['lifecycle']['ownership_transitions']==18 and switching['lifecycle']['retired_feedback_jobs']>0
 for r in [*cases.values(),switching]:
  assert r['full_ISR']['max_us']<16e6/44100
  assert r['lifecycle']['maximum_feedback_age_frames']<=3 and r['lifecycle']['maximum_worker_queue']<1024
 rows=[]
 for mode in (1,2,3):
  r=load(W/'integrated-results'/f'WTWT-SLAP-HAT-HANDOFF-OPT-M{mode}-static/FAST_ROW.json');inputs(r)
  assert r['inputs'][str(image)]==sha(image) and r['full_ISR']['frames']>=16384
  assert r['status']=='FUNCTIONAL_MODEL_ROW' and not r['audio_failures'] and r['playback_card_reads']>0
  assert not any(r['stream_exact'][k] for k in ('PCM_mismatches','state_mismatches','ring_mismatches','clock_mismatches','feedback_mismatches','blocking_RPC_calls'))
  assert not any(v for k,v in r['synthesis'].items() if k.endswith('_mismatches'))
  assert r['full_ISR']['deadline_misses']==0
  rows.append(r)
 baseline=ROOT/'out/perky/hybrid/noise-hat-handoff-f7'
 # Shared P contains A's new service in both uploads. Compare B-owned code
 # and every B X/Y/private-P word, rather than falsely equating whole uploads.
 import sys
 sys.path[:0]=[str(ROOT/'tools/build'),str(ROOT/'tools')]
 import ab_records as A
 def upload_words(path):
  blob=path.read_bytes();records,_=A.records(blob,A.BASE,len(blob))
  return {(space,at+i):A.rd(blob,off+3*i) for space,at,n,off in records for i in range(n)}
 old_b=upload_words(baseline/'dsp-B.upload.bin');new_b=upload_words(W/'dsp-B.upload.bin')
 assert {k:v for k,v in old_b.items() if k[0]!=0 or k[1]<0x30000}=={k:v for k,v in new_b.items() if k[0]!=0 or k[1]<0x30000}
 assert build['memory']['B_program']==load(baseline/'MEMORY.json')['B_program']
 for row in build['memory']['B_program']:
  for at in range(row['start'],row['start']+row['length']):assert old_b[(0,at)]==new_b[(0,at)]
 assert sha(W/'dsp-A.upload.bin')!=sha(baseline/'dsp-A.upload.bin')
 dsp_gate=load(W/'PRODUCTION_DSP_GATE.json');sources(dsp_gate);inputs(dsp_gate)
 assert dsp_gate['status']=='PASS_PERSISTENT_AUTHOR_IMPORT_AND_RESIDENT_EPOCH_RESET'
 registers=load(W/'REGISTER_GATE.json');sources(registers);inputs(registers)
 assert registers['status']=='PASS_SAVED_REGISTERS_SOURCE_IMPORT_AND_EMBED'
 copy=load(W/'COPY_GATE.json');sources(copy)
 assert copy['status']=='PASS_LINKED_COPY_BYTES_GUARDS_AND_CALLEE_ABI'
 assert copy['image_sha256']==sha(image) and copy['elf_sha256']==sha(elf)
 assert cases['dsp']['production_resets']['old_epoch_writes_checked_and_retired']>0
 m=build['memory'];assert m['A_private_X_words']<=m['A_private_X_capacity'] and m['shared_words']<=m['shared_capacity']
 for i,(_,lo,hi) in enumerate(m['A_private_X']):
  assert 0x3800<=lo<hi<=0x3a68
  assert all(hi<=a or lo>=b for _,a,b in m['A_private_X'][i+1:])
 assert sum(hi-lo for _,lo,hi in m['A_private_X'])==m['A_private_X_words']
 for label,r in cases.items():
  e=r['events'][-1]['counts'];assert 0<=e['pk_nhr_sequence']-e['pk_nhr_consumed']<=3
  assert e['pk_nhb_overflows']==e['pk_nhb_clock_errors']==0
 # The synthesis helpers are retained byte-for-byte, despite new control code.
 import sys
 sys.path.insert(0,str(ROOT/'tools/perky'));import perky_noise_hat_ata as a
 def body(path,name):
  at,blob=a.text_bytes(path);rows=subprocess.check_output(['m68k-elf-nm','-S',str(path)],text=True).splitlines()
  v=next(x for line in rows if len(x:=line.split())==4 and x[3]==name);start,n=int(v[0],16),int(v[1],16)
  return blob[start-at:start-at+n]
 for name in ('pk_cf_nh_delay_i16','pk_cf_slap_delay_block'):
  assert body(elf,name)==body(baseline/'probe/platform/runtime.elf',name)
 sparse=load(W/'SPARSE_GATE.json');sources(sparse)
 assert sparse['status']=='PASS_SPARSE_RESTORE_BYTES_TAILS_FALLBACK_FULL_ENGINE_AND_ABI'
 assert sparse['vectors']==1056 and sparse['dirty_generation_cases']==512
 transport=load(W/'TRANSPORT_GATE.json');sources(transport)
 assert transport['status']=='PASS_EXACT_SOURCE_PACK_CLEAR_RESAMPLING_CLOCK_EMAC_AND_ABI'
 assert transport['reciprocal_cases']==306179667 and transport['source_clock_cases']==9996
 for proof in (sparse,transport):assert proof['image_sha256']==sha(image) and proof['elf_sha256']==sha(elf)
 g2=ROOT/'out/perky/hybrid/noise-hat-production-g2'
 g2_report=load(g2/'source-g2/modules/perky/hybrid/PRODUCTION_LIFECYCLE.json')
 for core in ('A','B'):assert sha(W/f'dsp-{core}.upload.bin')==sha(g2/f'dsp-{core}.upload.bin')
 reset_profiles={}
 for backend in ('cf','dsp'):
  olddir=ROOT/f'out/perky/hybrid/reset-profile-g2/production-{backend}'
  newdir=ROOT/f'out/perky/hybrid/reset-profile-g3/production-{backend}'
  old=load(olddir/'RESET_PROFILE.json');new=load(newdir/'RESET_PROFILE.json')
  assert old['source_image_sha256']==g2_report['build']['main_sha256']
  assert new['source_image_sha256']==sha(image) and new['source_elf_sha256']==sha(elf)
  for label,directory,profile_row,normal in (('G2',olddir,old,g2_report['cases'][backend]),('G3',newdir,new,cases[backend])):
   assert profile_row['status']=='PASS_READ_ONLY_PRODUCTION_RESET_PROFILE'
   assert not any(profile_row['result']['errors'].values())
   inputs(profile_row['result'])
   archive=load(directory/'panel/INPUT_ARCHIVE.json')
   # The G2 profile used the original target sources plus the new read-only
   # instrument. Resolve each exact source through its executed archive.
   for receipt in (profile_row,profile_row['observer'],profile_row['result']):
    for name,h in receipt.get('source_sha256',{}).items():
     paths=[ROOT/name,g2/'source-g2'/name]
     if str(ROOT/name) in archive:paths.append(Path(archive[str(ROOT/name)]))
     assert any(path.exists() and sha(path)==h for path in paths),(label,backend,'profile source drift',name)
   for key in ('frames','frame_returns','full_ISR_sum_cycles','full_ISR_max_cycles','ISR_duration_misses'):
    assert profile_row['result']['safety'][key]==normal['safety'][key],(label,backend,'observer timing effect',key)
   assert len(profile_row['profile']['reset_frames'])==5
   assert all(f['reset_mask']==15 and sum(f['buckets'].values())==f['cycles'] for f in profile_row['profile']['reset_frames'])
  reset_profiles[backend]=dict(baseline_G2=old,candidate_G3=new)
 def restoration_cost(frame):
  return sum(v for k,v in frame['buckets'].items() if k.startswith(('pk_prod_copy','pk_prod_zero_patch','pk_prod_sparse_restore')))
 reset_comparison={}
 for label in ('baseline_G2','candidate_G3'):
  frames=[f for p in reset_profiles.values() for f in p[label]['profile']['reset_frames']]
  later=[f for f in frames if f['generation']>1]
  reset_comparison[label]=dict(later_restoration_cycles_min=min(map(restoration_cost,later)),later_restoration_cycles_max=max(map(restoration_cost,later)),later_reset_ISR_max_cycles=max(f['cycles'] for f in later),all_reset_ISR_max_cycles=max(f['cycles'] for f in frames))
 assert reset_comparison['candidate_G3']['later_restoration_cycles_max']<reset_comparison['baseline_G2']['later_restoration_cycles_min']
 assert reset_comparison['candidate_G3']['later_reset_ISR_max_cycles']<reset_comparison['baseline_G2']['later_reset_ISR_max_cycles']
 profile=load(W/'cf-profile/PROFILE.json');inputs(profile['result'])
 assert profile['source_image_sha256']==sha(image) and profile['source_elf_sha256']==sha(elf)
 assert not any(profile['result']['errors'].values())
 assert profile['profile']['sum_cycles']==profile['result']['safety']['full_ISR_sum_cycles']
 assert profile['profile']['top'][0]['cycles']==profile['result']['full_ISR']['max_cycles']
 retained=load(ROOT/'modules/perky/hybrid/NOISE_HAT_HANDOFF.json')
 assert retained['status']=='PASS_SWITCH_REGRESSION_FIXED_MODEL_SCOPE' and retained['build']['main_sha256']==sha(baseline/'probe/mainos_PKNHF7.bin')
 floor=ROOT/'out/perky/hybrid/production-g3-make-check.log';refhash=ROOT/'out/perky/hybrid/production-g3-refhash.log'
 assert 'module gates (shared isolated, perky-machine): 84 run, 0 failed' in floor.read_text() and 'module gates (image): 4 run, 0 failed' in floor.read_text()
 assert 'ALL 24 CASES BIT-IDENTICAL' in refhash.read_text()
 assert sha(ROOT/'out/mainos_bus.bin')=='354bdac8f2fe79696b3156a034894b1bd0d5f757ce76657ca608851089268a58'
 files=[Path(__file__),ROOT/'tools/perky/build_noise_hat_production_probe.py',ROOT/'tools/verify/build_perky_noise_hat_production_observer.py',ROOT/'tools/verify/qualify_perky_noise_hat_production.py',ROOT/'tools/verify/measure_perky_noise_hat_production.py',ROOT/'tools/verify/verify_perky_noise_hat_production_selection.py',ROOT/'tools/verify/verify_perky_noise_hat_production_persistence.py',ROOT/'tools/verify/profile_perky_noise_hat_production.py',ROOT/'tools/harness/perky_cf/production_lifecycle.h',ROOT/'tools/harness/perky_cf/production_lifecycle_observer.h',ROOT/'tools/harness/perky_cf/production_stream_oracle.c',ROOT/'tools/harness/perky_cf/production_handoff_engine.c',ROOT/'tools/harness/perky_cf/production_handoff_shadow.h',ROOT/'tools/perky/perky_noise_hat_production.py',ROOT/'modules/perky/production_copy.s',ROOT/'tools/verify/verify_perky_noise_hat_production_dsp.py',ROOT/'tools/verify/verify_perky_production_dsp_registers.py',ROOT/'tools/verify/verify_perky_production_copy.py',ROOT/'tools/verify/qualify_perky_noise_hat_production_switching.py',ROOT/'modules/perky/production_sparse.s',ROOT/'modules/perky/production_publish.s',ROOT/'modules/perky/production_resample.s',ROOT/'tools/harness/perky_cf/production_sparse.h',ROOT/'tools/harness/perky_cf/production_reset_profile.h',ROOT/'tools/verify/profile_perky_production_resets.py',ROOT/'tools/verify/verify_perky_production_sparse.py',ROOT/'tools/verify/verify_perky_production_transport.py']
 result=dict(schema='perky-production-lifecycle-v1',status='PASS_PRODUCTION_RESET_EXACT_AUDIO_AND_TIMING_MODEL_SCOPE',hardware_validated=False,build=build,observer=observer,selection=selection,persistence=persistence,persistence_reload=dict(stream=reload_stream,synthesis=reload_synthesis,ISR_cycles=reload_stack['full_ISR_max_cycles'],deadline_misses=reload_stack['ISR_duration_misses']),cases=cases,rows=rows,profile=profile,retained_F7=dict(image_sha256=retained['build']['main_sha256'],cases={n:r['full_ISR'] for n,r in retained['cases'].items()},rows=[r['full_ISR'] for r in retained['rows']],report_sha256=sha(ROOT/'modules/perky/hybrid/NOISE_HAT_HANDOFF.json')),deadline_us=16e6/44100,validation=dict(shared_gates=84,image_gates=4,identity_cases=24,floor_log_sha256=sha(floor),refhash_log_sha256=sha(refhash)),source_sha256={str(p.relative_to(ROOT)):sha(p) for p in files},limits=['Local instruction/cycle model qualification for WT/WT + Slap + Noise Hat across both CF and DSP-A ownership; no physical qualification or flash.',
 'V4 Noise Tone remains selectable/persisted but is excluded from audio admission because its source dispatch is not integrated into the resident Hat path.',
 'Exactness covers one independent original Hat stream, including initializer resets and old-epoch feedback checks, and the original Slap renderer at every actual native entry. Full-project post-FX bit identity and other family combinations are not asserted.',
 'Persistence uses real T2 ALGO/MODE encoder edits, stock SAVE PROJECT, and cold reload; fine detent response and power-loss atomicity are unqualified.'])
 result.update(dsp_gate=dsp_gate,register_gate=registers,copy_gate=copy,switching=switching,sparse_gate=sparse,transport_gate=transport,reset_profiles=reset_profiles,
  failed_G1=dict(report_sha256=sha(baseline.parent/'noise-hat-production-g1/source/modules/perky/hybrid/PRODUCTION_LIFECYCLE.json'),profile=load(baseline.parent/'noise-hat-production-g1/cf-profile/PROFILE.json')['result']['full_ISR']))
 streams=[*[r['lifecycle'] for r in cases.values()],switching['lifecycle'],*[r['stream_exact'] for r in rows],reload_stream]
 synthesis=[*[r['synthesis'] for r in cases.values()],switching['synthesis'],*[r['synthesis'] for r in rows],reload_synthesis]
 result['totals']=dict(exact_Hat_source_frames=sum(r['CF_frames']+r['DSP_frames'] for r in streams),
  exact_Slap_native_samples=sum(r['Slap_native_samples'] for r in synthesis),
  backend_transitions=cases['dsp']['lifecycle']['ownership_transitions']+switching['lifecycle']['ownership_transitions'],
  maximum_full_ISR_cycles=max([r['full_ISR']['max_cycles'] for r in [*cases.values(),switching,*rows,profile['result']]]+[reload_stack['full_ISR_max_cycles']]))
 result['totals']['minimum_deadline_reserve_us']=16e6/44100-result['totals']['maximum_full_ISR_cycles']/264
 old_max=g2_report['totals']['maximum_full_ISR_cycles']
 assert result['totals']['maximum_full_ISR_cycles']<old_max
 old_reserve=16e6/44100-old_max/264
 result['optimization']=dict(reset_costs=reset_comparison,baseline_G2_maximum_full_ISR_cycles=old_max,baseline_G2_minimum_deadline_reserve_us=old_reserve,reserve_ratio=result['totals']['minimum_deadline_reserve_us']/old_reserve,baseline_G2_report_sha256=sha(g2/'source-g2/modules/perky/hybrid/PRODUCTION_LIFECYCLE.json'),same_image_profile_timing_invariance=True,complete_DSP_uploads_identical_to_G2=True)

 # Raw drivers retain diagnostic-base scope notes. State the production witness
 # scope in the bound receipt, preserving those original notes for auditing.
 for r in result['cases'].values():
  r['driver_scope_notes']=r.pop('limits',[])
  r['limits']=['Production six-control selectors and Bank/Part generations; original witness resets from its own initializer, checks each late feedback sample, and commits ring writes only within their generation.','Backend enable is a probe switch. No physical hardware qualification.']

 dest=ROOT/'modules/perky/hybrid/PRODUCTION_LIFECYCLE.json';dest.write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps(dict(status=result['status'],persistence=persistence['status'],cases={k:dict(ISR=v['full_ISR'],errors={n:x for n,x in v['errors'].items() if x}) for k,v in cases.items()},rows=[r['full_ISR'] for r in rows]),indent=2))
if __name__=='__main__':main()

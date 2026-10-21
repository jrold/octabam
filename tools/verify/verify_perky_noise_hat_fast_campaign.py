#!/usr/bin/env python3
"""Bind CF bottleneck profiles, exact controls, and the optimized nine-row run."""
import hashlib,json,re,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];WORK=ROOT/'out/perky/hybrid/noise-hat-fast'
OLD=ROOT/'out/perky/hybrid/noise-hat-taps';PROFILE=ROOT/'out/perky/hybrid/noise-hat-taps-profile';FASTPROFILE=ROOT/'out/perky/hybrid/noise-hat-fast-profile'
DEST=ROOT/'modules/perky/hybrid/NOISE_HAT_CONTROLS.json'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def validate_profile(work,scenario,expected):
 d=work/'integrated-results'/(scenario+'-static');r=read(d/'cycles.json');row=read(d/('FAST_ROW.json' if work==FASTPROFILE else 'TAPS_ROW.json'))
 assert r['frames']==r['returns']==row['full_ISR']['frames']
 assert r['worst']['cycles']==row['full_ISR']['max_cycles']==expected['max_cycles']
 assert len(r['misses'])==row['full_ISR']['deadline_misses']==expected['deadline_misses']
 assert sum(r['aggregate'].values())==r['sum_cycles']==read(d/'stack.json')['full_ISR_sum_cycles']
 for f in [r['worst'],*r['misses']]:assert sum(f['buckets'].values())==f['cycles']
 assert row['exact'] and all(row['exact'][k]==0 for k in ('source_PCM_mismatches','state_mismatches','feedback_mismatches','clock_mismatches','ring_mismatches'))
 assert sha(d/'cycles.json')==row['outputs']['cycles.json']
 return dict(profile=r,raw_row_sha256=sha(d/('FAST_ROW.json' if work==FASTPROFILE else 'TAPS_ROW.json')),observer_binary_sha256=row['inputs'][str(work/'observer/ot_emu_safety')],image_sha256=row['inputs'][next(p for p in row['inputs'] if p.endswith('.bin') and '/probe/mainos_' in p)])
def main():
 build=read(WORK/'BUILD.json');image=WORK/'probe/mainos_PKNHE1.bin';elf=WORK/'probe/platform/runtime.elf'
 assert sha(image)==build['main_sha256'] and sha(elf)==build['runtime_sha256']
 assert all(sha(ROOT/p)==h for p,h in build['source_sha256'].items())
 assert build['DSP_uploads_identical_to_PKNHD1']
 for tag in ('A','B'):assert (WORK/f'dsp-{tag}.upload.bin').read_bytes()==(OLD/f'dsp-{tag}.upload.bin').read_bytes()
 controls=read(WORK/'CONTROLS_GATE.json');assert controls['status']=='PASS_RAW_CONTROLS_PCM_STATE_RING_RNG' and controls['control_calls']==2880 and len(controls['cases'])==15 and controls['native_samples']==24525
 assert all(sha(ROOT/p)==h for p,h in controls['source_sha256'].items())
 cached=read(OLD/'PERSISTENT_GATE.json');assert cached['frames']==720 and cached['arithmetic_vectors']==2560
 assert all(sha(ROOT/p)==h for p,h in cached['source_sha256'].items())
 observer=read(WORK/'observer/OBSERVER_BUILD.json')
 assert observer['binary_sha256']==sha(WORK/'observer/ot_emu_safety') and observer['complete_oracle_sha256']==sha(WORK/'observer/resident-oracle.dylib')
 assert observer['control_extension_sha256']==sha(ROOT/'tools/harness/perky_cf/noise_hat_controls_observer.h')
 assert observer['control_oracle_source_sha256']==sha(ROOT/'tools/harness/perky_cf/noise_hat_controls_oracle.c')
 summaries=[]
 for kind,name in (('optimized','INTEGRATED.json'),('unbatched','OLD_CONTROL.json'),('full_CF','CF_CONTROL.json')):
  rows=read(WORK/name)['rows'];assert {r['panel_mode'] for r in rows}=={1,2,3}
  for row in rows:
   assert row['status']=='FUNCTIONAL_MODEL_ROW' and row['requested_frames']==4096
   assert row['driver_sha256']==sha(ROOT/'tools/verify/measure_perky_noise_hat_fast.py')
   assert row['program_ownership'].startswith('all loaded private/shared P exact')
   d=WORK/'integrated-results'/(row['scenario']+'-static')
   for n in ('port.log','stack.json','private.json',*[k+'.bin' for k in row['transport_counts']]):assert sha(d/n)==row['outputs'][n]
   for p,h in row['inputs'].items():
    if not p.endswith('/card.img'):assert sha(p)==h,p
   stack=read(d/'stack.json');private=read(d/'private.json')
   assert stack['frames']==stack['frame_returns']==row['full_ISR']['frames']
   assert stack['DMA_active_restarts']==stack['DMA_read_write_overlaps']==stack['guard_writes_after_dispatch']==0
   assert private['ownership_register_frame_or_mask_violations']==private['fence_writes']==0
   assert all(int(v)==0 for v in re.findall(r'(\d+) not in time',(d/'port.log').read_text()))
   assert not row['audio_failures'] and len(row['source_and_post_FX'])==8 and row['playback_card_reads']>0
   assert all(a['source_significant']>64 and a['post_FX_significant']>64 for a in row['source_and_post_FX'].values())
   t=row['transport_counts'];assert t['pk_nhr_failures']==0 and t['pk_nhf_enabled']==(kind=='optimized')
   assert (t['pk_nhf_batches']>0)==(kind=='optimized')
   if kind!='full_CF':
    e=row['exact'];c=row['control_exact']
    assert e==read(d/'exact.json') and c==read(d/'exact.json.controls.json')
    for n in ('exact.json','exact.json.controls.json'):assert sha(d/n)==row['outputs'][n]
    assert all(e[k]==0 for k in ('source_PCM_mismatches','state_mismatches','feedback_mismatches','clock_mismatches','ring_mismatches'))
    assert c['calls']==t['pk_nhr_sequence'] and c['mismatches']==0
    assert e['source_frames']==t['pk_nhr_sequence']-2 and e['feedback_frames']==t['pk_nhr_consumed']==t['pk_nhr_sequence']-3
    assert t['pk_nhr_dma_reads']==t['pk_nhr_dma_done']==t['pk_nhr_sequence']-1
    assert t['pk_nhr_lag_min']==t['pk_nhr_lag_max']==2 and row['added_latency_OT_samples']==0
    assert row['native_samples'][3]==e['native_samples'] and t['pk_nht_pending_max']<573
   else:assert all(t[n]==0 for n in t if n not in ('pk_nhr_lag_min',))
   summaries.append(dict(kind=kind,panel_mode=row['panel_mode'],full_ISR=row['full_ISR'],control_exact=row['control_exact'],exact=row['exact'],transport_counts=t,
    private_stack_peak_bytes=row['private_stack_peak_bytes'],audio=row['source_and_post_FX'],playback_card_reads=row['playback_card_reads'],raw_row_sha256=sha(d/'FAST_ROW.json')))
 old=read(ROOT/'modules/perky/hybrid/NOISE_HAT_TAPS.json');profiles=[]
 for panel in (1,2):
  previous=next(r for r in old['rows'] if not r['reference'] and r['panel_mode']==panel)
  p=validate_profile(PROFILE,f'WTWT-SLAP-HAT-TAPS-DSP-M{panel}',previous['full_ISR'])
  assert p['image_sha256']==old['image_sha256'];profiles.append(p)
 first=read(WORK/'smoke-256/FAST_ROW.json')
 after=validate_profile(FASTPROFILE,'WTWT-SLAP-HAT-FAST-OPT-M1',first['full_ISR'])
 assert after['image_sha256']==sha(image)
 check=WORK.parent/'noise-hat-fast-make-check.log';refhash=WORK.parent/'noise-hat-fast-refhash.log'
 assert '84 run, 0 failed' in check.read_text() and '4 run, 0 failed' in check.read_text()
 assert 'ALL 24 CASES BIT-IDENTICAL' in refhash.read_text()
 shipping='354bdac8f2fe79696b3156a034894b1bd0d5f757ce76657ca608851089268a58';assert sha(ROOT/'out/mainos_bus.bin')==shipping
 deadline=16e6/44100;assert all(r['full_ISR']['max_us']<=deadline and r['full_ISR']['deadline_misses']==0 for r in summaries if r['kind']=='optimized')
 sources=[Path(__file__),*[ROOT/p for p in ('modules/perky/cf_noise_hat_controls.h','tools/perky/build_noise_hat_fast_probe.py','tools/verify/verify_perky_noise_hat_controls.py',
  'tools/verify/build_perky_noise_hat_fast_observer.py','tools/verify/measure_perky_noise_hat_fast.py','tools/verify/profile_perky_noise_hat_taps.py','tools/harness/perky_cf/noise_hat_cycle_profile.h',
  'tools/harness/perky_cf/noise_hat_controls_oracle.c','tools/harness/perky_cf/noise_hat_controls_observer.h')]]
 result=dict(schema='perky-noise-hat-controls-v1',status='EXACT_CONTROL_BATCHING_MEETS_ALL_THREE_MODEL_DEADLINES',version='PKNHE1',build_number=19,hardware_validated=False,
  source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),source_checkpoint_note='Checkpoint plus uncommitted source fingerprints; no release commit.',
  image_sha256=sha(image),runtime_sha256=sha(elf),build_receipt_sha256=sha(WORK/'BUILD.json'),DSP_uploads_identical_to_PKNHD1=True,memory=build['memory'],deadline_us=deadline,
  bottleneck_profiles=profiles,optimized_profile=after,control_gate=controls,cached_identical_DSP_gate_sha256=sha(OLD/'PERSISTENT_GATE.json'),rows=summaries,
  observer=observer,source_sha256={str(p.relative_to(ROOT)):sha(p) for p in sources},
  verification=dict(make_check='PASS: 84 shared, 4 image gates; project-specific gates skipped without OT_PROJECT',make_check_log_sha256=sha(check),
   refhash='PASS: all 24 configurations bit-identical to existing local baseline; baseline not re-saved',refhash_log_sha256=sha(refhash),shipping_bus_restored_sha256=shipping),
  limits=['Bounded local model workload; fixed WT/WT/Slap/Hat placement and three fixed Noise Hat modes.',
   'Same-image unbatched controls include changed CF outlining/layout; they are not the original PKNHD1 binary.',
   'No added source queue; unchanged stock scheduled DMA and original delay ring. STOP/Part/Bank, backend/mode migration, long sequence wrap and hardware timing remain unqualified.',
   'DSP scheduler remains 4532 instructions/sample; private-B tail and source/readback hooks remain hardware-unqualified.'])
 DEST.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(status=result['status'],rows=len(summaries),receipt=str(DEST)),indent=2))
if __name__=='__main__':main()

#!/usr/bin/env python3
"""Bind lifecycle findings and a fresh three-mode full-workload rerun."""
import json,re
from pathlib import Path
import measure_perky_cf_placement_integrated as c
ROOT=Path(__file__).resolve().parents[2];WORK=ROOT/'out/perky/hybrid/noise-hat-lifecycle'
DEST=ROOT/'modules/perky/hybrid/NOISE_HAT_LIFECYCLE.json'
def read(p):return json.loads(Path(p).read_text())
def main():
 image=WORK/'probe/mainos_PKNHE1.bin';elf=WORK/'probe/platform/runtime.elf';build=read(WORK.parent/'noise-hat-fast/BUILD.json')
 assert c.sha(image)==build['main_sha256'] and c.sha(elf)==build['runtime_sha256']
 assert all(c.sha(ROOT/p)==h for p,h in build['source_sha256'].items())
 observer=read(WORK/'observer/OBSERVER_BUILD.json')
 assert observer['binary_sha256']==c.sha(WORK/'observer/ot_emu_safety')
 assert observer['complete_oracle_sha256']==c.sha(WORK/'observer/resident-oracle.dylib')
 assert all(c.sha(ROOT/p)==h for p,h in observer['source_sha256'].items())
 ids=read(WORK/'WIRE_IDS.json');assert ids['vectors']==628 and ids['status']=='PASS_ACTUAL_COMPILED_OBSERVER_ID_EXTENSION'
 assert ids['generated_header_sha256']==observer['exact_observer_header_sha256']==c.sha(WORK/'lifecycle-observer.h')
 assert ids['source_sha256']==c.sha(WORK/'wire-ids.cpp') and ids['binary_sha256']==c.sha(WORK/'wire-ids')
 cases=[]
 for name in ('cf-calibration','panel','modes','backend'):
  d=WORK/name;r=read(d/'RESULT.json')
  archive=read(d/'INPUT_ARCHIVE.json')
  def resolve(p,h):
   path=Path(p)
   if path.is_file() and c.sha(path)==h:return path
   saved=Path(archive[str(path)]);assert c.sha(saved)==h,(path,'archived input drift');return saved
  for p,h in r['inputs'].items():
   if not p.endswith('/card.img'):resolve(p,h)
  receipt_path=next(p for p in r['inputs'] if p.endswith('/OBSERVER_BUILD.json'))
  actual_receipt=read(resolve(receipt_path,r['inputs'][receipt_path]))
  for p,h in actual_receipt['source_sha256'].items():resolve(str(ROOT/p),h)
  assert all(c.sha(d/p)==h for p,h in r['outputs'].items())
  assert r['exact']==read(d/'exact.json') and r['controls']==read(d/'exact.json.controls.json')
  assert r['lifecycle']==read(d/'exact.json.lifecycle.json')
  assert r['full_ISR']['max_us']==r['safety']['full_ISR_max_cycles']/264
  assert r['controls']['calls']>100 and r['controls']['mismatches']==0
  assert r['errors']['inactive_tracks']==0
  if name!='backend':assert r['status']=='PASS_MODEL_SCOPE' and not any(r['errors'].values())
  if name=='cf-calibration':
   assert r['lifecycle']['CF_native_calls']>100 and r['lifecycle']['CF_native_samples']>1000
   assert r['lifecycle']['CF_native_mismatches']==r['exact']['clock_mismatches']==0
   assert r['exact']['source_frames']==0
  if name=='panel':
   events=r['events'];assert len([e for e in events if e['label'].startswith('stop-')])==3
   assert len([e for e in events if e['label'].startswith('start-')])==3
   assert [e['part'] for e in events if e['label'].startswith('part-')]==[2,0]
   assert [e['playing_bank'] for e in events if e['label'].startswith('bank-')]==[1,0]
  if name=='modes':assert [e['mode'] for e in r['events'] if e['label'].startswith('mode-')]==[1,2,0,2,1,0]
  if name=='backend':assert r['lifecycle']['backend_transitions']==6 and r['lifecycle']['CF_native_calls']>100
  assert r['lifecycle']['dynamic_oracle_stopped_at_departure']==(name=='backend')
  if name=='backend':
   assert r['status']=='FAILED_QUALIFICATION' and r['errors']['transport_failures']==6
   assert all(v==0 for k,v in r['errors'].items() if k!='transport_failures')
  cases.append(dict(case=name,status=r['status'],errors=r['errors'],exact=r['exact'],controls=r['controls'],lifecycle=r['lifecycle'],
   full_ISR=r['full_ISR'],events=r['events'],audio=r['audio'],raw_sha256=c.sha(d/'RESULT.json'),input_archive_sha256=c.sha(d/'INPUT_ARCHIVE.json'),executed_instrument_receipt_sha256=r['inputs'][receipt_path]))
 rows=read(WORK/'rerun/INTEGRATED.json')['rows'];assert len(rows)==3
 for r in rows:
  d=WORK/'rerun/integrated-results'/(r['scenario']+'-static')
  assert r['status']=='FUNCTIONAL_MODEL_ROW' and r['requested_frames']==4096
  assert r['inputs'][str(WORK/'rerun/probe/mainos_PKNHE1.bin')]==c.sha(image)
  assert r['driver_sha256']==c.sha(ROOT/'tools/verify/measure_perky_noise_hat_fast.py')
  for p,h in r['inputs'].items():
   if not p.endswith('/card.img'):assert c.sha(Path(p))==h,p
  assert all(c.sha(d/n)==r['outputs'][n] for n in ('port.log','stack.json','private.json','exact.json','exact.json.controls.json'))
  assert not r['audio_failures'] and r['playback_card_reads']>0
  assert r['full_ISR']['deadline_misses']==0 and r['full_ISR']['max_us']<16e6/44100
  assert all(r['exact'][n]==0 for n in ('source_PCM_mismatches','state_mismatches','clock_mismatches','feedback_mismatches','ring_mismatches'))
  assert r['control_exact']['mismatches']==r['transport_counts']['pk_nhr_failures']==0
  assert r['program_ownership'].startswith('all loaded private/shared P exact')
  assert all(int(v)==0 for v in re.findall(r'(\d+) not in time',(d/'port.log').read_text()))
 check=WORK.parent/'noise-hat-lifecycle-make-check.log'
 assert '84 run, 0 failed' in check.read_text() and '4 run, 0 failed' in check.read_text()
 refhash=WORK.parent/'noise-hat-lifecycle-refhash.log';assert 'ALL 24 CASES BIT-IDENTICAL' in refhash.read_text()
 assert c.sha(ROOT/'out/mainos_bus.bin')=='354bdac8f2fe79696b3156a034894b1bd0d5f757ce76657ca608851089268a58'
 report=dict(schema='perky-noise-hat-lifecycle-campaign-v1',status='NOT_QUALIFIED_FOR_BACKEND_SWITCHING',hardware_validated=False,
  image_sha256=c.sha(image),runtime_sha256=c.sha(elf),observer_receipt_sha256=c.sha(WORK/'observer/OBSERVER_BUILD.json'),
  cases=cases,full_workload_rows=rows,checks=dict(make_check_sha256=c.sha(check),shared_gates=84,image_gates=4,refhash_cases=24,refhash_log_sha256=c.sha(refhash),wire_ID_gate_sha256=c.sha(WORK/'WIRE_IDS.json')),
  source_sha256={str(p.relative_to(ROOT)):c.sha(p) for p in (Path(__file__),ROOT/'tools/verify/qualify_perky_noise_hat_lifecycle.py',ROOT/'tools/verify/build_perky_noise_hat_lifecycle_observer.py',ROOT/'tools/verify/rerun_perky_noise_hat_lifecycle_workload.py',ROOT/'tools/verify/verify_perky_noise_hat_lifecycle_ids.py',ROOT/'tools/harness/perky_cf/noise_hat_lifecycle_observer.h')},
  limits=['Fixed diagnostic ALGO/MODE selectors: real Part/Bank key actions do not qualify product selector persistence or generation reset.',
   'Stock tracks/FX: retained program identity and active source/post-FX witnesses, not a stock-output bit-identity comparison across UI actions.',
   'No physical qualification, cache/card arbitration, long sequence-wrap, release wrapper or flash.'])
 DEST.write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(dict(status=report['status'],cases=[dict(case=r['case'],status=r['status'],errors=r['errors']) for r in cases],rows=[dict(mode=r['panel_mode'],ISR=r['full_ISR']) for r in rows]),indent=2))
if __name__=='__main__':main()

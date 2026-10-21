#!/usr/bin/env python3
"""Bind the complete local campaign to one final image and source snapshot."""
import hashlib,json,shutil,subprocess
from pathlib import Path
import measure_perky_full_map as f
ROOT=f.ROOT;W=f.W;DOC=ROOT/'modules/perky/hybrid'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def main():
 build=read(W/'BUILD.json');assert build['version']=='PKFM6'
 image=W/'probe/mainos_PKFM6.bin';elf=W/'probe/platform/runtime.elf';assert sha(image)==build['main_sha256'] and sha(elf)==build['runtime_sha256']
 for name,h in build['source_sha256'].items():assert sha(ROOT/name)==h,('build source drift',name)
 stage=read(W/'CF_STAGE_BUILD.json')
 for name,h in stage['result']['sources'].items():assert sha(ROOT/name)==h,('CF source drift',name)
 fixed=[W/'integrated-results'/f'FULL-WTWT-8-{algo}-M{mode}-static/FULL_ROW.json' for algo,mode in ((5,0),(5,1),(5,2),(3,1),(10,1))]
 paths=[W/p for p in ('SOURCE_GATE.json','MIXED_DSP_GATE.json','RNG_GATE.json','PRODUCTION_DSP_GATE.json','STOCK_FX_GATE.json','SELECTION.json','CARD_ASSET_GATE.json','CARD_RESET_GATE.json','REGISTER_GATE.json','WRAPPERS.json','SCENES.json','lifecycle/RESULT.json','persistence/RESULT.json','MATRIX.json','MODE_MATRIX.json','REPOSITORY_GATES.json','HANDOFF_PROJECT.json')]+fixed+[W/'integrated-results/HANDOFF-DEMO-static/FULL_ROW.json']
 reports={str(p.relative_to(W)):read(p) for p in paths}
 for name,r in reports.items():assert r['status'].startswith('PASS'),(name,r['status'])
 assert reports['MATRIX.json']['expected_tuples']==243 and reports['MODE_MATRIX.json']['expected_tuples']==324
 assert reports['SOURCE_GATE.json']['frames']==5355
 for name in ('MATRIX.json','MODE_MATRIX.json'):
  r=reports[name];assert not r['missing_tuples'] and f.exact(r['independent_source']) and r['full_ISR']['deadline_misses']==0
 for p in fixed:
  r=reports[str(p.relative_to(W))];assert r['requested_frames']==16384 and r['playback_card_reads']>0 and not r['audio_failures'] and f.exact(r['independent_source']) and len(r['card_assets_exact'])==3
  assert r['full_ISR']['deadline_misses']==0 and len(r['source_and_post_FX'])==8
 lifecycle=reports['lifecycle/RESULT.json'];assert f.exact(lifecycle['independent_source']) and lifecycle['full_ISR']['deadline_misses']==0
 assert any(e['label']=='fresh-CF-Hat-within-generation' for e in lifecycle['events'])
 assert lifecycle['events'][-1]['counts']['pk_nhb_switches']>=20 and lifecycle['independent_source']['mode_masks']==[7]*4
 # Reload is a new process. Its final safety output is not the save process's.
 reload=read(W/'persistence-stack.json');ownership=read(W/'persistence-private.json')
 assert reload['ISR_duration_misses']==reload['DMA_read_write_overlaps']==reload['guard_writes_after_dispatch']==ownership['ownership_register_frame_or_mask_violations']==ownership['fence_writes']==0
 assert f.exact(reports['persistence/RESULT.json']['independent_reload_source'])
 timing={name:r['full_ISR'] for name,r in reports.items() if 'full_ISR' in r}
 timing['persistence-cold-reload']=dict(frames=reload['frames'],max_cycles=reload['full_ISR_max_cycles'],max_us=reload['full_ISR_max_cycles']/264,deadline_misses=reload['ISR_duration_misses'])
 peak=max((r['max_cycles'],name) for name,r in timing.items());deadline=16e6/44100
 for name,r in timing.items():assert r['deadline_misses']==0,(name,r)
 memory=read(W/'MEMORY.json');assert memory['shared_words']==2220 and memory['shared_free']==184 and memory['private_P_used']=={'A':0,'B':0} and memory['A_private_X_words']==564 and memory['A_low_Y_words']==2093
 wrappers=reports['WRAPPERS.json'];assert wrappers['main_sha256']==sha(image)
 artifacts={k:v for k,v in wrappers['artifacts'].items() if k in ('main','card','midi')}
 for v in artifacts.values():assert sha(v['path'])==v['sha256']
 asset=build['asset_file'];assert sha(asset['path'])==asset['sha256'] and asset['bytes']==452124
 assert artifacts['card']['bytes']<=1048588
 # The loaded profiler-enable word, rather than the profile label, is evidence.
 symbols=f.c.private.symbols(elf);layout=read(W/'probe/platform/layout.json');raw=(W/'probe/platform/runtime.raw').read_bytes();at=symbols['pk_hybrid_profiler_enable']-layout['base'];assert int.from_bytes(raw[at:at+4],'big')==1
 profile=dict(version=build['version'],hybrid_source_id=stage['result']['hybrid_source_id'],main_sha256=sha(image),runtime_sha256=sha(elf),initial_profiler_enable=1,scope='PRF source fingerprint plus final wrapper hashes; no hardware acceptance implied')
 (W/'PROFILE_BUILD.json').write_text(json.dumps(profile,indent=2)+'\n')
 # Capture source dependencies without adding firmware/sample bytes to Git.
 sources=set(build['source_sha256'])|set(stage['result']['sources'])|set(stage['generated_sources'])
 for directory in ('modules/perky','tools/perky','tools/harness/perky_cf'):
  sources.update(str(p.relative_to(ROOT)) for p in (ROOT/directory).rglob('*') if p.is_file() and p.suffix in ('.c','.h','.s','.S','.py','.inc','.cpp','.asm'))
 sources.update(str(p.relative_to(ROOT)) for p in (ROOT/'tools/verify').glob('*perky_full_map*.py'))
 sources.update(str(p.relative_to(ROOT)) for p in (W/'probe/cf-generated').glob('*.s'))
 sources.add(str(Path(__file__).relative_to(ROOT)))
 snapshot=W/'source';snapshot.mkdir(exist_ok=True);hashes={}
 for name in sorted(sources):
  source=ROOT/name;assert source.is_file(),name;dest=snapshot/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest);hashes[name]=sha(source);assert sha(dest)==hashes[name]
 source_manifest=snapshot/'SOURCE.json';source_manifest.write_text(json.dumps(hashes,indent=2)+'\n')
 receipt_hashes={str(p):sha(p) for p in [W/'BUILD.json',W/'CF_STAGE_BUILD.json',W/'MEMORY.json',W/'PROFILE_BUILD.json',W/'observer/OBSERVER_BUILD.json',W/'persistence-stack.json',W/'persistence-private.json',source_manifest,*paths]}
 for p in (W/'REPOSITORY_GATES.json',):
  for cmd in read(p)['commands']:receipt_hashes[str(ROOT/cmd['log'])]=sha(ROOT/cmd['log'])
 result=dict(schema='perky-full-map-qualification-v1',status='PASS_LOCAL_FULL_MAP; MKII_ACCEPTANCE_PENDING',version=build['version'],source_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),branch=subprocess.check_output(['git','branch','--show-current'],text=True).strip(),source_tree_clean=False,hardware_flashed=False,physical_acceptance=False,artifacts=artifacts,asset_file=asset,memory=dict(shared_P_words=2220,shared_P_capacity=2404,shared_P_free=184,custom_private_P_words={'A':0,'B':0},A_private_X_words=564,A_private_X_capacity=616,A_low_Y_words=2093,A_low_Y_capacity=2139),placement={'T1':'CF: Fold1 / WT V1 / Simple','T2':'CF: Fold2 / WT V2 / Complex','T5':'CF: Resonant / Slap / Karplus','T6':'DSP-A: Noise Hat; CF: Noise/Tone / Acoustic Hats'},timing=timing,maximum=dict(case=peak[1],cycles=peak[0],microseconds=peak[0]/264,deadline_microseconds=deadline,observed_reserve_microseconds=deadline-peak[0]/264),coverage=dict(algorithm_layouts=81,layout_mode_tuples=243,additional_cartesian_mode_tuples=324,direct_source_frames=5355,mixed_DSP_frames=1224,sustained_frames_per_fixed_row=16384,lifecycle_frames=lifecycle['full_ISR']['frames'],backend_switches=lifecycle['events'][-1]['counts']['pk_nhb_switches'],old_generation_feedback_checked=lifecycle['independent_source']['old_generation_feedback_checked'],repository_floor='make check REMIX=perky-machine',refhash_configurations=24),receipts=receipt_hashes,source_snapshot=dict(path=str(snapshot),manifest_sha256=sha(source_manifest),files=len(hashes)),source_sha256=hashes,limits=['Local instruction/cycle model at CF264/PIT132; no physical WCET, cache/SDRAM/card/DMA contention or UI acceptance.','All 81 algorithm layouts with three rotated mode tuples; all 81 mode tuples on four specified demanding layouts. Not every Cartesian continuous-control/algorithm/mode combination.','Independent original source PCM/state/RNG/clocks and feedback; stock FX code/dispatch identity and active chains, not whole-project post-FX PCM identity across UI actions.','PK/2 projects; no automatic PK/1 migration. Exact Acoustic samples require /PERKYAH.DAT, loaded outside audio.','One final firmware candidate and consolidated hardware session. PERKY4S remains the hardware-confirmed release.'])
 (W/'QUALIFICATION.json').write_text(json.dumps(result,indent=2)+'\n')
 compact={k:v for k,v in result.items() if k not in ('source_sha256','receipts')};compact['receipt_sha256']={str(Path(p).relative_to(ROOT)):h for p,h in receipt_hashes.items()};compact['complete_local_receipt']=str(W/'QUALIFICATION.json')
 (DOC/'FULL_MAP_QUALIFICATION.json').write_text(json.dumps(compact,indent=2)+'\n')
 print(result['status'],result['maximum'],flush=True)
if __name__=='__main__':main()

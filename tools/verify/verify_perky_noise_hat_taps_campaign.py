#!/usr/bin/env python3
"""Bind current-source/feedback witnesses and six sustained native-clock rows."""
import hashlib,json,re,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];WORK=ROOT/'out/perky/hybrid/noise-hat-taps'
DEST=ROOT/'modules/perky/hybrid/NOISE_HAT_TAPS.json'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def main():
    build=read(WORK/'BUILD.json');image=WORK/'probe/mainos_PKNHD1.bin';elf=WORK/'probe/platform/runtime.elf'
    assert sha(image)==build['main_sha256'] and sha(elf)==build['runtime_sha256']
    assert all(sha(ROOT/p)==h for p,h in build['source_sha256'].items())
    gate=read(WORK/'PERSISTENT_GATE.json')
    assert gate['status']=='PASS_CURRENT_SOURCE_PCM_FEEDBACK_STATE_CLOCK' and len(gate['cases'])==9 and gate['frames']==720 and gate['arithmetic_vectors']==2560
    assert all(sha(ROOT/p)==h for p,h in gate['source_sha256'].items())
    observer=read(WORK/'observer/OBSERVER_BUILD.json')
    assert observer['binary_sha256']==sha(WORK/'observer/ot_emu_safety')
    assert observer['exact_observer_header_sha256']==sha(ROOT/'tools/harness/perky_cf/noise_hat_taps_observer.h')
    assert observer['complete_oracle_sha256']==sha(WORK/'observer/resident-oracle.dylib')
    summaries=[]
    for reference,name in ((False,'INTEGRATED.json'),(True,'CONTROL.json')):
        rows=read(WORK/name)['rows'];assert {r['panel_mode'] for r in rows}=={1,2,3}
        for row in rows:
            assert row['reference']==reference and row['status']=='FUNCTIONAL_MODEL_ROW' and row['requested_frames']==4096
            assert row['driver_sha256']==sha(ROOT/'tools/verify/measure_perky_noise_hat_taps.py')
            assert row['program_ownership'].startswith('all loaded private/shared P exact')
            directory=WORK/'integrated-results'/(row['scenario']+'-static')
            for filename in ('port.log','stack.json','private.json',*[n+'.bin' for n in row['transport_counts']]):
                assert sha(directory/filename)==row['outputs'][filename],filename
            for path,h in row['inputs'].items():
                if path.endswith('/card.img'):continue
                assert sha(path)==h,path
            stack=read(directory/'stack.json');private=read(directory/'private.json')
            assert stack['frames']==stack['frame_returns']==row['full_ISR']['frames']
            assert stack['DMA_active_restarts']==stack['DMA_read_write_overlaps']==stack['guard_writes_after_dispatch']==0
            assert private['ownership_register_frame_or_mask_violations']==private['fence_writes']==0
            assert all(int(x)==0 for x in re.findall(r'(\d+) not in time',(directory/'port.log').read_text()))
            assert len(row['source_and_post_FX'])==8 and not row['audio_failures'] and row['playback_card_reads']>0
            for audio in row['source_and_post_FX'].values():assert audio['source_significant']>64 and audio['post_FX_significant']>64
            t=row['transport_counts'];assert t['pk_nhr_failures']==0
            if not reference:
                e=row['exact'];assert e==read(directory/'exact.json')
                assert sha(directory/'exact.json')==row['outputs']['exact.json']
                assert all(e[k]==0 for k in ('source_PCM_mismatches','state_mismatches','feedback_mismatches','clock_mismatches','ring_mismatches'))
                assert e['source_frames']==t['pk_nhr_sequence']-2
                assert e['feedback_frames']==t['pk_nhr_consumed']==t['pk_nhr_sequence']-3
                assert t['pk_nhr_dma_reads']==t['pk_nhr_dma_done']==t['pk_nhr_sequence']-1
                assert row['native_samples'][3]==e['native_samples']
                assert t['pk_nhr_lag_min']==t['pk_nhr_lag_max']==2
                assert row['added_latency_OT_samples']==0 and row['feedback_latency_frames']==3
                assert 0<=t['pk_nht_pending_max']<573
                assert e['source_significant']>64 and 'DSP controls/taps' in row['source_and_post_FX']['T6']['source_kind']
                assert e['ring_frames']==(e['feedback_frames'] if row['panel_mode']!=3 else 0)
            else:assert all(t[n]==0 for n in t if n!='pk_nhr_lag_min')
            summaries.append(dict(reference=reference,panel_mode=row['panel_mode'],firmware_mode=row['firmware_mode'],full_ISR=row['full_ISR'],private_stack_peak_bytes=row['private_stack_peak_bytes'],
                native_samples=row['native_samples'],CF_frame_calls=row['CF_frame_calls'],transport_counts=t,exact=row['exact'],audio=row['source_and_post_FX'],playback_card_reads=row['playback_card_reads'],
                image_sha256=build['main_sha256'],runtime_sha256=build['runtime_sha256'],raw_row_sha256=sha(directory/'TAPS_ROW.json'),added_latency_OT_samples=row['added_latency_OT_samples']))
    checklog=WORK.parent/'noise-hat-taps-make-check.log';refhashlog=WORK.parent/'noise-hat-taps-refhash.log'
    assert '84 run, 0 failed' in checklog.read_text() and '4 run, 0 failed' in checklog.read_text()
    assert 'ALL 24 CASES BIT-IDENTICAL' in refhashlog.read_text()
    shipping='354bdac8f2fe79696b3156a034894b1bd0d5f757ce76657ca608851089268a58'
    assert sha(ROOT/'out/mainos_bus.bin')==shipping
    deadline=16e6/44100
    admitted=all(r['full_ISR']['max_us']<=deadline and not r['full_ISR']['deadline_misses'] for r in summaries if not r['reference'])
    sources=[Path(__file__),*[(ROOT/p) for p in (
        'modules/perky/cf_noise_hat_taps.c','modules/perky/noise_hat_taps_ring.h','tools/perky/perky_noise_hat_taps.py','tools/perky/build_noise_hat_taps_probe.py',
        'tools/harness/perky_cf/noise_hat_taps_engine.c','tools/harness/perky_cf/noise_hat_taps_host.cpp','tools/harness/perky_cf/noise_hat_taps_observer.h',
        'tools/verify/verify_perky_noise_hat_taps.py','tools/verify/measure_perky_noise_hat_taps.py','tools/verify/build_perky_noise_hat_taps_observer.py',
        'tools/perky/perky_noise_hat_resident.py','tools/perky/perky_noise_hat_offload.py','tools/perky/source_clock.py',
        'tools/harness/perky_cf/noise_hat_resident_oracle.c','modules/perky/cf_noise_hat.c','modules/perky/cf_noise_hat_offload.c',
        'tools/perky/build_cf_placement_probe.py','tools/verify/verify_perky_noise_hat_resident_boot.py')]]
    receipt=dict(schema='perky-noise-hat-taps-v1',status='FUNCTIONAL_CURRENT_FRAME_PROTOTYPE_'+('MEETS_MODEL_DEADLINE' if admitted else 'NOT_TIMING_QUALIFIED'),
        source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),source_checkpoint_note='Checkpoint plus uncommitted source fingerprints; no release commit.',
        hardware_validated=False,image_sha256=sha(image),runtime_sha256=sha(elf),version='PKNHD1',build_number=18,build_receipt_sha256=sha(WORK/'BUILD.json'),memory=build['memory'],
        transport=dict(evolving_state_round_trip_words=0,additional_host_commands=0,additional_DMA_words=0,feedback_mailbox_words=24,added_source_queue_latency_OT_samples=0,
            feedback_latency_frames=3,CF_new_SR_writes=0,CF_new_poll_loops=0,source_record_capacity_halfwords=168,conservative_maximum_packet_halfwords=154,
            minimum_delay_tap_native_samples=573,pending_guard='pending < 573; actual production function boundary-tested',
            ownership='A: original synthesis histories, delay arithmetic and exact native resampling. CF: original controls and 4805-sample ring.',
            latency_proof='Current sequence-tagged source PCM checked before AMP against current CF control event; delayed returns carry ring writes only.'),
        deadline_us=deadline,rows=summaries,persistent_gate=gate,observer=observer,
        verification=dict(make_check='PASS: 84 shared and 4 image gates; project-specific gate skipped',make_check_log_sha256=sha(checklog),
            refhash='PASS: 24 local-baseline configurations bit-identical; baseline not re-saved',refhash_log_sha256=sha(refhashlog),shipping_bus_restored_sha256=shipping),
        source_sha256={str(p.relative_to(ROOT)):sha(p) for p in sources},
        limits=['Fixed Noise Hat V4; STOP/Part/Bank, mode/backend transitions and long sequence-wrap runs are unqualified.',
            'Private-B upper tail, new source/readback hooks and physical timing are unqualified.',
            'DSP scheduler is 4532 instructions/sample, not cycle-accurate hardware; no flash wrapper or hardware release.',
            'Zero additional source queue is relative to the stock DMA schedule; physical input-to-DAC latency is not measured.'])
    DEST.write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(dict(status=receipt['status'],deadline_us=deadline,rows=len(summaries),current_source_frames=sum((r['exact'] or {}).get('source_frames',0) for r in summaries),receipt=str(DEST)),indent=2))
if __name__=='__main__':main()

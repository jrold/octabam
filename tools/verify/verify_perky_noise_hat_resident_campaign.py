#!/usr/bin/env python3
"""Validate bound resident campaign artifacts and emit a compact source receipt.

Timing failures remain findings. A successful validator exit means the
functional evidence is coherent; status explicitly refuses timing admission.
"""
import hashlib,json,re,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
WORK=ROOT/'out/perky/hybrid/noise-hat-resident'
FULL=ROOT/'out/perky/hybrid/noise-hat-resident-full'
DEST=ROOT/'modules/perky/hybrid/NOISE_HAT_RESIDENT.json'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def main():
    build=read(WORK/'BUILD.json');image=WORK/'probe/mainos_PKNHC1.bin';elf=WORK/'probe/platform/runtime.elf'
    assert sha(image)==build['main_sha256'] and sha(elf)==build['runtime_sha256']
    gates=read(WORK/'PERSISTENT_GATE.json');assert gates['status'].startswith('PASS') and len(gates['cases'])==9 and gates['native_samples']==2304
    assert all(sha(ROOT/p)==h for p,h in gates['source_sha256'].items())
    full=read(FULL/'FULL_GATE.json');assert full['status']=='PASS_COMPLETE_DELAYED_SOURCE_PCM' and len(full['rows'])==3
    assert all(r['source_PCM_mismatches']==r['clock_mismatches']==0 and r['checked_frames']>0 for r in full['rows'])
    summaries=[]
    for reference,name in ((False,'INTEGRATED.json'),(True,'CONTROL.json')):
        rows=read(WORK/name)['rows'];assert {r['panel_mode'] for r in rows}=={1,2,3}
        for row in rows:
            assert row['status']=='FUNCTIONAL_MODEL_ROW' and row['requested_frames']==4096
            assert row['program_ownership'].startswith('all loaded private/shared P exact')
            directory=WORK/'integrated-results'/(row['scenario']+'-static')
            # Bind the surviving raw witnesses. Large staged cards/blocks are
            # intentionally removed by the runner after their hashes are saved.
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
                e=row['exact'];assert e['pcm_mismatches']==e['state_mismatches']==0
                assert e==read(directory/'exact.json')
                assert t['pk_nhr_sequence']-t['pk_nhr_consumed']==3
                assert t['pk_nhr_dma_reads']==t['pk_nhr_dma_done']==t['pk_nhr_sequence']-1
                assert e['checked_frames']==t['pk_nhr_consumed'] and e['state_frames']==t['pk_nhr_sequence']-2
                assert 0<e['pending_native']<=60
                assert row['native_samples'][3]==e['native_samples']-e['pending_native']
                assert t['pk_nhr_lag_min']==t['pk_nhr_lag_max']==2 and row['added_latency_OT_samples']==48
            else:assert all(t[n]==0 for n in t if n not in ('pk_nhr_lag_min',))
            summaries.append(dict(reference=reference,panel_mode=row['panel_mode'],firmware_mode=row['firmware_mode'],
                full_ISR=row['full_ISR'],private_stack_peak_bytes=row['private_stack_peak_bytes'],
                native_samples=row['native_samples'],CF_frame_calls=row['CF_frame_calls'],transport_counts=t,
                exact={k:v for k,v in (row['exact'] or {}).items() if k!='source_seen'},
                audio=row['source_and_post_FX'],playback_card_reads=row['playback_card_reads'],
                image_sha256=build['main_sha256'],runtime_sha256=build['runtime_sha256'],raw_row_sha256=sha(directory/'RESIDENT_ROW.json'),
                executing_driver_sha256=row['driver_sha256'],added_latency_OT_samples=row['added_latency_OT_samples']))
    checklog=WORK.parent/'noise-hat-resident-make-check.log';refhashlog=WORK.parent/'noise-hat-resident-refhash.log'
    assert '84 run, 0 failed' in checklog.read_text() and '4 run, 0 failed' in checklog.read_text()
    assert 'ALL 24 CASES BIT-IDENTICAL' in refhashlog.read_text()
    shipping='354bdac8f2fe79696b3156a034894b1bd0d5f757ce76657ca608851089268a58'
    assert sha(ROOT/'out/mainos_bus.bin')==shipping
    deadline=16e6/44100
    assert all(r['full_ISR']['max_us']>deadline for r in summaries if not r['reference'])
    sources=[Path(__file__),*[(ROOT/p) for p in (
        'modules/perky/cf_noise_hat_resident.c','tools/perky/perky_noise_hat_resident.py','tools/perky/build_noise_hat_resident_probe.py',
        'tools/harness/perky_cf/noise_hat_resident_engine.c','tools/harness/perky_cf/noise_hat_resident_host.cpp',
        'tools/harness/perky_cf/noise_hat_resident_oracle.c','tools/harness/perky_cf/noise_hat_resident_observer.h',
        'tools/harness/perky_cf/noise_hat_resident_full_observer.h','tools/verify/verify_perky_noise_hat_resident.py',
        'tools/verify/verify_perky_noise_hat_resident_boot.py','tools/verify/measure_perky_noise_hat_resident.py',
        'tools/verify/build_perky_noise_hat_resident_observer.py','tools/verify/build_perky_noise_hat_resident_full_observer.py',
        'tools/verify/verify_perky_noise_hat_resident_full.py')]]
    receipt=dict(schema='perky-noise-hat-resident-v1',status='FUNCTIONAL_RESIDENT_PROTOTYPE_NOT_TIMING_QUALIFIED',
        source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        source_checkpoint_note='Checkpoint plus the uncommitted source fingerprints; no release commit.',hardware_validated=False,
        image_sha256=sha(image),runtime_sha256=sha(elf),version='PKNHC1',build_number=17,
        build_receipt_sha256=sha(WORK/'BUILD.json'),memory=build['memory'],
        transport=dict(evolving_state_round_trip_words=0,additional_host_commands=0,additional_DMA_words=0,
            native_return_payload_words=24,added_latency_OT_samples=48,added_latency_ms=48/44.1,
            CF_new_SR_writes=0,CF_new_poll_loops=0,source_record_capacity_halfwords=168,source_PCM_halfwords=80,
            control_padding_capacity_halfwords=88,calculated_maximum_live_command_halfwords=52,
            ownership='DSP-A classic/pulse histories and white hold/RNG; CF original controls, ring and native clock.',
            return_path='Low padding bytes of existing DSP-A post-FX readback; extracted and cleared in stock transfer state zero.'),
        deadline_us=deadline,rows=summaries,persistent_ARM_gate=gates,complete_source_gate=full,
        primary_observer=read(WORK/'observer/OBSERVER_BUILD.json'),full_source_observer=read(FULL/'observer/OBSERVER_BUILD.json'),
        rejected_smoke=read(WORK/'REJECTED_SMOKE.json'),
        verification=dict(make_check='PASS: 84 shared and 4 image gates; project-specific gate skipped',make_check_log_sha256=sha(checklog),
            refhash='PASS: 24 local-baseline configurations bit-identical; baseline not re-saved',refhash_log_sha256=sha(refhashlog),
            shipping_bus_restored_sha256=shipping),
        source_sha256={str(p.relative_to(ROOT)):sha(p) for p in sources},
        limits=['All three observed ISR maxima exceed the 362.812 us deadline; no full voice-layout admission.',
            '48 samples of added source latency; AMP/FX event alignment is not equivalent to the original path.',
            'Diagnostic 16-bit sequence ownership does not handle wrap; do not run beyond the bounded test window.',
            'Noise Hat fixed on V4; switching to another V4 algorithm/backend is unsupported in this prototype.',
            'STOP/Part/Bank lifecycle, mode transitions, private-B upper guard and physical timing remain unqualified.',
            'DSP integrated scheduler is 4532 instructions/sample, not cycle-accurate hardware.',
            'The earlier attribution of rejected marker traffic to a bank-handshake failure is retracted.'])
    DEST.write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(dict(status=receipt['status'],deadline_us=deadline,rows=len(summaries),full_source_frames=sum(r['checked_frames'] for r in full['rows']),receipt=str(DEST)),indent=2))
if __name__=='__main__':main()

#!/usr/bin/env python3
"""Measure unchanged stock STATIC/FLEX beside zero, one or two CF voices.

Emulation exercises stock code and actual card reads; it cannot qualify physical
CompactFlash latency, DMA arbitration, cache behavior or hardware UI response.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

import verify_perky_hybrid_workload as workload
import verify_perky_hybrid_private_stack as private

SCENARIOS = {
    'A': ((), (2, 3, 6)),
    'B': ((1,), (2, 3, 6)),
    'C': ((1, 5), ()),
    'D': ((1, 5), (2,)),
    'E': ((1, 5), (2, 3)),
    'F': ((1, 5), (2, 3, 6)),
    'G': ((1, 5), (2, 3, 6, 7)),
    'B6': ((5,), (2, 3, 6)),
    'B5': ((1,), (2, 3, 5, 6, 7)),
    'B65': ((5,), (1, 2, 3, 6, 7)),
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--image', type=Path, required=True)
    ap.add_argument('--work', type=Path, required=True)
    ap.add_argument('--frames', type=int, default=4096)
    ap.add_argument('--scenario', choices=SCENARIOS, action='append')
    ap.add_argument('--kind', choices=('static', 'flex'), action='append')
    ap.add_argument('--pair', action='append', help='T2/T6; default snare/bass')
    ap.add_argument('--audio', action='store_true')
    ap.add_argument('--observer', type=Path, help='Existing private-stack ot_emu_safety; records complete executed ISR and ownership')
    ap.add_argument('--legacy-startup-clock', action='store_true', help='Calibration only: preserve the older startup clock scope')
    args = ap.parse_args()
    if args.frames < 2048:
        ap.error('at least 2048 frames required to cover activation')
    pairs = [tuple(p.split('/')) for p in (args.pair or ['snare/bass'])]
    if any(len(p) != 2 or any(k not in workload.CF_SPEC for k in p) for p in pairs):
        ap.error('unknown algorithm pair')
    image, work = args.image.resolve(), args.work.resolve()
    if args.observer:
        workload.EMU=args.observer.resolve()
    work.mkdir(parents=True, exist_ok=True)
    elf = image.parent/'platform/runtime.elf'
    inputs = [image, elf, workload.EMU, Path(__file__).resolve(), Path(workload.__file__)]
    if args.observer:
        receipt=workload.EMU.parent/'OBSERVER_BUILD.json'
        build=private.read(receipt)
        assert sha(workload.EMU)==build['binary_sha256'], 'observer binary drift'
        inputs.append(receipt)
    audio_emu=workload.ROOT/'out/emu/ot_emu'
    if args.audio:
        inputs.append(audio_emu)
    hashes = {str(p): sha(p) for p in inputs}
    report = dict(schema='octabam.perky.stock-workload.v1', status='RUNNING',
                  git_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
                  inputs=hashes, rows=[], frames=args.frames,
                  limits=['ATA model serves reads immediately and advertises PIO only; physical card stalls and DMA contention are unmodeled.',
                          'Timer window excludes ISR entry-save/footer; ACK work includes intervening stock tasks.',
                          'UI snapshot publications do not measure input latency or prove physical responsiveness.',
                          'Short rows establish exercised behavior only; no hardware-safe voice count is inferred.'])
    path = work/'STOCK_MATRIX.json'

    def save():
        path.write_text(json.dumps(report, indent=2)+'\n')

    save()
    baseline = json.loads((workload.ROOT/'modules/perky/hybrid/BASELINE.json').read_text())
    syms = workload.load_elf_symbols(elf)
    tone = work/'HYB_SAMPLER_440.wav'
    workload.make_tone(tone)
    try:
        for kind in args.kind or ['static', 'flex']:
            for scenario in args.scenario or list('ABCDEFG')+['B6']:
                cf, stock = SCENARIOS[scenario]
                for left, right in pairs:
                    name = f'{kind}-{scenario}-{left}-{right}'
                    row = dict(name=name, scenario=scenario, kind=kind, pair=[left, right],
                               cf_tracks=list(cf), stock_tracks=list(stock), status='RUNNING')
                    report['rows'].append(row)
                    save()
                    try:
                        if args.observer:
                            env=private.environment(image.parent.parent,'stock-'+name)
                            env['HYBRID_SAFETY_REPORT']=str(work/name/'executed-stack.json')
                            env['HYBRID_PRIVATE_REPORT']=str(work/name/'private-stack.json')
                            os.environ.update(env)
                        result = workload.run_integrated_row(
                            name, left, right, image_path=image, syms=syms,
                            project_src=Path(baseline['project']['root']), work_dir=work/name,
                            tone_path=tone, frames=args.frames, verify_block_audio=args.audio,
                            sampler_kind=kind, cf_tracks=cf, sampler_tracks=stock,
                            clock_before_transport=not args.legacy_startup_clock,
                            audio_emu=audio_emu)
                        prof = result['dtim3_profiler']
                        expected_mask = sum(1 << t for t in (0, 4, *cf))
                        assert int(prof['active_voice_mask'], 16) == expected_mask, 'unexpected active PERKY mask'
                        assert all((v > 0) == (track in cf) for track, v in zip((1, 5), prof['dtim3_ticks']['inst_calls'])), 'CF activation mismatch'
                        if args.observer:
                            stack_path,private_path=work/name/'executed-stack.json',work/name/'private-stack.json'
                            stack,own=private.read(stack_path),private.read(private_path)
                            observed=stack['frames']
                            assert observed==stack['frame_returns']==own['switched']==own['restored']==prof['frame_count']==result['ot_emu']['cf_ack_interval']['frames_sampled']
                            assert observed>=args.frames, 'missing requested transport frames'
                            # Transport frame0 is established after startTransportLive;
                            # the IRQ/profiler/ACK counters also include startup frames.
                            terminal=own['in_flight_at_capture_end']
                            assert terminal in (0,1)
                            assert own['saved_A7_writes']==own['switched']+terminal
                            assert own['terminal_saved_store_before_private']==terminal
                            assert stack['DMA_read_write_overlaps']==stack['guard_writes_after_dispatch']==0
                            assert own['ownership_register_frame_or_mask_violations']==own['fence_writes']==0
                            assert not any(t['outside_extent'] for t in stack['stacks'])
                            assert own['private_observed_peak_bytes']<own['private_capacity_bytes']==4096
                            elapsed=stack['observed_ISR_elapsed_DTIM3']
                            assert elapsed['samples']==observed and elapsed['invalid_mode_samples']==0
                            assert sum(n for _,n in elapsed['histogram_ticks'])==observed
                            if not args.legacy_startup_clock:
                                assert prof['extension']['full_frame_window']
                                assert elapsed['max_ticks']>=prof['dtim3_ticks']['max_perky_service_ticks'], 'interior exceeds enclosing elapsed window'
                            result['executed_full_ISR']=dict(maximum_cycles=stack['full_ISR_max_cycles'],
                                maximum_us=stack['full_ISR_max_cycles']/264,duration_misses=stack['ISR_duration_misses'],
                                mean_cycles=stack['full_ISR_sum_cycles']/observed,
                                requested_transport_frames=args.frames,total_completed_frames=observed,
                                startup_frames=observed-args.frames,
                                terminal_uncompleted_saved_A7_prefix=terminal,
                                elapsed_timer=elapsed,
                                private_peak_bytes=own['private_observed_peak_bytes'],reports={str(p):sha(p) for p in (stack_path,private_path)})
                        row.update(status='LOCALLY_EXERCISED_SHORT_ROW', result=result)
                    except Exception as error:
                        row.update(status='LOCALLY_FAILING', error=str(error))
                    assert hashes == {str(p): sha(p) for p in inputs}, 'measurement input changed'
                    save()
                    print(json.dumps({k: row[k] for k in ('name', 'status')}), flush=True)
        report['status'] = 'COMPLETE_WITH_FAILURES' if any(r['status']=='LOCALLY_FAILING' for r in report['rows']) else 'PASS_EXERCISED_MATRIX'
    finally:
        save()


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Measure explicitly selected hybrid images with identical paired fixtures.

Uses the existing integrated sequencer/FX/sampler fixture and optional executed
ISR observer. No image rebuild, packaging, source substitution or hardware claim.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

import verify_perky_hybrid_workload as workload
import verify_perky_hybrid_private_stack as private

PAIRS = (
    ('snare', 'snare'), ('snare', 'bass'), ('bass', 'bass'),
    ('V1', 'V1'), ('V2', 'V2'), ('V1', 'V2'), ('V1', 'snare'),
    ('V2', 'bass'), ('third', 'snare'), ('third', 'third'),
    ('bass', 'snare'), ('snare', 'V1'), ('bass', 'V2'),
    ('snare', 'third'), ('V2', 'V1'),
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--image', type=Path, required=True)
    ap.add_argument('--work', type=Path, required=True)
    ap.add_argument('--frames', type=int, default=4096)
    ap.add_argument('--pair', action='append', help='T2/T6, e.g. snare/bass; default: all 15')
    ap.add_argument('--observer', type=Path, help='Existing private-stack ot_emu_safety')
    ap.add_argument('--audio', action='store_true', help='Also verify all eight tracks emit audio')
    ap.add_argument('--profiler-off', action='store_true')
    args = ap.parse_args()
    image, work = args.image.resolve(), args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    pairs = [tuple(p.split('/')) for p in args.pair] if args.pair else list(PAIRS)
    if args.frames < 2048:
        ap.error('at least 2048 frames required to cover voice activation')
    if any(len(p) != 2 or any(k not in workload.CF_SPEC for k in p) for p in pairs):
        ap.error('unknown pair')
    if args.observer:
        workload.EMU = args.observer.resolve()
    elf = image.parent / 'platform/runtime.elf'
    paths = [image, elf, workload.EMU, Path(__file__).resolve(),
             Path(workload.__file__), Path(private.__file__)]
    inputs = {str(p): sha(p) for p in paths}
    report = dict(schema='octabam.perky.campaign-matrix.v1', status='RUNNING',
                  git_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'],
                                                     cwd=workload.ROOT, text=True).strip(),
                  inputs=inputs, frames_per_row=args.frames, rows=[],
                  measurement='emulated ColdFire; not physical MKII timing',
                  limits=['Instruction/cycle model excludes physical cache, bus and DMA stalls.',
                          'Profiler DTIM3 window excludes entry-save/footer; executed observer is separate.',
                          'All retained FX remain present; this fixture uses its selected FX assignments.'])
    target = work / 'MATRIX.json'

    def save():
        target.write_text(json.dumps(report, indent=2) + '\n')

    save()
    baseline = json.loads((workload.ROOT / 'modules/perky/hybrid/BASELINE.json').read_text())
    syms = workload.load_elf_symbols(elf)
    tone = work / 'HYB_SAMPLER_440.wav'
    workload.make_tone(tone)
    try:
        for left, right in pairs:
            label = left + '_' + right
            if args.observer:
                # The observer reads paths and linked addresses at process start.
                os.environ.update(private.environment(image.parent.parent, 'campaign-' + label))
            row = workload.run_integrated_row(
                label, left, right, image_path=image, syms=syms,
                project_src=Path(baseline['project']['root']), work_dir=work / label,
                tone_path=tone, frames=args.frames, verify_block_audio=args.audio,
                profiler_enable=int(not args.profiler_off))
            if not args.profiler_off:
                prof = row['dtim3_profiler']
                assert prof['active_voice_mask'] == '0x33', 'four synthesis tracks not active'
                assert all(v > 0 for v in prof['dtim3_ticks']['inst_calls']), 'CF voice not executed'
            if args.observer:
                base = image.parent.parent / ('campaign-' + label)
                stack_path = base.with_name(base.name + '-stack.json')
                private_path = base.with_name(base.name + '-private.json')
                stack, own = private.read(stack_path), private.read(private_path)
                assert stack['frames'] == stack['frame_returns'] == own['switched'] == own['restored'] == args.frames
                assert stack['DMA_read_write_overlaps'] == stack['guard_writes_after_dispatch'] == 0
                assert own['ownership_register_frame_or_mask_violations'] == own['fence_writes'] == 0
                assert not any(t['outside_extent'] for t in stack['stacks'])
                assert own['private_observed_peak_bytes'] < own['private_capacity_bytes'] == 4096
                # A baseline may miss the deadline. Preserve that measurement.
                row['executed_full_ISR'] = dict(
                    maximum_cycles=stack['full_ISR_max_cycles'],
                    maximum_us=stack['full_ISR_max_cycles'] / 264,
                    duration_misses=stack['ISR_duration_misses'],
                    private_peak_bytes=own['private_observed_peak_bytes'],
                    reports={str(p): sha(p) for p in (stack_path, private_path)})
            assert inputs == {str(p): sha(p) for p in paths}, 'measurement input changed'
            report['rows'].append(row)
            save()
            print(json.dumps({'pair': left + '/' + right,
                              'full_ISR': row.get('executed_full_ISR'),
                              'timer_us': row['dtim3_profiler']['dtim3_us']}), flush=True)
        report['status'] = 'PASS_MEASURED_MATRIX'
    except Exception as error:
        report.update(status='FAIL', error=str(error))
        raise
    finally:
        save()


if __name__ == '__main__':
    main()

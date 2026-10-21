#!/usr/bin/env python3
"""Sustained four-voice Resonant Snare/Bass and sequenced MODE benchmarks.

Reuse the calibrated instrument and original source oracles. Change only the
project's T5 selection/MODE locks; preserve existing firmware and old receipts.
"""
import argparse
import json
import re
import shutil
from pathlib import Path

import measure_perky_state_handoff as state

calibration = state.calibration
budget = state.budget
ROOT = calibration.ROOT
V3 = {'slap-control': (8, 0, 'SlapControl'), 'snare': (4, 0, 'ResSnare'),
      'bass': (4, 1, 'ResBass'), 'alternate': (4, 0, 'ResSnareBassLocks')}
V4 = {'hat': (5, 1, 'MetallicHat'), 'noise-tone': (3, 1, 'NoiseTone')}


def trigger_steps(data, at):
    return [step for step in range(64) if data[at + 7 - step // 8] & (1 << (step % 8))]


def wanted_mode(kind, index):
    return index % 2 if kind == 'alternate' else V3[kind][1]


def project_stage(original, kind, build, configuration):
    """Patch after full.stage's original clearing of ALGO/MODE locks."""
    otp = calibration.integrated.workload.otp

    def stage(project, directory, sampler_kind, algos, modes, mask):
        previous = otp._bank_write
        local_algo = calibration.full.FAMILY[2].index(algos[2])

        def write(pdir, banknum, mutate, guard=True):
            def locked(data):
                mutate(data)
                for part in range(otp.NPARTS_ALL):
                    at = otp.PART_BASE + part * otp.PART_STRIDE + 9 + 48 + 30 * 4
                    data[at + 2] = local_algo
                    data[at + 5] = modes[2]
                for pattern in range(4):
                    tail = otp.PTRN0 + pattern * otp.PTRN_FSTRIDE + otp.PTRN_FSTRIDE - 11
                    data[tail + 2:tail + 4] = bytes((64, 2))  # 64 steps, 1X
                    at = otp.trac_off(pattern, 4)
                    for index, step in enumerate(trigger_steps(data, at)):
                        data[at + 0x59 + 32 * step + 2] = local_algo
                        data[at + 0x59 + 32 * step + 5] = wanted_mode(kind, index)
            return previous(pdir, banknum, locked, guard=guard)

        otp._bank_write = write
        try:
            card = original(project, directory, sampler_kind, algos, modes, mask)
        finally:
            otp._bank_write = previous
        # Inspect the actual final card, including all repeated FX/tempo writes.
        import emu_card
        files = emu_card.extract_image(card.read_bytes())
        banks = []
        for filename, data in sorted(files.items()):
            name = Path(filename).name.lower()
            if not re.fullmatch(r'bank\d+\.work', name):
                continue
            for part in range(otp.NPARTS_ALL):
                live = otp.PART_BASE + part * otp.PART_STRIDE + 9
                for voice, track in enumerate((0, 1, 4, 5)):
                    at = live + 48 + 30 * track
                    assert data[at + 2] == calibration.full.FAMILY[voice].index(algos[voice])
                    assert data[at + 5] == modes[voice]
                    assert data[live + 60 + 30 * track:live + 63 + 30 * track] == b'PK\x02'
            patterns = []
            for pattern in range(4):
                tail = otp.PTRN0 + pattern * otp.PTRN_FSTRIDE + otp.PTRN_FSTRIDE - 11
                assert data[tail + 2:tail + 4] == bytes((64, 2))
                at = otp.trac_off(pattern, 4)
                steps = trigger_steps(data, at)
                assert len(steps) >= 32
                sequence = []
                for index, step in enumerate(steps):
                    expected = wanted_mode(kind, index)
                    assert data[at + 0x59 + 32 * step + 2] == local_algo
                    assert data[at + 0x59 + 32 * step + 5] == expected
                    sequence.append(expected)
                if kind == 'alternate':
                    assert set(sequence) == {0, 1} and all(a != b for a, b in zip(sequence, sequence[1:]))
                patterns.append(dict(pattern=pattern, steps=steps, mode_sequence=sequence))
            banks.append(dict(path=filename, parts=otp.NPARTS_ALL, patterns=patterns))
        assert banks
        projects = [(name, data) for name, data in files.items() if Path(name).name.lower() == 'project.work']
        assert projects and all(b'TEMPOx24=2880' in data for _, data in projects)
        witness = dict(status='PASS_FINAL_CARD_RESONANT_SELECTION_AND_MODE_LOCKS',
                       image_sha256=build['main_sha256'], configuration=configuration,
                       card_sha256=calibration.sha(card), all_banks_parts_patterns_confirmed=True,
                       tempo_bpm=120, pattern_steps=64, pattern_scale='1X', banks=banks,
                       limits=['Sequence order is verified in final fixture bytes. The frozen runtime observer records mode/frame counts, not exact transition order or step numbers.'])
        calibration.save(directory / 'RESONANT_FIXTURE.json', witness)
        return card
    return stage


def actual_modes(row, kind, fourth):
    algo = V3[kind][0]
    allowed = {0, 1} if kind == 'alternate' else {V3[kind][1]}
    expected = {f'9:9:{algo}:{V4[fourth][0]}/1:2:{mode}:1' for mode in allowed}
    actual = row['exact_source']['combinations']
    assert set(actual) == expected, ('Actual selected source differs from fixture', actual, expected)
    assert all(frames > 1024 for frames in actual.values()), 'Inactive or trivial selected mode'
    assert row['exact_source']['algorithm_masks'] == [1 << 9, 1 << 9, 1 << algo, 1 << V4[fourth][0]]
    assert row['exact_source']['mode_masks'] == [1 << 1, 1 << 2, sum(1 << m for m in allowed), 1 << 1]
    assert all(value > 64 for value in row['exact_source']['source_significant'])
    return {str(mode): actual[f'9:9:{algo}:{V4[fourth][0]}/1:2:{mode}:1'] for mode in sorted(allowed)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--frames', type=int, default=32768)
    parser.add_argument('--v3', choices=V3, required=True)
    parser.add_argument('--voice4', choices=V4, required=True)
    args = parser.parse_args()
    assert args.frames >= 32768
    source, work = args.build.resolve(), args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    build = json.loads((source / 'BUILD.json').read_text())
    version = build['version']
    assert calibration.sha(source / 'probe' / f'mainos_{version}.bin') == build['main_sha256']
    frozen_path = ROOT / 'modules/perky/hybrid/EMULATOR_BUDGET.json'
    frozen = json.loads(frozen_path.read_text())
    observer = work / 'observer'
    if not observer.exists():
        observer.symlink_to(calibration.DEFAULT_WORK / 'observer', target_is_directory=True)
    assert calibration.sha(observer / 'ot_emu_safety') == frozen['observer_sha256']
    assert calibration.sha(source / 'observer/full-map-oracle.dylib') == calibration.sha(
        ROOT / 'out/perky/hybrid/full-map-release/observer/full-map-oracle.dylib')
    configuration = dict(version=version, role='candidate',
                         algos=[9, 9, V3[args.v3][0], V4[args.voice4][0]],
                         modes=[1, 2, V3[args.v3][1], 1], FX='all14',
                         v3_case=args.v3, voice4_case=args.voice4)
    name = f'{version}-WTWT-{V3[args.v3][2]}-{V4[args.voice4][2]}-all14'
    calibration.CURRENT = source
    calibration.PINNED[version] = build['main_sha256']
    calibration.cases = lambda: {name: configuration}
    original_stage = calibration.full.stage
    calibration.full.stage = project_stage(original_stage, args.v3, build, configuration)
    run, adapted = state.measurement_function()
    marker = 'Path(_calibration_source))}'
    assert adapted.count(marker) == 1
    adapted = adapted.replace(marker, 'Path(_calibration_source), Path(_resonant_driver))}', 1)
    namespace = dict(run.__globals__)
    namespace['_resonant_driver'] = str(Path(__file__).resolve())
    exec(compile(adapted, str(Path(__file__).resolve()), 'exec'), namespace)
    try:
        row = namespace['run'](work, name, args.frames)
    finally:
        calibration.full.stage = original_stage
    directory = work / name
    (directory / 'MEASUREMENT_ADAPTER.py').write_text(adapted)
    row['requested_transport_frames'] = args.frames
    assert row['clocks'] == frozen['clocks'] and row['observer_sha256'] == frozen['observer_sha256']
    assert row['exact_source']['feedback_frames'] > 0
    fixture_path = directory / 'RESONANT_FIXTURE.json'
    fixture = json.loads(fixture_path.read_text())
    assert fixture['card_sha256'] == row['inputs'][str(directory / 'card.img')]
    counts = actual_modes(row, args.v3, args.voice4)
    row['elf_sha256'] = build['runtime_sha256']
    row['resonant_workload'] = dict(v3_case=args.v3, voice4_case=args.voice4,
        driver_sha256=calibration.sha(Path(__file__)),
        adapted_function_sha256=calibration.sha(directory / 'MEASUREMENT_ADAPTER.py'),
        fixture=dict(path=str(fixture_path), sha256=calibration.sha(fixture_path),
                     status=fixture['status'], all_banks_parts_patterns_confirmed=True),
        actual_mode_frame_counts=counts,
        duration_seconds=args.frames * 16 / 44100,
        limits=['Actual source selection is witnessed independently; switching cadence is not inferred from aggregate combination counts.',
                'Same firmware, measuring binary, clocks and calibrated budget as PKFM17; new fixtures and longer matched Slap controls replace the prior missing Resonant screen.'])
    calibration.save(directory / 'ROW.json', row)
    assessment = budget.evaluate(row, frozen['budgets_us'])
    assessment.update(image_sha256=row['image_sha256'], observer_sha256=row['observer_sha256'],
                      budget_sha256=calibration.sha(frozen_path), row_sha256=calibration.sha(directory / 'ROW.json'),
                      admission='PHYSICAL_ACCEPTANCE_STILL_REQUIRED' if assessment['pass_budget'] else 'HOLD_FOR_PERFORMANCE_WORK')
    calibration.save(directory / 'BUDGET_ASSESSMENT.json', assessment)
    print(json.dumps(dict(case=name, steady_ISR=row['steady_ISR'], full_ISR=row['full_ISR'],
                         whole_CF_mean_us=budget.metric(row, 'whole_CPU_mean'),
                         actual_modes=counts, pass_budget=assessment['pass_budget']), indent=2), flush=True)
    # Only regenerable outputs are removed after their hashes/observations are saved.
    for filename in ('card.img', 'blocks.bin'):
        (directory / filename).unlink(missing_ok=True)
    for dirname in ('project', 'tree'):
        shutil.rmtree(directory / dirname, ignore_errors=True)


if __name__ == '__main__':
    main()

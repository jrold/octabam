#!/usr/bin/env python3
"""Measure on-demand DSP Hat state handoff with the frozen budget observer.

The old driver requires an active continuous CF shadow worker. This adapter
retains its instrument, clocks, stock/source witnesses and cycle accounting,
and replaces that obsolete assertion with actual source transport and native
call counters. No dummy worker completions or adjusted budget are accepted.
"""
import argparse
import inspect
import json
from pathlib import Path

import calibrate_perky_hybrid_budget as calibration
import qualify_perky_hybrid_budget as budget


COUNTERS = (
    'pk_nhb_inner_calls',
    'pk_nhb_snapshot_requests',
    'pk_nhb_snapshot_completed',
    'pk_nhb_snapshot_rejected',
    'pk_nhb_snapshot_words',
    'pk_nhb_replay_frames',
    'pk_nhb_handoff_jobs',
    'pk_nhr_sequence',
    'pk_nhr_consumed',
)


def measurement_function(*, allow_handoff=False):
    """Use the calibrated run body, asserting each deliberate adaptation."""
    original = inspect.getsource(calibration.run)
    source = original
    marker = "        active = set(range(8))"
    assert source.count(marker) == 1
    source = source.replace(marker, '''        for symbol in _handoff_counters:
            dumps.append((symbol, syms[symbol], 4))
''' + marker)
    marker = "        assert transport['pk_nhb_completed'] > 0"
    assert source.count(marker) == 1
    source = source.replace(marker, '''        assert transport['pk_nhr_sequence'] > 0
        assert transport['pk_nhr_consumed'] > 0
        assert transport['pk_nhb_completed'] <= transport['pk_nhb_produced']
        assert transport['pk_nhb_snapshot_completed'] <= transport['pk_nhb_snapshot_requests']
        if not _allow_handoff:
            assert transport['pk_nhb_inner_calls'] == 0, 'continuous CF Hat synthesis remains'
            assert transport['pk_nhb_replay_frames'] == 0
            assert transport['pk_nhb_handoff_jobs'] == 0
            assert transport['pk_nhb_snapshot_requests'] == 0
            assert transport['pk_nhb_snapshot_completed'] == 0
            assert transport['pk_nhb_snapshot_rejected'] == 0
            assert transport['pk_nhb_snapshot_words'] == 0
            assert transport['pk_nhb_produced'] == transport['pk_nhb_completed']
''')
    # Binding both files makes this exceptional adaptation reviewable. Using
    # this module's __file__ also puts the adapter in the ordinary INPUTS row.
    marker = "               Path(integrated.workload.__file__), Path(full.__file__))}"
    assert source.count(marker) == 1
    source = source.replace(marker, "               Path(integrated.workload.__file__), Path(full.__file__),\n"
                                  "               Path(_calibration_source))}")
    namespace = dict(vars(calibration))
    namespace.update(__file__=__file__, _handoff_counters=COUNTERS,
                     _allow_handoff=allow_handoff,
                     _calibration_source=calibration.__file__)
    exec(compile(source, str(Path(__file__).resolve()), 'exec'), namespace)
    return namespace['run'], source


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--frames', type=int, default=16384)
    parser.add_argument('--v4', type=int, choices=(5, 3, 10), default=5)
    parser.add_argument('--mode', type=int, choices=(0, 1, 2), default=1)
    parser.add_argument('--allow-handoff', action='store_true',
                        help='Permit real on-demand replay/snapshot jobs; not a steady no-shadow proof')
    parser.add_argument('--witness', type=Path,
                        help='Optional actual-image directed handoff proof, bound by hash for final qualification')
    args = parser.parse_args()
    source = args.build.resolve()
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    build = json.loads((source / 'BUILD.json').read_text())
    version = build['version']
    image = source / 'probe' / f'mainos_{version}.bin'
    assert calibration.sha(image) == build['main_sha256']
    symbols = calibration.integrated.private.symbols(source / 'probe/platform/runtime.elf')
    assert all(symbol in symbols for symbol in COUNTERS), 'missing real state-handoff counters'
    frozen_path = calibration.ROOT / 'modules/perky/hybrid/EMULATOR_BUDGET.json'
    frozen = json.loads(frozen_path.read_text())
    observer = work / 'observer'
    if not observer.exists():
        observer.symlink_to(calibration.DEFAULT_WORK / 'observer', target_is_directory=True)
    assert calibration.sha(observer / 'ot_emu_safety') == frozen['observer_sha256']
    oracle = source / 'observer'
    oracle.mkdir(exist_ok=True)
    reference = calibration.ROOT / 'out/perky/hybrid/full-map-release/observer/full-map-oracle.dylib'
    if not (oracle / reference.name).exists():
        (oracle / reference.name).symlink_to(reference)
    assert calibration.sha(oracle / reference.name) == calibration.sha(reference)
    calibration.CURRENT = source
    calibration.PINNED[version] = build['main_sha256']
    configuration = dict(version=version, role='candidate', algos=[9, 9, 8, args.v4],
                         modes=[1, 2, 0, args.mode], FX='all14')
    name = f'{version}-WTWT-Slap-{args.v4}-M{args.mode}-all14'
    calibration.cases = lambda: {name: configuration}
    run, adapted_source = measurement_function(allow_handoff=args.allow_handoff)
    row = run(work, name, args.frames)
    directory = work / name
    (directory / 'MEASUREMENT_ADAPTER.py').write_text(adapted_source)
    row['requested_transport_frames'] = args.frames
    assert row['clocks'] == frozen['clocks'] and row['observer_sha256'] == frozen['observer_sha256']
    assert row['exact_source']['feedback_frames'] > 0
    witness = None
    if args.witness:
        proof_path = args.witness.resolve()
        proof = json.loads(proof_path.read_text())
        assert proof['image_sha256'] == row['image_sha256']
        assert proof['status'].startswith('PASS_'), 'directed handoff proof did not pass'
        witness = dict(path=str(proof_path), sha256=calibration.sha(proof_path), status=proof['status'])
    row['state_handoff'] = dict(
        status='MEASURED_ON_DEMAND_HANDOFF' if args.allow_handoff else 'MEASURED_NO_DUPLICATE_CF_HAT_WORK',
        counters={key: row['transport'][key] for key in COUNTERS},
        directed_witness=witness,
        driver_sha256=calibration.sha(Path(__file__)),
        calibration_driver_sha256=calibration.sha(Path(calibration.__file__)),
        adapted_function_sha256=calibration.sha(directory / 'MEASUREMENT_ADAPTER.py'),
        limits=['Counters are actual target observations; the directed handoff proof must positively calibrate native-call counting.',
                'A zero steady replay count proves no duplicate work for this observed workload, not all possible control histories.',
                'The fixed measuring binary and budget are unchanged. Directed handoff and lifecycle qualification remain separate.'])
    calibration.save(directory / 'ROW.json', row)
    assessment = budget.evaluate(row, frozen['budgets_us'])
    assessment.update(image_sha256=row['image_sha256'],
                      observer_sha256=row['observer_sha256'],
                      budget_sha256=calibration.sha(frozen_path),
                      row_sha256=calibration.sha(directory / 'ROW.json'),
                      admission='PHYSICAL_ACCEPTANCE_STILL_REQUIRED' if assessment['pass_budget'] else 'HOLD_FOR_PERFORMANCE_WORK',
                      state_handoff=row['state_handoff'])
    calibration.save(directory / 'BUDGET_ASSESSMENT.json', assessment)
    print(json.dumps(assessment, indent=2))


if __name__ == '__main__':
    main()

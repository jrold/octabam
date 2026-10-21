#!/usr/bin/env python3
"""Bind the CF optimization campaign to its image and frozen budget.

Functional/model-deadline passes never substitute for the calibrated budget.
Exits 1 and saves a HOLD receipt when any measured budget ceiling is exceeded.
"""
import argparse
import json
from pathlib import Path

import calibrate_perky_hybrid_budget as c
import qualify_perky_hybrid_budget as budget


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build', type=Path, required=True)
    p.add_argument('--output', type=Path, default=c.ROOT / 'modules/perky/hybrid/CF_BUDGET_OPTIMIZATION.json')
    a = p.parse_args()
    w = a.build.resolve()
    build = json.loads((w / 'BUILD.json').read_text())
    version = build['version']
    image = w / 'probe' / f'mainos_{version}.bin'
    elf = w / 'probe/platform/runtime.elf'
    assert c.sha(image) == build['main_sha256']
    assert c.sha(elf) == build['runtime_sha256']
    for filename, expected in build['source_sha256'].items():
        target = Path(filename)
        if not target.is_absolute():
            target = c.ROOT / target
        assert c.sha(target) == expected, ('build source drift', filename)
    frozen_path = c.ROOT / 'modules/perky/hybrid/EMULATOR_BUDGET.json'
    frozen = json.loads(frozen_path.read_text())
    dsp_identity = {}
    for core in ('A', 'B'):
        upload = w / f'dsp-{core}.upload.bin'
        baseline_upload = c.ROOT / 'out/perky/hybrid/full-map-release' / upload.name
        assert upload.read_bytes() == baseline_upload.read_bytes()
        dsp_identity[core] = dict(identical_to_PKFM6=True, sha256=c.sha(upload))
    checks = []
    receipts = {}
    for v4, mode in ((5, 0), (5, 1), (5, 2), (3, 1), (10, 1)):
        name = f'{version}-WTWT-Slap-{v4}-M{mode}-all14'
        path = w / 'measurement' / name / 'ROW.json'
        row = json.loads(path.read_text())
        cmd = json.loads((path.parent / 'INPUTS.json').read_text())['command']
        row['requested_transport_frames'] = int(cmd[cmd.index('--frames') + 1])
        assert row['requested_transport_frames'] == 16384 and row['frames'] >= 16384
        assert row['image_sha256'] == build['main_sha256']
        assert row['observer_sha256'] == frozen['observer_sha256']
        assert row['clocks'] == frozen['clocks']
        assert row['full_ISR']['modeled_misses'] == 0
        assert row['playback_card_read_commands'] > 0 and c.full.exact(row['exact_source'])
        assert row['transport']['pk_nhb_completed'] > 0
        for key in ('pk_nhr_failures', 'pk_nhb_overflows', 'pk_nhb_clock_errors'):
            assert row['transport'][key] == 0
        for filename, expected in row['inputs'].items():
            # Disposable card/dumps were hashed and removed by the measurement.
            target = Path(filename)
            if target.is_file():
                assert c.sha(target) == expected, filename
        check = budget.evaluate(row, frozen['budgets_us'])
        before_path = c.DEFAULT_WORK / 'replay' / f'F6-WTWT-Slap-{v4}-M{mode}-all14' / 'ROW.json'
        before = json.loads(before_path.read_text())
        before['requested_transport_frames'] = 16384
        check['baseline_PKFM6_us'] = {m: budget.metric(before, m) for m in budget.METRICS}
        check['change_us'] = {m: budget.metric(row, m) - budget.metric(before, m) for m in budget.METRICS}
        check['receipt'] = str(path)
        checks.append(check)
        receipts[str(path)] = c.sha(path)
    expected_status = {
        'SOURCE_GATE.json': 'PASS_ACTUAL_IMAGE_ALL_LAYOUT_SOURCE_PCM_STATE_SHARED_RNG',
        'TAP_GATE.json': 'PASS_ALL_RING_CURSORS_PACKET_AND_CARRY',
        'FILTER_GATE.json': 'PASS_ORIGINAL_WRAP_CLAMP_FILTER',
        'STOCK_FX_GATE.json': 'PASS_ALL_FOURTEEN_FX_CODE_BOTH_DISPATCHES_STOCK_DATA_AND_B_SOURCE',
        'MATRIX.json': 'PASS_FULL_MAP_PRODUCTION_MATRIX_MODEL_SCOPE',
        'lifecycle/RESULT.json': 'PASS_FULL_MAP_LIFECYCLE_MODEL_SCOPE',
        'SCENES.json': 'PASS_FULL_MAP_SCENE_FADER_MODEL_SCOPE',
    }
    functional = {}
    interactive_ISR = {}
    for name, status in expected_status.items():
        path = w / name
        result = json.loads(path.read_text())
        assert result['status'] == status, (path, result['status'])
        if 'image_sha256' in result:
            assert result['image_sha256'] == build['main_sha256']
        if 'elf_sha256' in result:
            assert result['elf_sha256'] == build['runtime_sha256']
        for filename, expected in result.get('inputs', {}).items():
            target = Path(filename)
            if target == image:
                assert expected == build['main_sha256']
            if target.is_file():
                assert c.sha(target) == expected, filename
        functional[name] = dict(status=status, frames=result.get('frames', result.get('full_ISR', {}).get('frames')),
                                receipt=str(path), receipt_sha256=c.sha(path))
        if 'safety' in result:
            steady = c.histogram_stats(result['safety']['budget_cycles']['steady_histogram'])
            values = dict(steady_ISR_mean=steady['mean_us'], steady_ISR_p99=steady['p99_us'],
                          steady_ISR_p99_9=steady['p99_9_us'], full_ISR_peak=result['full_ISR']['max_us'])
            interactive_ISR[name] = {key: dict(measured_us=value, budget_us=frozen['budgets_us'][key],
                                                pass_budget=value <= frozen['budgets_us'][key])
                                     for key, value in values.items()}
        receipts[str(path)] = c.sha(path)
    profile_path = w / 'profile/PROFILE.json'
    profile = json.loads(profile_path.read_text())
    assert profile['status'] == 'PASS_UNCHANGED_AUDIO_AND_CYCLES'
    assert profile['row']['image_sha256'] == build['main_sha256']
    control = Path(profile['control_receipt'])
    assert profile['control_sha256'] == c.sha(control)
    for key in ('full_ISR', 'comparison_dumps', 'whole_CPU', 'stock_audio'):
        assert profile['row'][key] == json.loads(control.read_text())[key]
    receipts[str(profile_path)] = c.sha(profile_path)
    floor = {}
    for name, marker in (('full-map-budget-default-check.log', 'all runnable checks passed'),
                         ('full-map-budget-refhash.log', 'ALL 24 CASES BIT-IDENTICAL')):
        path = w.parent / name
        assert marker in path.read_text()
        floor[name] = dict(receipt=str(path), sha256=c.sha(path),
                          skipped=[line.strip() for line in path.read_text().splitlines() if '[SKIP]' in line])
    passed = (all(check['pass_budget'] for check in checks)
              and all(check['pass_budget'] for row in interactive_ISR.values() for check in row.values()))
    result = dict(schema='octabam.perky.cf-budget-optimization.v1',
                  status='PASS_FROZEN_BUDGET_MODEL_SCOPE' if passed else 'FAIL_FROZEN_BUDGET',
                  admission='PHYSICAL_ACCEPTANCE_STILL_REQUIRED' if passed else 'HOLD_FOR_PERFORMANCE_WORK',
                  hardware_validated=False, version=version,
                  main_sha256=build['main_sha256'], runtime_sha256=build['runtime_sha256'],
                  clocks=frozen['clocks'], observer_sha256=frozen['observer_sha256'],
                  DSP_uploads=dsp_identity,
                  budget_path=str(frozen_path), budget_sha256=c.sha(frozen_path),
                  assessments=checks, interactive_ISR_assessments=interactive_ISR,
                  functional=functional, receipts=receipts,
                  controlled_profile=dict(receipt=str(profile_path), receipt_sha256=c.sha(profile_path),
                                          per_frame_us=profile['per_frame_us']),
                  default_build_checks=floor,
                  build_receipt_sha256=c.sha(w / 'BUILD.json'),
                  source_snapshot_manifest_sha256=c.sha(w / 'SOURCE_SNAPSHOT.json'),
                  source_sha256={str(Path(__file__).relative_to(c.ROOT)): c.sha(Path(__file__))},
                  limits=[
                      'Same native clocks and fixed measuring binary as calibration; budget was not changed.',
                      'All fourteen stock FX and all eight track outputs active in workload rows; source state/PCM/shared RNG checked against independent originals.',
                      'Model correctness and nominal deadline passes are separate from the calibrated performance gate.',
                      'Seven ceilings assessed on sustained rows; interactive lifecycle/matrix/scenes additionally assess the four ISR ceilings. Whole-CPU ACK statistics were not captured for interactive runs.',
                      'The working-envelope budget is an engineering target, not a measured physical safe threshold.',
                      'No physical flash or performance qualification; no new release or handoff bundle.'])
    a.output.write_text(json.dumps(result, indent=2) + '\n')
    print(result['status'], result['admission'])
    raise SystemExit(0 if passed else 1)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Bind exact CF optimization proofs, complete workloads and the fixed budget.

The unchanged state-handoff campaign remains the correctness/admission floor.
This report additionally requires this task's default-build checks, original
kernel proofs, actual-linked proofs, and matched PKFM15 performance deltas.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import qualify_hat_state_campaign as handoff

ROOT = handoff.ROOT
BASELINE = ROOT / 'out/perky/hybrid/full-map-state-v4'
REQUIRED_LINKED = {'resample', 'stock_position', 'transport_taps', 'linked_synthesis'}


def read(path):
    return json.loads(Path(path).read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--output', type=Path,
                        default=ROOT / 'modules/perky/hybrid/CF_SYNTHESIS_QUALIFICATION.json')
    args = parser.parse_args()
    work = args.build.resolve()
    build = read(work / 'BUILD.json')
    bound_path = work / 'STATE_HANDOFF_CAMPAIGN.json'
    pending_path = work / 'STATE_HANDOFF_CAMPAIGN.pending.json'
    pending_path.unlink(missing_ok=True)
    result = subprocess.run([sys.executable, str(ROOT / 'tools/verify/qualify_hat_state_campaign.py'),
                             '--build', str(work), '--output', str(pending_path)])
    assert result.returncode in (0, 1), ('State handoff campaign failed', result.returncode)
    assert pending_path.is_file(), 'State handoff validation failed before writing a fresh report'
    campaign = read(pending_path)
    assert (result.returncode == 0) == campaign['status'].startswith('PASS_')
    pending_path.replace(bound_path)
    floor = {}
    for name, marker in (('full-map-synthesis-default-check.log', 'all runnable checks passed'),
                         ('full-map-synthesis-refhash.log', 'ALL 24 CASES BIT-IDENTICAL')):
        path = work.parent / name
        text = path.read_text()
        assert marker in text, ('Current repository check absent', path)
        floor[name] = dict(receipt=str(path), sha256=handoff.c.sha(path),
                          skipped=[line.strip() for line in text.splitlines() if '[SKIP]' in line])
    floor_path = work.parent / 'full-map-synthesis-floors.json'
    floor_summary = read(floor_path)
    assert floor_summary['status'] == 'PASS_CLEAN_LOCAL_FLOORS_AND_DEFAULT_IMAGE_RESTORE'
    assert all(code == 0 for code in floor_summary['exits'].values())
    handoff.check_hashes(floor_summary['logs'], required=True)
    assert handoff.c.sha(ROOT / floor_summary['image']) == floor_summary['image_sha256']
    proof_index = work / 'OPTIMIZATION_PROOFS.json'
    proofs = read(proof_index)
    assert proofs['image_sha256'] == build['main_sha256']
    assert proofs['elf_sha256'] == build['runtime_sha256']
    checked = {}
    for name, item in proofs['proofs'].items():
        path = Path(item['path'])
        proof = read(path)
        assert proof['status'].startswith('PASS_'), (name, proof['status'])
        assert item['sha256'] == handoff.c.sha(path), ('Proof changed after indexing', name)
        handoff.check_hashes(proof.get('source_sha256', {}), required=True)
        handoff.check_hashes(proof.get('input_sha256', {}), required=True)
        handoff.check_hashes(proof.get('inputs', {}))
        if name in REQUIRED_LINKED or item.get('linked_candidate'):
            assert proof.get('image_sha256', proof.get('base_image_sha256')) == build['main_sha256'], (name, 'Different linked image')
            if 'elf_sha256' in proof:
                assert proof['elf_sha256'] == build['runtime_sha256']
        if name == 'resample':
            assert proof['linked_candidate'] is True
        if name == 'stock_position':
            assert proof['actual_linked_symbols'] is True
        if name == 'transport_taps':
            assert proof['actual_linked_symbol'] is True
        if name == 'linked_synthesis':
            assert proof['status'] == 'PASS_ACTUAL_LINKED_KERNEL_NATIVE_PCM_FULLSTATE_RNG_HOLD'
        if name == 'profile_final':
            assert proof['status'] == 'PASS_UNCHANGED_AUDIO_STATE_AND_CYCLES'
            assert proof['row']['image_sha256'] == build['main_sha256']
            assert proof['control_sha256'] == handoff.c.sha(Path(proof['control_receipt']))
        if name == 'packet_serializer':
            assert any(binding['image_sha256'] == build['main_sha256'] and
                       binding['elf_sha256'] == build['runtime_sha256'] for binding in proof['bindings'])
            assert proof['Hat_actual_image_cases'] >= 540 and proof['Hat_overcapacity_rows'] > 0
            assert proof['external_CF_cases'] >= 252 and proof['external_checked_fallback_rows'] > 0
        checked[name] = dict(item, status=proof['status'])
    assert {'WT', 'NT', 'AH', 'Slap', 'controls', 'resample', 'stock_position', 'transport_taps',
            'linked_synthesis', 'profile_final'} <= set(checked)
    if build.get('packet_reservation_candidate'):
        assert 'packet_serializer' in checked
    baseline_build = read(BASELINE / 'BUILD.json')
    changes = []
    for v4, mode in ((5, 0), (5, 1), (5, 2), (3, 1), (10, 1)):
        path = work / 'measurement' / f'{build["version"]}-WTWT-Slap-{v4}-M{mode}-all14/ROW.json'
        before_path = BASELINE / 'measurement' / f'PKFM15-WTWT-Slap-{v4}-M{mode}-all14/ROW.json'
        row, before = read(path), read(before_path)
        assert before['image_sha256'] == baseline_build['main_sha256']
        assert row['observer_sha256'] == before['observer_sha256']
        assert row['clocks'] == before['clocks']
        assert handoff.requested_frames(before_path) == handoff.requested_frames(path) == 16384
        old = {key: handoff.budget.metric(before, key) for key in handoff.budget.METRICS}
        new = {key: handoff.budget.metric(row, key) for key in handoff.budget.METRICS}
        assert new['steady_ISR_mean'] < old['steady_ISR_mean'], ('Mean ISR regression', row['case'])
        assert new['whole_CPU_mean'] < old['whole_CPU_mean'], ('Mean total CF regression', row['case'])
        changes.append(dict(case=row['case'], baseline_receipt=str(before_path),
                            baseline_sha256=handoff.c.sha(before_path), before_us=old, after_us=new,
                            change_us={key: new[key] - old[key] for key in old},
                            reduction_percent={key: 100 * (old[key] - new[key]) / old[key] for key in old}))
    campaign.update(schema='octabam.perky.cf-synthesis-optimization.v1',
                    optimization_baseline=dict(version='PKFM15', image_sha256=baseline_build['main_sha256'],
                                               build_receipt_sha256=handoff.c.sha(BASELINE / 'BUILD.json')),
                    synthesis_options=build['synthesis_options'],
                    packet_reservation_candidate=build.get('packet_reservation_candidate', False),
                    optimization_proofs=checked,
                    changes_from_PKFM15=changes,
                    default_image_restore=dict(receipt=str(floor_path), sha256=handoff.c.sha(floor_path),
                                               image_sha256=floor_summary['image_sha256']),
                    earlier_default_checks=campaign['default_build_checks'], default_build_checks=floor)
    campaign['receipts'].update({str(bound_path): handoff.c.sha(bound_path),
                                str(proof_index): handoff.c.sha(proof_index)})
    campaign['source_sha256'][str(Path(__file__).relative_to(ROOT))] = handoff.c.sha(Path(__file__))
    campaign['limits'] += [
        'Each retained optimization is checked independently and through the final actual-image source/workload/lifecycle gates.',
        'Stock ColdFire changes are guarded exact sample-position/loop transformations; generic paths and original audio arithmetic remain.',
        'The PKFM15 comparison uses the same frozen native clocks, measuring binary, workloads and frame counts. Isolated benchmark gains are not added to predict integrated timing.']
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(campaign, indent=2) + '\n')
    print(campaign['status'], campaign['admission'])
    raise SystemExit(0 if campaign['status'].startswith('PASS_') else 1)


if __name__ == '__main__':
    main()

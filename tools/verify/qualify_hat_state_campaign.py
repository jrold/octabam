#!/usr/bin/env python3
"""Bind the on-demand Hat handoff campaign to its image and frozen budget.

Steady DSP ownership must perform zero CF Hat synthesis. Positive directed and
lifecycle witnesses establish that real snapshot/catch-up jobs still execute.
Correct audio and nominal deadlines never substitute for the fixed budget.
"""
import argparse
import json
from pathlib import Path

import calibrate_perky_hybrid_budget as c
import qualify_perky_hybrid_budget as budget

ROOT = c.ROOT
PREVIOUS = ROOT / 'out/perky/hybrid/full-map-budget-v5'
ERROR_COUNTERS = ('pk_nhr_failures', 'pk_nhb_overflows', 'pk_nhb_clock_errors')
ZERO_COUNTERS = ('pk_nhb_inner_calls', 'pk_nhb_snapshot_requests',
                 'pk_nhb_snapshot_completed', 'pk_nhb_snapshot_rejected',
                 'pk_nhb_snapshot_words', 'pk_nhb_replay_frames', 'pk_nhb_handoff_jobs')
STATUSES = {
    'SNAPSHOT_DSP_GATE.json': 'PASS_FROZEN_DSP_SNAPSHOT_AUDIO_STATE_AND_RING_FEEDBACK',
    'STATE_STOCK_FX_GATE.json': 'PASS_STATE_HANDOFF_ALL_FOURTEEN_FX_STOCK_DATA_AND_B_SOURCE',
    'SOURCE_GATE.json': 'PASS_ACTUAL_IMAGE_ALL_LAYOUT_SOURCE_PCM_STATE_SHARED_RNG',
    'HANDOFF_GATE.json': 'PASS_ACTUAL_CF_DSP_NONBLOCKING_STATE_HANDOFF',
    'DMA_GATE.json': 'PASS_ACTUAL_CF_DMA_STARTUP_FULL_WRAP_AND_CARRIER_CLEAR',
    'lifecycle/RESULT.json': 'PASS_FULL_MAP_LIFECYCLE_MODEL_SCOPE',
    'MATRIX.json': 'PASS_FULL_MAP_PRODUCTION_MATRIX_MODEL_SCOPE',
    'SCENES.json': 'PASS_FULL_MAP_SCENE_FADER_MODEL_SCOPE',
}


def read(path):
    return json.loads(path.read_text())


def check_hashes(entries, *, required=False):
    for filename, expected in entries.items():
        target = Path(filename)
        if not target.is_absolute():
            target = ROOT / target
        if target.is_file():
            assert c.sha(target) == expected, ('input/source drift', filename)
        else:
            assert not required, ('required input absent', filename)


def requested_frames(path):
    command = read(path.parent / 'INPUTS.json')['command']
    return int(command[command.index('--frames') + 1])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', '--work', dest='build', type=Path, required=True)
    parser.add_argument('--output', type=Path,
                        default=ROOT / 'modules/perky/hybrid/STATE_HANDOFF_QUALIFICATION.json')
    args = parser.parse_args()
    work = args.build.resolve()
    build_path = work / 'BUILD.json'
    build = read(build_path)
    version = build['version']
    image = work / 'probe' / f'mainos_{version}.bin'
    elf = work / 'probe/platform/runtime.elf'
    assert c.sha(image) == build['main_sha256']
    assert c.sha(elf) == build['runtime_sha256']
    assert build['boot_status'].startswith('PASS_'), 'Actual image boot/read-back proof absent'
    check_hashes(build['source_sha256'], required=True)
    snapshot_path = work / 'SOURCE_SNAPSHOT.json'
    source_snapshot = read(snapshot_path)
    for filename, expected in build['source_sha256'].items():
        if filename in source_snapshot:
            assert source_snapshot[filename] == expected, ('Prebuild source snapshot drift', filename)
    offload = 'modules/perky/cf_noise_hat_offload.c'
    assert source_snapshot[offload] == c.sha(ROOT / offload)
    frozen_path = ROOT / 'modules/perky/hybrid/EMULATOR_BUDGET.json'
    frozen = read(frozen_path)
    # The earlier completed campaign binds the budget before this redesign.
    previous_campaign_path = ROOT / 'modules/perky/hybrid/CF_BUDGET_OPTIMIZATION.json'
    previous_campaign = read(previous_campaign_path)
    assert c.sha(frozen_path) == previous_campaign['budget_sha256'], 'Frozen budget changed'
    assert frozen['observer_sha256'] == previous_campaign['observer_sha256']
    assert frozen['clocks'] == dict(CF=264000000, PIT=132000000)
    assert c.sha(work / 'observer/ot_emu_safety') == frozen['observer_sha256']
    receipts = {str(build_path): c.sha(build_path)}
    assessments = []
    no_shadow = {}
    baseline_build = read(PREVIOUS / 'BUILD.json')
    for v4, mode in ((5, 0), (5, 1), (5, 2), (3, 1), (10, 1)):
        name = f'{version}-WTWT-Slap-{v4}-M{mode}-all14'
        path = work / 'measurement' / name / 'ROW.json'
        row = read(path)
        row['requested_transport_frames'] = requested_frames(path)
        assert row['requested_transport_frames'] == 16384 and row['frames'] >= 16384
        assert row['image_sha256'] == build['main_sha256']
        assert row['observer_sha256'] == frozen['observer_sha256'] and row['clocks'] == frozen['clocks']
        assert row['configuration'] == dict(version=version, role='candidate',
                                             algos=[9, 9, 8, v4], modes=[1, 2, 0, mode], FX='all14')
        assert row['full_ISR']['modeled_misses'] == 0 and c.full.exact(row['exact_source'])
        assert row['exact_source']['feedback_frames'] > 0 and row['playback_card_read_commands'] > 0
        assert set(row['stock_audio']) == set(map(str, range(1, 9)))
        assert all(track['source_significant'] > 64 and track['post_FX_significant'] > 64
                   for track in row['stock_audio'].values())
        transport = row['transport']
        assert all(transport[key] == 0 for key in ERROR_COUNTERS + ZERO_COUNTERS)
        assert transport['pk_nhb_produced'] == transport['pk_nhb_completed'] == 0
        assert transport['pk_nhr_sequence'] > 0 and transport['pk_nhr_consumed'] > 0
        witness = row['state_handoff']
        assert witness['status'] == 'MEASURED_NO_DUPLICATE_CF_HAT_WORK'
        assert all(witness['counters'][key] == transport[key] for key in witness['counters'])
        assert witness['driver_sha256'] == c.sha(ROOT / 'tools/verify/measure_perky_state_handoff.py')
        assert witness['calibration_driver_sha256'] == c.sha(Path(c.__file__))
        assert witness['adapted_function_sha256'] == c.sha(path.parent / 'MEASUREMENT_ADAPTER.py')
        directed = witness.get('directed_witness')
        assert directed, 'Same-image positive handoff witness is required'
        assert Path(directed['path']).resolve() == (work / 'HANDOFF_GATE.json').resolve()
        assert c.sha(Path(directed['path'])) == directed['sha256']
        check_hashes(row['inputs'])
        assessment = budget.evaluate(row, frozen['budgets_us'])
        saved_path = path.parent / 'BUDGET_ASSESSMENT.json'
        saved = read(saved_path)
        for key in ('case', 'pass_budget', 'checks'):
            assert saved[key] == assessment[key]
        assert saved['row_sha256'] == c.sha(path) and saved['budget_sha256'] == c.sha(frozen_path)
        assert saved['image_sha256'] == build['main_sha256']
        before_path = PREVIOUS / 'measurement' / f'PKFM11-WTWT-Slap-{v4}-M{mode}-all14/ROW.json'
        before = read(before_path)
        before['requested_transport_frames'] = requested_frames(before_path)
        assert before['requested_transport_frames'] == 16384
        assert before['image_sha256'] == baseline_build['main_sha256']
        assert before['observer_sha256'] == frozen['observer_sha256'] and before['clocks'] == frozen['clocks']
        assessment.update(receipt=str(path), receipt_sha256=c.sha(path),
                          baseline_PKFM11_receipt=str(before_path), baseline_PKFM11_sha256=c.sha(before_path),
                          baseline_PKFM11_us={key: budget.metric(before, key) for key in budget.METRICS},
                          change_from_PKFM11_us={key: budget.metric(row, key) - budget.metric(before, key)
                                                for key in budget.METRICS})
        old_path = c.DEFAULT_WORK / 'replay' / f'F6-WTWT-Slap-{v4}-M{mode}-all14/ROW.json'
        if old_path.is_file():
            old = read(old_path)
            old['requested_transport_frames'] = requested_frames(old_path)
            assert old['requested_transport_frames'] == 16384
            assert old['observer_sha256'] == frozen['observer_sha256'] and old['clocks'] == frozen['clocks']
            assessment['baseline_PKFM6_us'] = {key: budget.metric(old, key) for key in budget.METRICS}
        assessments.append(assessment)
        no_shadow[name] = dict(status=witness['status'], counters=transport)
        receipts.update({str(path): c.sha(path), str(saved_path): c.sha(saved_path)})
    functional = {}
    interactive = {}
    results = {}
    for name, status in STATUSES.items():
        path = work / name
        result = read(path)
        assert result['status'] == status, (path, result['status'])
        if 'image_sha256' in result:
            assert result['image_sha256'] == build['main_sha256']
        if 'elf_sha256' in result:
            assert result['elf_sha256'] == build['runtime_sha256']
        check_hashes(result.get('inputs', {}))
        check_hashes(result.get('input_sha256', {}), required=True)
        check_hashes(result.get('source_sha256', {}))
        check_hashes(result.get('state_handoff', {}).get('source_sha256', {}), required=True)
        observer_inputs = {value for filename, value in result.get('inputs', {}).items()
                           if filename.endswith('/ot_emu_safety')}
        if 'safety' in result:
            assert observer_inputs == {frozen['observer_sha256']}, ('Different measuring observer', name)
            assert c.full.exact(result['independent_source'])
            assert all(result['safety'][key] == 0 for key in
                       ('ISR_duration_misses', 'DMA_read_write_overlaps', 'DMA_active_restarts',
                        'guard_writes_after_dispatch'))
            steady = c.histogram_stats(result['safety']['budget_cycles']['steady_histogram'])
            values = dict(steady_ISR_mean=steady['mean_us'], steady_ISR_p99=steady['p99_us'],
                          steady_ISR_p99_9=steady['p99_9_us'], full_ISR_peak=result['full_ISR']['max_us'])
            interactive[name] = {key: dict(measured_us=value, budget_us=frozen['budgets_us'][key],
                                           pass_budget=value <= frozen['budgets_us'][key])
                                 for key, value in values.items()}
        functional[name] = dict(status=status, frames=result.get('frames', result.get('full_ISR', {}).get('frames')),
                                receipt=str(path), receipt_sha256=c.sha(path))
        receipts[str(path)] = c.sha(path)
        results[name] = result
    snapshot = results['SNAPSHOT_DSP_GATE.json']
    assert snapshot['read_watch_positive_control'] is True
    assert snapshot['retired_Y_payload_reads_before_request'] == 0
    assert snapshot['retired_Y_payload_writes_before_request'] == 0
    assert snapshot['snapshot_payload_words'] == 190 and len(snapshot['captures']) >= 3
    assert len(snapshot['completed']) >= 2 and len(snapshot['canceled']) >= 1
    directed = results['HANDOFF_GATE.json']
    assert directed['poisoned_epoch_reset'] is True
    assert directed['transport_sequence_wrap'] is True
    assert directed['full_transport_sequence_wrap'] is True
    assert directed['zero_sequence_cf_request'] is True
    assert directed['startup_disabled_cf'] is True
    assert directed['startup_flag_poisoned_reset'] is True
    assert directed['repeated_zero_sequence_feedback'] is True
    assert directed['poisoned_consumer_valid_reset'] is True
    assert directed['native_ring_counters_wrap'] is True
    assert directed['owners']['0'] > 64 and directed['owners']['1'] > 64
    assert directed['counters']['pk_nhb_inner_calls'] > 0
    assert directed['counters']['pk_nhb_snapshot_completed'] >= 3
    assert all(value == 0 for value in directed['steady_before'].values())
    assert directed['steady_after'] == directed['counters']
    dma = results['DMA_GATE.json']
    for key in ('startup_no_extract', 'zero_sequence_extract', 'exact_mail', 'carrier_cleared'):
        assert dma[key] is True, ('DMA proof absent', key)
    assert dma['both_ping_banks'] and dma['cf_owner_extraction'] and dma['poisoned_startup_latch_reset']
    assert not dma['instruction_hooks'] and not dma['target_code_repaired']
    assert len(dma['cases']) == 10
    assert c.sha(work / 'dma-gate/pk_nhr_dma_step.dis') == dma['disassembly_sha256']
    life = results['lifecycle/RESULT.json']
    assert life['state_handoff']['status'] == 'PASS_ACTUAL_IMAGE_ON_DEMAND_HANDOFF_AND_GENERATIONS'
    counts = life['state_handoff']['counters']
    assert counts['pk_nhb_inner_calls'] > 0 and counts['pk_nhb_replay_frames'] > 0
    assert counts['pk_nhb_handoff_jobs'] > 0 and counts['pk_nhb_switches'] >= 22
    assert counts['pk_nhb_snapshot_requests'] >= counts['pk_nhb_snapshot_completed'] > 0
    assert counts['pk_nhb_snapshot_words'] >= 190 * counts['pk_nhb_snapshot_completed']
    assert counts['pk_nhb_completed'] <= counts['pk_nhb_produced']
    matrix = results['MATRIX.json']
    assert matrix['expected_tuples'] == 243 and matrix['missing_tuples'] == []
    assert matrix['state_handoff']['status'] == 'PASS_PRODUCTION_MATRIX_WITHOUT_CF_HAT_SHADOW'
    counts = matrix['state_handoff']['counters']
    assert counts['pk_nhb_inner_calls'] == counts['pk_nhb_snapshot_requests'] == 0
    assert counts['pk_nhb_produced'] == counts['pk_nhb_completed'] == 0 and counts['pk_nhr_consumed'] > 0
    floor = {}
    for name, marker in (('full-map-state-default-check.log', 'all runnable checks passed'),
                         ('full-map-state-refhash.log', 'ALL 24 CASES BIT-IDENTICAL')):
        path = work.parent / name
        text = path.read_text()
        assert marker in text, ('Repository check did not pass', path)
        floor[name] = dict(receipt=str(path), sha256=c.sha(path),
                          skipped=[line.strip() for line in text.splitlines() if '[SKIP]' in line])
    passed = (all(check['pass_budget'] for check in assessments)
              and all(check['pass_budget'] for row in interactive.values() for check in row.values()))
    result = dict(schema='octabam.perky.resident-state-handoff.v1',
                  status='PASS_FROZEN_BUDGET_MODEL_SCOPE' if passed else 'FAIL_HOLD',
                  admission='PHYSICAL_ACCEPTANCE_STILL_REQUIRED' if passed else 'HOLD_FOR_PERFORMANCE_WORK',
                  functional_status='PASS_EXACT_AUDIO_AND_NONBLOCKING_STATE_HANDOFF_MODEL_SCOPE',
                  hardware_validated=False, version=version,
                  main_sha256=build['main_sha256'], runtime_sha256=build['runtime_sha256'],
                  source_commit=build['source_commit'], source_checkpoint_note=build['source_checkpoint_note'],
                  source_snapshot=dict(receipt=str(snapshot_path), sha256=c.sha(snapshot_path)),
                  clocks=frozen['clocks'], observer_sha256=frozen['observer_sha256'],
                  budget_path=str(frozen_path), budget_sha256=c.sha(frozen_path),
                  prior_budget_binding=dict(receipt=str(previous_campaign_path), sha256=c.sha(previous_campaign_path)),
                  state_handoff=build['state_handoff_contract'], no_duplicate_work=no_shadow,
                  assessments=assessments, interactive_ISR_assessments=interactive,
                  functional=functional, receipts=receipts, default_build_checks=floor,
                  build_receipt_sha256=c.sha(build_path),
                  source_sha256={str(Path(__file__).relative_to(ROOT)): c.sha(Path(__file__))},
                  limits=[
                      'The calibration budget, native clocks and measuring binary are unchanged.',
                      'Zero steady CF native/replay/job counters replace the obsolete positive continuous-worker condition; positive same-image directed and interrupted lifecycle witnesses are required.',
                      'All eight track outputs and all fourteen stock FX are active in sustained rows; original-reference source PCM/state/shared RNG comparisons pass.',
                      'Seven budget ceilings apply to sustained rows, with four ISR ceilings additionally assessed on lifecycle/matrix/scenes. Interactive whole-CPU ACK statistics were not captured.',
                      'Correctness and nominal deadline passes are separate from the stricter fixed performance gate.',
                      'The working-envelope target is an engineering policy, not a measured physical safe threshold.',
                      'No physical flash, silicon timing qualification or new hardware handoff is implied.'])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(result['status'], result['admission'])
    raise SystemExit(0 if passed else 1)


if __name__ == '__main__':
    main()

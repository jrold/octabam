#!/usr/bin/env python3
"""Bind sustained Resonant Snare/Bass measurements to unchanged PKFM17.

Functional errors raise without publishing a qualification. A complete,
functionally valid campaign may still write FAIL_HOLD and return one because
the unchanged calibrated timing vector is an independent requirement.
"""
import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path

import calibrate_perky_hybrid_budget as calibration
import measure_perky_state_handoff as state
import qualify_perky_hybrid_budget as budget

ROOT = calibration.ROOT
DEFAULT_BUILD = ROOT / 'out/perky/hybrid/full-map-packet-reserve-v2'
DEFAULT_WORK = ROOT / 'out/perky/hybrid/resonant-feasibility-v1'
FRAMES = 32768
BUDGET_SHA256 = '8608844b96c6f20daed514147dc6cadab7a2c82aae80d2ef7c9a875a22ccaec4'
OBSERVER_SHA256 = 'f975b4d2c4b6a2d993d3158bc8e68c8a786b328e2902b58bdde418225287d022'
ORACLE_SHA256 = '84c9345815e71c78072902d69477d0c92ddf592c08aaca8bf0e09f6582cadf6d'
IMAGE_SHA256 = '7f3eeecafcfb6746207d981e3677e224d5321e2100b748fe5ba7e633dd314dcb'
ELF_SHA256 = 'e16f1da5b17b55083ab7fa7f165efd4e6ec262ada259291d4927b2412921d6c9'
CLOCKS = dict(CF=264000000, PIT=132000000)
V3 = {'slap-control': (8, 0), 'snare': (4, 0), 'bass': (4, 1), 'alternate': (4, 0)}
V4 = {'hat': 5, 'noise-tone': 3}
V3_LABEL = {'slap-control': 'SlapControl', 'snare': 'ResSnare', 'bass': 'ResBass',
            'alternate': 'ResSnareBassLocks'}
V4_LABEL = {'hat': 'MetallicHat', 'noise-tone': 'NoiseTone'}
ERROR_COUNTERS = ('pk_nhr_failures', 'pk_nhb_overflows', 'pk_nhb_clock_errors')
ZERO_COUNTERS = ('pk_nhb_inner_calls', 'pk_nhb_snapshot_requests',
                 'pk_nhb_snapshot_completed', 'pk_nhb_snapshot_rejected',
                 'pk_nhb_snapshot_words', 'pk_nhb_replay_frames',
                 'pk_nhb_handoff_jobs', 'pk_nhb_produced', 'pk_nhb_completed')


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check_inputs(mapping, *, missing_card=False):
    """Only the reproducible card image may have been deliberately removed."""
    for name, expected in mapping.items():
        path = Path(name)
        if not path.is_absolute():
            path = ROOT / path
        if not path.exists():
            assert missing_card and path.name == 'card.img', ('Missing input', name)
            continue
        assert path.is_file() and sha(path) == expected, ('Input changed', name)


def expected_configuration(row, version):
    configuration = row['configuration']
    kind = configuration['v3_case']
    assert kind in V3, ('Unknown V3 case', kind)
    v4 = configuration['algos'][3]
    assert v4 in V4.values()
    voice4 = next(label for label, value in V4.items() if value == v4)
    algo, mode = V3[kind]
    expected = dict(version=version, role='candidate', algos=[9, 9, algo, v4],
                    modes=[1, 2, mode, 1], FX='all14', v3_case=kind, voice4_case=voice4)
    assert configuration == expected, ('Configuration differs', configuration, expected)
    return kind, voice4


def validate_combinations(row, kind, voice4):
    exact = row['exact_source']
    assert calibration.full.exact(exact), ('Original-reference mismatch', row['case'])
    assert len(exact['source_frames']) == len(exact['source_significant']) == 4
    assert exact['source_frames'][:3] == [FRAMES] * 3
    assert exact['source_frames'][3] >= FRAMES - 4
    assert all(value > 64 for value in exact['source_significant'])
    assert exact['resident_state_frames_checked'] >= FRAMES - 4
    assert exact['feedback_frames'] >= FRAMES - 5
    assert exact['uninitialized_hat_frames'] == 0
    v3_algo, mode = V3[kind]
    expected_keys = {f'9:9:{v3_algo}:{V4[voice4]}/1:2:{m}:1'
                     for m in ((0, 1) if kind == 'alternate' else (mode,))}
    combinations = exact['combinations']
    assert set(combinations) == expected_keys, ('Actual sequencer selections differ', row['case'], combinations)
    assert sum(combinations.values()) == FRAMES
    assert all(count > (FRAMES // 8 if kind == 'alternate' else 0)
               for count in combinations.values()), ('Insufficient mode coverage', row['case'])
    assert exact['algorithm_masks'] == [1 << 9, 1 << 9, 1 << v3_algo, 1 << V4[voice4]]
    assert exact['mode_masks'] == [1 << 1, 1 << 2, 3 if kind == 'alternate' else 1 << mode, 1 << 1]
    return dict(actual_tuples=combinations,
                scope='Actual rendering tuples and coverage; not an exact count of MODE switches')


def validate_witness(row, path, kind, voice4, build):
    """The new measurement driver's final-card witness is checked here."""
    directory = path.parent
    witness = row['resonant_workload']
    assert witness['v3_case'] == kind and witness['voice4_case'] == voice4
    driver = ROOT / 'tools/verify/measure_perky_resonant_workload.py'
    assert witness['driver_sha256'] == sha(driver)
    adapter = directory / 'MEASUREMENT_ADAPTER.py'
    assert witness['adapted_function_sha256'] == sha(adapter)
    _, expected_adapter = state.measurement_function()
    marker = 'Path(_calibration_source))}'
    assert expected_adapter.count(marker) == 1
    expected_adapter = expected_adapter.replace(
        marker, 'Path(_calibration_source), Path(_resonant_driver))}', 1)
    assert adapter.read_text() == expected_adapter, 'Saved measurement adapter differs from its bound generator'
    assert witness['duration_seconds'] == FRAMES * 16 / 44100
    algo, mode = V3[kind]
    wanted_modes = (0, 1) if kind == 'alternate' else (mode,)
    expected_counts = {str(value): row['exact_source']['combinations'][
        f'9:9:{algo}:{V4[voice4]}/1:2:{value}:1'] for value in wanted_modes}
    assert witness['actual_mode_frame_counts'] == expected_counts
    fixture_ref = witness['fixture']
    fixture_path = Path(fixture_ref['path']).resolve()
    assert fixture_path == (directory / 'RESONANT_FIXTURE.json').resolve()
    assert fixture_ref['sha256'] == sha(fixture_path)
    status = 'PASS_FINAL_CARD_RESONANT_SELECTION_AND_MODE_LOCKS'
    assert fixture_ref['status'] == status
    assert fixture_ref['all_banks_parts_patterns_confirmed'] is True
    fixture = read(fixture_path)
    assert fixture['status'] == status
    assert fixture['image_sha256'] == build['main_sha256']
    assert fixture['configuration'] == row['configuration']
    assert fixture['all_banks_parts_patterns_confirmed'] is True
    assert fixture['tempo_bpm'] == 120
    assert fixture['pattern_steps'] == 64 and fixture['pattern_scale'] == '1X'
    assert fixture['card_sha256'] == row['inputs'][str(directory / 'card.img')]
    banks = fixture['banks']
    assert len(banks) == 16
    assert {Path(item['path']).name.lower() for item in banks} == {
        f'bank{bank:02d}.work' for bank in range(1, 17)}
    part_records = 0
    locks = 0
    for bank in banks:
        assert re.fullmatch(r'OCTABAM/RIG/bank\d\d\.work', bank['path'], re.I)
        assert bank['parts'] == calibration.integrated.workload.otp.NPARTS_ALL == 8
        part_records += bank['parts']
        patterns = bank['patterns']
        assert len(patterns) == 4 and {item['pattern'] for item in patterns} == set(range(4))
        for pattern in patterns:
            steps, sequence = pattern['steps'], pattern['mode_sequence']
            assert len(steps) == len(sequence) and 32 <= len(steps) <= 64
            assert steps == sorted(set(steps)) and all(0 <= step < 64 for step in steps)
            expected = [index % 2 if kind == 'alternate' else mode for index in range(len(steps))]
            assert sequence == expected, ('Final-card MODE sequence differs', bank['path'], pattern['pattern'])
            locks += len(steps)
    return dict(receipt=str(fixture_path), receipt_sha256=sha(fixture_path), status=status,
                banks=len(banks), part_records=part_records, patterns=4 * len(banks),
                fixture_trigger_MODE_locks=locks, tempo_bpm=120, pattern_steps=64, pattern_scale='1X',
                driver_sha256=sha(driver), adapted_function_sha256=sha(adapter),
                scope='Driver-bound scan of final card bytes; actual source modes checked independently; no exact runtime switch-count claim')


def validate_row(path, build, frozen):
    directory = path.parent
    row = read(path)
    kind, voice4 = expected_configuration(row, build['version'])
    assert row['case'] == directory.name == f'PKFM17-WTWT-{V3_LABEL[kind]}-{V4_LABEL[voice4]}-all14'
    assert row['requested_transport_frames'] == row['frames'] == FRAMES
    assert row['image_sha256'] == IMAGE_SHA256
    assert row['elf_sha256'] == ELF_SHA256
    assert row['observer_sha256'] == OBSERVER_SHA256 and row['clocks'] == CLOCKS
    inputs_path = directory / 'INPUTS.json'
    inputs = read(inputs_path)
    assert inputs['case'] == row['configuration']
    assert inputs['inputs'] == row['inputs']
    check_inputs(row['inputs'], missing_card=True)
    command = inputs['command']
    assert int(command[command.index('--frames') + 1]) == FRAMES
    assert command[command.index('--cf-cycles-clock') + 1] == '1.0'
    assert command[command.index('--pit-clock-hz') + 1] == '132000000'
    assert '--cf-cycles-clock-before-transport' in command
    assert '--sequencer' in command and '--dsp' in command and '--internal-clock' in command
    image = Path(command[command.index('--image') + 1]).resolve()
    observer = Path(command[0]).resolve()
    elf = DEFAULT_BUILD / 'probe/platform/runtime.elf'
    assert row['inputs'][str(image)] == IMAGE_SHA256
    assert sha(image) == IMAGE_SHA256 and sha(observer) == OBSERVER_SHA256
    assert row['inputs'][str(elf)] == ELF_SHA256
    driver = ROOT / 'tools/verify/measure_perky_resonant_workload.py'
    assert row['inputs'][str(driver)] == sha(driver), 'New driver is absent/unbound'
    environment = inputs['environment']
    exact_path = directory / 'full-map-exact.json'
    assert Path(environment['FM_REPORT']).resolve() == exact_path.resolve()
    assert read(exact_path) == row['exact_source'], 'ROW source claims differ from the frozen observer report'
    oracle = DEFAULT_BUILD / 'observer/full-map-oracle.dylib'
    assert Path(environment['FM_REFERENCE_LIBRARY']).resolve() == oracle.resolve()
    assert sha(oracle) == ORACLE_SHA256, 'Original-reference oracle changed'
    stack_path, private_path = directory / 'stack.json', directory / 'private.json'
    assert Path(environment['HYBRID_SAFETY_REPORT']).resolve() == stack_path.resolve()
    assert Path(environment['HYBRID_PRIVATE_REPORT']).resolve() == private_path.resolve()
    stack, private = read(stack_path), read(private_path)
    assert stack['frames'] == stack['frame_returns'] == private['switched'] == private['restored'] == FRAMES
    assert stack['budget_cycles']['steady_after_completed_ISR'] == 512
    assert stack['budget_cycles']['steady_frames'] == FRAMES - 512
    assert calibration.histogram_stats(stack['budget_cycles']['steady_histogram']) == row['steady_ISR']
    assert calibration.histogram_stats(stack['budget_cycles']['all_histogram']) == row['all_ISR']
    assert row['all_ISR']['frames'] == FRAMES
    assert row['steady_ISR']['frames'] == FRAMES - 512
    assert row['full_ISR'] == dict(mean_us=stack['full_ISR_sum_cycles'] / FRAMES / 264,
                                   max_us=stack['full_ISR_max_cycles'] / 264,
                                   modeled_misses=stack['ISR_duration_misses'])
    assert not any(stack[key] for key in ('DMA_read_write_overlaps',
                                         'DMA_active_restarts', 'guard_writes_after_dispatch'))
    assert not private['ownership_register_frame_or_mask_violations'] and not private['fence_writes']
    assert all(item['outside_extent'] == 0 for item in stack['stacks'])
    log_path = directory / 'port.log'
    log = log_path.read_text()
    assert 'cycle clock: startup/pre-roll/transport use x1.00' in log
    assert 'one sample is 5986 ColdFire cycles at 264 MHz' in log
    assert 'PIT clock  : 132000000 Hz' in log
    assert re.search(rf'frames run\s*:\s*{FRAMES}\s+since transport start.*REACHED', log)
    assert 'FAULT:' not in log and 'ILLEGAL' not in log
    assert calibration.integrated.workload.parse_ot_emu_log(log) == row['whole_CPU']
    assert row['whole_CPU']['cf_ack_interval']['frames_sampled'] == FRAMES
    assert row['whole_CPU']['dsp_exchange_and_cores']['words_not_in_time'] == 0
    assert abs(budget.metric(row, 'whole_CPU_mean') - row['whole_CPU']['cf_ack_interval']['mean_us']) <= .051
    assert row['playback_card_read_commands'] > 0
    load = (directory / 'card-load.log').read_text().splitlines()
    end = (directory / 'card-end.log').read_text().splitlines()
    assert end[:len(load)] == load
    assert sum(line.startswith('READ ') for line in end[len(load):]) == row['playback_card_read_commands']
    assert set(row['stock_audio']) == set(map(str, range(1, 9)))
    assert all(value['source_significant'] > 64 and value['post_FX_significant'] > 64
               for value in row['stock_audio'].values())
    blocks_path = directory / 'blocks.bin'
    assert Path(command[command.index('--block-dump') + 1]).resolve() == blocks_path.resolve()
    blocks_sha256 = row['comparison_dumps']['blocks.bin']
    assert re.fullmatch('[0-9a-f]{64}', blocks_sha256)
    if blocks_path.exists():
        assert sha(blocks_path) == blocks_sha256
        classes = calibration.integrated.blockdump.classes(calibration.integrated.blockdump.read(blocks_path))
        activity = {}
        for track in range(1, 9):
            source = calibration.integrated.recloop.track_audio(classes, track)
            post = calibration.integrated.recloop.readback_audio(classes, track)
            activity[str(track)] = dict(source_significant=sum(abs(value) > 64 for value in source),
                                        post_FX_significant=sum(abs(value) > 64 for value in post))
        assert activity == row['stock_audio'], 'ROW activity counts differ from the raw block dump'
    transport = row['transport']
    assert all(transport[key] == 0 for key in ERROR_COUNTERS + ZERO_COUNTERS)
    assert transport['pk_nhr_sequence'] > 0 and transport['pk_nhr_consumed'] > 0
    assert transport['fma_ready'] == 0x41484f4b and transport['fma_status'] == 2
    for symbol, value in transport.items():
        blob = directory / (symbol + '.bin')
        assert blob.is_file() and len(blob.read_bytes()) == 4
        assert int.from_bytes(blob.read_bytes(), 'big') == value
    for name, expected in row['comparison_dumps'].items():
        if name == 'blocks.bin':
            continue
        assert sha(directory / name) == expected
    coverage = validate_combinations(row, kind, voice4)
    witness = validate_witness(row, path, kind, voice4, build)
    assessment = budget.evaluate(row, frozen['budgets_us'])
    saved_path = directory / 'BUDGET_ASSESSMENT.json'
    saved = read(saved_path)
    assert all(saved[key] == assessment[key] for key in ('case', 'checks', 'pass_budget'))
    assert saved['image_sha256'] == IMAGE_SHA256 and saved['observer_sha256'] == OBSERVER_SHA256
    assert saved['budget_sha256'] == BUDGET_SHA256 and saved['row_sha256'] == sha(path)
    assessment.update(v3_case=kind, voice4_case=voice4, receipt=str(path), receipt_sha256=sha(path),
                      actual_coverage=coverage, fixture_witness=witness,
                      activity_evidence=dict(
                          counts=row['stock_audio'], block_dump_sha256=blocks_sha256,
                          raw_dump_retained=blocks_path.exists(),
                          adapted_function_sha256=witness['adapted_function_sha256'],
                          scope=('Raw block dump independently recounted' if blocks_path.exists() else
                                 'Counts were extracted by the source-bound, independently reconstructed calibrated adapter before its deliberate raw-dump cleanup; only the dump hash and aggregate counts survive. These counts establish activity, not replayable or gap-free audio.')))
    receipts = {str(p): sha(p) for p in (path, inputs_path, stack_path, private_path, log_path, saved_path,
                                        directory / 'card-load.log', directory / 'card-end.log',
                                        exact_path, oracle, directory / 'RESONANT_FIXTURE.json',
                                        directory / 'MEASUREMENT_ADAPTER.py')}
    return (kind, voice4), row, assessment, receipts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, default=DEFAULT_WORK)
    parser.add_argument('--build', type=Path, default=DEFAULT_BUILD)
    parser.add_argument('--output', type=Path,
                        default=ROOT / 'modules/perky/hybrid/RESONANT_WORKLOAD_QUALIFICATION.json')
    args = parser.parse_args()
    work, build_directory, output = args.work.resolve(), args.build.resolve(), args.output.resolve()
    work.mkdir(parents=True, exist_ok=True)
    if output.exists():
        history = work / 'qualification-history'
        history.mkdir(exist_ok=True)
        previous = history / (sha(output) + '.json')
        if not previous.exists():
            shutil.copyfile(output, previous)
        output.unlink()
    build_path = build_directory / 'BUILD.json'
    build = read(build_path)
    assert build_directory == DEFAULT_BUILD.resolve(), 'This campaign qualifies the frozen PKFM17 image'
    assert build['version'] == 'PKFM17'
    assert build['main_sha256'] == IMAGE_SHA256 and build['runtime_sha256'] == ELF_SHA256
    assert sha(build_directory / 'probe/mainos_PKFM17.bin') == IMAGE_SHA256
    assert sha(build_directory / 'probe/platform/runtime.elf') == ELF_SHA256
    check_inputs(build['source_sha256'])
    prior_source_path = build_directory / 'SOURCE_GATE.json'
    prior_source = read(prior_source_path)
    assert prior_source['status'] == 'PASS_ACTUAL_IMAGE_ALL_LAYOUT_SOURCE_PCM_STATE_SHARED_RNG'
    assert prior_source['image_sha256'] == IMAGE_SHA256 and prior_source['elf_sha256'] == ELF_SHA256
    assert prior_source['frames'] == 5355
    check_inputs(prior_source.get('source_sha256', {}))
    check_inputs(prior_source.get('inputs', {}))
    budget_path = ROOT / 'modules/perky/hybrid/EMULATOR_BUDGET.json'
    assert sha(budget_path) == BUDGET_SHA256
    frozen = read(budget_path)
    assert frozen['clocks'] == CLOCKS and frozen['observer_sha256'] == OBSERVER_SHA256
    row_paths = sorted(work.rglob('ROW.json'))
    assert len(row_paths) == 8, ('Require exactly eight complete workload rows', row_paths)
    rows, assessments = {}, []
    receipts = {str(build_path): sha(build_path), str(budget_path): BUDGET_SHA256,
                str(prior_source_path): sha(prior_source_path)}
    for path in row_paths:
        key, row, assessment, bound = validate_row(path, build, frozen)
        assert key not in rows, ('Duplicate case', key)
        rows[key] = row
        assessments.append(assessment)
        receipts.update(bound)
    assert set(rows) == {(kind, voice4) for kind in V3 for voice4 in V4}
    changes = []
    for voice4 in V4:
        control = rows[('slap-control', voice4)]
        old = {name: budget.metric(control, name) for name in budget.METRICS}
        for kind in ('snare', 'bass', 'alternate'):
            row = rows[(kind, voice4)]
            new = {name: budget.metric(row, name) for name in budget.METRICS}
            changes.append(dict(v3_case=kind, voice4_case=voice4,
                                control_case=control['case'], case=row['case'],
                                control_us=old, measured_us=new,
                                change_from_matched_Slap_us={name: new[name] - old[name] for name in old}))
    passed = all(item['pass_budget'] for item in assessments)
    nominal_misses = {row['case']: row['full_ISR']['modeled_misses'] for row in rows.values()}
    result = dict(schema='octabam.perky.resonant-sustained-workload.v1',
                  status='PASS_FROZEN_BUDGET_MODEL_SCOPE' if passed else 'FAIL_HOLD',
                  admission='PHYSICAL_ACCEPTANCE_STILL_REQUIRED' if passed else 'HOLD_FOR_PERFORMANCE_WORK',
                  functional_status='PASS_EIGHT_EXACT_ACTIVE_FOUR_VOICE_STOCK_FX_WORKLOADS',
                  nominal_timing_status='FAIL_NOMINAL_DEADLINES' if any(nominal_misses.values()) else 'PASS_NOMINAL_DEADLINES_MODEL_SCOPE',
                  nominal_deadline_misses=nominal_misses,
                  hardware_validated=False, version=build['version'],
                  source_commit=build['source_commit'], main_sha256=IMAGE_SHA256,
                  runtime_sha256=ELF_SHA256, frames_per_case=FRAMES,
                  total_requested_transport_frames=FRAMES * 8,
                  prior_raw_CF_state_proof=dict(receipt=str(prior_source_path), sha256=sha(prior_source_path),
                                               status=prior_source['status'], frames=5355,
                                               scope='Prior unchanged-image direct CF raw-state/original-audio proof; not a new per-frame CF raw-state comparison in these sustained rows'),
                  clocks=CLOCKS, observer_sha256=OBSERVER_SHA256,
                  reference_oracle_sha256=ORACLE_SHA256,
                  budget_sha256=BUDGET_SHA256, assessments=assessments,
                  changes_from_matched_Slap=changes, receipts=receipts,
                  source_sha256={str(Path(__file__).relative_to(ROOT)): sha(Path(__file__))},
                  limits=[
                      'These eight rows use the unchanged PKFM17 image, frozen instrument and calibrated budget; no algorithm, precision or clock changes.',
                      'All four source voices play with four active stock sample tracks and all fourteen FX in the staged fixtures; significant source/post-FX audio and original-reference source PCM are required independently.',
                      'Original-source PCM claims and selectors are independently checked against each surviving frozen-observer report. Per-track source/post-FX activity counts were extracted by the source-bound calibrated adapter before raw block dumps were deliberately deleted; aggregate counts and dump hashes remain, so this qualifier cannot replay or establish gap-free stock audio.',
                      'The frozen runtime observer compares original-reference source PCM and DSP Hat state/side/clock/feedback; it does not byte-compare raw CF Resonant state on every new sustained frame. The earlier unchanged-image 5355-frame direct source gate supplies separate raw-CF-state evidence.',
                      'Alternate rows require substantial actual Snare/Bass rendering coverage and final-card MODE-lock confirmation. MODE alternates within each 45-trigger pattern, with one repeated mode at the loop boundary; this is not an exact count of runtime switches.',
                      'The earlier five sustained rows held V3 at Slap. Their 221.328 us worst mean was WT/WT/Slap/Noise-Tone, not Resonant Snare or Bass.',
                      'The earlier selector matrix exercised Resonant modes and transitions but its aggregate peak did not establish separate sustained Snare/Bass means.',
                      'Slap deltas compare only matched 32768-frame rows from this campaign; historical 16384-frame means are not treated as matched baselines.',
                      'Nominal ISR deadline misses are recorded as timing evidence, not hidden by rejection of an otherwise exact measurement; DMA/ownership/transport/audio errors remain functional failures. The stricter seven-ceiling vector is evaluated independently.',
                      'This local model does not establish physical cache/bus/IRQ timing or Octatrack hardware admission.'])
    output.parent.mkdir(parents=True, exist_ok=True)
    pending = output.with_suffix(output.suffix + '.pending')
    pending.write_text(json.dumps(result, indent=2) + '\n')
    pending.replace(output)
    print(result['status'], result['admission'])
    raise SystemExit(0 if passed else 1)


if __name__ == '__main__':
    main()

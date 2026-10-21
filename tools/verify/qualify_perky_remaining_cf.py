#!/usr/bin/env python3
"""Bind the remaining-CF optimization campaign to its actual new image.

The row checks are derived from the frozen Resonant workload qualifier, with
new-driver/helper bindings and a new-image proof index. Hardware admission is
separate; valid negative timing evidence writes FAIL_HOLD and returns one.
"""
import argparse
import hashlib
import json
import re
import shutil
import struct
from pathlib import Path

import calibrate_perky_hybrid_budget as calibration
import measure_perky_state_handoff as state
import qualify_perky_hybrid_budget as budget
import qualify_perky_resonant_workload as baseline

ROOT = calibration.ROOT
DEFAULT_BUILD = ROOT / 'out/perky/hybrid/full-map-packet-reserve-v2'
DEFAULT_WORK = ROOT / 'out/perky/hybrid/resonant-cf-optimization/final-workload'
CONTROL_WORK = ROOT / 'out/perky/hybrid/resonant-feasibility-v1'
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
    driver = ROOT / 'tools/verify/measure_perky_remaining_cf.py'
    assert witness['driver_sha256'] == sha(driver)
    adapter = directory / 'MEASUREMENT_ADAPTER.py'
    assert witness['adapted_function_sha256'] == sha(adapter)
    _, expected_adapter = state.measurement_function()
    marker = 'Path(_calibration_source))}'
    assert expected_adapter.count(marker) == 1
    expected_adapter = expected_adapter.replace(
        marker, 'Path(_calibration_source), Path(_resonant_driver), Path(_resonant_helpers))}', 1)
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
    assert row['case'] == directory.name == f"{build['version']}-WTWT-{V3_LABEL[kind]}-{V4_LABEL[voice4]}-all14"
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
    driver = ROOT / 'tools/verify/measure_perky_remaining_cf.py'
    assert row['inputs'][str(driver)] == sha(driver), 'New driver is absent/unbound'
    helpers = ROOT / 'tools/verify/measure_perky_resonant_workload.py'
    assert row['inputs'][str(helpers)] == sha(helpers), 'Original Resonant helper is absent/unbound'
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



REQUIRED_LINKED = ('source', 'handoff', 'lifecycle', 'matrix', 'scenes', 'linked_synthesis')
REQUIRED_NATIVE = ('prepare_native', 'resonant_linked')


def bound_proof(specification, image, elf):
    path = Path(specification['path']).resolve()
    assert sha(path) == specification['sha256'], ('Proof changed', path)
    proof = read(path)
    assert proof['status'].startswith('PASS_'), ('Functional proof did not pass', path, proof['status'])
    check_inputs(proof.get('inputs', {}), missing_card=True)
    check_inputs(proof.get('input_sha256', {}), missing_card=True)
    check_inputs(proof.get('source_sha256', {}))
    check_inputs(proof.get('generated_sources', {}))
    linked = specification['linked_candidate']
    assert type(linked) is bool
    if linked:
        hashes = proof.get('inputs', {})
        assert proof.get('image_sha256', proof.get('main_sha256')) == IMAGE_SHA256 or hashes.get(str(image)) == IMAGE_SHA256, ('Proof lacks new-image binding', path)
        assert proof.get('elf_sha256', proof.get('runtime_sha256')) == ELF_SHA256 or hashes.get(str(elf)) == ELF_SHA256, ('Proof lacks new-ELF binding', path)
        for key in ('image_sha256', 'main_sha256'):
            if key in proof:
                assert proof[key] == IMAGE_SHA256, ('Proof names another image', path)
        for key in ('elf_sha256', 'runtime_sha256'):
            if key in proof:
                assert proof[key] == ELF_SHA256, ('Proof names another ELF', path)
    return proof, dict(path=str(path), sha256=sha(path), status=proof['status'], linked_candidate=linked)


def check_interactive(proof, name, receipt):
    directory = Path(receipt['path']).parent
    if name != 'lifecycle':
        directory /= name
    surviving = {}
    for filename, key in (('full-map-exact.json', 'independent_source'),
                          ('stack.json', 'safety'), ('private.json', 'private')):
        path = directory / filename
        assert read(path) == proof[key], ('Interactive proof differs from its observer report', name, key)
        surviving[str(path)] = sha(path)
    logs = [path for path in (directory / 'startup.log', directory / 'stdout.log') if path.exists()]
    assert logs, ('No interactive startup clock witness', name)
    startup = '\n'.join(path.read_text() for path in logs)
    assert 'cycle clock: startup/pre-roll/transport use x1.00' in startup
    assert 'one sample is 5986 ColdFire cycles at 264 MHz' in startup
    assert 'PIT clock  : 132000000 Hz' in startup
    surviving.update({str(path): sha(path) for path in logs})
    assert any(Path(path).name == 'ot_emu_safety' and value == OBSERVER_SHA256
               for path, value in proof['inputs'].items())
    assert any(Path(path).name == 'full-map-oracle.dylib' and value == ORACLE_SHA256
               for path, value in proof['inputs'].items())
    receipt['observer_receipts'] = surviving
    exact = proof['independent_source']
    assert calibration.full.exact(exact) and all(value > 64 for value in exact['source_significant'])
    assert exact['resident_state_frames_checked'] > 0 and exact['feedback_frames'] > 0
    safety, private = proof['safety'], proof['private']
    assert safety['frames'] >= safety['frame_returns'] > 0
    assert safety['frames'] - safety['frame_returns'] <= 1
    assert private['switched'] == safety['frames'] and private['restored'] == safety['frame_returns']
    assert not any(safety[key] for key in ('DMA_read_write_overlaps', 'DMA_active_restarts', 'guard_writes_after_dispatch'))
    assert all(item['outside_extent'] == 0 for item in safety['stacks'])
    assert not private['ownership_register_frame_or_mask_violations'] and not private['fence_writes']
    timing = proof['full_ISR']
    assert timing['frames'] == safety['frames']
    assert timing['max_cycles'] == safety['full_ISR_max_cycles']
    assert timing['max_us'] == timing['max_cycles'] / 264
    assert timing['deadline_misses'] == safety['ISR_duration_misses']
    if name in ('lifecycle', 'scenes'):
        assert set(proof['post_FX_significant']) == set(map(str, range(1, 9)))
        assert all(value > 64 for value in proof['post_FX_significant'].values())
        assert set(proof['loaded_program_words_checked']) == {'0', '1'}
        assert all(value > 0 for value in proof['loaded_program_words_checked'].values())
    return dict(frames=safety['frames'], completed=safety['frame_returns'],
                max_us=timing['max_us'], nominal_deadline_misses=timing['deadline_misses'],
                resident_DSP_state_frames_checked=exact['resident_state_frames_checked'],
                uninitialized_hat_frames=exact['uninitialized_hat_frames'])


def elf_symbol(path, name):
    data = Path(path).read_bytes()
    assert data[:6] == b'\x7fELF\x01\x02'
    header = struct.unpack_from('>16sHHIIIIIHHHHHH', data)
    sections = [struct.unpack_from('>10I', data, header[6] + index * header[11])
                for index in range(header[12])]
    for section in sections:
        if section[1] != 2:
            continue
        strings = sections[section[6]]
        names = data[strings[4]:strings[4] + strings[5]]
        for offset in range(section[4], section[4] + section[5], section[9]):
            index, address, size, info, other, section_index = struct.unpack_from('>IIIBBH', data, offset)
            if names[index:names.index(0, index)].decode() != name:
                continue
            target = sections[section_index]
            assert size > 0 and 0 <= address - target[3] <= target[5] - size
            start = target[4] + address - target[3]
            return address, data[start:start + size]
    raise AssertionError(('Missing sized target ELF symbol', path, name))


def validate_stock_mix(proof, receipt, image, elf):
    """Require the executed artifact, final code, detour and boot proof chain."""
    assert proof['status'] == 'PASS_FINAL_IMAGE_STOCK_MIXER_PROOF_AND_BOOT_BINDING'
    assert proof['linked_candidate'] is True and receipt['linked_candidate'] is True
    assert proof['standalone_cases'] == 4096 and proof['same_image_cycle_controls'] is True
    assert proof['original_stock_remainder_unchanged'] is True
    helper, detour = proof['helper'], proof['detour']
    assert helper['name'] == 'pk_stock_source_mix_block' and helper['bytes'] == 558
    assert helper['linked_equals_proven'] is True and helper['boot_readback_equals_linked'] is True
    assert detour['address'] == 0x4000cbfa and detour['bytes'] == 8
    assert detour['packaged_and_booted_match'] is True and detour['padding'] == 'one NOP'
    assert set(proof['executed_binary_binding']) == {
        'full_binary_equals_pinned_ELF_objcopy', 'loaded_helper_equals_pinned_ELF_symbol',
        'symbols_equal_pinned_ELF_nm'}
    assert all(value is True for value in proof['executed_binary_binding'].values())
    binding_source = ROOT / 'tools/verify/verify_stock_source_mix_binding.py'
    assert proof['source_sha256'][str(binding_source)] == sha(binding_source)
    address, actual = elf_symbol(elf, helper['name'])
    assert address == helper['linked_address'] and len(actual) == helper['bytes']
    assert hashlib.sha256(actual).hexdigest() == helper['sha256']
    assert actual[-6:] == b'\x4e\xf9' + (0x4000cc62).to_bytes(4, 'big')
    wanted_detour = b'\x4e\xf9' + address.to_bytes(4, 'big') + b'\x4e\x71'
    assert hashlib.sha256(wanted_detour).hexdigest() == detour['sha256']
    main = image.read_bytes()
    stock_path = ROOT / 'out/raw/section_3_MAIN_OS.bin'
    stock = stock_path.read_bytes()
    offset = lambda at: at - 0x40000400
    assert main[offset(0x4000cbfa):offset(0x4000cc02)] == wanted_detour
    assert main[offset(0x4000cc02):offset(0x4000cc62)] == stock[offset(0x4000cc02):offset(0x4000cc62)]
    assert hashlib.sha256(stock[offset(0x4000cbfa):offset(0x4000cc62)]).hexdigest() == 'f50e53baf46b94381358b47323d80cf1784718496ad74296836f58f3bb4fb039'
    proof_paths = [Path(path) for path, value in proof['source_sha256'].items()
                   if Path(path).name == 'RESULT.json' and value == proof['proof_sha256']]
    assert len(proof_paths) == 1
    standalone_proof = read(proof_paths[0])
    assert standalone_proof['status'] == 'PASS_ACTUAL_COMPLETE_STOCK_MIX_BLOCK_REGS_CCR_EMAC_ALL_MEMORY'
    assert standalone_proof['cases'] == 4096 and standalone_proof['same_image_cycle_controls'] is True
    check_inputs(standalone_proof['source_sha256'])
    standalone = proof_paths[0].parent / 'kernel.elf'
    standalone_address, proven = elf_symbol(standalone, helper['name'])
    assert standalone_address == helper['standalone_address'] and actual == proven
    replay = proof['replay']
    assert replay['status'] == standalone_proof['status'] and replay['cases'] == 4096
    assert replay['same_image_cycle_controls'] is True and replay['inputs_unchanged_after_execution'] is True
    check_inputs(replay['inputs'])
    output = Path(replay['output_path'])
    assert sha(output) == replay['output_sha256'] == proof['source_sha256'][str(output)]
    execution = read(output)
    assert execution['status'] == replay['status'] and execution['cases'] == replay['cases']
    assert execution['same_image_cycle_controls'] is True
    assert execution['mean_saved_cycles'] == standalone_proof['mean_saved_cycles'] == proof['standalone_mean_saved_cycles']
    command = replay['command']
    assert len(command) == 3
    runner, replay_directory, original_image = map(Path, command)
    assert replay['inputs'][str(runner)] == sha(runner)
    assert sha(runner) == standalone_proof['source_sha256'][str(proof_paths[0].parent / 'runner')]
    assert original_image == Path(standalone_proof['commands'][-1][-1])
    assert standalone_proof['source_sha256'][str(original_image)] == sha(original_image)
    loaded = (replay_directory / 'kernel.bin').read_bytes()
    assert loaded == (replay_directory / 'elf-objcopy.bin').read_bytes()
    assert loaded == (proof_paths[0].parent / 'kernel.bin').read_bytes()
    start = standalone_address - 0x45000000
    assert loaded[start:start + len(proven)] == proven
    assert replay['inputs'][str(replay_directory / 'kernel.bin')] == sha(replay_directory / 'kernel.bin')
    assert replay['inputs'][str(replay_directory / 'kernel.nm')] == sha(replay_directory / 'kernel.nm')


def validate_proofs(index, image, elf, build=None):
    assert index['image_sha256'] == IMAGE_SHA256 and index['elf_sha256'] == ELF_SHA256
    specifications = index['proofs']
    assert set(REQUIRED_LINKED + REQUIRED_NATIVE) <= set(specifications)
    proofs, receipts = {}, {}
    for name, specification in specifications.items():
        proof, receipt = bound_proof(specification, image, elf)
        proofs[name], receipts[name] = proof, receipt
    assert all(receipts[name]['linked_candidate'] for name in REQUIRED_LINKED)
    if build and build.get('remaining_cf_options', {}).get('stock_source_mix'):
        assert 'stock_source_mix' in proofs, 'Selected stock mixer requires the final executed-binary/ELF/detour/boot binding proof'
        validate_stock_mix(proofs['stock_source_mix'], receipts['stock_source_mix'], image, elf)
    source = proofs['source']
    assert source['status'] == 'PASS_ACTUAL_IMAGE_ALL_LAYOUT_SOURCE_PCM_STATE_SHARED_RNG'
    assert source['frames'] == 5355 and source['algorithm_layouts'] == 81
    assert source['mode_rows'] == 3 and source['splits'] == list(range(17))
    expected = {(voice, old, new) for voice in range(4) for old in range(3) for new in range(3) if old != new}
    assert {tuple(item) for item in source['directed_algorithm_transitions']} == expected
    handoff = proofs['handoff']
    assert handoff['status'] == 'PASS_ACTUAL_CF_DSP_NONBLOCKING_STATE_HANDOFF'
    assert handoff['frames'] == 800 and set(handoff['owners']) == {'0', '1'}
    assert sum(handoff['owners'].values()) == 800 and all(value > 0 for value in handoff['owners'].values())
    assert handoff['worker_calls_per_frame_max'] <= 8
    for key in ('transport_sequence_wrap', 'full_transport_sequence_wrap', 'zero_sequence_cf_request',
                'startup_disabled_cf', 'startup_flag_poisoned_reset', 'repeated_zero_sequence_feedback',
                'poisoned_consumer_valid_reset', 'native_ring_counters_wrap', 'poisoned_epoch_reset'):
        assert handoff[key] is True, ('Missing directed handoff coverage', key)
    assert handoff['counters']['pk_nhb_inner_calls'] > 0
    assert handoff['counters']['pk_nhb_handoff_jobs'] > 0
    assert all(value == 0 for value in handoff['steady_before'].values())
    timing = {name: check_interactive(proofs[name], name, receipts[name])
              for name in ('lifecycle', 'matrix', 'scenes')}
    lifecycle = proofs['lifecycle']
    assert lifecycle['status'] == 'PASS_FULL_MAP_LIFECYCLE_MODEL_SCOPE'
    assert proofs['scenes']['status'] == 'PASS_FULL_MAP_SCENE_FADER_MODEL_SCOPE'
    labels = {event['label'] for event in lifecycle['events']}
    assert {'stop-0', 'start-0', 'part-2', 'part-0', 'bank-1', 'bank-0', 'fresh-CF-Hat-within-generation'} <= labels
    assert lifecycle['independent_source']['mode_masks'] == [7] * 4
    handoff_state = lifecycle['state_handoff']
    assert handoff_state['status'] == 'PASS_ACTUAL_IMAGE_ON_DEMAND_HANDOFF_AND_GENERATIONS'
    counters = handoff_state['counters']
    assert lifecycle['events'][-1]['counts'] == counters
    assert counters['pk_nhb_switches'] >= 20 and counters['pk_prod_generation'] >= 7
    assert counters['pk_nhb_inner_calls'] > 0 and counters['pk_nhb_handoff_jobs'] > 0
    assert counters['pk_nhb_produced'] >= counters['pk_nhb_completed'] > 0
    assert counters['pk_nhb_snapshot_requests'] >= counters['pk_nhb_snapshot_completed'] > 0
    assert all(counters[key] == 0 for key in ('pk_nhr_failures', 'pk_nhb_overflows', 'pk_nhb_clock_errors'))
    matrix = proofs['matrix']
    assert matrix['status'] == 'PASS_FULL_MAP_PRODUCTION_MATRIX_MODEL_SCOPE'
    assert matrix['expected_tuples'] == 243 and not matrix['missing_tuples']
    assert len(matrix['independent_source']['combinations']) == 243
    assert matrix['independent_source']['mode_masks'] == [7] * 4
    assert matrix['independent_source']['algorithm_masks'] == [577, 642, 276, 1064]
    kernel = proofs['linked_synthesis']
    assert kernel['status'] == 'PASS_ACTUAL_LINKED_KERNEL_NATIVE_PCM_FULLSTATE_RNG_HOLD'
    assert set(kernel['results']) == {'nt', 'ah', 'slap'}
    for name, result in kernel['results'].items():
        assert result['calls'] > 0 and result['native_samples'] > 0
        assert result['modes'] == ([1, 2] if name == 'nt' else [0, 1, 2])
        assert {0, 1, 2, 16, 17, 18, 19, 20, 21, 39, 41} <= set(result['counts'])
        assert result['edge_rows'] >= 8 and result['invalid_table_return_and_state'] is True
    prepare = proofs['prepare_native']
    assert prepare['status'] == 'PASS_FAST_PREPARE_ALL_FAMILY_STATE_CLOCK_AND_EVENT_OBSERVATION'
    assert prepare['prepare_events'] >= 6000 and prepare['poisoned_prepare_events'] >= 858
    assert prepare['bounded_delta_cases'] >= 24573 and prepare['unsigned_fallback_cases'] >= 30000
    resonant = proofs['resonant_linked']
    assert resonant['status'] == 'PASS_LINKED_CF_ORIGINAL_PCM_STATE_RNG_CLOCK'
    assert resonant['PKFM17_runtime_sha256'] == baseline.ELF_SHA256
    assert resonant['CF_hz'] == CLOCKS['CF']
    for variant in ('baseline', 'candidate'):
        result = resonant['results'][variant]
        check_inputs(result['source_sha256'])
        execution = result['execution']
        assert execution['correctness'] == 'passed'
        assert execution['frames'] >= 3360 and execution['state_snapshots'] == execution['frames']
        assert execution['native_samples'] >= 83670
        assert execution['algorithm_layouts'] == 2 and execution['mode_rows'] == 5
        assert result['direct']['status'] == 'PASS_RAW_STATE_PCM_RNG_GUARDS_MAC_ABI'
        assert result['direct']['cases'] >= 4320
    return receipts, timing


def dsp_identity(candidate):
    """Prior DSP-only proofs are reusable only for byte-identical uploads."""
    uploads = {}
    for core in ('A', 'B'):
        name = f'dsp-{core}.upload.bin'
        old, new = baseline.DEFAULT_BUILD / name, candidate / name
        assert sha(old) == sha(new), ('DSP upload changed: fresh DSP/FX qualification required', core)
        uploads[core] = dict(candidate=str(new), baseline=str(old), sha256=sha(new), bytes=new.stat().st_size)
    reused = {}
    for name in ('SNAPSHOT_DSP_GATE.json', 'STATE_STOCK_FX_GATE.json'):
        path = baseline.DEFAULT_BUILD / name
        proof = read(path)
        assert proof['status'].startswith('PASS_')
        check_inputs(proof.get('inputs', {}), missing_card=True)
        check_inputs(proof.get('source_sha256', {}))
        reused[name] = dict(path=str(path), sha256=sha(path), status=proof['status'],
                            scope='Prior DSP-only proof reused through candidate/baseline A/B upload byte identity')
    return dict(uploads=uploads, reused_DSP_only_receipts=reused)


def main():
    global DEFAULT_BUILD, IMAGE_SHA256, ELF_SHA256
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--work', type=Path, default=DEFAULT_WORK)
    parser.add_argument('--controls', type=Path, default=CONTROL_WORK)
    parser.add_argument('--proof-index', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'modules/perky/hybrid/REMAINING_CF_QUALIFICATION.json')
    args = parser.parse_args()
    DEFAULT_BUILD = args.candidate.resolve()
    work, controls, output = args.work.resolve(), args.controls.resolve(), args.output.resolve()
    work.mkdir(parents=True, exist_ok=True)
    if output.exists():
        history = work / 'qualification-history'
        history.mkdir(exist_ok=True)
        previous = history / (sha(output) + '.json')
        if not previous.exists():
            shutil.copyfile(output, previous)
        output.unlink()
    index_path = args.proof_index.resolve()
    index = read(index_path)
    IMAGE_SHA256, ELF_SHA256 = index['image_sha256'], index['elf_sha256']
    assert IMAGE_SHA256 != baseline.IMAGE_SHA256 and ELF_SHA256 != baseline.ELF_SHA256
    build_path = DEFAULT_BUILD / 'BUILD.json'
    build = read(build_path)
    assert build['main_sha256'] == IMAGE_SHA256 and build['runtime_sha256'] == ELF_SHA256
    image = DEFAULT_BUILD / 'probe' / f"mainos_{build['version']}.bin"
    elf = DEFAULT_BUILD / 'probe/platform/runtime.elf'
    assert sha(image) == IMAGE_SHA256 and sha(elf) == ELF_SHA256
    check_inputs(build['source_sha256'])
    budget_path = ROOT / 'modules/perky/hybrid/EMULATOR_BUDGET.json'
    assert sha(budget_path) == BUDGET_SHA256
    frozen = read(budget_path)
    assert frozen['clocks'] == CLOCKS and frozen['observer_sha256'] == OBSERVER_SHA256
    control_build = read(baseline.DEFAULT_BUILD / 'BUILD.json')
    assert control_build['main_sha256'] == baseline.IMAGE_SHA256 and control_build['runtime_sha256'] == baseline.ELF_SHA256
    assert sha(baseline.DEFAULT_BUILD / 'probe/mainos_PKFM17.bin') == baseline.IMAGE_SHA256
    assert sha(baseline.DEFAULT_BUILD / 'probe/platform/runtime.elf') == baseline.ELF_SHA256
    check_inputs(control_build['source_sha256'])
    proof_receipts, interactive_timing = validate_proofs(index, image, elf, build)
    dsp = dsp_identity(DEFAULT_BUILD)
    receipts = {str(build_path): sha(build_path), str(index_path): sha(index_path), str(budget_path): BUDGET_SHA256}
    candidate_paths, control_paths = sorted(work.rglob('ROW.json')), sorted(controls.rglob('ROW.json'))
    assert len(candidate_paths) == len(control_paths) == 8, 'Exactly eight candidate and matched control rows are required'
    rows, assessments, controls_by_case = {}, [], {}
    for path in control_paths:
        key, row, assessment, bound = baseline.validate_row(path, control_build, frozen)
        assert key not in controls_by_case
        controls_by_case[key] = row
        receipts.update(bound)
    for path in candidate_paths:
        key, row, assessment, bound = validate_row(path, build, frozen)
        assert key not in rows
        rows[key] = row
        assessments.append(assessment)
        receipts.update(bound)
    expected = {(kind, fourth) for kind in V3 for fourth in V4}
    assert set(rows) == set(controls_by_case) == expected
    changes = []
    for key, row in rows.items():
        control = controls_by_case[key]
        fixture = read(Path(row['resonant_workload']['fixture']['path']))
        control_fixture = read(Path(control['resonant_workload']['fixture']['path']))
        assert fixture['card_sha256'] == control_fixture['card_sha256'], ('Matched card bytes differ', key)
        assert fixture['banks'] == control_fixture['banks'], ('Matched MODE-lock fixtures differ', key)
        before = {metric: budget.metric(control, metric) for metric in budget.METRICS}
        after = {metric: budget.metric(row, metric) for metric in budget.METRICS}
        changes.append(dict(v3_case=key[0], voice4_case=key[1], control_case=control['case'], case=row['case'],
                            before_us=before, after_us=after,
                            candidate_minus_PKFM17_us={metric: after[metric] - before[metric] for metric in budget.METRICS},
                            saved_us={metric: before[metric] - after[metric] for metric in budget.METRICS}))
    nominal_misses = {row['case']: row['full_ISR']['modeled_misses'] for row in rows.values()}
    nominal_misses.update({name: value['nominal_deadline_misses'] for name, value in interactive_timing.items()})
    interactive_peak_checks = {name: dict(measured_us=value['max_us'],
                                         ceiling_us=frozen['budgets_us']['full_ISR_peak'],
                                         pass_budget=value['max_us'] <= frozen['budgets_us']['full_ISR_peak'])
                               for name, value in interactive_timing.items()}
    pass_budget = all(item['pass_budget'] for item in assessments) and all(
        item['pass_budget'] for item in interactive_peak_checks.values())
    pass_nominal = not any(nominal_misses.values())
    passed = pass_budget and pass_nominal
    result = dict(schema='octabam.perky.remaining-cf-qualification.v1',
                  status='PASS_FROZEN_BUDGET_MODEL_SCOPE' if passed else 'FAIL_HOLD',
                  admission='PHYSICAL_ACCEPTANCE_STILL_REQUIRED' if passed else 'HOLD_FOR_PERFORMANCE_WORK',
                  functional_status='PASS_NEW_IMAGE_SOURCE_HANDOFF_LIFECYCLE_MATRIX_SCENES_AND_EIGHT_EXACT_WORKLOADS',
                  pass_budget=pass_budget,
                  nominal_timing_status='PASS_NOMINAL_DEADLINES_MODEL_SCOPE' if pass_nominal else 'FAIL_NOMINAL_DEADLINES',
                  nominal_deadline_misses=nominal_misses,
                  hardware_validated=False, version=build['version'], source_commit=build['source_commit'],
                  image_sha256=IMAGE_SHA256, elf_sha256=ELF_SHA256,
                  clocks=CLOCKS, observer_sha256=OBSERVER_SHA256, reference_oracle_sha256=ORACLE_SHA256,
                  budget_sha256=BUDGET_SHA256, frames_per_case=FRAMES, total_requested_transport_frames=FRAMES * 8,
                  controls=dict(version='PKFM17', image_sha256=baseline.IMAGE_SHA256,
                                elf_sha256=baseline.ELF_SHA256, frames_per_case=FRAMES),
                  assessments=assessments, changes_from_matched_PKFM17=changes,
                  proof_index=proof_receipts, interactive_timing=interactive_timing,
                  interactive_full_ISR_peak_checks=interactive_peak_checks, DSP_reuse_identity=dsp,
                  receipts=receipts, source_sha256={str(Path(__file__).relative_to(ROOT)): sha(Path(__file__))},
                  limits=[
                      'Candidate measurements use a new actual image/ELF, unchanged original-source oracle, frozen cycle observer, CF264/PIT132 clocks and calibrated seven-ceiling budget.',
                      'All eight deltas compare matched 32768-frame PKFM17 controls with identical voice selections, MODE fixture order and all fourteen retained FX; they do not use unmatched historical maxima as hardware multipliers.',
                      'New-image 5355-frame direct source/state/RNG, 800-frame handoff, lifecycle, selector matrix and scene proofs are required. Prior CF proofs are not transferred to this changed image.',
                      'Native preparation and Resonant standalone proofs remain separately scoped; they do not replace the linked actual-image source gate.',
                      'Only DSP-only snapshot/stock-FX proofs are reused, and only after actual candidate A/B upload bytes match PKFM17 exactly.',
                      'Runtime exact-source reports compare original-reference PCM and DSP Hat state/side/clock/feedback. Raw CF state is checked separately by the new-image direct source gate.',
                      'Per-track activity counts were extracted by the source-bound calibrated adapter before deliberate raw-dump cleanup; aggregate counts and hashes cannot establish replayable or gap-free stock audio.',
                      'Alternate rows verify both source modes and MODE locks alternating within each 45-trigger pattern, with one repeated mode at its loop boundary; no exact runtime switch-count claim.',
                      'Valid exact workloads may fail the fixed performance budget or nominal deadlines and are recorded as FAIL_HOLD, not discarded or called hardware-ready.',
                      'The local model does not establish physical cache, SDRAM, card, bus or IRQ timing, UI acceptance, or Octatrack hardware admission.'])
    output.parent.mkdir(parents=True, exist_ok=True)
    pending = output.with_suffix(output.suffix + '.pending')
    pending.write_text(json.dumps(result, indent=2) + '\n')
    pending.replace(output)
    print(result['status'], result['admission'])
    raise SystemExit(0 if passed else 1)


if __name__ == '__main__':
    main()

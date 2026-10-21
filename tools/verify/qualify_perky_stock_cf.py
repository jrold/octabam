#!/usr/bin/env python3
"""Qualify a new stock-CF candidate against immutable PKFM20 controls.

Frozen checks execute in private namespaces. Candidate and control images,
drivers and receipts cannot overwrite each other's validation state.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import shutil
from types import SimpleNamespace

import measure_perky_stock_cf as measurement
import qualify_perky_remaining_cf as frozen

ROOT = frozen.ROOT
WORK = ROOT / 'out/perky/hybrid/stock-cf-optimization'
CONTROL_BUILD = ROOT / 'out/perky/hybrid/full-map-remaining-cf-mix-v1'
CONTROL_WORK = ROOT / 'out/perky/hybrid/resonant-cf-optimization/final-workload'
CONTROL_QUALIFICATION = ROOT / 'modules/perky/hybrid/REMAINING_CF_QUALIFICATION.json'
CHECKS_SHA256 = '9c520071279406e40932cc057edc67368686014e3ade2393587a919a811174f9'
CONTROL_IMAGE_SHA256 = '9bae33446c3206e200edabee5b8e1ee4eb1e40f950e2de2e5157cea6a59d6935'
CONTROL_ELF_SHA256 = 'ff1ea42382eb39d64db8a581c373502c011dd5d16dc3ef2df4f2d5f49468f8e2'
CONTROL_QUALIFICATION_SHA256 = 'd63df85fd69fddd1cfd98b304d8f1a83a8009e0ae136c3382220e121b6c69384'
MEASUREMENT_SHA256 = '90b20e961c53b5669591eeae4c7dea8d2f1f3d8a40819956da7618ce6941b843'
PROFILE_SHA256 = '4064554cd98ebbbd334ed2745616d400f35358abcd770969e13b92c2ad012380'
SLAP_PROOF_SHA256 = 'a9fccc6d45b3d40fb836d6ca013278be43e71e4eea31b5d7ae17bd0ff3477b76'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def function_source(path, name):
    source = Path(path).read_text()
    nodes = [node for node in ast.parse(source).body
             if isinstance(node, ast.FunctionDef) and node.name == name]
    assert len(nodes) == 1
    return ''.join(source.splitlines(keepends=True)[nodes[0].lineno - 1:nodes[0].end_lineno])


def reconstruct_adapter(driver_path, original_path):
    """Rebuild an inspected wrapper using source text, without runtime imports."""
    source = function_source(driver_path, 'main')
    assert source.count("    namespace['main']()") == 1
    source = source.replace("    namespace['main']()", '    return text', 1)
    namespace = dict(__file__=str(driver_path), ROOT=ROOT, Path=Path,
                     original=SimpleNamespace(main=None, __file__=str(original_path)),
                     generator=None,
                     inspect=SimpleNamespace(getsource=lambda unused: function_source(original_path, 'main')))
    exec(compile(source, str(driver_path) + ':qualification-reconstruction', 'exec'), namespace)
    return namespace['main']()


def checks(build_directory, *, candidate):
    """Clone the source-pinned checker without mutating its imported module."""
    helper = Path(frozen.__file__).resolve()
    assert sha(helper) == CHECKS_SHA256, 'Frozen PKFM20 qualification helper changed'
    source = helper.read_text()
    if candidate:
        before = "ROOT / 'tools/verify/measure_perky_remaining_cf.py'"
        assert source.count(before) == 2
        source = source.replace(before, "ROOT / 'tools/verify/measure_perky_stock_cf.py'")
        before = "'Path(_calibration_source), Path(_resonant_driver), Path(_resonant_helpers))}'"
        assert source.count(before) == 1
        source = source.replace(before,
            "'Path(_calibration_source), Path(_resonant_driver), Path(_resonant_helpers), Path(_remaining_helpers))}'", 1)
        before = "    assert row['inputs'][str(helpers)] == sha(helpers), 'Original Resonant helper is absent/unbound'"
        assert source.count(before) == 1
        source = source.replace(before, before + '''
    remaining_helpers = ROOT / 'tools/verify/measure_perky_remaining_cf.py'
    assert row['inputs'][str(remaining_helpers)] == sha(remaining_helpers), 'Frozen remaining-CF helper is absent/unbound'
''', 1)
    namespace = dict(__name__='stock_cf_private_checks', __file__=str(helper))
    exec(compile(source, str(helper), 'exec'), namespace)
    metadata = read(build_directory / 'BUILD.json')
    namespace.update(DEFAULT_BUILD=build_directory, IMAGE_SHA256=metadata['main_sha256'],
                     ELF_SHA256=metadata['runtime_sha256'])
    return namespace


def bound_input(proof, path):
    path = Path(path).resolve()
    expected = sha(path)
    names = {str(path), str(path.relative_to(ROOT))} if path.is_relative_to(ROOT) else {str(path)}
    assert any(mapping.get(name) == expected for key in ('inputs', 'source_sha256')
               for mapping in [proof.get(key, {})] for name in names), ('Unbound proof input', path)
    return expected


def helper_bindings(proof, candidate_checks, elf, required):
    helpers = proof.get('helpers', [proof['helper']] if 'helper' in proof else [])
    assert isinstance(helpers, list) and helpers
    actual_symbols = set()
    for helper in helpers:
        assert helper['name'] not in actual_symbols
        assert helper['linked_equals_proven'] is True and helper['boot_readback_equals_linked'] is True
        address, body = candidate_checks['elf_symbol'](elf, helper['name'])
        assert address == helper['linked_address'] and len(body) == helper['bytes'] > 0
        assert hashlib.sha256(body).hexdigest() == helper['sha256']
        actual_symbols.add(helper['name'])
    assert set(required) <= actual_symbols


def replay_binding(proof, candidate_checks, count):
    proof_paths = [Path(path) for path, expected in proof['source_sha256'].items()
                   if Path(path).name == 'RESULT.json' and expected == proof['proof_sha256']]
    assert len(proof_paths) == 1
    standalone = read(proof_paths[0])
    assert standalone['status'].startswith('PASS_') and standalone['cases'] == count
    assert standalone['same_image_cycle_controls'] is True
    candidate_checks['check_inputs'](standalone['source_sha256'])
    execution_binding = proof['executed_binary_binding']
    assert execution_binding and all(value is True for value in execution_binding.values())
    assert {'full_binary_equals_pinned_ELF_objcopy', 'loaded_helper_equals_pinned_ELF_symbol',
            'symbols_equal_pinned_ELF_nm'} <= set(execution_binding)
    replay = proof['replay']
    assert replay['status'].startswith('PASS_') and replay['cases'] == count
    assert replay['inputs_unchanged_after_execution'] is True
    candidate_checks['check_inputs'](replay['inputs'])
    assert replay['inputs']
    for path, expected in replay['inputs'].items():
        assert proof['source_sha256'][path] == expected
    output = Path(replay['output_path'])
    assert sha(output) == replay['output_sha256'] == proof['source_sha256'][str(output)]
    execution = read(output)
    assert execution['status'] == replay['status'] and execution['cases'] == count
    assert execution['same_image_cycle_controls'] is True
    assert proof['same_image_cycle_controls'] is True


def direct_resampler(proof, receipt, build, image, elf):
    assert proof['status'] == 'PASS_EXACT_SIGNED_RATIONAL_SOURCE_PCM_CLOCK_EMAC_ABI'
    assert proof['actual_CF_cases'] == 9996 and proof['exhaustive_difference_phase_cases'] == 19267437
    assert proof['helper_elf_sha256'] == sha(elf)
    directory = Path(receipt['path']).parent
    for path in (image, elf, directory / 'reference.dylib', directory / 'canary.elf', directory / 'canary.bin'):
        assert proof['inputs'][str(path)] == sha(path)
    for path in ('tools/verify/verify_perky_resample_signed.py', 'tools/verify/verify_perky_resample_lut.py',
                 'tools/perky/generate_cf_resample_signed.py', 'tools/perky/generate_cf_resample_lut.py',
                 'tools/verify/verify_perky_hybrid_runtime.py', 'tools/emu/emu_bringup.py',
                 'modules/perky/cf_native_clock.h'):
        bound_input(proof, ROOT / path)
    source = directory / 'source-resample-signed.s'
    generated_sha = bound_input(proof, source)
    build_path = image.parent.parent
    assert build['source_sha256'][str(build_path.relative_to(ROOT) / source.name)] == generated_sha
    adapter = directory / 'PROOF_ADAPTER.py'
    assert sha(adapter) == proof['proof_adapter_sha256']
    # Reconstruct the current source-bound adapter without executing target code.
    driver_path = ROOT / 'tools/verify/verify_perky_resample_signed.py'
    original_path = ROOT / 'tools/verify/verify_perky_resample_lut.py'
    assert adapter.read_text() == reconstruct_adapter(driver_path, original_path)
    assert len(proof['PCM_sha256']) == 64


def trace_source_binding(index, build, image, elf, candidate_checks):
    if not build.get('stock_cf_options', {}).get('trace'):
        return
    proof, receipt = candidate_checks['bound_proof'](index['proofs']['source'], image, elf)
    counts = proof['trace_enabled_frame_counts']
    assert len(counts) == 2 and all(type(count) is int and count > 0 for count in counts)
    assert sum(counts) == proof['frames'] == 5355
    driver = ROOT / 'tools/verify/verify_perky_stock_cf_sources.py'
    original = ROOT / 'tools/verify/verify_perky_full_map_sources.py'
    bound_input(proof, driver)
    bound_input(proof, original)
    adapter = Path(receipt['path']).parent / 'source-gate/PROOF_ADAPTER.py'
    assert sha(adapter) == proof['proof_adapter_sha256']
    assert adapter.read_text() == reconstruct_adapter(driver, original)


def delay_mix_binding(proof, build, image, elf, candidate_checks):
    assert proof['status'] == 'PASS_FINAL_IMAGE_STOCK_DELAY_MIX_PROOF_AND_BOOT_BINDING'
    assert proof['standalone_cases'] == 4096
    assert proof['standalone_fast_cases'] == 2458 and proof['standalone_fallback_cases'] == 1638
    assert proof['standalone_fast_cases'] + proof['standalone_fallback_cases'] == proof['standalone_cases']
    helper, detour = proof['helper'], proof['detour']
    assert helper['name'] == 'pk_stock_delay_steady_mix' and helper['bytes'] == 974
    address, body = candidate_checks['elf_symbol'](elf, helper['name'])
    assert body[-6:] == b'\x4e\xf9' + (0x4000377a).to_bytes(4, 'big')
    expected = b'\x4e\xf9' + address.to_bytes(4, 'big') + b'\x4e\x71' * 3
    assert detour['address'] == 0x40003734 and detour['bytes'] == 12 and detour['padding'] == 'three NOPs'
    assert hashlib.sha256(expected).hexdigest() == detour['sha256']
    offset = lambda at: at - 0x40000400
    main = image.read_bytes()
    stock = (ROOT / 'out/raw/section_3_MAIN_OS.bin').read_bytes()
    assert main[offset(0x40003734):offset(0x40003740)] == expected
    assert main[offset(0x40003740):offset(0x4000377a)] == stock[offset(0x40003740):offset(0x4000377a)]
    assert hashlib.sha256(stock[offset(0x40003734):offset(0x4000377a)]).hexdigest() == '85f0ddde1e0dd2b27983d4c804e8576dccbdbbb7bc0b011b7a1c56e412669908'
    sites = build['stock_cf_delay_contract']['sites']
    assert len(sites) == 1 and sites[0]['address'] == 0x40003734 and sites[0]['end'] == 0x40003740
    assert sites[0]['continuation'] == 0x4000377a and sites[0]['entry'] == helper['name']
    for filename in ('tools/verify/verify_stock_delay_mix_binding.py',
                     'tools/verify/verify_stock_source_mix_binding.py',
                     'tools/perky/generate_stock_delay_steady_mix.py'):
        bound_input(proof, ROOT / filename)
    execution = read(proof['replay']['output_path'])
    assert execution['fast_cases'] == proof['standalone_fast_cases']
    assert execution['fallback_cases'] == proof['standalone_fallback_cases']
    assert execution['mean_saved_cycles_fallback'] == proof['standalone_fallback_saved_cycles']


def slap_span_binding(index, build, image, elf, candidate_checks):
    """Selected Slap spans need the wide proof's executed and final-code chain."""
    if not build.get('stock_cf_options', {}).get('slap'):
        return {}
    specification = index['proofs']['slap_span_binding']
    assert specification['linked_candidate'] is True
    proof, receipt = candidate_checks['bound_proof'](specification, image, elf)
    assert proof['status'] == 'PASS_FINAL_IMAGE_SLAP_SPAN_PROOF_AND_BOOT_BINDING'
    assert proof['linked_candidate'] is True
    native_path = ROOT / 'out/perky/hybrid/slap-span-v2/RESULT.json'
    assert Path(proof['proof_path']).resolve() == native_path
    assert sha(native_path) == proof['proof_sha256'] == SLAP_PROOF_SHA256
    bound_input(proof, native_path)
    native = read(native_path)
    assert native['status'] == 'PASS_EXACT_TARGET_NATIVE_AND_FULL_RING_ABI'
    assert native['CPU_hz'] == frozen.CLOCKS['CF']
    candidate_checks['check_inputs'](native['input_sha256'])
    expected = native['results']['span']
    assert expected['execution'] == dict(frames=2880, state_snapshots=2880, native_samples=80334,
                                        algorithm_layouts=1, mode_rows=3, correctness='passed')
    assert expected['delay']['status'] == 'PASS_TARGET_RING_PCM_STATE_ABI'
    assert expected['delay']['cases'] == 76880
    assert expected['delay']['span_entries'] > 0 and expected['delay']['generic_entries'] > 0
    assert proof['standalone_frames'] == proof['standalone_state_snapshots'] == 2880
    assert proof['standalone_delay_cases'] == 76880
    standalone = proof['standalone_elf']
    standalone_elf = Path(standalone['path']).resolve()
    assert sha(standalone_elf) == standalone['sha256'] == expected['elf_sha256']
    assert standalone['binary_base'] == 0x40000400
    bound_input(proof, standalone_elf)
    names = ('pk_cf_slap_delay_span', 'pk_cf_slap_delay_span_fast', 'pk_cf_slap_delay_block')
    records = {helper['name']: helper for helper in proof['helpers']}
    assert len(proof['helpers']) == len(records) == 3 and set(records) == set(names)
    old = {name: candidate_checks['elf_symbol'](standalone_elf, name) for name in names}
    actual = {name: candidate_checks['elf_symbol'](elf, name) for name in names}
    generic = actual[names[2]][0]
    assert old[names[0]][1][-6:] == b'\x4e\xf9' + old[names[2]][0].to_bytes(4, 'big')
    assert actual[names[0]][1] == old[names[0]][1][:-4] + generic.to_bytes(4, 'big')
    for name in names:
        record, (address, body), (old_address, proven) = records[name], actual[name], old[name]
        assert record['linked_address'] == address and record['bytes'] == len(body) > 0
        assert record['sha256'] == hashlib.sha256(body).hexdigest()
        assert record['standalone_address'] == old_address and record['standalone_bytes'] == len(proven)
        assert record['standalone_sha256'] == hashlib.sha256(proven).hexdigest()
        assert record['boot_readback_equals_linked'] is True
        assert record['linked_equals_relocated_proven'] is True
        assert record['relocated_tail_binding'] is (name == names[0])
        if name != names[0]:
            assert record['linked_equals_proven'] is True and body == proven
    relocation = proof['relocated_tail']
    assert relocation['opcode'] == '4ef9' and relocation['only_absolute32_operand_changed'] is True
    assert relocation['source_relinked_at_final_address'] is True
    assert relocation['standalone_generic_address'] == old[names[2]][0]
    assert relocation['final_generic_address'] == generic
    relocated_elf = Path(relocation['elf_path'])
    assert sha(relocated_elf) == relocation['elf_sha256']
    bound_input(proof, relocated_elf)
    assert all(candidate_checks['elf_symbol'](relocated_elf, name) == actual[name] for name in names[:2])
    caller = proof['caller']
    assert caller['name'] == 'pk_cf_slap_render'
    caller_at, caller_body = candidate_checks['elf_symbol'](elf, caller['name'])
    assert caller_at == caller['linked_address'] and len(caller_body) == caller['bytes']
    assert hashlib.sha256(caller_body).hexdigest() == caller['sha256']
    assert caller['span_absolute_JSR_present'] is True and caller['boot_readback_equals_linked'] is True
    assert b'\x4e\xb9' + actual[names[0]][0].to_bytes(4, 'big') in caller_body
    binding = proof['executed_binary_binding']
    assert set(binding) == {'full_binary_equals_pinned_ELF_objcopy',
                            'loaded_helper_slices_equal_pinned_ELF_symbols', 'symbols_equal_pinned_ELF_nm'}
    assert all(value is True for value in binding.values())
    replay = proof['replay']
    assert replay['inputs_unchanged_after_execution'] is True
    assert replay['cycle_instruction_stack_rows_identical'] is True
    assert replay['frames'] == replay['state_snapshots'] == 2880
    assert replay['delay_cases'] == 76880 and replay['native_samples'] == 80334
    candidate_checks['check_inputs'](replay['inputs'])
    candidate_checks['check_inputs'](replay['outputs'])
    for path, expected_sha in {**replay['inputs'], **replay['outputs']}.items():
        assert proof['source_sha256'][path] == expected_sha
    inputs = {Path(path).name: Path(path) for path in replay['inputs']}
    outputs = {Path(path).name: Path(path) for path in replay['outputs']}
    assert {'target.bin', 'target.nm', 'runner', 'native.dylib'} <= set(inputs)
    assert set(outputs) == {'EXECUTION.json', 'DELAY.json', 'costs.csv', 'alignment.json', 'run.log'}
    loaded = inputs['target.bin'].read_bytes()
    for address, body in old.values():
        offset = address - standalone['binary_base']
        assert loaded[offset:offset + len(body)] == body
    assert read(outputs['EXECUTION.json']) == replay['execution'] == expected['execution']
    assert read(outputs['DELAY.json']) == replay['delay'] == expected['delay']
    for name in ('costs.csv', 'alignment.json'):
        assert outputs[name].read_bytes() == (standalone_elf.parent / name).read_bytes()
    for path in ('tools/verify/verify_perky_slap_span_binding.py', 'tools/harness/perky_cf/slap_span_delay.s',
                 'modules/perky/cf_synthesis_delay.s', 'tools/perky/generate_cf_slap_span.py'):
        bound_input(proof, ROOT / path)
    return dict(slap_span_binding=receipt)


def stock_extensions(index, build, candidate_checks, image, elf):
    """Separate new stock detours from normally called CF helper proofs."""
    stock = build.get('stock_cf_required_proofs')
    direct = build.get('stock_cf_required_direct_proofs')
    for field, required in (('stock_cf_required_proofs', stock), ('stock_cf_required_direct_proofs', direct)):
        assert isinstance(required, list) and len(required) == len(set(required)), ('Builder must declare proof list', field)
        assert all(isinstance(name, str) and name for name in required)
        assert index.get(field) == required, ('Proof index differs from selected builder contracts', field)
    assert set(direct) == {'resample_linked', 'publish_binding'}
    assert not set(stock) & set(direct)
    if build.get('stock_cf_options', {}).get('stock_delay'):
        assert 'stock_delay_mix' in stock, 'Selected stock DELAY specialization needs its actual-image binding proof'
    contracts = build.get('stock_cf_proof_contracts', {})
    receipts = {}
    for name in stock + direct:
        specification = index['proofs'][name]
        assert specification['linked_candidate'] is True
        proof, receipt = candidate_checks['bound_proof'](specification, image, elf)
        assert proof.get('linked_candidate') is True
        receipts[name] = receipt
        if name == 'resample_linked':
            direct_resampler(proof, receipt, build, image, elf)
            continue
        count = proof.get('standalone_cases', proof.get('cases'))
        minimum = contracts.get(name, {}).get('minimum_cases', 4096)
        assert type(minimum) is int and minimum > 0 and type(count) is int and count >= minimum
        required_symbols = contracts.get(name, {}).get('required_symbols', [])
        if name == 'publish_binding':
            assert proof['status'] == 'PASS_FINAL_IMAGE_PACKET_PUBLISH_PROOF_AND_BOOT_BINDING'
            assert count == 8192
            required_symbols = ['pk_prod_pack', 'pk_prod_clear']
        helper_bindings(proof, candidate_checks, elf, required_symbols)
        replay_binding(proof, candidate_checks, count)
        if name in direct:
            continue
        detours = proof.get('detours', [proof['detour']] if 'detour' in proof else [])
        assert isinstance(detours, list) and detours
        main = image.read_bytes()
        for detour in detours:
            assert detour['packaged_and_booted_match'] is True
            start = detour['address'] - 0x40000400
            data = main[start:start + detour['bytes']]
            assert start >= 0 and len(data) == detour['bytes'] > 0
            assert hashlib.sha256(data).hexdigest() == detour['sha256']
        assert proof['original_stock_remainder_unchanged'] is True
        if name == 'stock_delay_mix':
            delay_mix_binding(proof, build, image, elf, candidate_checks)
    return receipts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--work', type=Path, default=WORK / 'final-workload')
    parser.add_argument('--proof-index', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'modules/perky/hybrid/STOCK_CF_QUALIFICATION.json')
    args = parser.parse_args()
    assert sha(Path(measurement.__file__)) == MEASUREMENT_SHA256
    profile_source = ROOT / 'tools/verify/profile_perky_stock_cf_cost.py'
    assert sha(profile_source) == PROFILE_SHA256
    candidate, work, output = args.candidate.resolve(), args.work.resolve(), args.output.resolve()
    assert output != CONTROL_QUALIFICATION.resolve(), 'Never replace a frozen qualification'
    work.mkdir(parents=True, exist_ok=True)
    if output.exists():
        history = work / 'qualification-history'
        history.mkdir(exist_ok=True)
        previous = history / (sha(output) + '.json')
        if not previous.exists():
            shutil.copyfile(output, previous)
        output.unlink()
    assert sha(CONTROL_QUALIFICATION) == CONTROL_QUALIFICATION_SHA256
    ancestor = read(CONTROL_QUALIFICATION)
    assert ancestor['image_sha256'] == CONTROL_IMAGE_SHA256 and ancestor['elf_sha256'] == CONTROL_ELF_SHA256
    control_build = read(CONTROL_BUILD / 'BUILD.json')
    assert control_build['version'] == 'PKFM20'
    assert control_build['main_sha256'] == CONTROL_IMAGE_SHA256 and control_build['runtime_sha256'] == CONTROL_ELF_SHA256
    assert sha(CONTROL_BUILD / 'probe/mainos_PKFM20.bin') == CONTROL_IMAGE_SHA256
    assert sha(CONTROL_BUILD / 'probe/platform/runtime.elf') == CONTROL_ELF_SHA256
    control_checks = checks(CONTROL_BUILD, candidate=False)
    current_checks = checks(candidate, candidate=True)
    build = read(candidate / 'BUILD.json')
    index_path = args.proof_index.resolve()
    index = read(index_path)
    image = candidate / 'probe' / f"mainos_{build['version']}.bin"
    elf = candidate / 'probe/platform/runtime.elf'
    assert sha(image) == build['main_sha256'] == index['image_sha256'] != CONTROL_IMAGE_SHA256
    assert sha(elf) == build['runtime_sha256'] == index['elf_sha256'] != CONTROL_ELF_SHA256
    current_checks['check_inputs'](build['source_sha256'])
    control_checks['check_inputs'](control_build['source_sha256'])
    budget_path = ROOT / 'modules/perky/hybrid/EMULATOR_BUDGET.json'
    assert sha(budget_path) == frozen.BUDGET_SHA256
    budget = read(budget_path)
    assert budget['clocks'] == frozen.CLOCKS and budget['observer_sha256'] == frozen.OBSERVER_SHA256
    proof_receipts, timing = current_checks['validate_proofs'](index, image, elf, build)
    for name in ('dma', 'profile_final'):
        assert proof_receipts[name]['linked_candidate'] is True
    proof_receipts.update(stock_extensions(index, build, current_checks, image, elf))
    trace_source_binding(index, build, image, elf, current_checks)
    proof_receipts.update(slap_span_binding(index, build, image, elf, current_checks))
    paths = sorted(work.rglob('ROW.json'))
    control_paths = sorted(CONTROL_WORK.rglob('ROW.json'))
    assert len(paths) == len(control_paths) == 8
    controls, rows, assessments = {}, {}, []
    receipts = {str(path): sha(path) for path in
                (candidate / 'BUILD.json', CONTROL_BUILD / 'BUILD.json', CONTROL_QUALIFICATION,
                 Path(frozen.__file__), index_path, budget_path)}
    for path in control_paths:
        key, row, assessment, bound = control_checks['validate_row'](path, control_build, budget)
        assert key not in controls
        controls[key] = row
        receipts.update(bound)
    changes = []
    for path in paths:
        key, row, assessment, bound = current_checks['validate_row'](path, build, budget)
        assert key not in rows and key in controls
        rows[key] = row
        assessments.append(assessment)
        receipts.update(bound)
        control = controls[key]
        fixture = read(row['resonant_workload']['fixture']['path'])
        previous_fixture = read(control['resonant_workload']['fixture']['path'])
        assert fixture['card_sha256'] == previous_fixture['card_sha256'] and fixture['banks'] == previous_fixture['banks']
        before = {metric: frozen.budget.metric(control, metric) for metric in frozen.budget.METRICS}
        after = {metric: frozen.budget.metric(row, metric) for metric in frozen.budget.METRICS}
        changes.append(dict(v3_case=key[0], voice4_case=key[1], control_case=control['case'], case=row['case'],
                            before_us=before, after_us=after,
                            candidate_minus_PKFM20_us={metric: after[metric] - before[metric] for metric in before},
                            saved_us={metric: before[metric] - after[metric] for metric in before}))
    expected = {(kind, fourth) for kind in frozen.V3 for fourth in frozen.V4}
    assert set(rows) == set(controls) == expected
    peaks = {name: dict(measured_us=value['max_us'], ceiling_us=budget['budgets_us']['full_ISR_peak'],
                       pass_budget=value['max_us'] <= budget['budgets_us']['full_ISR_peak'])
             for name, value in timing.items()}
    misses = {row['case']: row['full_ISR']['modeled_misses'] for row in rows.values()}
    misses.update({name: value['nominal_deadline_misses'] for name, value in timing.items()})
    passed_budget = all(value['pass_budget'] for value in assessments) and all(value['pass_budget'] for value in peaks.values())
    passed = passed_budget and not any(misses.values())
    dsp = current_checks['dsp_identity'](candidate)
    for core in ('A', 'B'):
        assert sha(candidate / f'dsp-{core}.upload.bin') == sha(CONTROL_BUILD / f'dsp-{core}.upload.bin')
    result = dict(schema='octabam.perky.stock-cf-qualification.v1',
                  status='PASS_FROZEN_BUDGET_MODEL_SCOPE' if passed else 'FAIL_HOLD',
                  admission='PHYSICAL_ACCEPTANCE_STILL_REQUIRED' if passed else 'HOLD_FOR_PERFORMANCE_WORK',
                  functional_status='PASS_NEW_IMAGE_PROOFS_AND_EIGHT_EXACT_MATCHED_WORKLOADS',
                  pass_budget=passed_budget, hardware_validated=False, version=build['version'],
                  source_commit=build['source_commit'], image_sha256=sha(image), elf_sha256=sha(elf),
                  clocks=frozen.CLOCKS, observer_sha256=frozen.OBSERVER_SHA256,
                  reference_oracle_sha256=frozen.ORACLE_SHA256, budget_sha256=frozen.BUDGET_SHA256,
                  frames_per_case=32768, total_requested_transport_frames=262144,
                  controls=dict(version='PKFM20', image_sha256=CONTROL_IMAGE_SHA256, elf_sha256=CONTROL_ELF_SHA256,
                                qualification=str(CONTROL_QUALIFICATION), qualification_sha256=CONTROL_QUALIFICATION_SHA256,
                                frames_per_case=32768, PKFM17_ancestry=ancestor['controls']),
                  assessments=assessments, changes_from_matched_PKFM20=changes,
                  nominal_deadline_misses=misses,
                  nominal_timing_status='PASS_NOMINAL_DEADLINES_MODEL_SCOPE' if not any(misses.values()) else 'FAIL_NOMINAL_DEADLINES',
                  proof_index=proof_receipts, stock_cf_required_proofs=build['stock_cf_required_proofs'],
                  stock_cf_required_direct_proofs=build['stock_cf_required_direct_proofs'],
                  interactive_timing=timing, interactive_full_ISR_peak_checks=peaks, DSP_reuse_identity=dsp,
                  receipts=receipts, source_sha256={str(path.relative_to(ROOT)): sha(path) for path in
                                                  (Path(__file__).resolve(), Path(measurement.__file__), profile_source)},
                  limits=[
                      'All eight deltas use immediate matched PKFM20 controls with identical 32768-block final card fixtures; PKFM17 remains preserved ancestry, not the immediate comparison.',
                      'Original-source oracle, seven ceilings, native CF264/PIT132 clocks and frozen timing instrument are unchanged.',
                      'New actual-image source/state/RNG, handoff, lifecycle, selector matrix, scenes, DMA and profile proofs are required. New stock detours require executed-artifact/final-code/detour/boot bindings; ordinary CF helpers require actual linked execution or replay/final-code/boot bindings. Selected Slap spans additionally require the reconstructed-binary wide native/ring replay and final span/fallback/caller boot binding.',
                      'Runtime source PCM and DSP state/side/clock/feedback are checked; direct source gates separately check raw CF state. Aggregate source/post-FX activity and card reads do not establish replayable or gap-free stock audio.',
                      'Interactive captures may end with one entered but unreturned ISR; completed returns and nominal observations remain explicit.',
                      'Only byte-identical DSP-only evidence is reused. A valid exact workload that misses fixed timing ceilings remains FAIL_HOLD.',
                      'The local model is not physical Octatrack timing, UI acceptance, or hardware admission.'])
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + '.pending')
    temporary.write_text(json.dumps(result, indent=2) + '\n')
    temporary.replace(output)
    print(result['status'], result['admission'])
    raise SystemExit(0 if passed else 1)


if __name__ == '__main__':
    main()

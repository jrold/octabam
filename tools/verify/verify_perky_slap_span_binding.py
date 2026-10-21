#!/usr/bin/env python3
"""Bind frozen Slap native/ring proof artifacts to the final booted image.

Reconstruct the binary/symbol inputs actually consumed by the frozen runner,
replay it privately, and bind both the span kernel and immutable fallback.
The span's final external JMP is relocated explicitly; no target code or
frozen artifact is patched or overwritten.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess

import verify_perky_hybrid_runtime as rt
from verify_stock_source_mix_binding import symbol_bytes

ROOT = Path(__file__).resolve().parents[2]
PROOF = ROOT / 'out/perky/hybrid/slap-span-v2/RESULT.json'
BUILD = ROOT / 'out/perky/hybrid/full-map-stock-cf-v1'
ASSETS = ('pitch', 'chromatic', 'envelope1', 'envelope2', 'w0', 'w1', 'w2', 'w3',
          'm1', 'interp_a', 'interp_b', 'wt_base', 'wt_bank', 'closed', 'open', 'ride')
HELPERS = ('pk_cf_slap_delay_span', 'pk_cf_slap_delay_span_fast', 'pk_cf_slap_delay_block')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def mapping(paths):
    return {str(path): sha(path) for path in paths}


def check_inputs(inputs):
    for name, expected in inputs.items():
        path = Path(name)
        if not path.is_absolute():
            path = ROOT / path
        assert path.is_file() and sha(path) == expected, ('Input changed', name)


def binary_base(path):
    """objcopy starts at the first allocated, file-backed ELF section."""
    data = Path(path).read_bytes()
    assert data[:6] == b'\x7fELF\x01\x02'
    header = struct.unpack_from('>16sHHIIIIIHHHHHH', data)
    sections = [struct.unpack_from('>10I', data, header[6] + i * header[11])
                for i in range(header[12])]
    return min(section[3] for section in sections
               if section[2] & 2 and section[1] != 8 and section[5])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, default=BUILD)
    parser.add_argument('--proof', type=Path, default=PROOF)
    parser.add_argument('--work', type=Path)
    args = parser.parse_args()
    build, proof_path = args.build.resolve(), args.proof.resolve()
    work = (args.work or build / 'slap-span-binding-v1').resolve()
    work.mkdir(parents=True, mode=0o700, exist_ok=False)
    proof = json.loads(proof_path.read_text())
    assert proof['status'] == 'PASS_EXACT_TARGET_NATIVE_AND_FULL_RING_ABI'
    check_inputs(proof['input_sha256'])
    original_directory = proof_path.parent / 'span'
    standalone = original_directory / 'target.elf'
    expected = proof['results']['span']
    assert sha(standalone) == expected['elf_sha256']
    assert expected['execution'] == dict(frames=2880, state_snapshots=2880,
        native_samples=80334, algorithm_layouts=1, mode_rows=3, correctness='passed')
    assert expected['delay']['status'] == 'PASS_TARGET_RING_PCM_STATE_ABI'
    assert expected['delay']['cases'] == 76880
    assert expected['delay']['span_entries'] > 0 and expected['delay']['generic_entries'] > 0
    assert sha(original_directory / 'slap-generic-span.c') == expected['source_sha256']
    metadata_path = build / 'BUILD.json'
    metadata = json.loads(metadata_path.read_text())
    assert metadata['stock_cf_options']['slap'] is True
    check_inputs(metadata['source_sha256'])
    image = build / 'probe' / f"mainos_{metadata['version']}.bin"
    elf = build / 'probe/platform/runtime.elf'
    assert sha(image) == metadata['main_sha256'] and sha(elf) == metadata['runtime_sha256']
    assembly = ROOT / 'tools/harness/perky_cf/slap_span_delay.s'
    generic_source = ROOT / 'modules/perky/cf_synthesis_delay.s'
    generator = ROOT / 'tools/perky/generate_cf_slap_span.py'
    for path in (assembly, generic_source, generator):
        assert metadata['source_sha256'][str(path.relative_to(ROOT))] == proof['input_sha256'][str(path)] == sha(path)

    # The original artifact gap is closed against the already-pinned ELF,
    # never by trusting an unrecorded binary or symbol file independently.
    replay = work / 'replay'
    replay.mkdir(mode=0o700)
    commands = []

    def run(command, log=None):
        command = list(map(str, command))
        commands.append(command)
        if log:
            with Path(log).open('w') as output:
                subprocess.run(command, cwd=ROOT, check=True, stdout=output, stderr=subprocess.STDOUT)
        else:
            subprocess.run(command, cwd=ROOT, check=True, stdout=subprocess.DEVNULL)

    run(['m68k-elf-objcopy', '-O', 'binary', standalone, replay / 'target.bin'])
    reconstructed_nm = subprocess.check_output(['m68k-elf-nm', '-S', str(standalone)])
    (replay / 'target.nm').write_bytes(reconstructed_nm)
    assert (replay / 'target.bin').read_bytes() == (original_directory / 'target.bin').read_bytes()
    assert reconstructed_nm == (original_directory / 'target.nm').read_bytes()
    base = binary_base(standalone)
    assert base == 0x40000400, 'Frozen runner loads target.bin at its stock MAIN base'
    binary = (replay / 'target.bin').read_bytes()
    proven = {name: symbol_bytes(standalone, name) for name in HELPERS}
    for name, (address, data) in proven.items():
        assert binary[address - base:address - base + len(data)] == data, ('Loaded helper slice', name)

    original_runner = proof_path.parent / 'runner'
    assert sha(original_runner) == proof['input_sha256'][str(original_runner)]
    shutil.copy2(original_runner, replay / 'runner')
    assert sha(replay / 'runner') == sha(original_runner)
    native = (original_directory / 'native.dylib').resolve()
    assert sha(native) == proof['input_sha256'][str(native)]
    (replay / 'native.dylib').symlink_to(native)
    assets = (original_directory / 'assets').resolve()
    (replay / 'assets').symlink_to(assets, target_is_directory=True)
    asset_manifest = assets.parent / 'BUILD.json'
    asset_metadata = json.loads(asset_manifest.read_text())
    asset_paths = [assets / (name + '.bin') for name in ASSETS]
    for path in asset_paths:
        assert sha(path) == asset_metadata['inputs'][str(path)], ('Original asset fixture drift', path)
    dependencies = [Path(__file__).resolve(), ROOT / 'tools/verify/verify_stock_source_mix_binding.py',
        proof_path, standalone, original_directory / 'target.bin', original_directory / 'target.nm',
        original_directory / 'slap-generic-span.c', original_runner, native, asset_manifest,
        *asset_paths, assembly, generic_source, generator, metadata_path, image, elf]
    inputs_before = mapping(dependencies)
    replay_paths = [replay / 'target.bin', replay / 'target.nm', replay / 'runner',
                    replay / 'native.dylib', *[replay / 'assets' / (name + '.bin') for name in ASSETS]]
    replay_inputs = mapping(replay_paths)
    run([replay / 'runner', replay, replay / 'assets'], replay / 'run.log')
    check_inputs(inputs_before)
    check_inputs(replay_inputs)
    execution = json.loads((replay / 'EXECUTION.json').read_text())
    delay = json.loads((replay / 'DELAY.json').read_text())
    assert execution == expected['execution'], 'Frozen native execution result differs'
    assert delay == expected['delay'], 'Frozen complete-ring/ABI result differs'
    assert (replay / 'costs.csv').read_bytes() == (original_directory / 'costs.csv').read_bytes(), 'Replay cycle/instruction/stack rows differ'
    assert (replay / 'alignment.json').read_bytes() == (original_directory / 'alignment.json').read_bytes()

    # Generic fallback is entirely position-independent. Only the span's
    # final absolute external JMP differs between standalone and production.
    final = {name: symbol_bytes(elf, name) for name in HELPERS}
    generic_address = final['pk_cf_slap_delay_block'][0]
    old_generic_address = proven['pk_cf_slap_delay_block'][0]
    old_span = proven['pk_cf_slap_delay_span'][1]
    assert old_span[-6:] == b'\x4e\xf9' + old_generic_address.to_bytes(4, 'big')
    normalized_span = old_span[:-4] + generic_address.to_bytes(4, 'big')
    assert final['pk_cf_slap_delay_span'][1] == normalized_span, 'Span differs beyond its explicit final JMP relocation'
    for name in HELPERS[1:]:
        assert final[name][1] == proven[name][1], ('Unchanged helper differs', name)
    span_address = final['pk_cf_slap_delay_span'][0]
    relocated = work / 'relocated-helper.elf'
    run(['m68k-elf-gcc', '-mcpu=54455', '-nostdlib',
         f'-Wl,-Ttext=0x{span_address:x}', '-Wl,--entry=pk_cf_slap_delay_span',
         f'-Wl,--defsym,pk_cf_slap_delay_block=0x{generic_address:x}', assembly, '-o', relocated], work / 'relocation.log')
    for name in HELPERS[:2]:
        assert symbol_bytes(relocated, name) == final[name], ('Relinked tested assembly differs', name)
    caller_address, caller = symbol_bytes(elf, 'pk_cf_slap_render')
    call = b'\x4e\xb9' + span_address.to_bytes(4, 'big')
    assert call in caller, 'Final Slap renderer does not call the proven span helper'

    # Boot the actual packaged MAIN. No helper/fixture code is injected into
    # this machine; read back the real loader's installed bytes.
    boot = rt.g.emu.boot(str(image), count=200000000)
    assert boot.clean, (boot.stopped, boot.error)
    symbols = rt.g.load_elf_symbols(elf)
    assert int.from_bytes(boot.uc.mem_read(symbols['pk_hybrid_pcm_cookie'], 4), 'big') == 0x504b5052
    assert int.from_bytes(boot.uc.mem_read(symbols['pk_hybrid_rt_cookie'], 4), 'big') == 0x504b4852
    helpers = []
    for name in HELPERS:
        address, data = final[name]
        original_address, original_data = proven[name]
        assert bytes(boot.uc.mem_read(address, len(data))) == data, ('Boot helper readback', name)
        helpers.append(dict(name=name, standalone_address=original_address,
            standalone_bytes=len(original_data), standalone_sha256=digest(original_data),
            linked_address=address, bytes=len(data), sha256=digest(data),
            linked_equals_proven=name != HELPERS[0], linked_equals_relocated_proven=True,
            relocated_tail_binding=name == HELPERS[0], boot_readback_equals_linked=True))
    assert bytes(boot.uc.mem_read(caller_address, len(caller))) == caller
    check_inputs(inputs_before)
    check_inputs(replay_inputs)
    check_inputs(proof['input_sha256'])
    check_inputs(metadata['source_sha256'])
    output_paths = [replay / name for name in ('EXECUTION.json', 'DELAY.json', 'costs.csv', 'alignment.json', 'run.log')]
    report = dict(status='PASS_FINAL_IMAGE_SLAP_SPAN_PROOF_AND_BOOT_BINDING', linked_candidate=True,
        version=metadata['version'], source_commit=metadata.get('source_commit'),
        image_sha256=sha(image), elf_sha256=sha(elf), proof_path=str(proof_path), proof_sha256=sha(proof_path),
        standalone_elf=dict(path=str(standalone), sha256=sha(standalone), binary_base=base),
        standalone_frames=2880, standalone_state_snapshots=2880, standalone_delay_cases=76880,
        executed_binary_binding=dict(full_binary_equals_pinned_ELF_objcopy=True,
            loaded_helper_slices_equal_pinned_ELF_symbols=True, symbols_equal_pinned_ELF_nm=True),
        replay=dict(command=commands[1], execution=execution, delay=delay,
            frames=2880, state_snapshots=2880, delay_cases=76880,
            native_samples=80334, inputs=replay_inputs, inputs_unchanged_after_execution=True,
            outputs=mapping(output_paths), cycle_instruction_stack_rows_identical=True,
            scope='span_entries counts fast-loop sample iterations, not job calls'),
        helpers=helpers,
        relocated_tail=dict(opcode='4ef9', standalone_generic_address=old_generic_address,
            final_generic_address=generic_address, only_absolute32_operand_changed=True,
            source_relinked_at_final_address=True, elf_path=str(relocated), elf_sha256=sha(relocated)),
        caller=dict(name='pk_cf_slap_render', linked_address=caller_address, bytes=len(caller),
            sha256=digest(caller), span_absolute_JSR_present=True, boot_readback_equals_linked=True),
        source_sha256=dict(inputs_before, **{str(relocated): sha(relocated)}, **mapping(output_paths), **replay_inputs),
        commands=commands,
        limits=['Fresh replay establishes the frozen native/ring proof with reconstructed loaded binary/symbols and pinned native fixtures.',
                'Relocation/readback establishes final helper/fallback/caller identity, not a new full-workload timing or lifecycle result.',
                'The standalone combined layout uses retained cf-placement bodies for other algorithms; its timing is not a whole-image prediction.',
                'Physical Octatrack timing, cache/bus effects and hardware acceptance remain separate.'])
    (work / 'BINDING.json').write_text(json.dumps(report, indent=2) + '\n')
    print(report['status'], metadata['version'], '2880 native frames; 76880 complete-ring/ABI cases')


if __name__ == '__main__':
    main()

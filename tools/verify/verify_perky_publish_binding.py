#!/usr/bin/env python3
"""Bind executed packet helper proofs to the final ELF and booted MAIN."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import verify_perky_hybrid_runtime as rt
from verify_stock_source_mix_binding import symbol_bytes

ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--proof', type=Path, default=ROOT / 'out/perky/hybrid/stock-cf-optimization/publish-unrolled/RESULT.json')
    args = parser.parse_args()
    build, proof_path = args.build.resolve(), args.proof.resolve()
    work = build / 'publish-binding'
    work.mkdir(exist_ok=True)
    proof = json.loads(proof_path.read_text())
    assert proof['status'] == 'PASS_EXACT_PACKET_PUBLISH_CLEAR_MEMORY_MAC_ABI'
    assert proof['cases'] == 8192 and proof['same_image_cycle_controls']
    for path, expected in proof['source_sha256'].items():
        assert sha(path) == expected, ('Proof input drift', path)
    metadata = json.loads((build / 'BUILD.json').read_text())
    image = build / 'probe' / f'mainos_{metadata["version"]}.bin'
    elf = build / 'probe/platform/runtime.elf'
    assert sha(image) == metadata['main_sha256'] and sha(elf) == metadata['runtime_sha256']
    standalone = proof_path.parent / 'kernel.elf'
    helpers = []
    for name in ('pk_prod_pack', 'pk_prod_clear'):
        old_at, proven = symbol_bytes(standalone, name)
        actual_at, actual = symbol_bytes(elf, name)
        assert actual == proven, ('Final helper differs from executed proof', name)
        helpers.append(dict(name=name, standalone_address=old_at, linked_address=actual_at,
                            bytes=len(actual), sha256=hashlib.sha256(actual).hexdigest(),
                            linked_equals_proven=True, boot_readback_equals_linked=True))
    replay = work / 'standalone-replay'
    replay.mkdir(exist_ok=True)
    reconstructed = replay / 'elf-objcopy.bin'
    subprocess.run(['m68k-elf-objcopy', '-O', 'binary', str(standalone), str(reconstructed)], check=True)
    assert reconstructed.read_bytes() == (proof_path.parent / 'kernel.bin').read_bytes()
    symbols = subprocess.check_output(['m68k-elf-nm', '-n', str(standalone)])
    assert symbols == (proof_path.parent / 'kernel.nm').read_bytes()
    shutil.copy2(proof_path.parent / 'kernel.bin', replay / 'kernel.bin')
    (replay / 'kernel.nm').write_bytes(symbols)
    shutil.copy2(proof_path.parent / 'runner', replay / 'runner')
    original_image = Path(proof['commands'][-1][-1])
    assert sha(original_image) == proof['source_sha256'][str(original_image)]
    for helper in helpers:
        at = helper['standalone_address'] - 0x45000000
        loaded = (replay / 'kernel.bin').read_bytes()[at:at + helper['bytes']]
        assert hashlib.sha256(loaded).hexdigest() == helper['sha256']
    replay_inputs = {str(path): sha(path) for path in (replay / 'kernel.bin', replay / 'kernel.nm', replay / 'runner', original_image)}
    command = [str(replay / 'runner'), str(replay), str(original_image)]
    with (replay / 'run.log').open('w') as log:
        subprocess.run(command, cwd=ROOT, check=True, stdout=log, stderr=subprocess.STDOUT)
    for path, expected in replay_inputs.items():
        assert sha(path) == expected, ('Replay input changed', path)
    output = replay / 'EXECUTION.json'
    execution = json.loads(output.read_text())
    for key in ('status', 'cases', 'same_image_cycle_controls', 'mean_saved_pack_cycles', 'mean_saved_clear_cycles'):
        assert execution[key] == proof[key], ('Replay result differs', key)
    boot = rt.g.emu.boot(str(image), count=200000000)
    assert boot.clean, (boot.stopped, boot.error)
    final_symbols = rt.g.load_elf_symbols(elf)
    for name, expected in (('pk_hybrid_pcm_cookie', 0x504b5052), ('pk_hybrid_rt_cookie', 0x504b4852)):
        assert int.from_bytes(boot.uc.mem_read(final_symbols[name], 4), 'big') == expected
    for helper in helpers:
        loaded = bytes(boot.uc.mem_read(helper['linked_address'], helper['bytes']))
        assert hashlib.sha256(loaded).hexdigest() == helper['sha256']
    paths = [Path(__file__).resolve(), Path(rt.__file__), Path(rt.g.emu.__file__),
             ROOT / 'tools/verify/verify_stock_source_mix_binding.py', proof_path,
             standalone, image, elf, build / 'BUILD.json', reconstructed,
             output, replay / 'costs.csv', *map(Path, replay_inputs)]
    result = dict(status='PASS_FINAL_IMAGE_PACKET_PUBLISH_PROOF_AND_BOOT_BINDING',
                  linked_candidate=True, image_sha256=sha(image), elf_sha256=sha(elf),
                  standalone_cases=8192, proof_sha256=sha(proof_path), same_image_cycle_controls=True,
                  helpers=helpers,
                  executed_binary_binding=dict(full_binary_equals_pinned_ELF_objcopy=True,
                                               loaded_helper_equals_pinned_ELF_symbol=True,
                                               symbols_equal_pinned_ELF_nm=True),
                  replay=dict(status=execution['status'], cases=execution['cases'], command=command,
                              inputs=replay_inputs, inputs_unchanged_after_execution=True,
                              output_path=str(output), output_sha256=sha(output), same_image_cycle_controls=True),
                  source_sha256={str(p): sha(p) for p in paths},
                  limits=['Ordinary CF helper calls need no stock detour. Both exact tested helper bodies must match final ELF and real loader readback.',
                          'Full workload, lifecycle and fixed-budget admission remain separate.'])
    (work / 'BINDING.json').write_text(json.dumps(result, indent=2) + '\n')
    print(result['status'], len(helpers), result['standalone_cases'])


if __name__ == '__main__':
    main()

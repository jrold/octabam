#!/usr/bin/env python3
"""Bounded actual-image wrapper and memory-map rejection gates. Never installs.

Positive tests use the actual native EFT and exact MAIN. Malformed fixtures
are disposable artifact copies, not source checkouts. No generic synthetic
release test is substituted for qualification of these packages.
"""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import verify_perky_hybrid_probe_gates as g
import verify_perky_final_wrappers as wrappers


def run(probe, output):
    output.mkdir(parents=True, exist_ok=True)
    b = g.builder
    files = {
        'mainos': probe/'mainos_PKHYB2P.bin', 'elek': probe/'elek_PKHYB2P.bin',
        'card': probe/'OCTATRACK_PKHYB2P.bin',
        'midi': probe/'OCTATRACK_OS1.40C_PKHYB2P.syx',
    }
    hashes = {k: b.item_meta(p) for k, p in files.items()}
    base = [sys.executable, str(Path(wrappers.__file__)),
            '--eft', str(b.base.EFT), '--version', b.PROBE_VERSION,
            '--work', str(output/'roundtrip')]
    for flag, path in files.items():
        base += ['--'+flag, str(path)]

    def command(name, argv, pass_expected):
        r = subprocess.run(argv, capture_output=True, text=True, timeout=90)
        log = output/(name+'.log'); log.write_text(r.stdout+r.stderr)
        assert (r.returncode == 0) == pass_expected, (name, r.returncode, log)
        return {'exit_status': r.returncode, 'log': b.item_meta(log)}

    tests = {'exact_card_and_midi_roundtrip': command('positive', base, True)}
    card = files['card'].read_bytes()
    with tempfile.TemporaryDirectory(prefix='malformed-', dir=output) as td:
        temp = Path(td)
        mutations = {
            'card_short': card[:8], 'card_unaligned': card[:-1],
            'card_bad_magic': b'NOPE'+card[4:],
            'card_bad_checksum': card[:-1]+bytes([card[-1] ^ 1]),
            'card_corrupt_payload': card[:256]+bytes([card[256] ^ 0x40])+card[257:],
        }
        for name, raw in mutations.items():
            path = temp/(name+'.bin'); path.write_bytes(raw)
            try:
                wrappers.decode_card(path)
            except SystemExit as error:
                tests[name] = {'status': 'REJECTED', 'reason': str(error)}
            else:
                raise AssertionError('accepted '+name)
        for name, flag, raw in (
            ('midi_truncated', 'midi', files['midi'].read_bytes()[:64]),
            ('elek_bad_version', 'elek', files['elek'].read_bytes()[:8]+b'XXXXXXXXXX'+files['elek'].read_bytes()[18:]),
        ):
            path = temp/(name+'.bin'); path.write_bytes(raw)
            args = base.copy(); args[args.index('--'+flag)+1] = str(path)
            tests[name] = command(name, args, False)

        # Exercise actual memory verifier on altered artifact metadata.
        fixture = temp/'map'; fixture.mkdir()
        shutil.copy2(probe/'MEMORY.json', fixture/'memory.json')
        for folder, names in (
            ('platform', ('layout.json',)),
            ('platform-loader', ('layout.json', 'pretable.inc')),
        ):
            (fixture/folder).mkdir()
            for name in names:
                shutil.copy2(probe/folder/name, fixture/folder/name)
        (fixture/'platform/runtime.elf').symlink_to(probe/'platform/runtime.elf')
        layout_path = fixture/'platform/layout.json'
        original = layout_path.read_bytes(); layout = json.loads(original)
        layout['stage'] = layout['base']; layout['stage_end'] = layout['base']+128
        layout_path.write_text(json.dumps(layout))
        try:
            b.emit_memory_report(fixture, None, None, None)
        except RuntimeError as error:
            assert 'overlap' in str(error).lower(), str(error)
            tests['overlapping_runtime_stage'] = {'status': 'REJECTED', 'reason': str(error)}
        else:
            raise AssertionError('accepted runtime overlap')
        layout_path.write_bytes(original)
        huge = temp/'oversized-card.bin'
        with huge.open('wb') as f:
            f.truncate(1048588+4)
        try:
            b.emit_memory_report(fixture, huge, files['elek'], files['midi'])
        except RuntimeError as error:
            assert 'exceeds 1 MiB' in str(error), str(error)
            tests['over_cap_card_payload'] = {'status': 'REJECTED', 'reason': str(error)}
        else:
            raise AssertionError('accepted oversized payload')
    assert hashes == {k: b.item_meta(p) for k, p in files.items()}, 'artifact drift'
    memory = json.loads((probe/'MEMORY.json').read_text())
    result = {'schema': 'octabam.perky.hybrid.safety-packages.v1', 'status': 'PASS',
              'artifacts': hashes, 'tests': tests, 'wrappers': memory['wrappers'],
              'physical_overlaps': memory['coldfire_dram']['physical_overlaps'],
              'limitations': ['Not physical DMA/cache/stack/nesting qualification.',
                              'No exhaustive malformed compressed-token or loader table execution test.',
                              'Packages remain UNQUALIFIED; this gate never authorizes installation.']}
    (output/'PACKAGES.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--probe', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    a = ap.parse_args()
    run(a.probe.resolve(), a.out.resolve())

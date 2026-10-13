#!/usr/bin/env python3
"""Verify the built full-machine loader's boot and exact DRAM payloads.

No project/card fixture is needed. This stops at the RTOS handoff; it does not
qualify the machine chooser or AMP/FX/output after project load.
"""
from pathlib import Path
import argparse
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'tools'), str(ROOT / 'tools/build'),
                str(ROOT / 'tools/perky')]
import perky_image
from remix import pack, platform_build
from verify_perky_table_image import parse_upload, exact_record


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    # Defaults deliberately name paths a plain checkout does NOT have, so the gate
    # SKIPs under `make check` instead of failing on a set the caller did not
    # choose. Pointing --image at an existing image made it RUN and then fail on
    # a preblob mismatch (322 PASS + 1 FAIL, vs 332 + 0) -- a gate that fails for
    # a reason its runner cannot influence is worse than one that skips.
    # A real caller names all four: see build_multi_machine_canary.py:101.
    ap.add_argument('--image', type=Path, default=ROOT / 'out/mainos_perky_machine.bin')
    ap.add_argument('--packed', type=Path, default=ROOT / 'out/perky/machine-canary/packed')
    ap.add_argument('--platform-work', type=Path, default=ROOT / 'out/platform-perky-machine')
    # layout.json and runtime.raw were read from a FIXED path, so a caller could not
    # point this gate at ONE build's outputs: `make bus` rewrites out/platform/*
    # in place, and the gate then compared a canary image against whatever build had
    # run last. Name the directory instead.
    ap.add_argument('--platform', type=Path, default=ROOT / 'out/platform-perky-machine/platform',
                    help='the directory holding layout.json and runtime.raw for the '
                         'SAME build as --image')
    ap.add_argument('--normal-image', type=Path, default=ROOT / 'out/mainos_bus.bin')
    ap.add_argument('--p-records', type=Path, help='exact appended P records for this build')
    args = ap.parse_args()
    p_records = json.loads(args.p_records.read_text()) if args.p_records else {}

    missing = [str(p) for p in (args.image, args.packed, args.platform) if not p.exists()]
    if missing:
        print('  [SKIP] needs ' + ' and '.join(missing)
              + ' (the multi-machine canary writes these; run it, or pass '
                '--image/--packed/--platform explicitly)')
        return 0

    work = args.platform_work
    packed, image_path = args.packed, args.image
    image = image_path.read_bytes()
    normal = args.normal_image.read_bytes()
    layout = json.loads((args.platform / 'layout.json').read_text())
    raw_runtime = (args.platform / 'runtime.raw').read_bytes()
    ywords, meta = perky_image.load_tables(packed)
    xwords = perky_image.load_state_init(packed, meta)
    extra_x = perky_image.extra_state_init(meta)
    extra_y = perky_image.load_extra_y_init(packed, meta)
    dumps = [(layout['base'], raw_runtime, 'runtime')]

    for index, tag in enumerate(('A', 'B')):
        raw, _ = perky_image.extend_upload(
            normal, tag, ywords, xwords, extra_x, extra_y, p_records.get(tag)
        )
        records = parse_upload(raw)
        for addr, words in p_records.get(tag, []):
            exact_record(records, 0, addr, words, tag)
        exact_record(records, 1, perky_image.X_BASE, xwords, tag)
        for base, values in extra_x:
            exact_record(records, 1, base, values, tag)
        exact_record(records, 2, perky_image.Y_BASE, ywords, tag)
        for base, values, purpose in extra_y:
            exact_record(records, 2, base, values, f'{tag}:{purpose}')

        expected_blob = (
            platform_build.SIGNATURE + pack.PACKED_MAGIC
            + len(raw).to_bytes(4, 'big')
            + pack.pack(raw, platform_build.MAX_CANDIDATES)
        )
        assert (work / f'preblob{index}.bin').read_bytes() == expected_blob
        dst = perky_image.PRE[tag][0]
        off = perky_image.PAY[tag]['pointer'] - perky_image.ab_records.BASE
        assert int.from_bytes(image[off:off+4], 'big') == dst + platform_build.UNCACHED
        dumps.append((dst, raw, tag))

    append_at = platform_build.LOADER_AT - perky_image.ab_records.BASE
    assert image[append_at:] == (work / 'append.bin').read_bytes()
    nm = subprocess.run(
        ['m68k-elf-nm', str(work / 'loader.elf')],
        capture_output=True, text=True, check=True,
    ).stdout
    syms = {
        f[2]: int(f[0], 16)
        for line in nm.splitlines()
        if len(f := line.split()) == 3
    }
    entry, fatal = syms['octabam_bootstrap'], syms['fatal']
    output = ROOT / 'out/perky/machine-boot'
    output.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(ROOT / 'out/emu/ot_emu'), '--image', str(image_path),
        '--max', '80000000', '--watch-pc', f'0x{entry:x},0x{fatal:x}',
        '--mem-dump', ';'.join(
            f'0x{at:x},{len(raw)}={output/name}.bin'
            for at, raw, name in dumps
        ),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=120)
    (output / 'boot.log').write_text(r.stdout + r.stderr)
    hits = [
        line for line in r.stdout.splitlines()
        if line.strip().startswith('[') and ' at 0x' in line
    ]
    assert 'HANDOFF' in r.stdout
    assert sum(f'at 0x{entry:x}' in line for line in hits) == 1
    assert not any(f'at 0x{fatal:x}' in line for line in hits)
    for at, raw, name in dumps:
        got = (output / f'{name}.bin').read_bytes()
        assert got == raw, f'{name} at {at:#x}: boot memory differs from packed payload'

    print(
        'PERKY full-machine boot: PASS (loader ran once, no fatal; RTOS handoff; '
        'ColdFire runtime and A/B extended DSP uploads read back byte-identical; '
        'exact X/Y/extra-Y records, upload pointers and loader append verified)'
    )


if __name__ == '__main__':
    sys.path.insert(0, str(ROOT / 'tools/verify'))
    main()

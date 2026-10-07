#!/usr/bin/env python3
"""Compare Fold2/Karplus post-trigger updates with complete original ARM objects."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'modules/perky'), str(ROOT/'tools/perky')]
import hw4_control_update as control
from extract_noise_tone_tables import parse_container, find_m7

FIX = ROOT/'out/perky/engine-fixtures'
FIRMWARE_SHA = 'adcdbc4a2c660ffb6477f202211ae3cb70170bfe6ddfaecc3df0e4cb7db398c6'


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--firmware', type=Path, default=Path(os.environ.get(
        'PERKONS_FIRMWARE', str(Path.home()/'Downloads/perkons_both_v1.2.1-0-gbcccfd0.img'))))
    args = ap.parse_args()
    blob = args.firmware.expanduser().read_bytes()
    if hashlib.sha256(blob).hexdigest() != FIRMWARE_SHA:
        raise RuntimeError('control update gate requires pinned PĒRKONS v1.2.1')
    manifest = json.loads((FIX/'manifest.json').read_text())
    if manifest['firmware_sha256'] != FIRMWARE_SHA:
        raise RuntimeError('control update fixture firmware drift')
    m7 = find_m7(parse_container(blob)[1])
    pitch = m7.read(0x080202a0, 8192)
    chromatic = m7.read(0x08030ecc, 24)
    count = 0
    for engine, offset, size, update in (
        (4, 0xc4, 0x134, control.fold2_update),
        (9, 0x2908, 0x10e0, control.karplus_update),
    ):
        for mode in range(1, 4):
            for corner in range(3):
                case = FIX/f'engine-{engine}-mode-{mode}-corner-{corner}'
                for pre, post in (
                    ('wrapper-window-trigger-only.bin', 'wrapper-window-before.bin'),
                    ('wrapper-window-retrigger-only.bin', 'wrapper-window-retrigger-before.bin'),
                ):
                    files = [case/pre, case/post, case/(pre+'.targets.bin')]
                    for path in files:
                        name = str(path.relative_to(FIX))
                        if hashlib.sha256(path.read_bytes()).hexdigest() != manifest['files'][name]:
                            raise RuntimeError(f'capture hash drift: {name}')
                    before = files[0].read_bytes()[offset:offset+size]
                    expected = files[1].read_bytes()[offset:offset+size]
                    targets = struct.unpack('<4I', files[2].read_bytes())
                    actual = update(before, targets, pitch, chromatic)
                    if actual != expected:
                        differences = [hex(i) for i, (a, b) in enumerate(zip(actual, expected)) if a != b]
                        raise AssertionError(f'{case.name}/{pre}: update differences {differences}')
                    count += 1
    print(f'HW4 original ARM control update: PASS ({count} complete objects; captured targets/history; Karplus double smoother and integer divisions)')


if __name__ == '__main__':
    main()

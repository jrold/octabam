#!/usr/bin/env python3
"""Exact compact-state gate for engine 007 Resonant Drums modes M1/M2.

M1 is NativeV121ResonantSnare, M2 is NativeV121ResonantBass.  The capture
harness exposes explicit RNG state only for continuation blocks, so those are
the authoritative ARM PCM/state/RNG comparisons.  Firmware-owned static tables
are read directly from the user's v1.2.1 image and never committed.
"""
from __future__ import annotations

from pathlib import Path
import argparse
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'modules/perky'), str(ROOT / 'tools/perky')]

import resonant_bass_compact as bass
import resonant_snare_compact as snare
from extract_noise_tone_tables import parse_container, find_m7

FIX = ROOT / 'out/perky/engine-fixtures'

ENV1 = 0x08022EA0
ENV2 = 0x080236A2
INTERP_A = 0x0803237C
INTERP_B = 0x08032178


def tables(image: Path):
    segment = find_m7(parse_container(image.read_bytes())[1])
    return (
        segment.read(ENV1, 4096),
        segment.read(ENV2, 4096),
        segment.read(INTERP_A, 514),
        segment.read(INTERP_B, 514),
    )


def state(case: Path, name: str, offset: int, size: int) -> bytes:
    raw = (case / name).read_bytes()
    return raw[offset:offset + size]


def gate_snare(t):
    e1, e2, ia, ib = t
    checked = 0
    # Engine 007 M1 -> firmware mode 1 -> wrapper +0x2734 Resonant Snare.
    for corner in range(3):
        case = FIX / f'engine-7-mode-1-corner-{corner}'
        before = state(case, 'wrapper-window-after.bin', 0x2734, 0x1D4)
        voice = snare.ResonantSnare.from_arm(before)
        rng = list(struct.unpack('<II', (case / 'rng-continuation-before.bin').read_bytes()))
        got = voice.render(256, e1, e2, ia, ib, rng)
        want = list(struct.unpack('<256h', (case / 'arm-pcm-continuation.bin').read_bytes()))
        assert got == want, ('snare', corner, 'PCM', next((i for i,(a,b) in enumerate(zip(got,want)) if a!=b), None))
        expected = snare.ResonantSnare.from_arm(
            state(case, 'wrapper-window-continuation-after.bin', 0x2734, 0x1D4)
        ).words
        assert voice.words == expected, ('snare', corner, 'state')
        assert struct.pack('<II', *rng) == (case / 'rng-continuation-after.bin').read_bytes(), ('snare', corner, 'RNG')
        # Round-trip all renderer-owned compact fields into the captured ARM object.
        assert snare.ResonantSnare.from_arm(voice.apply_to_arm(
            state(case, 'wrapper-window-continuation-after.bin', 0x2734, 0x1D4)
        )).words == voice.words
        checked += 1
    return checked


def gate_bass(t):
    e1, e2, ia, ib = t
    checked = 0
    # Engine 007 M2 -> firmware mode 0 -> wrapper +0x39e8 Resonant Bass.
    for corner in range(3):
        case = FIX / f'engine-7-mode-2-corner-{corner}'
        before = state(case, 'wrapper-window-after.bin', 0x39E8, 0x178)
        voice = bass.ResonantBass.from_arm(before)
        rng = list(struct.unpack('<II', (case / 'rng-continuation-before.bin').read_bytes()))
        got = voice.render(256, e1, e2, ia, ib, rng)
        want = list(struct.unpack('<256h', (case / 'arm-pcm-continuation.bin').read_bytes()))
        assert got == want, ('bass', corner, 'PCM', next((i for i,(a,b) in enumerate(zip(got,want)) if a!=b), None))
        expected = bass.ResonantBass.from_arm(
            state(case, 'wrapper-window-continuation-after.bin', 0x39E8, 0x178)
        ).words
        assert voice.words == expected, ('bass', corner, 'state')
        assert struct.pack('<II', *rng) == (case / 'rng-continuation-after.bin').read_bytes(), ('bass', corner, 'RNG')
        assert bass.ResonantBass.from_arm(voice.apply_to_arm(
            state(case, 'wrapper-window-continuation-after.bin', 0x39E8, 0x178)
        )).words == voice.words
        checked += 1
    return checked


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('firmware', type=Path, help='PĒRKONS v1.2.1 firmware image/container')
    a = ap.parse_args()
    t = tables(a.firmware)
    sn = gate_snare(t)
    ba = gate_bass(t)
    print(f'Resonant compact: PASS ({sn} snare + {ba} bass continuation blocks; exact PCM/state/RNG)')


if __name__ == '__main__':
    main()

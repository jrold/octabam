#!/usr/bin/env python3
"""Exact compact-state gate for engine 010 Noise Hat, all panel modes."""
from pathlib import Path
import argparse
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'modules/perky'), str(ROOT / 'tools/perky')]

import noise_hat_compact as hats
from extract_noise_tone_tables import parse_container, find_m7

FIX = ROOT / 'out/perky/engine-fixtures'
ENV1 = 0x08022EA0
ENV2 = 0x080236A2
PULSE_OFFSET = 0x2C98
PANEL_TO_FIRMWARE = {1: 1, 2: 0, 3: 2}


def tables(image: Path):
    section = find_m7(parse_container(image.read_bytes())[1])
    return section.read(ENV1, 4096), section.read(ENV2, 4096)


def window(case: Path, name: str) -> bytes:
    return (case / name).read_bytes()


def classic_state(case: Path, name: str) -> bytes:
    return window(case, name)[:0x2DD8]


def pulse_state(case: Path, name: str) -> bytes:
    raw = window(case, name)
    return raw[PULSE_OFFSET:PULSE_OFFSET + 0x160]


def hold_state(case: Path, when: str) -> bytes:
    path = case / f'noise-hat-hold-continuation-{when}.bin'
    if not path.exists():
        raise RuntimeError(
            f'{path} is missing; regenerate engine fixtures with the updated '
            'capture_engine_fixtures.py so the Noise Hat global hold state is '
            'captured.'
        )
    data = path.read_bytes()
    if len(data) != 4:
        raise RuntimeError(f'{path} must contain exactly 4 bytes')
    return data


def first_difference(got, want):
    return next(
        (i for i, (x, y) in enumerate(zip(got, want)) if x != y),
        None,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('firmware', type=Path)
    args = parser.parse_args()

    envelope1, envelope2 = tables(args.firmware)
    checked = 0

    for panel_mode in range(1, 4):
        firmware_mode = PANEL_TO_FIRMWARE[panel_mode]
        for corner in range(3):
            case = FIX / f'engine-10-mode-{panel_mode}-corner-{corner}'
            want = list(struct.unpack(
                '<256h',
                (case / 'arm-pcm-continuation.bin').read_bytes(),
            ))
            rng_before_bytes = (
                case / 'rng-continuation-before.bin'
            ).read_bytes()
            rng_after_bytes = (
                case / 'rng-continuation-after.bin'
            ).read_bytes()

            if firmware_mode == 2:
                voice = hats.NoiseHatPulseStack.from_arm(
                    pulse_state(case, 'wrapper-window-after.bin')
                )
                got = voice.render(256, envelope1, envelope2)
                expected = hats.NoiseHatPulseStack.from_arm(
                    pulse_state(
                        case,
                        'wrapper-window-continuation-after.bin',
                    )
                )
                assert got == want, (
                    'noise-hat-pulse',
                    panel_mode,
                    corner,
                    'PCM',
                    first_difference(got, want),
                )
                assert voice.words == expected.words, (
                    'noise-hat-pulse',
                    panel_mode,
                    corner,
                    'state',
                )
                # Pulse Stack owns a local LCG; it must not consume the
                # firmware-global PRNG.
                assert rng_before_bytes == rng_after_bytes, (
                    'noise-hat-pulse',
                    panel_mode,
                    corner,
                    'global RNG changed',
                )
            else:
                rng = list(struct.unpack('<II', rng_before_bytes))
                voice = hats.NoiseHatClassic.from_arm(
                    classic_state(case, 'wrapper-window-after.bin'),
                    hold_state(case, 'before'),
                )
                got = voice.render(
                    256,
                    firmware_mode,
                    envelope1,
                    envelope2,
                    rng,
                )
                expected = hats.NoiseHatClassic.from_arm(
                    classic_state(
                        case,
                        'wrapper-window-continuation-after.bin',
                    ),
                    hold_state(case, 'after'),
                )
                assert got == want, (
                    'noise-hat-classic',
                    panel_mode,
                    corner,
                    'PCM',
                    first_difference(got, want),
                )
                assert voice.words == expected.words, (
                    'noise-hat-classic',
                    panel_mode,
                    corner,
                    'state',
                )
                assert voice.ring == expected.ring, (
                    'noise-hat-classic',
                    panel_mode,
                    corner,
                    'ring',
                )
                assert voice.hold == expected.hold, (
                    'noise-hat-classic',
                    panel_mode,
                    corner,
                    'hold',
                )
                assert struct.pack('<II', *rng) == rng_after_bytes, (
                    'noise-hat-classic',
                    panel_mode,
                    corner,
                    'RNG',
                )

            checked += 1

    print(
        'Noise Hat compact: PASS '
        f'({checked} continuation blocks; exact PCM/state/ring/hold/RNG)'
    )


if __name__ == '__main__':
    main()

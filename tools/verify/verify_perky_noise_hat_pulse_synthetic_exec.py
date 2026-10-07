#!/usr/bin/env python3
"""CI-safe executable gate for the Noise Hat Pulse Stack DSP candidate.

Exercises all 60 compact continuation words, both shaped envelope curves,
phase wraps/local LCG, two filter passes, signed interpolation, velocity and
final int16 saturation without requiring firmware-derived fixtures.
"""
from __future__ import annotations

from pathlib import Path
import random
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'modules/perky'), str(ROOT / 'tools/perky')]

import noise_hat_compact as hats  # noqa:E402
import resonator_compact as c  # noqa:E402
import simple_drum_tables as tables  # noqa:E402
from build_noise_tone_synth_source import (  # noqa:E402
    force_long_local_jsr,
    relativize_local_conditionals,
)

OUT = ROOT / 'out/perky/noise-hat-pulse-synthetic'
ASM = ROOT / 'vendor/dsp56300/build/source/dsp_host/dsp_asm'
HOST = ROOT / 'out/perky/simple-drum-envelope/bd909_host'
ORG = 0x2800
ENV1_BASE = 0x09A5
ENV2_BASE = 0x0C51


def fail(message: str) -> None:
    raise SystemExit('verify-perky-noise-hat-pulse-synthetic-exec: ' + message)


def set_u32(words: list[int], off: int, value: int) -> None:
    value &= c.MASK32
    words[off] = value & c.MASK16
    words[off + 1] = (value >> 16) & c.MASK16


def set_s32(words: list[int], off: int, value: int) -> None:
    set_u32(words, off, value & c.MASK32)


def make_envelopes():
    # 1025 values are sufficient because the envelope accumulator is clamped
    # to 0..$0fffff: index <=1023 and the interpolation neighbour <=1024.
    env1_values = []
    env2_values = []
    for i in range(1025):
        env1_values.append(min(65535, (i * i * 65535) // (1024 * 1024)))
        # Deliberately non-monotonic-ish but bounded, so signed17 interpolation
        # deltas exercise both signs rather than only a linear ramp.
        env2_values.append((i * 251 + ((i * 37) & 0x1fff)) & 0xffff)
    env1_blob = b''.join(struct.pack('<H', x) for x in env1_values)
    env2_blob = b''.join(struct.pack('<H', x) for x in env2_values)
    return (
        env1_blob,
        env2_blob,
        tables.pack_u16(env1_values),
        tables.pack_u16(env2_values),
    )


def make_filter(words: list[int], base: int, rng: random.Random) -> None:
    words[base + hats.F_DAMP] = rng.randrange(0x10000)
    words[base + hats.F_COEFF] = rng.randrange(0x10000)
    set_s32(words, base + hats.F_FIRST, rng.randint(-32767, 32767))
    set_s32(words, base + hats.F_SECOND, rng.randint(-32767, 32767))
    set_s32(words, base + hats.F_VELOCITY, rng.randint(-32767, 32767))


def make_voice(seed: int) -> hats.NoiseHatPulseStack:
    rng = random.Random(0x48415400 + seed)
    w = [0] * hats.PULSE_STACK_WORDS
    w[hats.PS_VELOCITY] = rng.choice((0, 1, 31, 63, 127, 255))

    env = hats.PS_ENV
    w[env + c.ENV_STATE] = rng.choice((0, 1, 3, 4))
    w[env + c.ENV_SHAPE] = seed % 3
    w[env + c.ENV_FLAG4] = rng.choice((0, 1))
    w[env + c.ENV_FLAG6] = rng.choice((0, 1))
    w[env + c.ENV_TRIGGER] = rng.choice((0, 1))
    raw_value = rng.choice((
        0,
        1,
        0x3ff,
        0x400,
        0x7ffff,
        0xffbff,
        0xfffff,
        rng.randrange(0x100000),
    ))
    set_u32(w, env + c.ENV_VALUE, raw_value)
    set_u32(w, env + c.ENV_HOLD, rng.choice((0, 1, 0x100, rng.randrange(0x10000))))
    w[env + c.ENV_ATTACK] = rng.choice((1, 0x20, 0x400, 0xffff))
    w[env + c.ENV_DECAY] = rng.choice((1, 0x10, 0x200, 0xffff))

    make_filter(w, hats.PS_FILTER_A, rng)
    make_filter(w, hats.PS_FILTER_B, rng)

    for i in range(6):
        phase = rng.randrange(1 << 32)
        increment = rng.randrange(1 << 32)
        if seed % 11 == 0:
            phase = (0x7ffffff0 + i) & c.MASK32
            increment = 0x20 + i
        set_u32(w, hats.PS_PHASES + 2 * i, phase)
        set_u32(w, hats.PS_INCREMENTS + 2 * i, increment)

    if seed % 4 == 0:
        set_u32(w, hats.PS_RANDOM_PHASE, 0xfffffff0)
        set_u32(w, hats.PS_RANDOM_INCREMENT, 0x40)
    else:
        set_u32(w, hats.PS_RANDOM_PHASE, rng.randrange(1 << 32))
        set_u32(w, hats.PS_RANDOM_INCREMENT, rng.randrange(1 << 32))
    set_u32(w, hats.PS_RANDOM, rng.randrange(1 << 32))
    w[hats.PS_SECOND_INPUT] = rng.randrange(0x10000)
    w[hats.PS_MIX] = rng.randrange(0x10000)
    return hats.NoiseHatPulseStack(w)


def assemble() -> tuple[Path, int]:
    missing = [p for p in (ASM, HOST) if not p.exists()]
    if missing:
        fail('run the existing PERKY setup/build gates first; missing '
             + ', '.join(map(str, missing)))

    OUT.mkdir(parents=True, exist_ok=True)
    math = (ROOT / 'modules/perky/noise_tone_math.asm').read_text()
    marker = '\npk_u32_add:'
    if marker not in math:
        fail('noise_tone_math.asm no longer exposes pk_u32_add')
    math_helpers = math[math.index(marker) + 1:]

    source = (
        'pk_noise_hat_pulse_probe:\n'
        ' move #>$200,r6\n'
        ' move #>$3900,r5\n'
        ' jsr pk_noise_hat_pulse_voice\n'
        ' rts\n'
    )
    for name in (
        'noise_hat_pulse_voice.asm',
        'noise_hat_phase.asm',
        'noise_hat_filter.asm',
        'noise_hat_envelope.asm',
    ):
        source += (ROOT / 'modules/perky' / name).read_text() + '\n'
    source += math_helpers
    source = force_long_local_jsr(relativize_local_conditionals(source))

    asm = OUT / 'candidate.asm'
    binary = OUT / 'candidate.bin'
    symbols = OUT / 'candidate.sym'
    asm.write_text(source)
    result = subprocess.run(
        [str(ASM), '-in', str(asm), '-org', f'{ORG:x}',
         '-out', str(binary), '-sym', str(symbols)],
        capture_output=True, text=True,
    )
    if result.returncode:
        fail('assembler failed:\n' + result.stdout[-5000:] + result.stderr[-2500:])
    labels = {
        p[0]: int(p[1], 16)
        for p in map(str.split, symbols.read_text().splitlines())
        if len(p) == 2
    }
    if 'pk_noise_hat_pulse_probe' not in labels:
        fail('assembler emitted no Pulse Stack probe symbol')
    return binary, labels['pk_noise_hat_pulse_probe']


def main() -> None:
    binary, entry = assemble()
    env1, env2, env1_words, env2_words = make_envelopes()
    script = OUT / 'case.script'
    script.write_text(' '.join(['0'] * 12 + ['-1']) + '\n')

    meters = []
    shape_counts = [0, 0, 0]
    lcg_wrap_cases = 0
    for index in range(96):
        voice = make_voice(index + 1)
        before = list(voice.words)
        shape_counts[before[hats.PS_ENV + c.ENV_SHAPE]] += 1
        old_clock = c.get_u32(before, hats.PS_RANDOM_PHASE)
        clock_increment = c.get_u32(before, hats.PS_RANDOM_INCREMENT)
        if ((old_clock + clock_increment) & c.MASK32) < old_clock:
            lcg_wrap_cases += 1

        expected = hats.NoiseHatPulseStack(list(before))
        want = expected.render(16, env1, env2)

        data = OUT / 'case.data'
        data.write_text(
            'X 200 ' + ' '.join(f'{x:06x}' for x in before) + '\n'
            + f'Y {ENV1_BASE:x} ' + ' '.join(f'{x:06x}' for x in env1_words) + '\n'
            + f'Y {ENV2_BASE:x} ' + ' '.join(f'{x:06x}' for x in env2_words) + '\n'
        )
        pcm = OUT / 'case.raw'
        dump = OUT / 'case.state'
        meter = OUT / 'case.meter'
        result = subprocess.run(
            [str(HOST), '-code', str(binary), '-org', f'{ORG:x}',
             '-entry', f'{entry:x}', '-data', str(data), '-script', str(script),
             '-out', str(pcm), '-state', str(dump),
             '-state-words', str(hats.PULSE_STACK_WORDS),
             '-meter', str(meter), '-cycle-meter', '1'],
            capture_output=True, text=True,
        )
        if result.returncode:
            fail(
                f'case {index}: host failed:\n'
                + result.stdout[-2500:] + result.stderr[-2500:]
            )

        got = list(struct.unpack('<32i', pcm.read_bytes()))[::2]
        if got != want:
            diffs = [
                (i, actual, expected_sample)
                for i, (actual, expected_sample) in enumerate(zip(got, want))
                if actual != expected_sample
            ]
            fail(f'case {index} PCM mismatch: {diffs[:8]}')

        final = [
            int(x, 16) & 0xffff
            for x in dump.read_text().split()[:hats.PULSE_STACK_WORDS]
        ]
        if final != expected.words:
            diffs = [
                (i, actual, expected_word)
                for i, (actual, expected_word) in enumerate(zip(final, expected.words))
                if actual != expected_word
            ]
            fail(f'case {index} state mismatch: {diffs[:12]}')
        meters.append(int(meter.read_text().strip()))

    if min(shape_counts) == 0:
        fail(f'not all envelope shapes were exercised: {shape_counts}')
    if lcg_wrap_cases == 0:
        fail('test corpus never exercised a local-LCG phase wrap')

    print(
        f'Noise Hat Pulse Stack synthetic DSP: PASS (96 cases / 1536 samples; '
        f'shapes={shape_counts}; LCG-wrap cases={lcg_wrap_cases}; '
        f'{binary.stat().st_size // 3} P words; worst {max(meters)} modeled cycles)'
    )


if __name__ == '__main__':
    main()

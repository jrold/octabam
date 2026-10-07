#!/usr/bin/env python3
"""Execute Noise Hat Pulse Stack phase/LCG DSP kernel against a u32 oracle."""
from __future__ import annotations

from pathlib import Path
import random
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
PERKY = ROOT / 'modules/perky'
OUT = ROOT / 'out/perky/noise-hat-phase'
ASM = ROOT / 'vendor/dsp56300/build/source/dsp_host/dsp_asm'
HOST = ROOT / 'out/perky/simple-drum-envelope/bd909_host'
ORG = 0x2800
STATE_BASE = 0x200
PHASE_BASE = 0x70
SIGN_COUNT_OFF = 0x62
WORDS = 30

sys.path[:0] = [str(PERKY), str(ROOT / 'tools/perky')]
from build_noise_tone_synth_source import (  # noqa:E402
    force_long_local_jsr,
    relativize_local_conditionals,
)

MASK32 = 0xffffffff


def fail(message: str) -> None:
    raise SystemExit('verify-perky-noise-hat-phase-exec: ' + message)


def get_u32(words: list[int], off: int) -> int:
    return (words[off] & 0xffff) | ((words[off + 1] & 0xffff) << 16)


def set_u32(words: list[int], off: int, value: int) -> None:
    value &= MASK32
    words[off] = value & 0xffff
    words[off + 1] = (value >> 16) & 0xffff


def oracle(words: list[int]) -> tuple[list[int], int]:
    out = list(words)

    old_clock = get_u32(out, 24)
    new_clock = (old_clock + get_u32(out, 26)) & MASK32
    set_u32(out, 24, new_clock)
    if new_clock < old_clock:
        random_state = (
            get_u32(out, 28) * 0x0019660d + 0x3c6ef35f
        ) & MASK32
        set_u32(out, 28, random_state)

    sign_count = 0
    for i in range(6):
        off = i * 2
        increment_off = 12 + i * 2
        phase = (get_u32(out, off) + get_u32(out, increment_off)) & MASK32
        set_u32(out, off, phase)
        sign_count += phase >> 31

    return out, sign_count


def assemble() -> tuple[Path, int]:
    missing = [p for p in (ASM, HOST) if not p.exists()]
    if missing:
        fail('run the existing PERKY setup/build gates first; missing '
             + ', '.join(map(str, missing)))

    OUT.mkdir(parents=True, exist_ok=True)
    phase = (PERKY / 'noise_hat_phase.asm').read_text()
    math = (PERKY / 'noise_tone_math.asm').read_text()
    marker = '\npk_u32_add:'
    if marker not in math:
        fail('noise_tone_math.asm no longer exposes pk_u32_add')
    math_helpers = math[math.index(marker) + 1:]

    source = (
        'pk_noise_hat_phase_probe:\n'
        f' move #>${STATE_BASE + PHASE_BASE:x},r6\n'
        f' move #>${STATE_BASE:x},r5\n'
        ' jsr pk_noise_hat_phase_step\n'
        ' rts\n'
        + phase + '\n' + math_helpers
    )
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
        fail('assembler failed:\n' + result.stdout[-4000:] + result.stderr[-2000:])
    labels = {
        p[0]: int(p[1], 16)
        for p in map(str.split, symbols.read_text().splitlines())
        if len(p) == 2
    }
    if 'pk_noise_hat_phase_probe' not in labels:
        fail('assembler emitted no phase probe symbol')
    return binary, labels['pk_noise_hat_phase_probe']


def run(binary: Path, entry: int, tag: str,
        phase_words: list[int]) -> tuple[list[int], int, int]:
    state = [0] * 0xb0
    state[PHASE_BASE:PHASE_BASE + WORDS] = phase_words
    data = OUT / f'{tag}.data'
    script = OUT / f'{tag}.script'
    raw = OUT / f'{tag}.raw'
    dump = OUT / f'{tag}.state'
    meter = OUT / f'{tag}.meter'
    data.write_text(
        f'X {STATE_BASE:x} ' + ' '.join(f'{x:06x}' for x in state) + '\n'
    )
    script.write_text(' '.join(['0'] * 12 + ['-1']) + '\n')

    result = subprocess.run(
        [str(HOST), '-code', str(binary), '-org', f'{ORG:x}',
         '-entry', f'{entry:x}', '-data', str(data), '-script', str(script),
         '-out', str(raw), '-state', str(dump), '-state-words', str(len(state)),
         '-meter', str(meter), '-cycle-meter', '1'],
        capture_output=True, text=True,
    )
    if result.returncode:
        fail(f'{tag}: host failed:\n{result.stdout[-2000:]}{result.stderr[-2000:]}')

    dumped = [int(x, 16) for x in dump.read_text().split()]
    got = [x & 0xffff for x in dumped[PHASE_BASE:PHASE_BASE + WORDS]]
    sign_count = dumped[SIGN_COUNT_OFF] & 0xffffff
    return got, sign_count, int(meter.read_text().strip())


def make_words(phases, increments, clock, clock_increment, random_state):
    words = [0] * WORDS
    for i, value in enumerate(phases):
        set_u32(words, 2 * i, value)
    for i, value in enumerate(increments):
        set_u32(words, 12 + 2 * i, value)
    set_u32(words, 24, clock)
    set_u32(words, 26, clock_increment)
    set_u32(words, 28, random_state)
    return words


def cases():
    yield make_words([0] * 6, [0] * 6, 0, 0, 0)
    yield make_words([0x7fffffff] * 6, [1] * 6, 0, 1, 0x12345678)
    yield make_words([0xffffffff] * 6, [1] * 6, 0xffffffff, 1, 0)
    yield make_words(
        [0, 0x7fffffff, 0x80000000, 0xffffffff, 0x12345678, 0xfedcba98],
        [0xffffffff, 1, 0xffffffff, 1, 0x87654321, 0x01234567],
        0xfffffffe, 3, 0xffffffff,
    )
    yield make_words(
        [0x80000000, 0x7fffffff, 0x0000ffff, 0xffff0000, 1, 0xffffffff],
        [0, 0, 0xffff0001, 0x0000ffff, 0xffffffff, 0],
        0x7fffffff, 0x80000000, 0x80000000,
    )

    rng = random.Random(0x50554c53)
    for _ in range(251):
        yield make_words(
            [rng.randrange(1 << 32) for _ in range(6)],
            [rng.randrange(1 << 32) for _ in range(6)],
            rng.randrange(1 << 32),
            rng.randrange(1 << 32),
            rng.randrange(1 << 32),
        )


def main() -> None:
    binary, entry = assemble()
    checked = 0
    wrap_cases = 0
    worst = 0

    for index, before in enumerate(cases()):
        old_clock = get_u32(before, 24)
        clock_increment = get_u32(before, 26)
        expected, expected_sign_count = oracle(before)
        if ((old_clock + clock_increment) & MASK32) < old_clock:
            wrap_cases += 1

        got, sign_count, cycles = run(
            binary, entry, f'case-{index:03d}', before
        )
        if got != expected:
            diffs = [
                (i, actual, want)
                for i, (actual, want) in enumerate(zip(got, expected))
                if actual != want
            ]
            fail(f'case {index} state mismatch: {diffs[:8]}')
        if sign_count != expected_sign_count:
            fail(
                f'case {index} signCount got {sign_count}, '
                f'want {expected_sign_count}'
            )
        checked += 1
        worst = max(worst, cycles)

    if not wrap_cases:
        fail('test corpus never exercised the local-LCG wrap branch')

    print(
        f'Noise Hat Pulse Stack phase DSP: PASS ({checked} exact states; '
        f'{wrap_cases} LCG-wrap cases; {binary.stat().st_size // 3} P words; '
        f'worst {worst} modeled cycles)'
    )


if __name__ == '__main__':
    main()

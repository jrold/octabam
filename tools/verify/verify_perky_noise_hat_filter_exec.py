#!/usr/bin/env python3
"""Execute the compact Noise Hat one-pass DSP filter against its host oracle."""
from __future__ import annotations

from pathlib import Path
import random
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
PERKY = ROOT / 'modules/perky'
OUT = ROOT / 'out/perky/noise-hat-filter'
ASM = ROOT / 'vendor/dsp56300/build/source/dsp_host/dsp_asm'
HOST = ROOT / 'out/perky/simple-drum-envelope/bd909_host'
ORG = 0x2800
STATE_BASE = 0x200
FILTER_BASE = 0x20
INPUT_OFF = 0x61

sys.path.insert(0, str(PERKY))
import noise_hat_compact as hats  # noqa:E402


def fail(message: str) -> None:
    raise SystemExit('verify-perky-noise-hat-filter-exec: ' + message)


def signed16(value: int) -> int:
    value &= 0xffff
    return value - 0x10000 if value & 0x8000 else value


def limbs(value: int) -> tuple[int, int]:
    value &= 0xffffffff
    return value & 0xffff, (value >> 16) & 0xffff


def encode_filter(coeff: int, damping: int, first: int,
                  second: int, velocity: int) -> list[int]:
    words = [0] * hats.FILTER_WORDS
    words[hats.F_DAMP] = damping & 0xffff
    words[hats.F_COEFF] = coeff & 0xffff
    lo, hi = limbs(first)
    words[hats.F_FIRST:hats.F_FIRST + 2] = [lo, hi]
    lo, hi = limbs(second)
    words[hats.F_SECOND:hats.F_SECOND + 2] = [lo, hi]
    lo, hi = limbs(velocity)
    words[hats.F_VELOCITY:hats.F_VELOCITY + 2] = [lo, hi]
    return words


def oracle(words: list[int], sample: int) -> list[int]:
    expected = list(words)
    hats._advance_filter(expected, 0, signed16(sample))
    return expected


def assemble() -> tuple[Path, int]:
    missing = [p for p in (ASM, HOST) if not p.exists()]
    if missing:
        fail('run the existing PERKY setup/build gates first; missing '
             + ', '.join(map(str, missing)))

    OUT.mkdir(parents=True, exist_ok=True)
    source = (
        'pk_noise_hat_filter_probe:\n'
        f' move #>${STATE_BASE + FILTER_BASE:x},r6\n'
        f' move #>${STATE_BASE:x},r5\n'
        ' jsr pk_noise_hat_filter\n'
        ' rts\n'
        + (PERKY / 'noise_hat_filter.asm').read_text()
    )
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
    if 'pk_noise_hat_filter_probe' not in labels:
        fail('assembler emitted no probe symbol')
    return binary, labels['pk_noise_hat_filter_probe']


def run(binary: Path, entry: int, tag: str,
        filter_words: list[int], sample: int) -> tuple[list[int], int]:
    state = [0] * 0x70
    state[FILTER_BASE:FILTER_BASE + hats.FILTER_WORDS] = filter_words
    state[INPUT_OFF] = sample & 0xffff

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
    got = [x & 0xffff for x in dumped[FILTER_BASE:FILTER_BASE + hats.FILTER_WORDS]]
    return got, int(meter.read_text().strip())


def cases():
    edge = [
        # coeff, damping, first, second, velocity, input-u16
        (0, 0, 0, 0, 0, 0),
        (0, 0xffff, 12345, -12345, -23456, 0x7fff),
        (0xffff, 0, -12345, 12345, 23456, 0x8000),
        (1, 1, 32767, -32767, 32767, 0x7fff),
        (1, 1, -32767, 32767, -32767, 0x8001),
        (0x7fff, 0x7fff, 0, 0, 32767, 0x7fff),
        (0x7fff, 0x7fff, 0, 0, -32767, 0x8000),
        (0xffff, 0xffff, 30000, -30000, 30000, 0x7fff),
        (0xffff, 0xffff, -30000, 30000, -30000, 0x8000),
        (0x4000, 0x2000, 32760, -1, 32760, 0x7fff),
        (0x4000, 0x2000, -32760, 1, -32760, 0x8000),
        (0x1234, 0xabcd, 0x1234, -0x1234, -0x2345, 0x8ace),
        (0xabcd, 0x1234, -0x1234, 0x1234, 0x2345, 0x7531),
        (0xfffe, 0x8001, 1, -1, -1, 0xffff),
        (0x8001, 0xfffe, -1, 1, 1, 0x0001),
    ]
    yield from edge

    rng = random.Random(0x48415431)
    for _ in range(192):
        yield (
            rng.randrange(0x10000),
            rng.randrange(0x10000),
            rng.randint(-32767, 32767),
            rng.randint(-32767, 32767),
            rng.randint(-32767, 32767),
            rng.randrange(0x10000),
        )


def main() -> None:
    binary, entry = assemble()
    worst = 0
    checked = 0
    for index, case in enumerate(cases()):
        coeff, damping, first, second, velocity, sample = case
        before = encode_filter(coeff, damping, first, second, velocity)
        want = oracle(before, sample)
        got, cycles = run(binary, entry, f'case-{index:03d}', before, sample)
        if got != want:
            diffs = [
                (i, actual, expected)
                for i, (actual, expected) in enumerate(zip(got, want))
                if actual != expected
            ]
            fail(f'case {index} mismatch: {diffs[:8]}')
        worst = max(worst, cycles)
        checked += 1

    print(
        f'Noise Hat one-pass filter DSP: PASS ({checked} exact states; '
        f'{binary.stat().st_size // 3} P words; worst {worst} modeled cycles)'
    )


if __name__ == '__main__':
    main()

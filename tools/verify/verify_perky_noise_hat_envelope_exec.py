#!/usr/bin/env python3
"""Execute the Noise Hat two-curve DSP envelope against the compact oracle."""
from __future__ import annotations

from pathlib import Path
import random
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
PERKY = ROOT / 'modules/perky'
OUT = ROOT / 'out/perky/noise-hat-envelope'
ASM = ROOT / 'vendor/dsp56300/build/source/dsp_host/dsp_asm'
HOST = ROOT / 'out/perky/simple-drum-envelope/bd909_host'
ORG = 0x2800
STATE_BASE = 0x200
ENV_BASE = 0x20
RESULT_OFF = 0x61
ENV1_BASE = 0x09A5
ENV2_BASE = 0x0C51

sys.path.insert(0, str(PERKY))
import resonator_compact as c  # noqa:E402
import simple_drum_tables as tables  # noqa:E402


def fail(message: str) -> None:
    raise SystemExit('verify-perky-noise-hat-envelope-exec: ' + message)


def set_u32(words: list[int], off: int, value: int) -> None:
    value &= c.MASK32
    words[off] = value & c.MASK16
    words[off + 1] = (value >> 16) & c.MASK16


def make_tables():
    env1 = [min(65535, (i * i * 65535) // (1024 * 1024)) for i in range(1025)]
    env2 = [((i * 251) + ((i * 37) & 0x1fff)) & 0xffff for i in range(1025)]
    blob1 = b''.join(struct.pack('<H', value) for value in env1)
    blob2 = b''.join(struct.pack('<H', value) for value in env2)
    return blob1, blob2, tables.pack_u16(env1), tables.pack_u16(env2)


def oracle(before: list[int], env1: bytes, env2: bytes):
    state = list(before)
    amplitude = c.render_envelope(state, 0, env1, env2)
    return state, amplitude


def assemble() -> tuple[Path, int]:
    missing = [p for p in (ASM, HOST) if not p.exists()]
    if missing:
        fail('run the existing PERKY setup/build gates first; missing '
             + ', '.join(map(str, missing)))
    OUT.mkdir(parents=True, exist_ok=True)
    source = (
        'pk_noise_hat_envelope_probe:\n'
        f' move #>${STATE_BASE + ENV_BASE:x},r6\n'
        f' move #>${STATE_BASE:x},r5\n'
        ' jsrl pk_noise_hat_envelope\n'
        f' move a1,x:(r5+${RESULT_OFF:x})\n'
        ' rts\n'
        + (PERKY / 'noise_hat_envelope.asm').read_text()
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
        parts[0]: int(parts[1], 16)
        for parts in map(str.split, symbols.read_text().splitlines())
        if len(parts) == 2
    }
    if 'pk_noise_hat_envelope_probe' not in labels:
        fail('assembler emitted no envelope probe symbol')
    return binary, labels['pk_noise_hat_envelope_probe']


def run(binary: Path, entry: int, tag: str, before: list[int],
        env1_words, env2_words):
    state = [0] * 0x70
    state[ENV_BASE:ENV_BASE + c.ENV_WORDS] = before
    data = OUT / f'{tag}.data'
    script = OUT / f'{tag}.script'
    raw = OUT / f'{tag}.raw'
    dump = OUT / f'{tag}.state'
    meter = OUT / f'{tag}.meter'
    data.write_text(
        f'X {STATE_BASE:x} ' + ' '.join(f'{word:06x}' for word in state) + '\n'
        + f'Y {ENV1_BASE:x} ' + ' '.join(f'{word:06x}' for word in env1_words) + '\n'
        + f'Y {ENV2_BASE:x} ' + ' '.join(f'{word:06x}' for word in env2_words) + '\n'
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
    dumped = [int(word, 16) for word in dump.read_text().split()]
    final = [
        word & 0xffff
        for word in dumped[ENV_BASE:ENV_BASE + c.ENV_WORDS]
    ]
    amplitude = dumped[RESULT_OFF] & 0xffff
    cycles = int(meter.read_text().strip())
    return final, amplitude, cycles


def cases():
    # Hand-picked endpoint/transition states first.
    for shape in range(3):
        for state, value, trigger in (
            (0, 0, 0),
            (0, 0, 1),
            (1, 0x0ffbff, 0),
            (1, 0x0fffff, 0),
            (3, 0x080000, 0),
            (4, 1, 0),
            (4, 0x040000, 1),
        ):
            words = [0] * c.ENV_WORDS
            words[c.ENV_STATE] = state
            words[c.ENV_SHAPE] = shape
            words[c.ENV_FLAG4] = 0
            words[c.ENV_FLAG6] = 0
            words[c.ENV_TRIGGER] = trigger
            set_u32(words, c.ENV_VALUE, value)
            set_u32(words, c.ENV_HOLD, 0)
            words[c.ENV_ATTACK] = 0x400
            words[c.ENV_DECAY] = 0x200
            yield words

    rng = random.Random(0x454e5632)
    for index in range(192):
        words = [0] * c.ENV_WORDS
        words[c.ENV_STATE] = rng.choice((0, 1, 3, 4))
        words[c.ENV_SHAPE] = index % 3
        words[c.ENV_FLAG4] = rng.choice((0, 1))
        words[c.ENV_FLAG6] = rng.choice((0, 1))
        words[c.ENV_TRIGGER] = rng.choice((0, 1))
        set_u32(words, c.ENV_VALUE, rng.randrange(0x100000))
        set_u32(words, c.ENV_HOLD, rng.choice((0, 1, 0x100, rng.randrange(1 << 20))))
        words[c.ENV_ATTACK] = rng.randrange(0x10000)
        words[c.ENV_DECAY] = rng.randrange(0x10000)
        yield words


def main() -> None:
    binary, entry = assemble()
    env1, env2, env1_words, env2_words = make_tables()
    worst = 0
    checked = 0
    shape_counts = [0, 0, 0]
    for index, before in enumerate(cases()):
        shape_counts[before[c.ENV_SHAPE]] += 1
        expected_state, expected_amplitude = oracle(before, env1, env2)
        final, amplitude, cycles = run(
            binary, entry, f'case-{index:03d}', before, env1_words, env2_words
        )
        if final != expected_state:
            diffs = [
                (i, actual, want)
                for i, (actual, want) in enumerate(zip(final, expected_state))
                if actual != want
            ]
            fail(f'case {index} state mismatch: {diffs[:8]}')
        if amplitude != expected_amplitude:
            fail(
                f'case {index} amplitude got {amplitude:04x}, '
                f'want {expected_amplitude:04x}'
            )
        worst = max(worst, cycles)
        checked += 1

    print(
        f'Noise Hat two-curve envelope DSP: PASS ({checked} exact states; '
        f'shapes={shape_counts}; {binary.stat().st_size // 3} P words; '
        f'worst {worst} modeled cycles)'
    )


if __name__ == '__main__':
    main()

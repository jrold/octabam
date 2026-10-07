#!/usr/bin/env python3
"""Local full-DSP gate for both classic Noise Hat modes.

Assembles and executes the complete inner renderer + authentic 4,805-word
wrapper delay. Synthetic envelope tables are relocated only for this gate so
the Y ring can occupy a contiguous test range. Compares exact PCM, all 121 hot
X-state words, all 4,805 ring words, and for white-noise M1 the outer hold and
firmware-global RNG sideband.
"""
from __future__ import annotations

from pathlib import Path
import json
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

OUT = ROOT / 'out/perky/noise-hat-classic-synthetic'
ASM = ROOT / 'vendor/dsp56300/build/source/dsp_host/dsp_asm'
HOST = ROOT / 'out/perky/simple-drum-envelope/bd909_host'
ORG = 0x2800
STATE = 0x0200
RING = STATE
SCRATCH = 0x1400
SCRATCH_DUMP_OFF = SCRATCH - STATE
ENV1_BASE = 0x2000
ENV2_BASE = 0x2600
FRAMES = 16
BLOCKS = 4
CASES_PER_MODE = 32


from verify_perky_simple_drum_envelope_exec import build_host  # noqa:E402
from perky_noise_hat_dsp_support import audit_source, audit_binary  # noqa:E402

def fail(message: str) -> None:
    raise SystemExit('verify-perky-noise-hat-classic-synthetic-exec: ' + message)


def set_u32(words: list[int], off: int, value: int) -> None:
    value &= c.MASK32
    words[off] = value & c.MASK16
    words[off + 1] = (value >> 16) & c.MASK16


def set_s32(words: list[int], off: int, value: int) -> None:
    set_u32(words, off, value & c.MASK32)


def make_envelopes():
    values1 = []
    values2 = []
    for i in range(2048):
        values1.append((i * 43 + i * i * 5) & 0xffff)
        values2.append((0xffff - ((i * 181) ^ (i * 17))) & 0xffff)
    blob1 = b''.join(struct.pack('<H', value) for value in values1)
    blob2 = b''.join(struct.pack('<H', value) for value in values2)
    return blob1, blob2, tables.pack_u16(values1), tables.pack_u16(values2)


def make_env(w: list[int], base: int, rng: random.Random, shape: int) -> None:
    w[base + c.ENV_STATE] = rng.choice((0, 1, 3, 4))
    w[base + c.ENV_SHAPE] = shape
    w[base + c.ENV_FLAG4] = rng.choice((0, 1))
    w[base + c.ENV_FLAG6] = rng.choice((0, 1))
    w[base + c.ENV_TRIGGER] = rng.choice((0, 1))
    set_u32(w, base + c.ENV_VALUE, rng.randrange(0x100000))
    set_u32(w, base + c.ENV_HOLD, rng.randrange(1 << 20))
    w[base + c.ENV_ATTACK] = rng.randrange(0x10000)
    w[base + c.ENV_DECAY] = rng.randrange(0x10000)


def make_filter(w: list[int], base: int, rng: random.Random) -> None:
    w[base + hats.F_DAMP] = rng.randrange(0x10000)
    w[base + hats.F_COEFF] = rng.randrange(0x10000)
    set_s32(w, base + hats.F_FIRST, rng.randint(-32767, 32767))
    set_s32(w, base + hats.F_SECOND, rng.randint(-32767, 32767))
    set_s32(w, base + hats.F_VELOCITY, rng.randint(-32767, 32767))


def make_voice(mode: int, seed: int):
    rng = random.Random(0x434c41530000 + mode * 0x1000 + seed)
    w = [0] * hats.CLASSIC_WORDS
    w[hats.C_MUTE] = int(seed % 19 == 0)

    if mode == 0:
        w[hats.C0_VELOCITY] = rng.randrange(0x100)
        make_env(w, hats.C0_ENV, rng, seed % 3)
        for i in range(6):
            base = hats.C0_PULSES + i * hats.PULSE_WORDS
            if seed % 7 == 0:
                set_u32(w, base + hats.P_PHASE, 0x00100001 + i)
                set_u32(w, base + hats.P_INCREMENT, 1 + i)
            else:
                set_u32(w, base + hats.P_PHASE, rng.randrange(1 << 32))
                set_u32(w, base + hats.P_INCREMENT, rng.randrange(1 << 32))
            w[base + hats.P_WIDTH] = rng.randrange(0x10000)
            w[base + hats.P_RELOAD] = rng.randrange(0x10000)
        for i in range(4):
            make_filter(w, hats.C0_FILTERS + i * hats.FILTER_WORDS, rng)
    else:
        w[hats.C1_VELOCITY] = rng.randrange(0x100)
        make_env(w, hats.C1_ENV, rng, seed % 3)
        w[hats.C1_NOISE + 0] = rng.randrange(4)
        w[hats.C1_NOISE + 1] = rng.randrange(5)
        w[hats.C1_NOISE + 2] = rng.randrange(0x10000)
        make_filter(w, hats.C1_FILTER, rng)
        w[hats.C1_USE_SECOND] = rng.randrange(2)
        w[hats.C1_MUTE] = int(seed % 23 == 0)
        w[hats.C1_HOLD_RELOAD] = rng.randrange(5)
        w[hats.C1_MIX] = rng.randrange(0x10000)
        w[hats.C1_RANGE] = rng.randrange(0x10000)

    for i in range(5):
        w[hats.C_DELAY_TAPS + i] = rng.randrange(hats.RING_LEN)
        w[hats.C_DELAY_TAPS + 5 + i] = rng.randrange(0x10000)
    w[hats.C_DELAY_INDEX] = hats.RING_LEN - 1 if seed % 5 == 0 else rng.randrange(hats.RING_LEN)
    w[hats.C_DELAY_MIX] = rng.randrange(0x10000)

    ring = [rng.randrange(0x10000) for _ in range(hats.RING_LEN)]
    hold = [rng.randrange(5), rng.randrange(0x10000)]
    global_rng = [rng.randrange(1 << 32), rng.randrange(1 << 32)]
    return hats.NoiseHatClassic(w, ring, hold), global_rng


def assemble(mode: int) -> tuple[Path, int]:
    build_host()
    missing = [p for p in (ASM, HOST) if not p.exists()]
    if missing:
        fail('local DSP toolchain is missing: ' + ', '.join(map(str, missing)))
    OUT.mkdir(parents=True, exist_ok=True)

    voice_name = f'noise_hat_classic_mode{mode}_voice.asm'
    inner_name = f'noise_hat_classic_mode{mode}.asm'
    entry_name = f'pk_noise_hat_classic_mode{mode}_probe'
    target_name = f'pk_noise_hat_classic_mode{mode}_voice'

    source = (
        f'{entry_name}:\n'
        f' move #>${STATE:x},r6\n'
        f' move #>${SCRATCH:x},r5\n'
        f' move #>${RING:x},r4\n'
        f' jsr {target_name}\n'
        ' rts\n'
    )
    for name in (
        voice_name,
        inner_name,
        'noise_hat_classic_delay.asm',
        'noise_hat_filter.asm',
        'noise_hat_envelope.asm',
        'noise_tone_math.asm',
    ):
        source += (ROOT / 'modules/perky' / name).read_text() + '\n'

    # Keep the full authentic ring at Y:$0200..$14c4. Only the synthetic test
    # curves move; runtime math/layout is otherwise unchanged.
    source = source.replace('#>$0009a5,r1', f'#>${ENV1_BASE:06x},r1')
    source = source.replace('#>$000c51,r1', f'#>${ENV2_BASE:06x},r1')
    source = force_long_local_jsr(relativize_local_conditionals(source))

    audit_source(source)
    asm = OUT / f'mode{mode}.asm'
    binary = OUT / f'mode{mode}.bin'
    symbols = OUT / f'mode{mode}.sym'
    asm.write_text(source)
    result = subprocess.run(
        [str(ASM), '-in', str(asm), '-org', f'{ORG:x}',
         '-out', str(binary), '-sym', str(symbols), '-list'],
        capture_output=True, text=True,
    )
    if result.returncode:
        fail(f'mode {mode} assembler failed:\n' + result.stdout[-6000:] + result.stderr[-3000:])
    audit_binary(result.stdout, binary, ORG)
    labels = {
        p[0]: int(p[1], 16)
        for p in map(str.split, symbols.read_text().splitlines())
        if len(p) == 2
    }
    if entry_name not in labels:
        fail(f'mode {mode}: assembler emitted no {entry_name} symbol')
    return binary, labels[entry_name]


def split_u32(value: int):
    return value & 0xffff, (value >> 16) & 0xffff


def main() -> None:
    env1, env2, env1_words, env2_words = make_envelopes()
    script = OUT / 'case.script'
    OUT.mkdir(parents=True, exist_ok=True)
    script.write_text((' '.join(['0'] * 12 + ['-1']) + '\n') * BLOCKS)

    total_samples = 0
    worst = {0: 0, 1: 0}
    for mode in (0, 1):
        binary, entry = assemble(mode)
        for index in range(CASES_PER_MODE):
            voice, global_rng = make_voice(mode, index + 1)
            expected = hats.NoiseHatClassic(
                list(voice.words), list(voice.ring), list(voice.hold)
            )
            expected_rng = list(global_rng)
            want = expected.render(FRAMES * BLOCKS, mode, env1, env2, expected_rng)

            # Host state dump starts at X/Y:$0200. Scratch lives at X:$1400,
            # still inside the 4,805-word dump span, so hold/RNG are observable.
            xwords = [0] * hats.RING_LEN
            xwords[:hats.CLASSIC_WORDS] = voice.words
            sb = SCRATCH_DUMP_OFF
            xwords[sb + 0x70] = voice.hold[0]
            xwords[sb + 0x71] = voice.hold[1]
            lo, hi = split_u32(global_rng[0])
            xwords[sb + 0x72:sb + 0x74] = [lo, hi]
            lo, hi = split_u32(global_rng[1])
            xwords[sb + 0x74:sb + 0x76] = [lo, hi]

            data = OUT / 'case.data'
            data.write_text(
                f'X {STATE:x} ' + ' '.join(f'{v:06x}' for v in xwords) + '\n'
                + f'Y {RING:x} ' + ' '.join(f'{v:06x}' for v in voice.ring) + '\n'
                + f'Y {ENV1_BASE:x} ' + ' '.join(f'{v:06x}' for v in env1_words) + '\n'
                + f'Y {ENV2_BASE:x} ' + ' '.join(f'{v:06x}' for v in env2_words) + '\n'
            )
            pcm = OUT / 'case.raw'
            dump = OUT / 'case.state'
            meter = OUT / 'case.meter'
            result = subprocess.run(
                [str(HOST), '-code', str(binary), '-org', f'{ORG:x}',
                 '-entry', f'{entry:x}', '-data', str(data), '-script', str(script),
                 '-out', str(pcm), '-state', str(dump),
                 '-state-words', str(hats.RING_LEN), '-meter', str(meter),
                 '-cycle-meter', '1'],
                capture_output=True, text=True,
            )
            if result.returncode:
                fail(f'mode {mode} case {index}: host failed:\n'
                     + result.stdout[-2500:] + result.stderr[-2500:])

            stereo = list(struct.unpack(f'<{2 * FRAMES * BLOCKS}i', pcm.read_bytes()))
            got = stereo[::2]
            if stereo[1::2] != got:
                fail(f'mode {mode} case {index}: stereo channels differ')
            if got != want:
                diffs = [(i, a, b) for i, (a, b) in enumerate(zip(got, want)) if a != b]
                fail(f'mode {mode} case {index} PCM mismatch: {diffs[:8]}')

            dumped = [int(v, 16) for v in dump.read_text().splitlines()[-1].split()]
            xdump = dumped[:hats.RING_LEN]
            ydump = dumped[hats.RING_LEN:2 * hats.RING_LEN]
            final_words = [v & 0xffff for v in xdump[:hats.CLASSIC_WORDS]]
            if final_words != expected.words:
                diffs = [(i, a, b) for i, (a, b) in enumerate(zip(final_words, expected.words)) if a != b]
                fail(f'mode {mode} case {index} X-state mismatch: {diffs[:10]}')
            final_ring = [v & 0xffff for v in ydump]
            if final_ring != expected.ring:
                diffs = [(i, a, b) for i, (a, b) in enumerate(zip(final_ring, expected.ring)) if a != b]
                fail(f'mode {mode} case {index} ring mismatch: {diffs[:8]}')

            if mode == 1:
                hold = [xdump[sb + 0x70] & 0xffff, xdump[sb + 0x71] & 0xffff]
                if hold != expected.hold:
                    fail(f'mode 1 case {index} hold mismatch: {hold} != {expected.hold}')
                rng0 = (xdump[sb + 0x72] & 0xffff) | ((xdump[sb + 0x73] & 0xffff) << 16)
                rng1 = (xdump[sb + 0x74] & 0xffff) | ((xdump[sb + 0x75] & 0xffff) << 16)
                if [rng0, rng1] != expected_rng:
                    fail(f'mode 1 case {index} RNG mismatch: {[rng0, rng1]} != {expected_rng}')

            worst[mode] = max(worst[mode], max(map(int, meter.read_text().split())))
            total_samples += FRAMES * BLOCKS

    report = dict(pcm_samples=total_samples, continuation_blocks=2 * CASES_PER_MODE * BLOCKS,
                  state_words=hats.CLASSIC_WORDS, ring_words=hats.RING_LEN,
                  scratch_words=0x77, max_modeled_cycles=worst,
                  development_block_allowance=23040,
                  within_allowance={mode: cycles <= 23040 for mode, cycles in worst.items()},
                  program_words={mode: (OUT / f'mode{mode}.bin').stat().st_size // 3 for mode in (0, 1)},
                  hardware_qualified=False, production_integrated=False)
    (OUT / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(
        'Noise Hat classic synthetic DSP: PASS '
        f'({total_samples} exact PCM samples; 121 X words + {hats.RING_LEN} Y-ring words/case; '
        f'M1 hold/RNG exact; worst cycles M2={worst[0]} M1={worst[1]})'
    )


if __name__ == '__main__':
    main()

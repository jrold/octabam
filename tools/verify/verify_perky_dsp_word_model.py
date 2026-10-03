#!/usr/bin/env python3
"""Bit-exact gate for the DSP56300-oriented PERKY Noise/Tone word model.

No firmware fixture is needed.  Synthetic waves/envelopes and deterministic
engine states exercise the proposed one-byte-per-DSP-word representation and
the 16-bit-limb 32-bit arithmetic.  Samples, all 0x120 state bytes and both RNG
words must match noise_tone_ref after every block.
"""
from __future__ import annotations

import math
import pathlib
import random
import struct
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
PERKY = ROOT / "modules" / "perky"
sys.path.insert(0, str(PERKY))

import noise_tone_ref as ref  # noqa: E402
import noise_tone_word_model as dsp  # noqa: E402

MASK32 = 0xFFFFFFFF


def fail(msg: str) -> None:
    raise SystemExit(f"verify-perky-dsp-word-model: {msg}")


def put16(s: bytearray, off: int, value: int) -> None:
    value &= 0xFFFF
    s[off] = value & 0xFF
    s[off + 1] = value >> 8


def put32(s: bytearray, off: int, value: int) -> None:
    value &= MASK32
    s[off] = value & 0xFF
    s[off + 1] = (value >> 8) & 0xFF
    s[off + 2] = (value >> 16) & 0xFF
    s[off + 3] = value >> 24


def s16_bytes(values) -> bytes:
    return b"".join(struct.pack("<h", max(-32768, min(32767, int(v)))) for v in values)


def u16_bytes(values) -> bytes:
    return b"".join(struct.pack("<H", int(v) & 0xFFFF) for v in values)


def synthetic_tables() -> tuple[dict[int, bytes], bytes, bytes]:
    addresses = (0x10000000, 0x10001000, 0x10002000, 0x10003000)
    waves = {
        addresses[0]: s16_bytes(round(30000 * math.sin(2 * math.pi * i / 256)) for i in range(256)),
        addresses[1]: s16_bytes(-30000 + round(60000 * i / 255) for i in range(256)),
        addresses[2]: s16_bytes(28000 if i < 128 else -28000 for i in range(256)),
        addresses[3]: s16_bytes(((i * 4051 + 1777) & 0xFFFF) - 32768 for i in range(256)),
    }
    env1 = u16_bytes(round(65535 * i / 2047) for i in range(2048))
    env2 = u16_bytes(round(65535 * (i / 2047) ** 2) for i in range(2048))
    return waves, env1, env2


def fixture(r: random.Random, waves: dict[int, bytes]) -> bytearray:
    s = bytearray(r.getrandbits(8) for _ in range(ref.STATE_BYTES))
    addresses = tuple(waves)

    # Overall velocity and Noise/Hold.
    s[6] = r.randrange(128)
    put16(s, 0x60, r.randrange(5))
    put16(s, 0x62, r.randrange(5))
    put16(s, 0x70, r.randrange(0x10000))

    # Amplitude envelope at +0x74.  Values stay in the real 20-bit domain but
    # increments/decrements deliberately cross boundaries during a block.
    e = 0x74
    s[e] = r.choice((0, 1, 3, 4))
    s[e + 1] = r.randrange(4)          # 0/3 linear, 1/2 table-shaped
    s[e + 4] = r.randrange(2)
    s[e + 6] = r.randrange(2)
    s[e + 7] = r.randrange(2)
    put32(s, e + 0x0C, r.randrange(0x100000))
    put32(s, e + 0x10, r.choice((0, r.getrandbits(32))))
    put16(s, e + 0x20, r.randrange(1, 0x10000))
    put16(s, e + 0x22, r.randrange(1, 0x10000))

    # The resonant noise filter.  Its integrators are small signed values in
    # normal operation; coefficient/damping cover the full stored u16 range.
    f = 0x9C
    put16(s, f + 0x0C, r.randrange(0x10000))
    put16(s, f + 0x0E, r.randrange(0x10000))
    put32(s, f + 0x10, r.randrange(-32767, 32768))
    put32(s, f + 0x14, r.randrange(-32767, 32768))
    put32(s, f + 0x18, r.randrange(-32767, 32768))

    # Two wavetable oscillators.  Current/next addresses are firmware-style
    # identifiers here; the real DSP table extractor will map them to local
    # table bases before assembly/runtime use.
    for base in (0x2C, 0xC4):
        put32(s, base + 4, r.randrange(0x100001))
        put32(s, base + 8, r.randrange(1, 0x50000))
        put32(s, base + 0x0C, r.choice(addresses))
        put32(s, base + 0x10, r.choice(addresses))

    put32(s, 0xF8, r.randrange(0x1000))
    return s


def primitive_gate() -> None:
    r = random.Random(0x504B5931)
    for i in range(20000):
        a = r.getrandbits(32)
        b = r.getrandbits(32)
        shift = r.randrange(32)
        aw, bw = dsp.U32.from_int(a), dsp.U32.from_int(b)

        got = dsp.mul_low32_words(aw, bw).unsigned()
        want = (a * b) & MASK32
        if got != want:
            fail(f"mul-low32 case {i}: {got:08x} != {want:08x}")

        low, high = dsp.mul_full64_words(aw, bw)
        product = a * b
        if low.unsigned() != (product & MASK32) or high.unsigned() != ((product >> 32) & MASK32):
            fail(f"mul-full64 case {i}")

        got_shift = dsp.arshift32_words(aw, shift).signed()
        signed = a - 0x100000000 if a & 0x80000000 else a
        want_shift = signed >> shift
        if got_shift != want_shift:
            fail(f"arshift case {i}: {got_shift} != {want_shift}")

    # RNG is a particularly useful primitive gate because it needs low32 and
    # high32 products, carry from +1, modulo addition and the 31-bit return.
    for i in range(64):
        low = r.getrandbits(32)
        high = r.getrandbits(32)
        rr = ref.RngState(low, high)
        dr = dsp.WordRng.from_ints(low, high)
        for step in range(128):
            want = ref.next_random(rr)
            got = dsp.next_random(dr).unsigned()
            if got != want or dr.low.unsigned() != rr.low or dr.high.unsigned() != rr.high:
                fail(f"rng case {i} step {step}")


def renderer_gate() -> None:
    waves, env1, env2 = synthetic_tables()
    r = random.Random(0x12056300)

    for case in range(96):
        original = fixture(r, waves)
        state_ref = bytearray(original)
        state_dsp = bytearray(original)
        low, high = r.getrandbits(32), r.getrandbits(32)
        rng_ref = ref.RngState(low, high)
        rng_dsp = dsp.WordRng.from_ints(low, high)
        n = r.randrange(1, 97)

        want = ref.render_block(state_ref, n, waves, rng_ref, env1, env2)
        got, final_state = dsp.render_block(state_dsp, n, waves, rng_dsp, env1, env2)

        if got != want:
            at = next(i for i, (a, b) in enumerate(zip(got, want)) if a != b)
            fail(f"render case {case}: sample {at}: word model {got[at]} != oracle {want[at]}")
        if final_state != bytes(state_ref):
            at = next(i for i, (a, b) in enumerate(zip(final_state, state_ref)) if a != b)
            fail(f"render case {case}: state byte 0x{at:03x}: {final_state[at]:02x} != {state_ref[at]:02x}")
        if rng_dsp.low.unsigned() != rng_ref.low or rng_dsp.high.unsigned() != rng_ref.high:
            fail(f"render case {case}: final RNG differs")


def main() -> None:
    primitive_gate()
    renderer_gate()
    print("PERKY DSP word model: PASS (20k arithmetic cases, 8192 RNG steps, 96 render blocks)")


if __name__ == "__main__":
    main()

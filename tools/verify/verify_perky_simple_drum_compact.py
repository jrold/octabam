#!/usr/bin/env python3
"""Qualify the 34-word Simple Drum compact renderer and pitch cache.

The test uses deterministic synthetic tables only. It compares the compact
state against the independent ARM-shaped translation of PerkyBits'
``NativeV121SimpleDrum`` implementation, then proves that preparing the static
base pitch once per block is bit-identical to the reference's per-sample lookup.
"""
from __future__ import annotations

from pathlib import Path
import random
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
PERKY = ROOT / "modules" / "perky"
sys.path.insert(0, str(PERKY))

import simple_drum_compact as compact  # noqa: E402
import simple_drum_ref as ref  # noqa: E402

MASK32 = 0xFFFFFFFF
WAVE_ADDRESSES = (0x10001000, 0x10001200)


def put16(state: bytearray, off: int, value: int) -> None:
    struct.pack_into("<H", state, off, value & 0xFFFF)


def put32(state: bytearray, off: int, value: int) -> None:
    struct.pack_into("<I", state, off, value & MASK32)


def table_u16(count: int, fn) -> bytes:
    out = bytearray()
    for i in range(count):
        out += struct.pack("<H", fn(i) & 0xFFFF)
    return bytes(out)


def table_s16(count: int, fn) -> bytes:
    out = bytearray()
    for i in range(count):
        out += struct.pack("<h", max(-32768, min(32767, int(fn(i)))))
    return bytes(out)


def tables():
    pitch = table_u16(4096, lambda i: (17 + i * 13 + (i * i >> 7)) & 0xFFFF)
    env1 = table_u16(2048, lambda i: min(0xFFFF, i * 31))
    env2 = table_u16(2048, lambda i: ((i * i) >> 5) & 0xFFFF)
    wave_a = table_s16(256, lambda i: ((i * 257) & 0xFFFF) - 32768)
    wave_b = table_s16(256, lambda i: 28000 - abs(128 - i) * 430)
    return {WAVE_ADDRESSES[0]: wave_a, WAVE_ADDRESSES[1]: wave_b}, pitch, env1, env2


def seed_envelope(state: bytearray, base: int, r: random.Random) -> None:
    state[base] = r.choice((0, 1, 2, 3, 4))
    state[base + 1] = r.randrange(4)
    state[base + 4] = r.randrange(2)
    state[base + 6] = r.randrange(2)
    state[base + 7] = r.randrange(2)
    put32(state, base + 0x0C, r.randrange(0x100000))
    put32(state, base + 0x10, r.choice((0, r.getrandbits(32))))
    put16(state, base + 0x20, r.randrange(1, 0x10000))
    put16(state, base + 0x22, r.randrange(1, 0x10000))


def fixture(r: random.Random) -> bytearray:
    state = bytearray(r.getrandbits(8) for _ in range(ref.STATE_BYTES))
    state[6] = r.randrange(256)
    state[0xB8] = r.randrange(2)
    put32(state, 0x30, r.randrange(0x00100001))
    put32(state, 0x34, r.randrange(1, 0x50000))
    put32(state, 0x38, r.choice(WAVE_ADDRESSES))
    put32(state, 0x3C, r.choice(WAVE_ADDRESSES))
    seed_envelope(state, 0x74, r)
    seed_envelope(state, 0xC4, r)
    # All raw 16-bit values are valid in the native lookup except 0x8000,
    # whose signed-magnitude corner would address outside the 4096-entry table.
    raw_pitch = r.randrange(0x10000)
    if raw_pitch == 0x8000:
        raw_pitch = 0x7FFF
    put16(state, 0xBA, raw_pitch)
    put16(state, 0xEC, r.randrange(0x10000))
    return state


def main() -> None:
    if compact.WORDS_PER_VOICE != 34:
        raise AssertionError(f"Simple Drum ABI drifted to {compact.WORDS_PER_VOICE} words")
    offsets = compact.abi_offsets()
    if offsets["velocity"] != 0 or offsets["pitch_env_amount"] != 33:
        raise AssertionError("Simple Drum named ABI no longer spans words 0..33")

    waves, pitch, env1, env2 = tables()
    r = random.Random(0x5344524D)
    max_block = 0
    extended_pitch_cases = 0
    for case in range(240):
        original = fixture(r)
        raw_pitch = original[0xBA] | (original[0xBB] << 8)
        signed_pitch = raw_pitch if raw_pitch < 0x8000 else raw_pitch - 0x10000
        magnitude = signed_pitch if signed_pitch >= 0 else ((-raw_pitch) & 0xFFFF)
        magnitude = magnitude if magnitude < 0x8000 else magnitude - 0x10000
        if magnitude >= 0x1000:
            extended_pitch_cases += 1
        cv = compact.CompactSimpleDrum.from_arm(original)
        if cv.apply_to_arm(original) != bytes(original):
            raise AssertionError(f"case {case}: compact import/export is not lossless")

        count = r.randrange(1, 97)
        max_block = max(max_block, count)
        full_state = bytearray(original)
        want, final_full = ref.render_block(full_state, count, waves, pitch, env1, env2)

        # The actual compact shipping candidate uses one prepared pitch value
        # per block. This is the optimization that removes the 4096-word pitch
        # table from the per-sample DSP data path.
        prepared = compact.cached_base_frequency(cv, pitch)
        got = compact.render_block(
            cv, count, waves, pitch, env1, env2,
            prepared_base_frequency=prepared,
        )
        final_compact = cv.apply_to_arm(original)

        if got != want:
            at = next(i for i, (a, b) in enumerate(zip(got, want)) if a != b)
            raise AssertionError(
                f"case {case}: PCM sample {at}: compact {got[at]} != ref {want[at]}"
            )
        if final_compact != final_full:
            at = next(i for i, (a, b) in enumerate(zip(final_compact, final_full)) if a != b)
            raise AssertionError(
                f"case {case}: final state byte 0x{at:03x}: "
                f"compact {final_compact[at]:02x} != ref {final_full[at]:02x}"
            )

    print(
        "PERKY Simple Drum compact: PASS "
        f"(34 words/voice, 240 randomized renders, blocks up to {max_block} samples, "
        f"prepared base-pitch path exact; {extended_pitch_cases} extended-pitch cases)"
    )


if __name__ == "__main__":
    main()

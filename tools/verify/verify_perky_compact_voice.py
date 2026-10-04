#!/usr/bin/env python3
"""Prove the 41-word PERKY Noise/Tone shipping-state candidate.

This gate compares the compact voice directly with the already-proven full
DSP word model.  Synthetic tables are used; no firmware-owned data enters the
repository.  For every randomized case it requires:

* ARM-shaped -> compact -> ARM-shaped is lossless for renderer-owned fields;
* PCM is bit-identical for the complete renderer;
* every renderer-mutated byte is identical after writing compact state back;
* the shared two-word RNG ends in the identical state;
* four compact voices + the four-word RNG consume exactly 168 X words.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import random
import struct
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
PERKY = ROOT / "modules" / "perky"
TOOLS = ROOT / "tools" / "perky"
sys.path.insert(0, str(PERKY))

import noise_tone_compact as compact  # noqa: E402
import noise_tone_word_model as full  # noqa: E402
import noise_tone_ref as ref  # noqa: E402


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot import {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


fab = load_module("perky_fixture_fab", TOOLS / "fabricate_noise_tone_fixtures.py")

MASK32 = 0xFFFFFFFF


def put16(state: bytearray, off: int, value: int) -> None:
    struct.pack_into("<H", state, off, value & 0xFFFF)


def put32(state: bytearray, off: int, value: int) -> None:
    struct.pack_into("<I", state, off, value & MASK32)


def fixture(r: random.Random) -> bytearray:
    # Start noisy so apply_to_arm() has to preserve every byte outside the
    # renderer ABI rather than getting a free pass from a zero-filled object.
    state = bytearray(r.getrandbits(8) for _ in range(ref.STATE_BYTES))
    addresses = fab.WAVE_ADDRESSES

    state[6] = r.randrange(256)

    # Two oscillators: phases straddle the strict > 0x00100000 wrap threshold
    # across the randomized block, and current/next pointers vary independently.
    for base in (0x2C, 0xC4):
        put32(state, base + 4, r.randrange(0x00100001))
        put32(state, base + 8, r.randrange(1, 0x50000))
        put32(state, base + 0x0C, r.choice(addresses))
        put32(state, base + 0x10, r.choice(addresses))

    # Noise sample-and-hold.
    put16(state, 0x60, r.randrange(6))
    put16(state, 0x62, r.randrange(6))
    put16(state, 0x70, r.randrange(0x10000))

    # Amplitude envelope, including linear/table shapes and all live states.
    e = 0x74
    state[e] = r.choice((0, 1, 2, 3, 4))
    state[e + 1] = r.randrange(4)
    state[e + 4] = r.randrange(2)
    state[e + 6] = r.randrange(2)
    state[e + 7] = r.randrange(2)
    put32(state, e + 0x0C, r.randrange(0x100000))
    put32(state, e + 0x10, r.choice((0, r.getrandbits(32))))
    put16(state, e + 0x20, r.randrange(1, 0x10000))
    put16(state, e + 0x22, r.randrange(1, 0x10000))

    # Resonant noise filter state.
    f = 0x9C
    put16(state, f + 0x0C, r.randrange(0x10000))
    put16(state, f + 0x0E, r.randrange(0x10000))
    put32(state, f + 0x10, r.randrange(-32767, 32768))
    put32(state, f + 0x14, r.randrange(-32767, 32768))
    put32(state, f + 0x18, r.randrange(-32767, 32768))

    # The real path normally keeps MIX around a 12-bit domain, but the integer
    # renderer is modulo-32 exact. Exercise normal and deliberately hostile
    # values so compacting state never smuggles in an accidental clamp.
    put32(state, 0xF8, r.choice((r.randrange(0x1000), r.getrandbits(32))))
    return state


def load_tables(directory: Path):
    fab.emit_tables(directory)
    waves = {
        address: (directory / f"wave_{address:08x}.bin").read_bytes()
        for address in fab.WAVE_ADDRESSES
    }
    return (
        waves,
        (directory / "envelope1.bin").read_bytes(),
        (directory / "envelope2.bin").read_bytes(),
    )


def main() -> None:
    if compact.WORDS_PER_VOICE != 41:
        raise AssertionError(f"compact ABI drifted to {compact.WORDS_PER_VOICE} words")
    if compact.WORDS_PER_VOICE * 4 + 4 != 168:
        raise AssertionError("four compact voices + global RNG no longer equal 168 X words")

    offsets = compact.abi_offsets()
    if len(offsets) != 27:
        raise AssertionError(f"ABI field map has {len(offsets)} entries, expected 27")
    if min(offsets.values()) != 0 or max(offsets.values()) != 39:
        raise AssertionError("ABI named offsets escaped the 0..40 voice block")

    with tempfile.TemporaryDirectory(prefix="perky-compact.") as td:
        waves, env1, env2 = load_tables(Path(td))
        r = random.Random(0x504B5943)

        for case in range(160):
            original = fixture(r)
            cv = compact.CompactVoice.from_arm(original)
            if cv.apply_to_arm(original) != bytes(original):
                raise AssertionError(f"case {case}: compact import/export is not lossless")

            state_full = bytearray(original)
            low, high = r.getrandbits(32), r.getrandbits(32)
            rng_full = full.WordRng.from_ints(low, high)
            rng_compact = full.WordRng.from_ints(low, high)
            count = r.randrange(1, 97)

            want, final_full = full.render_block(
                state_full, count, waves, rng_full, env1, env2
            )
            got = compact.render_block(cv, count, waves, rng_compact, env1, env2)
            final_compact = cv.apply_to_arm(original)

            if got != want:
                at = next(i for i, (a, b) in enumerate(zip(got, want)) if a != b)
                raise AssertionError(
                    f"case {case}: PCM sample {at}: compact {got[at]} != full {want[at]}"
                )
            if final_compact != final_full:
                at = next(
                    i for i, (a, b) in enumerate(zip(final_compact, final_full)) if a != b
                )
                raise AssertionError(
                    f"case {case}: final state byte 0x{at:03x}: "
                    f"compact {final_compact[at]:02x} != full {final_full[at]:02x}"
                )
            if (rng_compact.low != rng_full.low or rng_compact.high != rng_full.high):
                raise AssertionError(f"case {case}: final RNG state differs")

    print(
        "PERKY compact voice: PASS "
        "(41 words/voice, 168 X words/core incl RNG, 160 full render cases)"
    )


if __name__ == "__main__":
    main()

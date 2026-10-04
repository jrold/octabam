#!/usr/bin/env python3
"""Prove packed-table Noise/Tone is bit-identical to raw-table compact render."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import random
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
PERKY = ROOT / "modules/perky"
sys.path.insert(0, str(PERKY))

import noise_tone_compact as raw  # noqa:E402
import noise_tone_compact_packed as packed_render  # noqa:E402
import noise_tone_tables as pack  # noqa:E402
import noise_tone_word_model as word  # noqa:E402


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


fab = load_module(
    "perky_compact_packed_fab",
    ROOT / "tools/perky/fabricate_noise_tone_fixtures.py",
)
MASK32 = 0xFFFFFFFF


def put16(state: bytearray, off: int, value: int) -> None:
    struct.pack_into("<H", state, off, value & 0xFFFF)


def put32(state: bytearray, off: int, value: int) -> None:
    struct.pack_into("<I", state, off, value & MASK32)


def s16_blob(values) -> bytes:
    return struct.pack(f"<{len(values)}h", *(max(-32768, min(32767, int(v))) for v in values))


def u16_blob(values) -> bytes:
    return struct.pack(f"<{len(values)}H", *(int(v) & 0xFFFF for v in values))


def tables():
    wave_values = fab.waves()
    raw_waves = {
        address: s16_blob(values)
        for address, values in zip(fab.WAVE_ADDRESSES, wave_values)
    }
    env_values = (fab.envelope_linear(), fab.envelope_ease())
    env1, env2 = map(u16_blob, env_values)
    packed = packed_render.PackedTables(
        waves=pack.pack_waves(
            (address, [v & 0xFFFF for v in values])
            for address, values in zip(fab.WAVE_ADDRESSES, wave_values)
        ),
        envelope1=pack.pack_envelope(env_values[0]),
        envelope2=pack.pack_envelope(env_values[1]),
    )
    return raw_waves, env1, env2, packed


def fixture(r: random.Random, shape: int) -> raw.CompactVoice:
    state = bytearray(r.getrandbits(8) for _ in range(0x120))
    state[6] = r.randrange(1, 256)

    for base in (0x2C, 0xC4):
        # Deliberately place many phases close to wrap so current->next table
        # switching is common inside a short render block.
        put32(state, base + 4, r.choice((r.randrange(0x100001), r.randrange(0xF0000, 0x100001))))
        put32(state, base + 8, r.randrange(1, 0x30000))
        put32(state, base + 0x0C, r.choice(fab.WAVE_ADDRESSES))
        put32(state, base + 0x10, r.choice(fab.WAVE_ADDRESSES))

    put16(state, 0x60, r.randrange(5))
    put16(state, 0x62, r.randrange(5))
    put16(state, 0x70, r.randrange(0x10000))

    e = 0x74
    state[e] = r.choice((0, 1, 3, 4))
    state[e + 1] = shape
    state[e + 4] = r.randrange(2)
    state[e + 6] = r.randrange(2)
    state[e + 7] = r.randrange(2)
    # Include values around a 16-entry curve-cache boundary and the attack top.
    boundary_index = r.randrange(128) * 16 + r.choice((14, 15, 0, 1))
    boundary_value = min(0xFFFFF, (boundary_index << 10) | r.randrange(0x400))
    put32(state, e + 0x0C, r.choice((boundary_value, 0x0FFFFE, 0x0FFFFF, r.randrange(0x100000))))
    put32(state, e + 0x10, r.choice((0, r.getrandbits(32))))
    put16(state, e + 0x20, r.randrange(1, 0x10000))
    put16(state, e + 0x22, r.randrange(1, 0x10000))

    f = 0x9C
    put16(state, f + 0x0C, r.randrange(0x10000))
    put16(state, f + 0x0E, r.randrange(0x10000))
    put32(state, f + 0x10, r.randrange(-32767, 32768))
    put32(state, f + 0x14, r.randrange(-32767, 32768))
    put32(state, f + 0x18, r.randrange(-32767, 32768))
    put32(state, 0xF8, r.randrange(0x1000))
    return raw.CompactVoice.from_arm(state)


def main() -> None:
    raw_waves, env1, env2, packed_tables = tables()
    if len(packed_tables.waves.words) != 683:
        raise AssertionError("packed wave footprint drifted")
    if [len(packed_tables.envelope1.words), len(packed_tables.envelope2.words)] != [646, 646]:
        raise AssertionError("packed envelope footprint drifted")

    r = random.Random(0x504B5950)
    total_samples = 0
    for case in range(180):
        shape = case % 3  # linear, envelope1, envelope2 all exercised equally
        initial = fixture(r, shape)
        a = raw.CompactVoice(list(initial.words))
        b = raw.CompactVoice(list(initial.words))
        low, high = r.getrandbits(32), r.getrandbits(32)
        ra = word.WordRng.from_ints(low, high)
        rb = word.WordRng.from_ints(low, high)
        count = r.randrange(1, 97)
        total_samples += count

        want = raw.render_block(a, count, raw_waves, ra, env1, env2)
        got = packed_render.render_block(b, count, packed_tables, rb)

        if got != want:
            at = next(i for i, (x, y) in enumerate(zip(got, want)) if x != y)
            raise AssertionError(
                f"case {case} shape {shape} sample {at}: packed {got[at]} != raw {want[at]}"
            )
        if b.words != a.words:
            at = next(i for i, (x, y) in enumerate(zip(b.words, a.words)) if x != y)
            raise AssertionError(
                f"case {case} shape {shape} word {at}: packed {b.words[at]:04x} != raw {a.words[at]:04x}"
            )
        if rb.low != ra.low or rb.high != ra.high:
            raise AssertionError(f"case {case} shape {shape}: RNG state differs")

    print(
        "PERKY complete packed renderer: PASS "
        f"(180 blocks / {total_samples} samples; linear + both curve shapes; "
        "PCM/state/RNG bit-identical to raw-table compact renderer)"
    )


if __name__ == "__main__":
    main()

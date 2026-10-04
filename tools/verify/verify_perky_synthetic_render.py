#!/usr/bin/env python3
"""Run fabricated PERKY assets through both complete Noise/Tone models."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import struct
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
PERKY = ROOT / "modules/perky"
sys.path.insert(0, str(PERKY))

import noise_tone_ref as ref  # noqa: E402
import noise_tone_word_model as dsp  # noqa: E402


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot import {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


fab = load_module(
    "perky_fabricate_render",
    ROOT / "tools/perky/fabricate_noise_tone_fixtures.py",
)


def put16(state: bytearray, off: int, value: int) -> None:
    struct.pack_into("<H", state, off, value & 0xFFFF)


def put32(state: bytearray, off: int, value: int) -> None:
    struct.pack_into("<I", state, off, value & 0xFFFFFFFF)


def prepared_state(path: Path) -> bytearray:
    s = bytearray(path.read_bytes())
    if len(s) != ref.STATE_BYTES:
        raise AssertionError(f"fabricated state is {len(s)} bytes, expected {ref.STATE_BYTES}")

    s[6] = 213

    # Noise sample/hold.
    put16(s, 0x60, 0)
    put16(s, 0x62, 3)
    put16(s, 0x70, 0)

    # Amplitude envelope: table-1 shape, rising immediately, then releasing.
    e = 0x74
    s[e] = 1
    s[e + 1] = 1
    s[e + 4] = 0
    s[e + 6] = 1
    s[e + 7] = 0
    put32(s, e + 0x0C, 0x00018000)
    put32(s, e + 0x10, 0)
    put16(s, e + 0x20, 0x1800)
    put16(s, e + 0x22, 0x0900)

    # Resonant noise filter.
    f = 0x9C
    put16(s, f + 0x0C, 0x1200)
    put16(s, f + 0x0E, 0x5200)
    put32(s, f + 0x10, 0)
    put32(s, f + 0x14, 0)
    put32(s, f + 0x18, 0x00000800)

    # Oscillator phase increments. Current/next table ids were written by the
    # fixture generator at 0x38/0x3c and 0xd0/0xd4 respectively.
    put32(s, 0x2C + 4, 0x00001000)
    put32(s, 0x2C + 8, 0x00003700)
    put32(s, 0xC4 + 4, 0x00021000)
    put32(s, 0xC4 + 8, 0x00005900)

    # Equal-ish noise/tone crossmix, inside the real renderer's 0..0xfff law.
    put32(s, 0xF8, 0x00000780)
    return s


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="perky-synth-render.") as td:
        td = Path(td)
        tables_dir = td / "tables"
        fab.emit_tables(tables_dir)

        env1 = (tables_dir / "envelope1.bin").read_bytes()
        env2 = (tables_dir / "envelope2.bin").read_bytes()
        waves = {
            address: (tables_dir / f"wave_{address:08x}.bin").read_bytes()
            for address in fab.WAVE_ADDRESSES
        }

        initial = prepared_state(tables_dir / "state.bin")
        state_ref = bytearray(initial)
        state_dsp = bytearray(initial)
        rng_ref = ref.RngState(0x12345678, 0x9ABCDEF0)
        rng_dsp = dsp.WordRng.from_ints(rng_ref.low, rng_ref.high)

        want = ref.render_block(state_ref, 256, waves, rng_ref, env1, env2)
        got, final_dsp = dsp.render_block(
            state_dsp, 256, waves, rng_dsp, env1, env2
        )

        if got != want:
            at = next(i for i, (a, b) in enumerate(zip(got, want)) if a != b)
            raise AssertionError(
                f"fabricated render differs at sample {at}: DSP {got[at]} != ref {want[at]}"
            )
        if final_dsp != bytes(state_ref):
            at = next(i for i, (a, b) in enumerate(zip(final_dsp, state_ref)) if a != b)
            raise AssertionError(
                f"fabricated render state differs at byte 0x{at:03x}: "
                f"DSP {final_dsp[at]:02x} != ref {state_ref[at]:02x}"
            )
        if rng_dsp.low.unsigned() != rng_ref.low or rng_dsp.high.unsigned() != rng_ref.high:
            raise AssertionError("fabricated render final RNG differs")
        if not any(want):
            raise AssertionError("fabricated complete render unexpectedly produced silence")

    print(
        "PERKY synthetic complete render: OK -- 256 samples, state and RNG bit-identical"
    )


if __name__ == "__main__":
    main()

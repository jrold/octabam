#!/usr/bin/env python3
"""Hand-computable gates for the PERKY Noise / Tone host oracle.

This gate has no firmware dependency.  It exists before the active module so
DSP56300 work has fixed signed/wrap/RNG/interpolation targets from the first
instruction onward.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "modules" / "perky"))

import noise_tone_ref as ref  # noqa: E402


def put32(buf: bytearray, off: int, value: int) -> None:
    value &= 0xFFFFFFFF
    buf[off : off + 4] = value.to_bytes(4, "little")


def put16(buf: bytearray, off: int, value: int) -> None:
    buf[off : off + 2] = (value & 0xFFFF).to_bytes(2, "little")


def fail(label: str, got, want) -> None:
    if got != want:
        raise SystemExit(f"PERKY ref: {label}: got {got!r}, want {want!r}")


def arithmetic_gate() -> None:
    fail("asr +", ref.arshift32(0x40000000, 2), 0x10000000)
    fail("asr -", ref.arshift32(-8, 2), -2)
    fail("mul signed bits", ref.multiply_low32(-3, 7), -21)
    # Only the low 32 bits survive: 0x40000000 * 4 = 0x1_00000000 -> 0.
    fail("mul low wrap", ref.multiply_low32(0x40000000, 4), 0)


def rng_gate() -> None:
    rng = ref.RngState(1, 0)
    expected = (
        (0x4C957F2E, 0x5851F42D, 0x5851F42D),
        (0x4E252D17, 0xC0B18CCF, 0x40B18CCF),
        (0x404A560C, 0xCBB5F646, 0x4BB5F646),
        (0xD2BD141D, 0xC7033129, 0x47033129),
        (0x2917EC1A, 0x30705B04, 0x30705B04),
    )
    for i, (low, high, out) in enumerate(expected):
        fail(f"rng[{i}] out", ref.next_random(rng), out)
        fail(f"rng[{i}] low", rng.low, low)
        fail(f"rng[{i}] high", rng.high, high)


def envelope_gate() -> None:
    state = bytearray(ref.STATE_BYTES)
    base = 0x74
    state[base] = 1
    put32(state, base + 0x0C, 0x00001000)
    put16(state, base + 0x20, 0x0020)
    # Linear shape: one attack step -> 0x1020, then >> 4.
    fail("linear envelope", ref.render_envelope(state, base, None, None), 0x0102)
    fail("linear envelope state", int.from_bytes(state[base + 0x0C : base + 0x10], "little"), 0x1020)


def oscillator_gate() -> None:
    state = bytearray(ref.STATE_BYTES)
    base = 0x2C
    address = 0x12345678
    put32(state, base + 4, 0)
    put32(state, base + 8, 0x800)  # half way between table samples 0 and 1
    put32(state, base + 0x0C, address)
    put32(state, base + 0x10, address)

    wave = bytearray(ref.WAVE_BYTES)
    put16(wave, 0, 0)
    put16(wave, 2, 1000)
    # fraction=0x800 on a 12-bit interpolation -> exactly 500.
    fail("oscillator interpolation", ref.render_oscillator(state, base, {address: bytes(wave)}), 500)


def main() -> None:
    arithmetic_gate()
    rng_gate()
    envelope_gate()
    oscillator_gate()
    print("PERKY Noise/Tone reference arithmetic: PASS")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Verify the exact compact static-table ABI for PERKY Simple Drum.

This gate uses generated fixtures only.  Authentic PĒRKONS bytes are never
committed; the real-data payload builder runs the same codecs against locally
extracted v1.2.1 assets.
"""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
PERKY = ROOT / "modules" / "perky"
sys.path.insert(0, str(PERKY))

import simple_drum_tables as tables  # noqa: E402


def main() -> None:
    # A full 4096-entry fixture constructed from one exact top-octave basis.
    # Constant in-block slope intentionally gives a legal u6 first delta and
    # signed-2 second differences while still exercising every octave shift.
    basis = [20000 + 40 * i for i in range(tables.PITCH_BASIS_SAMPLES)]
    pitch = [
        basis[index & 0x1FF] >> (7 - (index >> 9))
        for index in range(4096)
    ]
    packed_pitch = tables.pack_pitch_basis(pitch)
    if len(packed_pitch.words) != 67:
        raise AssertionError(
            f"pitch basis uses {len(packed_pitch.words)} words, expected 67"
        )
    for index, want in enumerate(pitch):
        got = tables.pitch_at(packed_pitch, index)
        if got != want:
            raise AssertionError(f"pitch[{index}] {got} != {want}")

    # Simple Drum's shaped pitch envelope reaches 0..1024.  Index 1024 is the
    # authentic duplicate endpoint and therefore need not consume another
    # stored entry.  Constant slope keeps the fixture simple while exercising
    # all 64 compressed blocks and endpoint clamping.
    curve = [min(0xFFFF, 100 * i) for i in range(1024)]
    curve.append(curve[-1])
    curve.extend([curve[-1]] * (2048 - len(curve)))
    packed_env = tables.pack_pitch_envelope(curve)
    if len(packed_env.words) != 179:
        raise AssertionError(
            f"pitch envelope uses {len(packed_env.words)} words, expected 179"
        )
    for index in range(1025):
        got = tables.envelope_at(packed_env, index)
        want = curve[index]
        if got != want:
            raise AssertionError(f"envelope[{index}] {got} != {want}")

    # Three 256-sample signed16 bit-pattern waves use ordinary 16-bit packing:
    # 768 samples * 16 / 24 = exactly 512 DSP words.
    waves: list[int] = []
    for wave in range(tables.WAVES):
        for i in range(tables.WAVE_SAMPLES):
            waves.append((wave * 0x2345 + i * 0x0197 + i * i * 3) & 0xFFFF)
    packed_waves = tables.pack_u16(waves)
    if len(packed_waves) != 512:
        raise AssertionError(f"waves use {len(packed_waves)} words, expected 512")
    for index, want in enumerate(waves):
        got = tables.u16_at(packed_waves, index, len(waves))
        if got != want:
            raise AssertionError(f"wave sample {index}: {got} != {want}")

    total = len(packed_waves) + len(packed_env.words) + len(packed_pitch.words)
    if total != 758:
        raise AssertionError(f"Simple Drum static payload is {total} words, expected 758")

    print(
        "PERKY Simple Drum tables: PASS "
        "(768/768 wave samples, 1025/1025 envelope values, "
        "4096/4096 pitch values; exact 512+179+67 = 758 DSP words)"
    )


if __name__ == "__main__":
    main()

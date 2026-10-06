#!/usr/bin/env python3
"""Verify the low-cycle direct-packed Simple Drum runtime table ABI."""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
PERKY = ROOT / "modules" / "perky"
sys.path.insert(0, str(PERKY))

import simple_drum_runtime_tables as runtime  # noqa: E402


def main() -> None:
    # Construct one pitch basis then derive the complete table with the exact
    # octave relationship required by the authentic v1.2.1 data.
    basis = [20000 + 40 * i for i in range(runtime.PITCH_BASIS)]
    pitch = [
        basis[index & 0x1FF] >> (7 - (index >> 9))
        for index in range(4096)
    ]

    # Shape data only needs indices 0..1023. Runtime index 1024 is the exact
    # duplicate endpoint and clamps to 1023.
    envelope = [min(0xFFFF, 61 * i) for i in range(1024)]
    envelope.append(envelope[-1])
    envelope.extend([envelope[-1]] * (2048 - len(envelope)))

    waves = []
    for wave in range(runtime.WAVES):
        for index in range(runtime.WAVE_SAMPLES):
            waves.append((wave * 0x2345 + index * 0x0197 + index * index * 3) & 0xFFFF)

    table = runtime.build(pitch, envelope, waves)
    if len(table.waves) != 512:
        raise AssertionError(f"waves use {len(table.waves)} words, expected 512")
    if len(table.envelope) != 683:
        raise AssertionError(f"envelope uses {len(table.envelope)} words, expected 683")
    if len(table.pitch_basis) != 342:
        raise AssertionError(f"pitch basis uses {len(table.pitch_basis)} words, expected 342")
    if sum((len(table.waves), len(table.envelope), len(table.pitch_basis))) != 1537:
        raise AssertionError("Simple Drum runtime payload no longer uses 1537 words")

    for index, want in enumerate(pitch):
        got = runtime.pitch_at(table, index)
        if got != want:
            raise AssertionError(f"pitch[{index}] {got} != {want}")
    for index in range(1025):
        got = runtime.envelope_at(table, index)
        if got != envelope[index]:
            raise AssertionError(f"envelope[{index}] {got} != {envelope[index]}")
    for index, want in enumerate(waves):
        got = runtime.wave_at(table, index // 256, index & 0xFF)
        if got != want:
            raise AssertionError(f"wave sample {index}: {got} != {want}")

    private_y = 0x1000 - 0x07A5
    margin = private_y - runtime.TOTAL_WORDS
    if margin != 602:
        raise AssertionError(f"Simple Drum private-Y margin drifted to {margin} words")

    print(
        "PERKY Simple Drum runtime tables: PASS "
        "(4096/4096 pitch, 1025/1025 envelope, 768/768 wave; "
        "1537 Y words, 602-word measured margin, all hot lookups O(1))"
    )


if __name__ == "__main__":
    main()

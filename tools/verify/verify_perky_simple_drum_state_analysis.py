#!/usr/bin/env python3
"""Verify Simple Drum 27-capture state-diff analysis."""
from __future__ import annotations

from pathlib import Path
import struct
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools" / "perky"
sys.path.insert(0, str(TOOLS))

import analyze_simple_drum_states as analyzer  # noqa: E402


def put16(state: bytearray, off: int, value: int) -> None:
    struct.pack_into("<H", state, off, value & 0xFFFF)


def put32(state: bytearray, off: int, value: int) -> None:
    struct.pack_into("<I", state, off, value & 0xFFFFFFFF)


def base_state(mode: int) -> bytearray:
    state = bytearray(0x120)
    state[0x06] = 255
    put32(state, 0x38, 0x08030000 + (mode - 1) * 0x400)
    put32(state, 0x3C, 0x08030200 + (mode - 1) * 0x400)
    put16(state, 0xBA, 0x1000)
    put16(state, 0xEC, 0x4000)
    put16(state, 0x96, 0x2000)
    return state


def capture(mode: int, preset: str) -> bytes:
    state = base_state(mode)
    if preset == "tune0":
        put16(state, 0xBA, 0x0000)
    elif preset == "tune4095":
        put16(state, 0xBA, 0x7FFF)
    elif preset == "decay0":
        put16(state, 0x96, 0x0001)
    elif preset == "decay4095":
        put16(state, 0x96, 0xFFFF)
    elif preset == "env0":
        put16(state, 0xEC, 0x0000)
    elif preset == "env4095":
        put16(state, 0xEC, 0xFFFF)
    elif preset == "mix0":
        state[0x75] = 1
    elif preset == "mix4095":
        state[0x75] = 2
    return bytes(state)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="perky-simple-state-analysis.") as td:
        directory = Path(td)
        for mode in (1, 2, 3):
            for preset in analyzer.PRESETS:
                (directory / f"simple_drum_m{mode}_{preset}.bin").write_bytes(
                    capture(mode, preset)
                )

        report = analyzer.analyze(directory)
        if report["state_bytes"] != 0x120 or report["compact_words"] != 34:
            raise AssertionError("state/compact geometry drifted")

        m1 = report["modes"]["M1"]["captures"]
        if "raw_pitch" not in m1["tune0"]["vs_mid"]["known_fields"]:
            raise AssertionError("TUNE raw-pitch field was not identified")
        if "amp_env.decay" not in m1["decay4095"]["vs_mid"]["known_fields"]:
            raise AssertionError("DECAY envelope field was not identified")
        if "pitch_env.amount" not in m1["env0"]["vs_mid"]["known_fields"]:
            raise AssertionError("ENV pitch-envelope amount was not identified")
        if "amp_env.shape" not in m1["mix4095"]["vs_mid"]["known_fields"]:
            raise AssertionError("MIX fixture field was not identified")

        summary = report["control_summary"]
        if "raw_pitch" not in summary["tune"]["low_known_fields"]:
            raise AssertionError("cross-mode TUNE summary lost raw_pitch")
        if "amp_env.decay" not in summary["decay"]["high_known_fields"]:
            raise AssertionError("cross-mode DECAY summary lost amp_env.decay")
        if "pitch_env.amount" not in summary["env"]["high_known_fields"]:
            raise AssertionError("cross-mode ENV summary lost pitch_env.amount")

        mode_diff = report["mode_midpoint_comparisons"]["M1_vs_M2"]
        if "osc.current_wave" not in mode_diff["known_fields"]:
            raise AssertionError("MODE wave identity change was not identified")

    print(
        "PERKY Simple Drum state analysis: PASS "
        "(27 captures, byte ranges, known renderer fields, compact-word diffs, cross-mode summaries)"
    )


if __name__ == "__main__":
    main()

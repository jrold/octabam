#!/usr/bin/env python3
"""Synthetic gate for PERKY's exact table/state memory planner.

No PĒRKONS firmware bytes are used. The gate proves the 24-bit packing and
random-access block-delta codecs round-trip, then feeds the analyzer one
compressible and one deliberately hostile table set. A fit must mean both
measured X/Y budgets close under the realtime decode policy; the hostile set
must be refused rather than gaining a bogus compression win.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import struct
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/perky/analyze_noise_tone_tables.py"
spec = importlib.util.spec_from_file_location("perky_memory", TOOL)
if spec is None or spec.loader is None:
    raise SystemExit("verify-perky-memory-plan: cannot import analyzer")
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def put_u16(path: Path, values: list[int]) -> None:
    path.write_bytes(struct.pack(f"<{len(values)}H", *values))


def make_case(root: Path, envelopes: tuple[list[int], list[int]]) -> Path:
    root.mkdir()
    files = []
    put_u16(root / "envelope1.bin", envelopes[0])
    put_u16(root / "envelope2.bin", envelopes[1])
    files += [{"file": "envelope1.bin"}, {"file": "envelope2.bin"}]

    for table in range(4):
        name = f"wave_{0x08024000 + table * 0x200:08x}.bin"
        # Exercise every 16-bit bit pattern family without making any claim
        # about the real PĒRKONS waves.
        values = [((i * (257 + 97 * table)) ^ (0x1357 * (table + 1))) & 0xFFFF
                  for i in range(mod.WAVE_SAMPLES)]
        put_u16(root / name, values)
        files.append({"file": name})

    (root / "manifest.json").write_text(json.dumps({"files": files}) + "\n")
    return root


def codec_gate() -> None:
    for width in (1, 2, 5, 8, 16, 17, 23, 24):
        mask = (1 << width) - 1
        values = [((i * 0x1F123 + 7) ^ (i << 3)) & mask for i in range(137)]
        packed = mod.pack_fixed(values, width)
        got = mod.unpack_fixed(packed, len(values), width)
        if got != values:
            raise AssertionError(f"fixed {width}-bit round-trip failed")
        if any(word & ~mod.DSP_WORD_MASK for word in packed):
            raise AssertionError(f"fixed {width}-bit pack escaped 24-bit words")

    curve = []
    value = 30000
    for i in range(mod.ENVELOPE_SAMPLES):
        if i % 16 == 0:
            value = (30000 + (i // 16) * 13) & 0xFFFF
        elif i & 1:
            value += 7
        else:
            value -= 5
        curve.append(value)

    for block in (4, 8, 16, 32, 64, 128, 256):
        packed, width = mod.pack_block_delta(curve, block)
        got = mod.unpack_block_delta(packed, len(curve), block, width)
        if got != curve:
            raise AssertionError(f"block-delta-{block} round-trip failed")
        for index in (0, 1, block - 1, block, 511, 1023, 2047):
            if mod.block_delta_at(packed, index, len(curve), block, width) != curve[index]:
                raise AssertionError(f"block-delta-{block} random access failed at {index}")


def main() -> None:
    codec_gate()

    if mod.LIVE_STATE_WORDS_PER_VOICE != 41:
        raise AssertionError(
            f"live state drifted to {mod.LIVE_STATE_WORDS_PER_VOICE} words/voice"
        )
    if mod.LIVE_STATE_X_WORDS != 168:
        raise AssertionError(f"four voices + RNG drifted to {mod.LIVE_STATE_X_WORDS} X words")
    if mod.REALTIME_MAX_DELTA_ADDS != 15:
        raise AssertionError("realtime delta lookup policy drifted")

    # Small monotonic deltas: 16-sample anchored blocks are compact and cheap.
    env_a = [i for i in range(mod.ENVELOPE_SAMPLES)]
    env_b = [50000 - 2 * i for i in range(mod.ENVELOPE_SAMPLES)]

    # Hostile exact curves: alternating endpoints force 17-bit deltas within
    # every useful block, so realtime selection must fall back to u16pack.
    hostile_a = [0 if i % 2 == 0 else 0xFFFF for i in range(mod.ENVELOPE_SAMPLES)]
    hostile_b = [0xFFFF if i % 2 == 0 else 0 for i in range(mod.ENVELOPE_SAMPLES)]

    with tempfile.TemporaryDirectory(prefix="perky-memory-gate.") as td:
        td = Path(td)
        fit = mod.analyze(make_case(td / "fit", (env_a, env_b)))
        if fit["waves"]["u16pack_words"] != 683:
            raise AssertionError(
                f"four contiguous waves need {fit['waves']['u16pack_words']} words, expected 683"
            )
        if fit["live_state"]["x_words"] != 168:
            raise AssertionError("fit report lost compact live-state budget")
        if not fit["combined"]["fits_measured_private_xy_realtime"]:
            raise AssertionError("compressible synthetic tables should fit")
        for env in fit["envelopes"]["tables"]:
            rt = env["realtime_best"]
            if rt["max_decode_deltas"] > mod.REALTIME_MAX_DELTA_ADDS:
                raise AssertionError("fit used a non-realtime envelope codec")
            if rt["block"] is None:
                raise AssertionError("small-delta synthetic curve unexpectedly used raw u16pack")

        bad = mod.analyze(make_case(td / "hostile", (hostile_a, hostile_b)))
        if bad["combined"]["fits_measured_private_xy_realtime"]:
            raise AssertionError("hostile exact tables were falsely reported as fitting")
        for env in bad["envelopes"]["tables"]:
            if env["realtime_best"]["name"] != "u16pack":
                raise AssertionError("17-bit hostile deltas should fall back to u16pack")

    print("PERKY exact memory-plan gate: OK")


if __name__ == "__main__":
    main()

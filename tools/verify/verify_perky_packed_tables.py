#!/usr/bin/env python3
"""Gate PERKY's exact 24-bit packed table runtime ABI."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import struct
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
PERKY = ROOT / "modules" / "perky"
sys.path.insert(0, str(PERKY))

import noise_tone_tables as packed  # noqa: E402


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot import {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


fab = load_module(
    "perky_table_fixture_fab",
    ROOT / "tools/perky/fabricate_noise_tone_fixtures.py",
)
mem = load_module(
    "perky_table_memory_plan",
    ROOT / "tools/perky/analyze_noise_tone_tables.py",
)


def main() -> None:
    raw_waves = fab.waves()
    wave_pairs = [
        (address, [sample & 0xFFFF for sample in values])
        for address, values in zip(fab.WAVE_ADDRESSES, raw_waves)
    ]
    waves = packed.pack_waves(wave_pairs)
    if len(waves.words) != 683:
        raise AssertionError(f"four packed waves use {len(waves.words)} words, expected 683")
    for address, values in wave_pairs:
        for index, expected in enumerate(values):
            got = packed.wave_at(waves, address, index)
            if got != expected:
                raise AssertionError(
                    f"wave 0x{address:08x}[{index}]: {got:04x} != {expected:04x}"
                )

    env_values = [fab.envelope_linear(), fab.envelope_ease()]
    envelopes = [packed.pack_envelope(values) for values in env_values]
    for which, (table, values) in enumerate(zip(envelopes, env_values), 1):
        if table.delta_bits != 7:
            raise AssertionError(
                f"synthetic envelope {which} uses {table.delta_bits} delta bits, expected 7"
            )
        if len(table.words) != 646:
            raise AssertionError(
                f"synthetic envelope {which} uses {len(table.words)} words, expected 646"
            )
        if table.max_adds != 15:
            raise AssertionError(f"envelope {which}: max adds {table.max_adds} != 15")
        decoded = packed.unpack_envelope(table)
        if decoded != values:
            at = next(i for i, (a, b) in enumerate(zip(decoded, values)) if a != b)
            raise AssertionError(
                f"envelope {which}[{at}]: {decoded[at]} != {values[at]}"
            )

    # The runtime ABI and the independently-written memory planner must agree
    # on byte-for-byte storage geometry, or neither one is allowed to drift.
    with tempfile.TemporaryDirectory(prefix="perky-packed-tables.") as td:
        root = Path(td)
        fab.emit_tables(root)
        report = mem.analyze(root)
        if report["waves"]["u16pack_words"] != len(waves.words):
            raise AssertionError("runtime wave packer disagrees with memory planner")
        plan = report["envelopes"]["tables"]
        for i, table in enumerate(envelopes):
            rt = plan[i]["realtime_best"]
            if rt["block"] != 16 or rt["delta_bits"] != table.delta_bits:
                raise AssertionError(
                    f"envelope {i+1}: runtime ABI block/width disagrees with planner"
                )
            if rt["words"] != len(table.words):
                raise AssertionError(
                    f"envelope {i+1}: runtime ABI size disagrees with planner"
                )
        if report["combined"]["realtime_table_y_words"] != (
            len(waves.words) + sum(len(table.words) for table in envelopes)
        ):
            raise AssertionError("combined runtime table footprint disagrees with planner")

    print(
        "PERKY packed tables: PASS "
        "(1024 wave samples -> 683 words; two 2048-point synthetic envelopes "
        "-> 646 words each; all 5120 lookups exact)"
    )


if __name__ == "__main__":
    main()

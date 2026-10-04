#!/usr/bin/env python3
"""Gate the packed PERKY Noise/Tone DSP payload builder with synthetic data."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import struct
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


fab = load_module("perky_payload_fab", ROOT / "tools/perky/fabricate_noise_tone_fixtures.py")
builder = load_module("perky_payload_builder", ROOT / "tools/perky/build_noise_tone_payload.py")


def read24(blob: bytes) -> list[int]:
    if len(blob) % 3:
        raise AssertionError("payload byte count is not a multiple of three")
    return [
        blob[i] | (blob[i + 1] << 8) | (blob[i + 2] << 16)
        for i in range(0, len(blob), 3)
    ]


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="perky-table-payload.") as td:
        td = Path(td)
        source, out = td / "source", td / "out"
        fab.emit_tables(source)
        layout = builder.build(source, out)

        if layout["synthetic"] is not True:
            raise AssertionError("synthetic provenance marker was lost")
        if layout["total_words"] != 1975:
            raise AssertionError(f"payload has {layout['total_words']} words, expected 1975")
        if layout["total_bytes"] != 5925:
            raise AssertionError(f"payload has {layout['total_bytes']} bytes, expected 5925")
        if layout["waves"]["offset_words"] != 0 or layout["waves"]["words"] != 683:
            raise AssertionError("wave payload layout drifted")
        if [x["offset_words"] for x in layout["envelopes"]] != [683, 1329]:
            raise AssertionError("envelope payload offsets drifted")
        if [x["words"] for x in layout["envelopes"]] != [646, 646]:
            raise AssertionError("envelope payload sizes drifted")
        if [x["delta_bits"] for x in layout["envelopes"]] != [7, 7]:
            raise AssertionError("synthetic envelope delta widths drifted")

        disk_layout = json.loads((out / "layout.json").read_text())
        if disk_layout != layout:
            raise AssertionError("layout.json differs from returned layout")
        blob = (out / "tables.bin").read_bytes()
        words = read24(blob)
        text_words = [int(line, 16) for line in (out / "tables.words").read_text().splitlines()]
        if words != text_words:
            raise AssertionError("binary and textual DSP-word payloads differ")
        if len(words) != layout["total_words"]:
            raise AssertionError("payload word count disagrees with metadata")

        # Determinism is part of the image-build contract.
        second = td / "out2"
        layout2 = builder.build(source, second)
        if layout2 != layout:
            raise AssertionError("same source produced different layout metadata")
        if (second / "tables.bin").read_bytes() != blob:
            raise AssertionError("same source produced different packed table bytes")

    print(
        "PERKY table payload builder: PASS "
        "(1975 x 24-bit words / 5925 bytes; deterministic layout + binary)"
    )


if __name__ == "__main__":
    main()

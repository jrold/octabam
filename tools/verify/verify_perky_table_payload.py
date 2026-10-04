#!/usr/bin/env python3
"""Gate the packed PERKY Noise/Tone DSP payload builder with synthetic data."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
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
            raise AssertionError(f"Y payload has {layout['total_words']} words, expected 1975")
        if layout["total_bytes"] != 5925:
            raise AssertionError(f"Y payload has {layout['total_bytes']} bytes, expected 5925")
        if layout["waves"]["offset_words"] != 0 or layout["waves"]["words"] != 683:
            raise AssertionError("wave payload layout drifted")
        if [x["offset_words"] for x in layout["envelopes"]] != [683, 1329]:
            raise AssertionError("envelope payload offsets drifted")
        if [x["words"] for x in layout["envelopes"]] != [646, 646]:
            raise AssertionError("envelope payload sizes drifted")
        if [x["delta_bits"] for x in layout["envelopes"]] != [7, 7]:
            raise AssertionError("synthetic envelope delta widths drifted")

        xi = layout.get("x_init", {})
        if xi.get("base_word") != 0x3800 or xi.get("words") != 236:
            raise AssertionError(f"X init geometry drifted: {xi!r}")
        if xi.get("voice_words") != 41 or xi.get("cache_words_per_voice") != 17:
            raise AssertionError("X init voice/cache geometry drifted")
        if xi.get("voices") != 4 or xi.get("rng_words") != 4:
            raise AssertionError("X init voice/RNG count drifted")
        if xi.get("synthetic_audible_preset") is not True:
            raise AssertionError("synthetic X init lost audible-preset provenance")

        disk_layout = json.loads((out / "layout.json").read_text())
        if disk_layout != layout:
            raise AssertionError("layout.json differs from returned layout")

        y_blob = (out / "tables.bin").read_bytes()
        y_words = read24(y_blob)
        y_text = [int(line, 16) for line in (out / "tables.words").read_text().splitlines()]
        if y_words != y_text:
            raise AssertionError("binary and textual Y-word payloads differ")
        if len(y_words) != layout["total_words"]:
            raise AssertionError("Y payload word count disagrees with metadata")

        x_blob = (out / "state_init.bin").read_bytes()
        x_words = read24(x_blob)
        x_text = [int(line, 16) for line in (out / "state_init.words").read_text().splitlines()]
        if x_words != x_text:
            raise AssertionError("binary and textual X-init words differ")
        if len(x_words) != 236 or len(x_blob) != 708:
            raise AssertionError("X init must be 236 x 24-bit words / 708 bytes")
        if any(word > 0xFFFF for word in x_words):
            raise AssertionError("compact X init contains a word above 16 bits")

        # Four [41 state + 17 cache] blocks. Each cache key starts invalid.
        stride = 58
        for voice in range(4):
            base = voice * stride
            if x_words[base] != 255:
                raise AssertionError(f"voice {voice}: synthetic velocity is not 255")
            if x_words[base + 41] != 0xFFFF:
                raise AssertionError(f"voice {voice}: cache key is not invalid")
            if any(x_words[base + 42:base + 58]):
                raise AssertionError(f"voice {voice}: cache values are not zero-initialized")
        if x_words[-4:] != [1, 0, 0, 0]:
            raise AssertionError(f"RNG seed drifted: {x_words[-4:]}")

        # Determinism is part of the image-build contract, for BOTH assets.
        second = td / "out2"
        layout2 = builder.build(source, second)
        if layout2 != layout:
            raise AssertionError("same source produced different layout metadata")
        if (second / "tables.bin").read_bytes() != y_blob:
            raise AssertionError("same source produced different packed table bytes")
        if (second / "state_init.bin").read_bytes() != x_blob:
            raise AssertionError("same source produced different X-init bytes")

    print(
        "PERKY payload builder: PASS "
        "(Y 1975 x 24-bit words; X init 236 x 24-bit words; "
        "4 x [41 state + 17 cache] + RNG; deterministic binaries/layout)"
    )


if __name__ == "__main__":
    main()

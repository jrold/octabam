#!/usr/bin/env python3
"""Gate PERKY's private-Y packed-table injection policy without a stock image."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/build"))

import perky_image  # noqa:E402


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


fab = load_module("perky_image_fab", ROOT / "tools/perky/fabricate_noise_tone_fixtures.py")
builder = load_module("perky_image_builder", ROOT / "tools/perky/build_noise_tone_payload.py")


def expect_fail(fn, text: str) -> None:
    try:
        fn()
    except SystemExit as exc:
        if text not in str(exc):
            raise AssertionError(f"failure {exc!s} does not contain {text!r}") from exc
    else:
        raise AssertionError(f"expected failure containing {text!r}")


def main() -> None:
    if perky_image.Y_BASE != 0x0795 or perky_image.Y_END != 0x1000:
        raise AssertionError("private-Y interval drifted from hardware-measured 0x0795..0x0fff")
    if perky_image.Y_WORDS != 2155:
        raise AssertionError(f"private-Y capacity is {perky_image.Y_WORDS}, expected 2155")

    with tempfile.TemporaryDirectory(prefix="perky-image-tables.") as td:
        td = Path(td)
        source, packed = td / "source", td / "packed"
        fab.emit_tables(source)
        layout = builder.build(source, packed)
        words, loaded = perky_image.load_tables(packed)
        if loaded != layout:
            raise AssertionError("injector changed packed layout metadata")
        if len(words) != 1975:
            raise AssertionError(f"synthetic table payload has {len(words)} words, expected 1975")
        if perky_image.Y_BASE + len(words) - 1 != 0x0F4B:
            raise AssertionError("synthetic table end address drifted")
        if perky_image.Y_END - (perky_image.Y_BASE + len(words)) != 180:
            raise AssertionError("synthetic private-Y tail margin drifted")

        # A finalized stock-like map ending immediately before our interval is
        # legal; so is an unrelated FX1 record beginning at 0x1000.
        legal = [
            (2, 0x0200, 0x0595, 0),   # ends at 0x0794
            (2, 0x1000, 0x0C00, 0),   # FX1 starts immediately after private gap
            (1, 0x0700, 0x0200, 0),   # X is a different address space
        ]
        perky_image._check_y_free(legal, len(words), "A")

        for record in (
            (2, 0x0794, 2, 0),                    # crosses lower boundary
            (2, 0x0795, 1, 0),                    # first PERKY word
            (2, 0x0800, 0x20, 0),                 # middle
            (2, 0x0F4B, 1, 0),                    # last synthetic word
        ):
            expect_fail(
                lambda record=record: perky_image._check_y_free([record], len(words), "A"),
                "overlaps PERKY table destination",
            )

        # The still-free tail after a smaller table is legal, while a table
        # one word beyond the measured interval is refused by load_tables.
        perky_image._check_y_free([(2, 0x0F4C, 0xB4, 0)], len(words), "B")
        raw = (packed / "tables.bin").read_bytes()
        layout_path = packed / "layout.json"
        layout_text = layout_path.read_text()
        try:
            # Append 181 zero words and make metadata internally consistent
            # enough to reach the capacity check.
            oversized = raw + bytes(181 * 3)
            (packed / "tables.bin").write_bytes(oversized)
            import hashlib, json
            meta = json.loads(layout_text)
            meta["total_words"] = 2156
            meta["total_bytes"] = len(oversized)
            meta["sha256"] = hashlib.sha256(oversized).hexdigest()
            layout_path.write_text(json.dumps(meta))
            expect_fail(lambda: perky_image.load_tables(packed), "holds only 2155")
        finally:
            (packed / "tables.bin").write_bytes(raw)
            layout_path.write_text(layout_text)

    print(
        "PERKY image table policy: PASS "
        "(Y:0795..0fff = 2155 words; synthetic ends 0f4b, margin 180; "
        "overlap/oversize refusals exercised)"
    )


if __name__ == "__main__":
    main()

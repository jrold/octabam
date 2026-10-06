#!/usr/bin/env python3
"""Gate PERKY's private-X/Y injection policy without a stock image."""
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
    if (perky_image.X_BASE, perky_image.X_WORDS) != (0x3800, 236):
        raise AssertionError("private-X init geometry drifted from X:3800 + 236")
    if perky_image.Y_BASE != 0x07a5 or perky_image.Y_END != 0x1000:
        raise AssertionError("private-Y interval drifted from hardware-measured 0x07a5..0x0fff")
    if perky_image.Y_WORDS != 2139:
        raise AssertionError(f"private-Y capacity is {perky_image.Y_WORDS}, expected 2139")

    with tempfile.TemporaryDirectory(prefix="perky-image-tables.") as td:
        td = Path(td)
        source, packed = td / "source", td / "packed"
        fab.emit_tables(source)
        layout = builder.build(source, packed)
        y_words, loaded = perky_image.load_tables(packed)
        x_words = perky_image.load_state_init(packed, loaded)
        if loaded != layout:
            raise AssertionError("injector changed packed layout metadata")
        if len(y_words) != 1975:
            raise AssertionError(f"synthetic table payload has {len(y_words)} words, expected 1975")
        if len(x_words) != 236:
            raise AssertionError(f"synthetic X init has {len(x_words)} words, expected 236")
        if perky_image.Y_BASE + len(y_words) - 1 != 0x0F5B:
            raise AssertionError("synthetic table end address drifted")
        if perky_image.Y_END - (perky_image.Y_BASE + len(y_words)) != 164:
            raise AssertionError("synthetic private-Y tail margin drifted")

        legal = [
            (2, 0x0200, 0x05A5, 0),   # Y ends at 0x07a4
            (2, 0x1000, 0x0C00, 0),   # FX1 Y begins after private gap
            (1, 0x3700, 0x0100, 0),   # X ends at 0x37ff
            (1, 0x38EC, 0x0014, 0),   # X gap before shared scratch at 0x3900
        ]
        perky_image._check_y_free(legal, len(y_words), "A")
        perky_image._check_x_free(legal, "A")

        for record in (
            (2, 0x07a4, 2, 0),
            (2, 0x07a5, 1, 0),
            (2, 0x0800, 0x20, 0),
            (2, 0x0F5B, 1, 0),
        ):
            expect_fail(
                lambda record=record: perky_image._check_y_free([record], len(y_words), "A"),
                "overlaps PERKY table destination",
            )

        for record in (
            (1, 0x37FF, 2, 0),
            (1, 0x3800, 1, 0),
            (1, 0x3840, 0x20, 0),
            (1, 0x38EB, 1, 0),
        ):
            expect_fail(
                lambda record=record: perky_image._check_x_free([record], "B"),
                "overlaps PERKY state-init destination",
            )

        # The still-free Y tail after the synthetic tables remains legal.
        perky_image._check_y_free([(2, 0x0F5C, 0xA4, 0)], len(y_words), "B")

        # Corrupting the X-init hash must refuse before image integration.
        state_path = packed / "state_init.bin"
        state_raw = state_path.read_bytes()
        try:
            state_path.write_bytes(state_raw[:-3] + b"\x01\x00\x00")
            expect_fail(
                lambda: perky_image.load_state_init(packed, layout),
                "state_init.bin sha256",
            )
        finally:
            state_path.write_bytes(state_raw)

        # A Y table one word beyond the measured interval is refused.
        raw = (packed / "tables.bin").read_bytes()
        layout_path = packed / "layout.json"
        layout_text = layout_path.read_text()
        try:
            oversized = raw + bytes(165 * 3)
            (packed / "tables.bin").write_bytes(oversized)
            import hashlib, json
            meta = json.loads(layout_text)
            meta["total_words"] = 2140
            meta["total_bytes"] = len(oversized)
            meta["sha256"] = hashlib.sha256(oversized).hexdigest()
            layout_path.write_text(json.dumps(meta))
            expect_fail(lambda: perky_image.load_tables(packed), "holds only 2139")
        finally:
            (packed / "tables.bin").write_bytes(raw)
            layout_path.write_text(layout_text)

    print(
        "PERKY image data policy: PASS "
        "(X:3800..38eb = 236 init words; Y:07a5..0fff = 2139 capacity; "
        "synthetic Y ends 0f5b; overlap/hash/oversize refusals exercised)"
    )


if __name__ == "__main__":
    main()

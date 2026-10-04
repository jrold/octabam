#!/usr/bin/env python3
"""Assemble and budget PERKY's generated complete synth-seam source."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "tools/perky")]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


fab = load_module("perky_synexec_fab", ROOT / "tools/perky/fabricate_noise_tone_fixtures.py")
payload = load_module("perky_synexec_payload", ROOT / "tools/perky/build_noise_tone_payload.py")
sourcegen = load_module("perky_synexec_source", ROOT / "tools/perky/build_noise_tone_synth_source.py")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="perky-synth-source-exec.") as td:
        td = Path(td)
        raw, packed = td / "raw", td / "packed"
        fab.emit_tables(raw)
        payload.build(raw, packed)
        src = sourcegen.generate(packed / "layout.json")
        out = td / "perky_synth.asm"
        out.write_text(src)
        words = sourcegen.measure(src, out)

    spring = words <= sourcegen.SPRING_DONOR_WORDS
    print(
        "PERKY generated synth source: PASS "
        f"({words}/{sourcegen.FULL_DONOR_WORDS} P words in full donor, "
        f"FREE {sourcegen.FULL_DONOR_WORDS - words}; "
        f"SPRING-only {sourcegen.SPRING_DONOR_WORDS}: {'FITS' if spring else 'not yet'})"
    )


if __name__ == "__main__":
    main()

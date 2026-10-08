#!/usr/bin/env python3
"""Build a one-purpose PERKY hardware renderer diagnostic firmware.

The normal final builder still runs its complete production PCM/control
qualification first. Only after that passes does this wrapper swap the generated
pkcontrol translation unit to control_cf_hw_render_diag.c.

This is not a release firmware.
"""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "tools/perky"), str(ROOT / "modules/perky")]

import build_cf_final  # noqa:E402


def main() -> None:
    original_sources = build_cf_final.generate_cf_final.SOURCES
    diag_sources = tuple(
        (label, "control_cf_hw_render_diag.c") if label == "pkcontrol" else (label, name)
        for label, name in original_sources
    )
    build_cf_final.generate_cf_final.SOURCES = diag_sources
    try:
        print("=== PERKY HARDWARE RENDER DIAGNOSTIC ===")
        print("Production PCM/control qualification runs first, unchanged.")
        print("Final firmware only: T1 bypasses signature/trig/SRC staging and self-triggers Fold1.")
        build_cf_final.main()
    finally:
        build_cf_final.generate_cf_final.SOURCES = original_sources


if __name__ == "__main__":
    main()

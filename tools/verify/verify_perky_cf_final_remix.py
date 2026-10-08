#!/usr/bin/env python3
"""Gate the final Perky remix's complete stock FX chooser contract."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
path = ROOT / "remixes/test/perky-cf-final/remix.py"
spec = importlib.util.spec_from_file_location("perky_cf_final_remix_gate", path)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)
r = mod.REMIX

stock = (
    "FILTER", "EQUALIZER", "DJ EQ", "PHASER", "FLANGER", "CHORUS",
    "SPATIALIZER", "COMB FILTER", "COMPRESSOR", "LO-FI", "DELAY",
    "PLATE REV", "SPRING REV", "DARK REV",
)
if r.name != "perky-cf-final":
    raise AssertionError(r.name)
if r.modules != ("PERKY PROBE", *stock):
    raise AssertionError(f"final remix stock FX order drifted: {r.modules!r}")
# Empty means: do not rewrite/replace stock FX1's own chooser tables. The stock
# effects remain in the stock FX1 set; the final Perky module carries no DSP id.
if r.fx1 != ():
    raise AssertionError("final remix must leave the stock FX1 chooser untouched")
if r.hidden or r.locked:
    raise AssertionError("final remix must not hide/lock stock effects")
print(
    "PERKY final remix: PASS "
    "(14 stock effects retained on FX2 profile incl. Plate/Spring/Dark; "
    "stock FX1 chooser untouched; no hidden/locked stock rows)"
)

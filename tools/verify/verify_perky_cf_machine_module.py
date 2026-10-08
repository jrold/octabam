#!/usr/bin/env python3
"""Gate the final all-stock-FX Perky Machines declaration."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tools/perky")]

import perky_cf_machine_module


def load(path: Path):
    spec = importlib.util.spec_from_file_location("perky_cf_gate_manifest", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod.MODULE


def main() -> None:
    original = load(ROOT / "modules/perky/manifest.py")
    final = perky_cf_machine_module.build(original)
    if final.dsp is not None:
        raise AssertionError("final Perky Machines must not carry a DSP section")
    if final.claims is None or final.claims.dsp_ranges:
        raise AssertionError("final Perky Machines must reserve zero DSP ranges")
    if final.arena is not None:
        raise AssertionError("DSP preboot arena must not survive ColdFire-only design")
    if final.kind.value != "cf_patch":
        raise AssertionError(f"final kind is {final.kind}")
    got = [(x.label, x.source, x.dram, x.include is not None) for x in final.linked]
    want = [
        ("pkmachine", "modules/perky/machine.s", True, False),
        ("pkassets", "modules/perky/cf_assets.s", True, True),
        ("pkfold", "out/perky/cf-final/pkfold.s", True, False),
        ("pkkarplus", "out/perky/cf-final/pkkarplus.s", True, False),
        ("pknoise", "out/perky/cf-final/pknoise.s", True, False),
        ("pkcore", "out/perky/cf-final/pkcore.s", True, False),
        ("pkcontrol", "out/perky/cf-final/pkcontrol.s", True, False),
    ]
    if got != want:
        raise AssertionError(f"linked units {got!r}")
    refs = {(r.addr, r.expect, r.unit, r.symbol) for r in final.symbol_refs}
    if (0x400D6438, 0x40004008, "pkcontrol", "pk_render") not in refs:
        raise AssertionError("FLEX render pointer is not final pk_render")
    print(
        "PERKY CF machine declaration: PASS "
        "(7 DRAM CF units; build-time SHA-pinned assets; stock DSP section absent; "
        "0 DSP ranges; 0 DSP preboot arena)"
    )


if __name__ == "__main__":
    main()

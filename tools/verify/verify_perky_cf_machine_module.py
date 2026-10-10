#!/usr/bin/env python3
"""Gate the final all-stock-FX Perky Machines declaration."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tools/perky"), str(ROOT / "modules/perky")]

import perky_cf_machine_module
import perky_cf_assets
import generate_cf_final


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
    if final.cf_patches:
        raise AssertionError(f"final Perky Machines must carry zero direct CF patch blocks: {final.cf_patches!r}")

    dsp_lo, dsp_hi = 0x400E21E0, 0x401086F4
    touched = []
    for row in (*final.detours, *final.pokes, *final.symbol_refs):
        addr = getattr(row, "site", getattr(row, "addr", None))
        if addr is not None and dsp_lo <= addr < dsp_hi:
            touched.append((type(row).__name__, addr))
    if touched:
        raise AssertionError(f"final CPU patch surface touches stock DSP bootstrap/payload span: {touched!r}")
    got = [(x.label, x.source, x.dram, x.include is not None) for x in final.linked]
    want = [
        ("pkmachine", "modules/perky/machine.s", True, False),
        ("pkassets", "modules/perky/cf_assets.s", True, True),
        ("pkfold", "out/perky/cf-final/pkfold.s", True, False),
        ("pkkarplus", "out/perky/cf-final/pkkarplus.s", True, False),
        ("pknoise", "out/perky/cf-final/pknoise.s", True, False),
        ("pkresonant", "out/perky/cf-final/pkresonant.s", True, False),
        ("pknoisehat", "out/perky/cf-final/pknoisehat.s", True, False),
        ("pksimpledrum", "out/perky/cf-final/pksimpledrum.s", True, False),
        ("pkcomplexdrum", "out/perky/cf-final/pkcomplexdrum.s", True, False),
        ("pkslap", "out/perky/cf-final/pkslap.s", True, False),
        ("pkwavetable", "out/perky/cf-final/pkwavetable.s", True, False),
        ("pkah", "out/perky/cf-final/pkah.s", True, False),
        ("pkcore", "out/perky/cf-final/pkcore.s", True, False),
        ("pkcontrol", "out/perky/cf-final/pkcontrol.s", True, False),
    ]
    if got != want:
        raise AssertionError(f"linked units {got!r}")
    refs = {(r.addr, r.expect, r.unit, r.symbol) for r in final.symbol_refs}
    if (0x400D6438, 0x40004008, "pkcontrol", "pk_render") not in refs:
        raise AssertionError("FLEX render pointer is not final pk_render")

    generated = tuple((label, name) for label, name in generate_cf_final.SOURCES)
    expected_generated = (
        ("pkcontrol", "control_cf_final.c"),
        ("pkcore", "cf_perky4.c"),
        ("pkfold", "cf_fold.c"),
        ("pkkarplus", "cf_karplus.c"),
        ("pknoise", "cf_noise_tone.c"),
        ("pkresonant", "cf_resonant.c"),
        ("pknoisehat", "cf_noise_hat.c"),
    ("pksimpledrum", "cf_simple_drum.c"),
    ("pkcomplexdrum", "cf_complex_drum.c"),
    ("pkslap", "cf_slap.c"),
    ("pkwavetable", "cf_wavetable.c"),
    ("pkah", "cf_acoustic_hats.c"),
    )
    if generated != expected_generated:
        raise AssertionError(f"ColdFire generator units drifted: {generated!r}")

    control = (ROOT / "modules/perky/control_cf_final.c").read_text()
    asset_labels = tuple(row[0] for row in perky_cf_assets.ASSETS)
    for label in asset_labels:
        if f"extern const uint8_t {label}[];" not in control:
            raise AssertionError(f"shipping control is missing asset extern {label}")
    if len(asset_labels) != 16 or len(set(asset_labels)) != 16:
        raise AssertionError(f"expected exactly sixteen unique firmware assets, got {asset_labels!r}")

    asset_source = (ROOT / "modules/perky/cf_assets.s").read_text()
    if '.include "remix.inc"' not in asset_source:
        raise AssertionError("cf_assets.s no longer includes generated SHA-pinned remix.inc")

    machine = (ROOT / "modules/perky/machine.s").read_text()
    for shim in ("pk_stock_validate", "pk_stock_pool_open"):
        if f".global {shim}" not in machine or f"{shim}:" not in machine:
            raise AssertionError(f"machine.s is missing required final-control shim {shim}")

    # A PERKY synth does not require a file sample, but the stock FLEX voice
    # scheduler still requires a valid source object. Selecting PERKY must seed
    # the track's own recorder buffer (FLEX slots 129..136, zero-based 128..135)
    # in both the live Part and its SRAM mirror before the stock FLEX commit.
    donor_contract = (
        ".equ    FLEX_SLOT_OFF, 0x2ca",
        ".equ    FLEX_SLOT_KIND, 1",
        ".equ    RECORDER_BASE, 128",
        "lea     FLEX_SLOT_OFF+FLEX_SLOT_KIND(%a0),%a1",
        "move.b  %d2,(%a1,%d3.l)",
        "addi.l  #SRAM_PART+FLEX_SLOT_OFF+FLEX_SLOT_KIND,%d2",
        "addi.l  #RECORDER_BASE,%d2",
    )
    for needle in donor_contract:
        if needle not in machine:
            raise AssertionError(f"sample-free PERKY recorder-donor contract missing: {needle}")

    print(
        "PERKY CF machine declaration: PASS "
        "(12 DRAM CF units; generator/assets/shims closed; sample-free recorder donor live+SRAM; "
        "no CPU writes in stock DSP span; build-time SHA-pinned assets; stock DSP section absent; "
        "0 DSP ranges; 0 DSP preboot arena)"
    )


if __name__ == "__main__":
    main()

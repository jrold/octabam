#!/usr/bin/env python3
"""Static gate for the isolated PERKY CF->DSP source-seam canary.

This is deliberately image-independent. The build itself asserts the stock
ColdFire pointer and both DSP hook words before writing them; this gate makes
sure the module declaration and the two small assembly halves still describe
the measured Analog-BD seam we mean to test.

PERKY also owns a small bottom audio-arena reservation for preboot DSP data
uploads. That data-loader path is allowed here only when it stays completely
separate from source-seam placement: DspHook remains the one source of truth
for the two DSP patch sites.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))


def fail(msg: str) -> None:
    raise SystemExit(f"verify-perky-probe: {msg}")


def need(text: str, token: str, where: str) -> None:
    if token not in text:
        fail(f"{where}: missing {token!r}")


manifest_path = ROOT / "modules/perky/manifest.py"
spec = importlib.util.spec_from_file_location("perky_manifest", manifest_path)
if spec is None or spec.loader is None:
    fail("cannot load modules/perky/manifest.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
m = mod.MODULE

if m.key != "PERKY PROBE":
    fail(f"module key is {m.key!r}, expected 'PERKY PROBE'")
if len(m.linked) != 1 or m.linked[0].label != "pkprobe":
    fail("expected one linked ColdFire unit named pkprobe")
if m.linked[0].dram:
    fail("pkprobe must stay in ROM; the data loader uses its own small arena reservation")
if len(m.symbol_refs) != 1:
    fail("expected exactly one ColdFire symbol-ref rewrite")
sr = m.symbol_refs[0]
if (sr.addr, sr.expect, sr.unit, sr.symbol) != (
        0x400D6438, 0x40004008, "pkprobe", "pk_probe_render"):
    fail("FLEX renderer pointer is not the measured 0x400d6438 -> pk_probe_render rewrite")

if m.arena is None or m.arena.where != "bottom" or m.arena.pages != 242:
    fail("PERKY preboot scratch must reserve exactly 242 bottom audio-arena pages")

ranges = {(r.space, r.start, r.length) for r in m.claims.dsp_ranges}
for want in (
    ("x", 0x3800, 236),
    ("x", 0x3900, 100),
    ("y", 0x07a5, 0x1000 - 0x07a5),
):
    if want not in ranges:
        fail(f"missing DSP data claim {want!r}")

if m.dsp is None or len(m.dsp.hooks) != 1:
    fail("expected one hook-only DSP section")
h = m.dsp.hooks[0]
if dict(h.site) != {"A": 0x0039C, "B": 0x001A2}:
    fail(f"DSP source hook sites drifted: {dict(h.site)!r}")
if tuple(h.stock) != (0x567000, 0x00020E):
    fail(f"DSP source hook stock words drifted: {tuple(h.stock)!r}")
if h.label != "pk_probe_source":
    fail(f"DSP hook label is {h.label!r}")
want_subst = {
    "A": {"@CONT@": "$000426"},
    "B": {"@CONT@": "$000221"},
}
if {p: dict(v) for p, v in m.dsp.subst.items()} != want_subst:
    fail("per-payload source continuation substitutions drifted")

cf = (ROOT / "modules/perky/probe_cf.s").read_text()
for token in (
    "0x80001c80", "0x80001c90", "0x0a80", "336",
    "0x46104d0c", "0x504b0000", "0x59310000",
    "move.l  16(%sp),%d0", "cmpi.l  #16,%d0", "andi.l  #16,%d0", "ori.l   #1,%d1",
):
    need(cf, token, "probe_cf.s")

dsp = (ROOT / "modules/perky/probe_glue.asm").read_text()
for token in (
    "pk_probe_source:",
    "move    a,x:>$20e",
    "move    x:>$209,r4",
    "move    #>$10,n7",
    "do      #$20,pk_probe_zero_done",
    "move    x:(r4+$3),b",
    "beq     pk_probe_continue",
    "move    x:>$20c,a",
    "asl     a",
    "move    a1,n1",
    "move    #>$400000,a",
    "move    #$0,r1",
    "move    a,x:(r1+n1)",
    "move    #$1,r1",
    "move    ssh,x0",
    "jmp     @CONT@",
):
    need(dsp, token, "probe_glue.asm")
if dsp.count("move    a,x:(r1+n1)") != 2:
    fail("probe_glue.asm: diagnostic impulse must be written once to L and once to R")

test_remix = ROOT / "remixes/test/perky-probe/remix.py"
if not test_remix.exists():
    fail("remixes/test/perky-probe/remix.py is missing")
if (ROOT / "remixes/perky-probe").exists():
    fail("perky-probe must not also exist as a top-level remix")

# The old abandoned perky_image prototype repacked DSP code and owned the seam.
# The current file is data-only: it may append private X/Y records and replace
# the boot upload pointers, but it must never know the source hook addresses,
# stock hook words, or probe labels. DspHook above stays the sole seam owner.
image_tool = ROOT / "tools/build/perky_image.py"
if not image_tool.exists():
    fail("tools/build/perky_image.py data integrator is missing")
image_text = image_tool.read_text()
for token in (
    "X_BASE = 0x3800", "X_WORDS = 236",
    "Y_BASE = 0x07a5", "Y_END = 0x1000",
    "ot_record(1, X_BASE, x_words)",
    "ot_record(2, Y_BASE, y_words)",
):
    need(image_text, token, "perky_image.py")
for forbidden in (
    "0x0039C", "0x001A2", "0x567000", "0x00020E",
    "pk_probe_source", "probe_glue.asm",
):
    if forbidden in image_text:
        fail(f"perky_image.py has forbidden source-seam knowledge {forbidden!r}")

print("PERKY probe gate: OK")

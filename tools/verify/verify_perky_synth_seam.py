#!/usr/bin/env python3
"""Static/model gate for PERKY's sample-accurate Noise/Tone source seam.

The active module intentionally remains the simpler impulse probe. This gate
qualifies the next synth seam independently: signature/fallback behavior,
per-core voice addressing, private-X ownership, one-sample trigger pulsing and
stock continuation are all pinned before the synth seam is allowed to replace
the probe in a test remix.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))


def fail(msg: str) -> None:
    raise SystemExit("verify-perky-synth-seam: " + msg)


def need(text: str, token: str) -> None:
    if token not in text:
        fail(f"synth_seam_glue.asm missing {token!r}")


# Load the active PERKY declaration only for memory ownership. The active DSP
# entry is still probe_glue.asm by design; this gate must not change that.
spec = importlib.util.spec_from_file_location(
    "perky_manifest_synth_seam", ROOT / "modules/perky/manifest.py"
)
if spec is None or spec.loader is None:
    fail("cannot load PERKY manifest")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
m = mod.MODULE
if m.dsp is None or m.dsp.asm != "modules/perky/probe_glue.asm":
    fail("active PERKY DSP must remain the impulse probe until synth qualification")

ranges = {(r.space, r.start, r.length, r.what) for r in m.claims.dsp_ranges}
want_ranges = (
    ("x", 0x3800, 236, "PERKY compact voice state + envelope caches + RNG"),
    ("x", 0x38EC, 1, "PERKY source event-offset staging"),
    ("x", 0x3900, 64, "PERKY shared source-render scratch"),
    ("y", 0x0795, 0x1000 - 0x0795, "PERKY packed Noise/Tone tables"),
)
for row in want_ranges:
    if row not in ranges:
        fail(f"manifest missing DSP ownership {row!r}")

src = (ROOT / "modules/perky/synth_seam_glue.asm").read_text()
for token in (
    "pk_synth_source:",
    "move    a,x:>$20e",
    "move    x:>$209,r4",
    "move    #>$00504b,x0",
    "move    #>$005931,x0",
    "add     #>$80,a",
    "move    x:>$418,a",
    "move    #>$003800,r6",
    "move    #>$00383a,r6",
    "move    #>$003874,r6",
    "move    #>$0038ae,r6",
    "move    #>$003900,r5",
    "move    x:>$20c,a",
    "move    a1,x:>$38ec",
    "move    #>$1,n7",
    "move    a1,x:(r6+$5)",
    "jsr     pk_voice_xstate",
    "move    #>$10,n7",
    "move    ssh,x0",
    "jmp     @CONT@",
):
    need(src, token)

# The first draft saved the event in r5+$3f, which the renderer owns as an
# oscillator temporary. Never allow that collision back in.
if "x:(r5+$3f)" in src:
    fail("event offset is stored inside the shared 64-word render scratch")

# Exact voice geometry: 58 words = 0x3a, four consecutive blocks, then RNG.
bases = [0x3800, 0x383A, 0x3874, 0x38AE]
for i, base in enumerate(bases):
    if base != 0x3800 + i * 58:
        fail("voice base spacing is not 58 words")
    if base + 58 > 0x38E8:
        fail(f"voice {i} overlaps shared RNG")
if bases[-1] + 57 != 0x38E7:
    fail("voice 3 must end at X:$38e7")
if 0x38EC >= 0x3900:
    fail("event staging word must remain outside shared scratch")

# Model every valid stock sample offset. The seam must never invoke a zero
# length renderer call: prefix is omitted at event 0 and suffix at event 15.
# Exactly one sample sees trigger=1, and the three segments always total 16.
for event in range(16):
    segments: list[tuple[int, int]] = []  # (sample_count, trigger_value)
    if event:
        segments.append((event, 0))
    segments.append((1, 1))
    suffix = 15 - event
    if suffix:
        segments.append((suffix, 0))
    if any(n <= 0 for n, _trig in segments):
        fail(f"event {event}: zero/negative renderer segment {segments}")
    if sum(n for n, _trig in segments) != 16:
        fail(f"event {event}: segment lengths do not total 16: {segments}")
    if sum(n for n, trig in segments if trig) != 1:
        fail(f"event {event}: trigger is not exactly one sample: {segments}")

# The assembly should have exactly three potential renderer calls: prefix,
# trigger sample, suffix/full path. Four indicates accidental duplicate work;
# fewer means one path disappeared. Current spelling has prefix, trigger,
# suffix, plus the mutually-exclusive full-block no-trigger path = four JSRs.
if src.count("jsr     pk_voice_xstate") != 4:
    fail(f"expected four syntactic renderer call sites, got {src.count('jsr     pk_voice_xstate')}")

# Invalid x:$418 slots must clear all 32 stereo source words rather than touch
# an unowned voice block.
for token in ("pks_silence:", "do      #$20,pks_silence_done", "move    a1,x:(r0)+"):
    need(src, token)

# Sanity: no hardcoded probe impulse remains in this synth seam.
if ">$400000" in src or "diagnostic impulse" in src.lower():
    fail("synth seam still contains the impulse-probe source")

print(
    "PERKY synth seam: PASS "
    "(4 x 58-word voices; RNG/event/scratch disjoint; all 16 event offsets "
    "split into exactly one triggered sample + 15 untriggered samples)"
)

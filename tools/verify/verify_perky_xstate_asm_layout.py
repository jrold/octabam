#!/usr/bin/env python3
"""Statically pin PERKY's shipping X-state assembly ABI.

This gate exists specifically to prevent a class of mistakes that is easy to
make in DSP56300 source: compact-state word numbers are documented in decimal,
while ``$NN`` assembler displacements are hexadecimal.

The complete renderer keeps one 58-word persistent block per voice:
  0..40   compact live state
  41..57  envelope cache
and a sparse shared scratch block at r5+$00..$63 (100 words).
"""
from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "modules/perky/noise_tone_voice_xstate_glue.asm"

R6 = re.compile(r"r6\+\$([0-9a-fA-F]+)")
ANNOTATED = re.compile(
    r"r6\+\$([0-9a-fA-F]+).*?;\s*compact word\s+(\d+)",
    re.IGNORECASE,
)
R5 = re.compile(r"r5\+\$([0-9a-fA-F]+)")


def fail(msg: str) -> None:
    raise SystemExit("verify-perky-xstate-asm-layout: " + msg)


def main() -> None:
    text = SRC.read_text()

    r6_offsets = [int(x, 16) for x in R6.findall(text)]
    if not r6_offsets:
        fail("no persistent r6 accesses found")
    if min(r6_offsets) < 0 or max(r6_offsets) > 57:
        fail(
            f"persistent access escaped 58-word voice/cache block: "
            f"min={min(r6_offsets)} max={max(r6_offsets)}"
        )

    annotated = [(int(h, 16), int(d)) for h, d in ANNOTATED.findall(text)]
    if not annotated:
        fail("no decimal compact-word annotations found")
    for actual, documented in annotated:
        if actual != documented:
            fail(
                f"decimal/hex ABI mismatch: assembler displacement ${actual:x} "
                f"addresses word {actual}, comment says compact word {documented}"
            )

    # Every compact word above decimal 9 is dangerous because its decimal
    # spelling differs from its hexadecimal displacement. Require the composer
    # to touch the full renderer ranges using their true hexadecimal offsets.
    required = set(range(10, 41))
    seen = {off for off in r6_offsets if off <= 40}
    missing = sorted(required - seen)
    if missing:
        fail(f"renderer no longer references compact words {missing}")

    if "lua     (r6+$29),r4" not in text:
        fail("persistent envelope cache must begin at compact/cache word 41 ($29)")

    r5_offsets = [int(x, 16) for x in R5.findall(text)]
    if not r5_offsets:
        fail("no shared-scratch r5 accesses found")
    if max(r5_offsets) != 0x63:
        fail(f"shared scratch high-water is ${max(r5_offsets):x}, expected $63")
    if any(off > 0x63 for off in r5_offsets):
        fail("shared scratch access escaped 100-word X:$3900..$3963 block")

    print(
        "PERKY X-state assembly ABI: PASS "
        f"({len(r6_offsets)} persistent accesses within words 0..57; "
        f"{len(annotated)} decimal/hex annotations exact; "
        "cache key word 41=$29; scratch high-water $63)"
    )


if __name__ == "__main__":
    main()

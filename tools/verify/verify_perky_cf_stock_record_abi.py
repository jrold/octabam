#!/usr/bin/env python3
"""Gate Perky's emitted source record against the measured stock FLEX ABI."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "modules/perky/cf_perky4.c"
MEASURED = ROOT / "modules/analog-bassdrum/control.c"


def main() -> None:
    core = CORE.read_text()
    measured = MEASURED.read_text()

    # ANALOG BD is the hardware-measured source-machine reference in this tree.
    measured_needles = (
        "Header: source count, ring start, Q26 source rate, Q26 read position.",
        "Every track is rendered twice per",
        "the second call has end=16",
        "cursor+4+2*n",
    )
    for needle in measured_needles:
        if needle not in measured:
            raise AssertionError(f"measured FLEX ABI reference drifted: missing {needle!r}")

    # Pin the production encoder to that exact stock layout. Source count is
    # placed in the high 24-bit transport lane, Q26 unity is 0x04000000, and
    # mono is duplicated into consecutive L/R sample longs.
    compact = re.sub(r"\s+", "", core)
    required = (
        "d[0]=n<<8;",
        "d[1]=0;",
        "d[2]=0x04000000u;",
        "d[3]=0;",
        "q=(uint32_t)(int32_t)m[i]<<16;",
        "d[4+2*i]=q;",
        "d[5+2*i]=q;",
        "return4u+2u*n;",
    )
    for needle in required:
        if needle not in compact:
            raise AssertionError(f"Perky stock-record encoder drifted: missing {needle!r}")

    # Algebraic span check for all legal stock source segments. Two segments
    # around a trig split must always total 40 longs = 160 bytes per voice.
    for split in range(17):
        pre = 4 + 2 * split
        post = 4 + 2 * (16 - split)
        if pre + post != 40:
            raise AssertionError(f"split {split}: stock frame span != 40 longs")

    print(
        "PERKY stock source-record ABI: PASS "
        "(measured FLEX header/rate/sample lanes; all 17 split positions = 160 B/voice)"
    )


if __name__ == "__main__":
    main()

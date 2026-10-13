#!/usr/bin/env python3
"""Step 1 of the FX-recovery sharding plan: the composed program's label -> address map.

    REMIX=perky-machine BUILD=3 python3 tools/perky/perky_shard_map.py [out.json]

`FX_RECOVERY_FEASIBILITY.md` lays out the sharding plan. This is its first step, and it
is the prerequisite for all the others: you cannot re-emit a shard with its cross-shard
targets as `$hex` literals until you know what address every label lands at.

TWO THINGS THIS DOES THAT NAIVE ASSEMBLY DOES NOT, both learned by failing:

1. `out/perky/light2/multi.asm` IS NOT ASSEMBLABLE AS WRITTEN. It still carries the
   `@CONT@` marker; the build substitutes it per payload and only then assembles
   (build log: `SUBST: PERKY PROBE payload A -- @CONT@ -> $000426`). So the marker is
   substituted here first. Add a new payload-relative marker and this must learn it too.

2. The assembler is TWO-PASS and reports "pass-1 sizing drift" when a label resolves to
   a different instruction size between passes, moving every address after it. One such
   site is visible at line 408 of the QUALIFIED build, so drift is not hypothetical on
   this code. That matters enormously for sharding: the plan re-emits cross-shard
   references as literals, and a literal that encodes to a different size than the label
   form did would shift every subsequent address in the shard. This tool therefore prints
   the assembled word count so it can be compared against the build's own ledger figure
   (`p_words` in out/perky/light2/memory.json); a mismatch means the map does not describe
   the shipped code and must not be used for splitting.

MEASURED at the time of writing: 3051 words, 0x1000..0x1bea, 205 symbols.

THE THREE-WORD DISCREPANCY, RESOLVED. The build's progress line says

    PERKY PROBE   P:0x01000..0x01bee (3054 words)

which is three MORE than this assembly. It is the build's progress line that is the
outlier, and two independent artifacts say so:

    out/perky/light2/multi.measure.bin   9153 bytes / 3 = 3051 words
    out/perky/light2/memory.json         p_words = 3051

`0x1bee - 0x1000 = 3054`, so that line's range simply extends three words past where the
code ends (`0x1bea`), i.e. it reports a region end rather than the program length. The map
is the side confirmed twice; the progress line is not used as a source of truth here.

Falsification, since the difference is small enough to be dangerous: if a shard split on
this map ever produces a program that does not match the measured binary, the map is
wrong and this resolution is wrong with it.
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tools/build"), str(ROOT / "tools/perky")]

# Payload A's continuation address, from the build log's SUBST line.
CONT_A = "$000426"
PROGRAM_ORG = 0x1000
COMPOSED = ROOT / "out/perky/light2/multi.asm"
LEDGER = ROOT / "out/perky/light2/memory.json"


def main() -> int:
    out = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "out/perky/light2/shards.json"
    if not COMPOSED.exists():
        print(f"  missing {COMPOSED} -- build the light2 machine first", file=sys.stderr)
        return 2

    source = COMPOSED.read_text()
    if "@CONT@" in source:
        source = source.replace("@CONT@", CONT_A)
        print(f"  substituted @CONT@ -> {CONT_A} (unchanged on disk; this is the "
              f"build's own preprocessing)")

    import build_bus  # imported late: it needs REMIX set, and says so if it is not

    words, syms = build_bus.assemble_syms(source, PROGRAM_ORG, "perky-shard-map")
    end = PROGRAM_ORG + len(words) - 1
    print(f"  assembled: {len(words)} words  0x{PROGRAM_ORG:x}..0x{end:x}")
    print(f"  symbols  : {len(syms)}")

    if LEDGER.exists():
        p_words = json.loads(LEDGER.read_text())["p_words"]
        if p_words != len(words):
            print(f"  *** MISMATCH: the ledger says {p_words} P words, this assembly "
                  f"produced {len(words)}. The map does NOT describe the shipped code; "
                  f"do not split on it.", file=sys.stderr)
            return 1
        print(f"  ledger agrees: p_words={p_words}")

    ordered = sorted(syms.items(), key=lambda kv: (kv[1], kv[0]))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"org": PROGRAM_ORG, "words": len(words),
                               "symbols": dict(ordered)}, indent=1) + "\n")
    print(f"  first: " + ", ".join(f"{k}=0x{v:x}" for k, v in ordered[:4]))
    print(f"  last : " + ", ".join(f"{k}=0x{v:x}" for k, v in ordered[-4:]))
    print(f"  wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

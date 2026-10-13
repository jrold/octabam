#!/usr/bin/env python3
"""Verify the Perky DSP program emits as independently placeable shards.

The program is one 3051-word code stream, so it can only be placed in one
contiguous harvested run. Restoring SPRING REV, DARK REV and LO-FI leaves the
largest run at PLATE's 594 words, so the program has to be emitted as shards --
and `build_bus.py`'s `place(words, start)` can then be called once per shard.

This gate pins the three properties that make that valid. It checks the SHAPE
of the emission, not the renderer, so a regression in the sharding fails here
rather than at a flash.

  1. ENCODING. Each piece, assembled at its MONOLITH origin, must equal the
     monolith's own bytes for that source range. This is a real byte-identity
     claim: two independent assemblies of the same code over all 3051 words.
  2. EXTENTS. Each piece, assembled at its ASSIGNED origin across the two local
     runs and the five shared tails, must produce exactly its measured extent.
     Byte-identity is deliberately NOT claimed here -- relocation moves internal
     label addresses, and pretending otherwise would be a false gate.
  3. THE CALL GRAPH. Every cross-piece reference is rewritten to an absolute
     $hex; each must name a final address inside some shard. This is what
     "disassemble what you assemble, and verify actual branches, calls and
     ranges" reduces to at the source level: the encoding is pinned by (1),
     so what remains is that no call or jump aims outside the placed program.

Also asserted: the pieces are pairwise disjoint, and the pieces occupy no span
of any stock effect except the two approved sacrifices (PLATE REV and
COMPRESSOR). That is release gate 7's placement half.

Nothing here renders audio. `verify_perky_synth_port.py` and the *_seam_exec
gates own the renderer; this one owns placement.
"""
from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "modules/perky"), str(ROOT / "tools/perky"),
                str(ROOT / "tools"), str(ROOT / "tools/build"), str(ROOT / "tools/remix")]

FAILURES: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        FAILURES.append(msg)


def main() -> int:
    import build_multi_payload as payload
    import perky_emit_shards as emit

    assets = Path(os.environ.get("PERKY_SIMPLE_ASSETS", ROOT / "out/perky/simple-drum-assets"))
    target = ROOT / "out/perky/multi"
    payload.build(assets, target)
    multi = target / "multi.asm"
    check(multi.exists(), f"payload did not produce {multi}")
    if FAILURES:
        for f in FAILURES:
            print(f"  FAIL {f}")
        return 1

    # emit.check prints its own three lines and returns nonzero on failure.
    rc = emit.check(multi, verbose=False)
    check(rc == 0, "perky_emit_shards.check() reported a failure")

    # Release gate 7's placement half: disjoint, and clear of every retained
    # stock effect. Recomputed here rather than trusted from the tool.
    import json
    from remix import registry, stock
    pieces, whole, dest, final, syms = emit.emit(multi)
    spans = sorted((dest[n], dest[n] + (b - a) - 1, n) for n, a, b, _, _ in pieces)
    for i in range(len(spans)):
        for j in range(i + 1, len(spans)):
            check(not (spans[i][0] <= spans[j][0] <= spans[i][1]),
                  f"shards {spans[i][2]} and {spans[j][2]} overlap")

    r = registry.remix("perky-machine")
    sp = stock.p_spans("A")
    listed = set(r.modules) | set(r.fx1 or [k for k in sp if k])
    keep = set(sp) - stock.harvested(listed)
    for eff, (lo, n) in sp.items():
        if eff not in keep:
            continue
        for s_lo, s_hi, name in spans:
            check(s_hi < lo or s_lo > lo + n - 1,
                  f"shard {name} overlaps the RETAINED effect {eff} at 0x{lo:05x}")

    print(f"  shards: {len(pieces)}   words: {sum(b - a for _, a, b, _, _ in pieces)}"
          f"   monolith: {len(whole)}")
    print(f"  retained stock effects clear of every shard: {len(keep)}")
    if FAILURES:
        for f in FAILURES:
            print(f"  FAIL {f}")
        return 1
    print("  shard emission OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

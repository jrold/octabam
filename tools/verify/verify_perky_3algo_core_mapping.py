#!/usr/bin/env python3
"""Prove T1 and T5 -- and ONLY T1 and T5 -- are the tracks this machine admits.

The definition of done asks for "T1 mapping to its correct DSP payload/core" and
"T5 mapping to its correct DSP payload/core" to be tested, and nothing in this
branch tested them. This gate does, from the STOCK payloads rather than from an
assumption, because the mapping is entirely a property of stock's own slot
bookkeeping:

* the composed dispatcher admits a record only when `x:$418` is `ADMITTED_SLOT`
  (0) -- its one-Perky-track-per-core admission rule;
* the STOCK dispatcher walks `x:$418` from 0 by `0x20` while the value is below
  `0x80` (`add #<$20,b` / `cmp #>$80,b` / `bne` at `0x537..0x53c` on payload A,
  `0x243..` on B). Four steps of `0x20` to `0x80` is exactly FOUR tracks per
  core, one slot each, so `x:$418 = 0` is that core's FIRST track;
* the payloads record their own track base in `x:$420`: **0 on payload B** and
  **4 on payload A**. Payload B serves tracks 1-4 and payload A serves tracks
  5-8, so slot 0 is track 1 on B and track 5 on A.

Therefore admitting only slot 0 admits T1 on payload B and T5 on payload A, and
admitting no other slot is what keeps T2-T4 and T6-T8 ordinary. The gate fails if
either payload's base changes, if the stride/limit stops describing four tracks,
or if the composed dispatcher's admitted slot stops being 0.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "modules/perky"),
                str(ROOT / "tools/perky")]

import build_dsp_3algo_source as composed  # noqa: E402

DISASM = ROOT / "tools/build/dsp_disasm_all.py"
OUT = ROOT / "out/dsp"
# Stock's per-core track base, read from its own initialiser: `move #$N,x0 /
# move x0,x:>$420` immediately before the x:$418 setup.
TRACK_BASE = {"A": 4, "B": 0}
TRACKS_PER_CORE = 4


def die(message: str) -> "NoReturn":
    raise SystemExit("verify-perky-3algo-core-mapping: " + message)


def payload_asm(tag: str) -> str:
    path = OUT / f"payload_{tag}.asm"
    if not path.exists():
        result = subprocess.run([sys.executable, str(DISASM)],
                                capture_output=True, text=True)
        if result.returncode or not path.exists():
            die(f"could not disassemble the stock payloads: "
                f"{(result.stdout or result.stderr)[-500:]}")
    return path.read_text()


def main() -> None:
    text = {tag: payload_asm(tag) for tag in "AB"}

    # ---- stock's per-core track base -------------------------------------
    for tag in "AB":
        # The two payloads spell the same immediate differently -- `#>$4` on A,
        # `#$0` on B -- so the pattern accepts the optional `>`.
        pattern = re.compile(r"move\s+#>?\$([0-9a-f]+),x0\s*;.*\n"
                             r"[0-9a-f]{6}:\s*move\s+x0,x:>\$420", re.M)
        match = pattern.search(text[tag])
        if not match:
            die(f"payload {tag}: could not find the x:$420 initialiser")
        got = int(match.group(1), 16)
        if got != TRACK_BASE[tag]:
            die(f"payload {tag}: x:$420 base is {got}, expected "
                f"{TRACK_BASE[tag]} -- the track<->core mapping moved, so "
                f"slot 0 is no longer T1/T5")
    print(f"track base : payload B x:$420 = {TRACK_BASE['B']} (tracks 1-4), "
          f"payload A x:$420 = {TRACK_BASE['A']} (tracks 5-8)")

    # ---- four tracks per core: x:$418 walks 0, 0x20, 0x40, 0x60 ----------
    for tag in "AB":
        walk = re.search(r"move\s+x:>\$418,b\s*;.*\n"
                         r"[0-9a-f]{6}:\s*move\s+a,x:>\$209\s*;.*\n"
                         r"[0-9a-f]{6}:\s*add\s+#<\$([0-9a-f]+),b\s*;.*\n"
                         r"[0-9a-f]{6}:\s*cmp\s+#>\$([0-9a-f]+),b\s*;.*\n"
                         r"[0-9a-f]{6}:\s*move\s+b,x:>\$418", text[tag])
        if not walk:
            die(f"payload {tag}: could not find the x:$418 slot walk")
        stride, limit = int(walk.group(1), 16), int(walk.group(2), 16)
        if limit % stride:
            die(f"payload {tag}: x:$418 limit {limit:#x} is not a multiple of "
                f"the stride {stride:#x}")
        tracks = limit // stride
        if tracks != TRACKS_PER_CORE:
            die(f"payload {tag}: the slot walk spans {tracks} tracks, expected "
                f"{TRACKS_PER_CORE}")
        print(f"slot walk  : payload {tag} x:$418 steps {stride:#04x} to "
              f"{limit:#04x} = {tracks} tracks per core")

    # ---- the composed machine admits exactly slot 0 ----------------------
    source = composed.normalize(composed.compose())
    admitted = composed.ADMITTED_SLOT
    if admitted != 0:
        die(f"the composed dispatcher admits x:$418 == {admitted:#x}; slot 0 is "
            f"the core's first track (T1/T5), so any other value admits a "
            f"different track and lets T2-T4/T6-T8 become Perky")
    # Slot 0 is admitted, so the rule is written as "is the slot zero" --
    # `move x:>$418,b` / `tst b` / `bne <not admitted>` -- not as a compare.
    if re.search(r"move\s+x:>\$418,b.*\n\s*tst\s+b\s*\n\s*bne\s+(\S+)",
                 source) is None:
        die("the composed dispatcher does not read x:$418 and refuse a "
            "non-zero slot; the admission rule is not in the artifact")
    # NO SET-AND-NEVER-CLEARED LATCH -- guard the defect, do not re-introduce it.
    #
    # The machine used to latch `x:$38ed = 1` on the first admission and NEVER
    # clear it, so the first admitted block silenced every later one: the Perky
    # track rendered one block and then nothing, for good. It guarded a case the
    # target cannot produce -- each core has exactly ONE Perky-capable track, so
    # exactly one record per core can pass the PK/Y1 test -- and its only
    # observable effect was that silence. Removing it is the fix; this check
    # refuses to let it come back.
    writes = re.findall(r"move\s+\S+,x:>\$%04x" % composed.ADMIT_LATCH, source)
    clears = re.findall(r"move\s+#>?\$0+,?\w*\s*\n\s*move\s+\w+,x:>\$%04x"
                        % composed.ADMIT_LATCH, source)
    if writes and not clears:
        die(f"the composed dispatcher WRITES x:${composed.ADMIT_LATCH:04x} "
            f"({len(writes)} time(s)) and never clears it -- an admission latch "
            f"like that silences every block after the first, because the "
            f"machine is installed only at the per-track source site and has no "
            f"once-per-block hook to reset it from")
    print(f"latch      : x:${composed.ADMIT_LATCH:04x} is "
          f"{'unused' if not writes else 'written and cleared'} -- no "
          f"set-and-never-cleared admission latch (one voice per core is "
          f"already guaranteed by admitting slot 0 only)")
    print(f"admission  : composed dispatcher admits x:$418 == {admitted:#x} "
          f"(the core's first track)")

    print()
    print("perky-3algo-core-mapping: PASS (stock walks four slots per core from "
          "x:$418 = 0 and records its track base in x:$420 -- 0 for payload B, "
          "4 for payload A; the composed machine admits slot 0 only, i.e. T1 on "
          "payload B and T5 on payload A, and nothing else)")


if __name__ == "__main__":
    main()

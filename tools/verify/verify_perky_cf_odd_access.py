#!/usr/bin/env python3
"""Fail the Perky ColdFire build if it emits an odd-address word/long access.

A real ColdFire raises an address error on any word/long access whose
effective address is odd; the vendored Musashi (in ColdFire mode) does not
emulate that, so such an access runs fine under ot_emu and faults on the unit.
GCC's store-merging pass is the usual source: two adjacent byte stores (e.g.
active_algo/active_mode at an odd struct offset) become one move.w at an odd
address. The CF units are built with -fno-store-merging to prevent it; this
gate is the check that it stayed prevented.

The audit is deliberately conservative: it flags any word/long memory operand
whose constant displacement is odd. A false positive is a byte store GCC
merged wrongly-sized past a byte field, which is itself worth seeing.
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
DEFAULT = ROOT / "out/perky/cf-final/generated"

OP = re.compile(
    r"^(move\.w|move\.l|movea\.l|movem\.l|clr\.w|clr\.l|add\.w|add\.l|sub\.w|sub\.l|"
    r"cmp\.w|cmp\.l|tst\.w|tst\.l|muls\.w|mulu\.w|ext\.l|extb\.l)\b")
EA = re.compile(r"([+-]?(?:0x[0-9a-fA-F]+|\d+))?\(%a([0-7])")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--generated", type=pathlib.Path, default=DEFAULT)
    args = ap.parse_args()
    gen = args.generated
    if not gen.is_dir():
        raise SystemExit(f"PERKY CF odd-access: missing generated dir {gen}")

    hits = []
    total = 0
    for f in sorted(gen.glob("*.s")):
        for n, line in enumerate(f.read_text().splitlines(), 1):
            s = line.split("|")[0].strip()
            if not s or s.endswith(":") or not OP.match(s):
                continue
            for disp, _reg in EA.findall(s):
                total += 1
                if disp and (int(disp, 0) % 2) == 1:
                    hits.append((f.name, n, s))
    if hits:
        for h in hits[:20]:
            print(f"  {h[0]}:{h[1]}: {h[2]}", file=sys.stderr)
        raise SystemExit(
            f"PERKY CF odd-access: FAIL: {len(hits)} word/long access(es) at an odd "
            f"displacement (a real ColdFire faults on these)")
    print(f"PERKY CF odd-address access: PASS ({total} word/long operands, none odd)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

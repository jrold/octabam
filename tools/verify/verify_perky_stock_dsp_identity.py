#!/usr/bin/env python3
"""Require the final Perky MAIN OS to preserve stock DSP boot/payload bytes.

Octatrack 1.40C stores the two DSP bootstraps and their two self-describing
payloads contiguously in MAIN OS VA 0x400e21e0..0x401086f3. The final ColdFire
Perky architecture does not need to touch that span at all. This gate compares
all 156,948 bytes, not a selection of effect modules, so any DSP code/data,
dispatch, upload or bootstrap mutation fails the final build.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

BASE = 0x40000400
DSP_START = 0x400E21E0
DSP_END = 0x401086F4  # exclusive
EXPECTED_BYTES = DSP_END - DSP_START


def digest(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("stock", nargs="?", type=Path,
                    default=Path("out/raw/section_3_MAIN_OS.bin"),
                    help="decoded stock 1.40C MAIN OS")
    ap.add_argument("candidate", nargs="?", type=Path,
                    default=Path("out/mainos_bus.bin"),
                    help="final remixed MAIN OS")
    args = ap.parse_args()

    stock = args.stock.read_bytes()
    candidate = args.candidate.read_bytes()
    lo = DSP_START - BASE
    hi = DSP_END - BASE
    if len(stock) < hi or len(candidate) < hi:
        raise SystemExit(
            f"PERKY stock-DSP identity: image too short for 0x{DSP_START:08x}..0x{DSP_END-1:08x}"
        )
    a = stock[lo:hi]
    b = candidate[lo:hi]
    if len(a) != EXPECTED_BYTES or len(b) != EXPECTED_BYTES:
        raise AssertionError("DSP extent size drift")
    if a != b:
        first = next(i for i, (x, y) in enumerate(zip(a, b)) if x != y)
        absolute = DSP_START + first
        changed = sum(x != y for x, y in zip(a, b))
        raise SystemExit(
            "PERKY stock-DSP identity: FAIL "
            f"{changed} changed bytes; first at MAIN OS VA 0x{absolute:08x} "
            f"stock=0x{a[first]:02x} candidate=0x{b[first]:02x}"
        )

    print(
        "PERKY stock-DSP identity: PASS "
        f"({EXPECTED_BYTES:,} bootstrap/payload bytes byte-identical; "
        f"sha256={digest(a)})"
    )


if __name__ == "__main__":
    main()

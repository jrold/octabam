#!/usr/bin/env python3
"""Require the final Perky MAIN OS to preserve the ColdFire DSP boot path.

The final ColdFire-only Perky architecture deliberately redirects the *caller*
at 0x4000050c through octabam's platform loader, which later continues through
the stock DSP boot routine.  The uploader and boot routines themselves must
remain byte-identical so the two stock bootstraps/payloads are still selected,
addressed and uploaded exactly as 1.40C does.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

BASE = 0x40000400
BOOT_PATH_START = 0x40001B18  # dsp_upload_payload
BOOT_PATH_END = 0x40001F00    # exclusive; contains bootstrap uploader + dsp_boot
EXPECTED_BYTES = BOOT_PATH_END - BOOT_PATH_START
EXPECTED_STOCK_SHA256 = "9f89c105325a6af701b662c17b560b3f010909f66b4e2fe5a170640e15d3eb1a"


def digest(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("stock", nargs="?", type=Path,
                    default=Path("out/raw/section_3_MAIN_OS.bin"))
    ap.add_argument("candidate", nargs="?", type=Path,
                    default=Path("out/mainos_bus.bin"))
    args = ap.parse_args()

    stock = args.stock.read_bytes()
    candidate = args.candidate.read_bytes()
    lo = BOOT_PATH_START - BASE
    hi = BOOT_PATH_END - BASE
    if len(stock) < hi or len(candidate) < hi:
        raise SystemExit(
            f"PERKY stock-DSP boot path: image too short for "
            f"0x{BOOT_PATH_START:08x}..0x{BOOT_PATH_END-1:08x}"
        )
    a = stock[lo:hi]
    b = candidate[lo:hi]
    if len(a) != EXPECTED_BYTES or len(b) != EXPECTED_BYTES:
        raise AssertionError("DSP boot-path extent size drift")
    got_stock = digest(a)
    if got_stock != EXPECTED_STOCK_SHA256:
        raise SystemExit(
            "PERKY stock-DSP boot path: stock oracle drifted: "
            f"sha256={got_stock}, expected {EXPECTED_STOCK_SHA256}"
        )
    if a != b:
        first = next(i for i, (x, y) in enumerate(zip(a, b)) if x != y)
        absolute = BOOT_PATH_START + first
        changed = sum(x != y for x, y in zip(a, b))
        raise SystemExit(
            "PERKY stock-DSP boot path: FAIL "
            f"{changed} changed bytes; first at MAIN OS VA 0x{absolute:08x} "
            f"stock=0x{a[first]:02x} candidate=0x{b[first]:02x}"
        )

    print(
        "PERKY stock-DSP boot path: PASS "
        f"({EXPECTED_BYTES:,} ColdFire uploader/boot bytes byte-identical; "
        f"sha256={got_stock})"
    )


if __name__ == "__main__":
    main()

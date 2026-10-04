#!/usr/bin/env python3
"""Add PERKY's packed private-Y tables to a normal Octabam PERKY image.

This is the development bridge before the table preboot pass is folded into
``build_bus.py``.  It takes an already-built ``perky-probe`` image, extends
both finalized DSP uploads through ``perky_image``, and installs Octabam's
existing preboot loader.

It deliberately supports an image with NO existing platform loader.  If the
boot site is already redirected (for example a remix with DRAM units/Octakit),
this wrapper refuses instead of trying to compose two loaders; the eventual
in-tree build_bus integration will rebuild the one shared platform loader the
same way Analog BD does.

Typical development flow:

    REMIX=perky-probe python3 tools/build/build_bus.py
    python3 tools/perky/fabricate_noise_tone_fixtures.py --out out/perky/synthetic
    python3 tools/perky/build_noise_tone_payload.py out/perky/synthetic \
        --out out/perky/packed
    python3 tools/build/build_perky.py out/perky/packed

The result still carries the active PERKY *impulse* source canary unless the
DSP renderer module has explicitly been switched.  Loading tables alone is not
a claim that the Noise/Tone machine is hardware-ready.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/build"))

import dsp_modmap  # noqa:E402
import perky_image  # noqa:E402
from remix import platform_build  # noqa:E402

BASE = dsp_modmap.BASE


def apply_write(img: bytearray, address: int, expect: bytes, write: bytes, note: str) -> None:
    offset = address - BASE
    if offset < 0 or offset + len(expect) > len(img):
        raise SystemExit(f"build-perky: write {note} at 0x{address:08x} is outside image")
    got = bytes(img[offset:offset + len(expect)])
    if got != expect:
        raise SystemExit(
            f"build-perky: {note} at 0x{address:08x} finds {got.hex()}, "
            f"not expected {expect.hex()}; refusing"
        )
    img[offset:offset + len(write)] = write
    print(f"  poke 0x{address:08x}: {expect.hex()} -> {write.hex()}  {note}")


def build(image_path: Path, table_dir: Path, output: Path) -> None:
    if not image_path.exists():
        raise SystemExit(
            f"build-perky: missing {image_path}; build REMIX=perky-probe first"
        )
    img = bytearray(image_path.read_bytes())
    stock_len = len(dsp_modmap.IMG.read_bytes())
    if len(img) != stock_len:
        raise SystemExit(
            f"build-perky: {image_path} is {len(img):,} B, stock OS is {stock_len:,} B. "
            "This development wrapper expects an image with no existing loader append."
        )

    pres, pokes, log, layout = perky_image.integrate(img, table_dir)
    print("=== PERKY: packed tables, both DSP payloads, preboot loader ===")
    for line in log:
        print("  " + line)
    for address, expect, write, note in pokes:
        apply_write(img, address, expect, write, note)

    # No DRAM units and no ordinary payloads: this invocation exists solely to
    # obtain Octabam's established loader around the two PERKY preboot uploads.
    append, _symbols, boot, names = platform_build.build(
        [], [], ROOT / "out/platform-perky",
        reserve=None,
        defsyms={},
        preboot=pres,
        unit_defs={},
        includes={},
    )
    ba, bexp, bw, bnote = boot
    apply_write(img, ba, bexp, bw, bnote)
    img.extend(append)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(img)
    digest = hashlib.sha256(img).hexdigest()
    output.with_suffix(".remix").write_text(
        f"perky-table-canary {digest}\n"
    )
    kind = "SYNTHETIC" if layout.get("synthetic") else "REAL-DATA INPUT"
    print(
        f"{output}: {len(img):,} bytes, {kind}, tables "
        f"{layout['total_words']} words at Y:{perky_image.Y_BASE:05x}.."
        f"{perky_image.Y_BASE + layout['total_words'] - 1:05x}; "
        f"loader payloads {', '.join(names)}"
    )
    print("*** DEVELOPMENT TABLE-LOADED CANARY: active source renderer may still be impulse. ***")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("table_dir", type=Path,
                    help="directory from build_noise_tone_payload.py")
    ap.add_argument("--image", type=Path, default=ROOT / "out/mainos_bus.bin",
                    help="already-built perky-probe image with no loader append")
    ap.add_argument("--out", type=Path, default=ROOT / "out/mainos_perky_tables.bin")
    args = ap.parse_args()
    build(args.image, args.table_dir, args.out)


if __name__ == "__main__":
    main()

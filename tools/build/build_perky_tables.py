#!/usr/bin/env python3
"""Post-process a normal ``perky-probe`` build with packed Noise/Tone tables.

Unlike the deleted first draft, this uses platform_build's explicit
``preboot_reserve`` support.  The normal Octabam build has already applied the
PERKY module's 242-page bottom ArenaReserve to the OS image.  This tool verifies
those geometry pokes, extends both finalized DSP uploads through
``perky_image.py``, then appends the standard Octabam loader carrying those two
preboot payloads.

The active DSP source remains whatever the remix built (currently the impulse
canary). Loading tables is a separate transport/memory milestone and is not a
claim that the real Noise/Tone renderer is live.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tools/build")]

import dsp_modmap  # noqa:E402
import perky_image  # noqa:E402
from remix import arena, platform_build  # noqa:E402

BASE = dsp_modmap.BASE
PAGES = 242
RESERVE = (arena.BASE, PAGES * arena.PAGE)


def die(message: str) -> "NoReturn":
    raise SystemExit("build-perky-tables: " + message)


def image_slice(img: bytes | bytearray, address: int, size: int) -> bytes:
    off = address - BASE
    if off < 0 or off + size > len(img):
        die(f"0x{address:08x}..0x{address+size:08x} is outside the OS image")
    return bytes(img[off:off + size])


def apply_write(img: bytearray, address: int, expect: bytes, write: bytes, note: str) -> None:
    got = image_slice(img, address, len(expect))
    if got != expect:
        die(
            f"{note} at 0x{address:08x} finds {got.hex()}, not expected "
            f"{expect.hex()}; refusing"
        )
    off = address - BASE
    img[off:off + len(write)] = write
    print(f"  poke 0x{address:08x}: {expect.hex()} -> {write.hex()}  {note}")


def verify_reservation(img: bytes | bytearray) -> None:
    """Prove build_bus already installed exactly PERKY's arena geometry."""
    reservations = [("PERKY PROBE", "bottom", PAGES)]
    pokes = arena.pokes(reservations)
    if not pokes:
        die("arena helper returned no writes for the PERKY reservation")
    for address, stock, written, note in pokes:
        got = image_slice(img, address, len(written))
        if got != written:
            die(
                f"arena reservation is not present: 0x{address:08x} ({note}) "
                f"holds {got.hex()}, expected {written.hex()}. Build the "
                "perky-probe remix from this branch before adding tables."
            )


def build(image_path: Path, table_dir: Path, output: Path) -> None:
    if not image_path.exists():
        die(f"missing {image_path}; build REMIX=perky-probe first")
    stock_len = len(dsp_modmap.IMG.read_bytes())
    img = bytearray(image_path.read_bytes())
    if len(img) != stock_len:
        die(
            f"{image_path} is {len(img):,} B but stock-length build is "
            f"{stock_len:,} B. This isolated table canary expects no existing "
            "platform-loader append."
        )
    verify_reservation(img)

    pres, pokes, log, layout = perky_image.integrate(img, table_dir)
    print("=== PERKY packed private-Y tables ===")
    for line in log:
        print("  " + line)
    for address, expect, write, note in pokes:
        apply_write(img, address, expect, write, note)

    append, symbols, boot, names = platform_build.build(
        [], [], ROOT / "out/platform-perky-tables",
        preboot=pres,
        preboot_reserve=RESERVE,
    )
    if symbols:
        die("preboot-only loader unexpectedly produced runtime symbols")
    apply_write(img, *boot)
    img.extend(append)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(img)
    digest = hashlib.sha256(img).hexdigest()
    output.with_suffix(".remix").write_text(
        f"perky-table-canary {digest}\n"
    )
    kind = "SYNTHETIC" if layout.get("synthetic") else "REAL-DATA INPUT"
    print(
        f"{output}: {len(img):,} bytes; {kind}; "
        f"Y:{perky_image.Y_BASE:05x}.."
        f"{perky_image.Y_BASE + layout['total_words'] - 1:05x}; "
        f"loader preboot payloads: {', '.join(names)}"
    )
    print(
        "*** DEVELOPMENT TABLE-LOADED IMAGE: the active PERKY DSP source may "
        "still be the impulse canary. ***"
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("table_dir", type=Path,
                    help="directory from build_noise_tone_payload.py")
    ap.add_argument("--image", type=Path, default=ROOT / "out/mainos_bus.bin",
                    help="stock-length perky-probe build with its arena reservation")
    ap.add_argument("--out", type=Path,
                    default=ROOT / "out/mainos_perky_tables.bin")
    args = ap.parse_args()
    build(args.image, args.table_dir, args.out)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Rebuild one existing Octabam platform loader with PERKY DSP preboot uploads.

The full PERKY machine has DRAM-linked ColdFire units, so its normal build
already carries an Octabam platform loader.  A second loader would be wrong.
This helper preserves the exact already-linked runtime bytes/destination/stage,
adds PERKY's extended A/B DSP uploads as *preboot* entries, and rebuilds one
shared loader append at the same fixed LOADER_AT address.

Expected input is a normal ``build_bus.py`` result for the isolated
``perky-machine`` development remix.  That remix must have exactly one normal
platform payload: Octabam's own runtime.  Any extra payload is refused rather
than silently lost.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import NoReturn

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tools/build")]

import dsp_modmap  # noqa:E402
import perky_image  # noqa:E402
from remix import arena, pack, platform_build  # noqa:E402

BASE = dsp_modmap.BASE
PAGES = 242
RESERVE = (arena.BASE, PAGES * arena.PAGE)
RUNTIME_RESERVE = (RESERVE[0] + RESERVE[1], arena.PLATFORM_PAGES * arena.PAGE)
REQUIRED_LAYOUT = ("base", "runtime_end", "stage", "stage_end", "ceiling", "size")


def die(message: str) -> NoReturn:
    raise SystemExit("perky-machine-loader: " + message)


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


def _cached(address: int) -> int:
    if 0x48000000 <= address < 0x50000000:
        return address - platform_build.UNCACHED
    return address


def _overlap(a: int, ae: int, b: int, be: int) -> bool:
    return a < be and b < ae


def verify_reservation(img: bytes | bytearray) -> None:
    pokes = arena.pokes([("PERKY PROBE", "bottom", PAGES),
                         ("octabam platform", "bottom", arena.PLATFORM_PAGES)])
    if not pokes:
        die("arena helper returned no PERKY reservation writes")
    for address, _stock, written, note in pokes:
        got = image_slice(img, address, len(written))
        if got != written:
            die(
                f"PERKY arena reservation missing at 0x{address:08x} ({note}): "
                f"{got.hex()} != {written.hex()}"
            )


def load_runtime(platform_dir: Path) -> tuple[dict, bytes, dict]:
    layout_path = platform_dir / platform_build.LAYOUT
    raw_path = platform_dir / "runtime.raw"
    table_path = platform_dir / "table.inc"
    blob0_path = platform_dir / "blob0.bin"
    for path in (layout_path, raw_path, table_path, blob0_path):
        if not path.exists():
            die(f"missing {path}; run the normal perky-machine build first")

    try:
        layout = json.loads(layout_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        die(f"{layout_path}: {exc}")
    missing = [key for key in REQUIRED_LAYOUT if key not in layout]
    if missing:
        die(f"{layout_path}: missing {', '.join(missing)}")
    if layout.get("loader") != platform_build.LOADER_AT:
        die(
            f"platform loader is {layout.get('loader')!r}, expected "
            f"0x{platform_build.LOADER_AT:08x}"
        )
    if layout["base"] != RUNTIME_RESERVE[0] or layout["size"] != RUNTIME_RESERVE[1]:
        die(
            f"runtime reserve {layout['base']:#x}+{layout['size']:#x} does not "
            f"match platform {RUNTIME_RESERVE[0]:#x}+{RUNTIME_RESERVE[1]:#x}"
        )
    if layout["ceiling"] != layout["base"] + layout["size"]:
        die("platform layout ceiling is inconsistent with base+size")

    raw = raw_path.read_bytes()
    if layout["runtime_end"] - layout["base"] != len(raw):
        die(
            f"runtime.raw is {len(raw)} B but layout runtime span is "
            f"{layout['runtime_end'] - layout['base']} B"
        )

    # This repacker deliberately supports exactly the isolated Octabam runtime.
    # The first .long in table.inc is the normal payload count.
    match = re.search(r"^\s*\.long\s+(\d+)\s*$", table_path.read_text(), re.M)
    if not match or int(match.group(1)) != 1:
        die("normal platform loader must contain exactly one payload (octabam runtime)")

    packed = (
        pack.PACKED_MAGIC
        + len(raw).to_bytes(4, "big")
        + pack.pack(raw, platform_build.MAX_CANDIDATES)
    )
    runtime_payload = {
        "name": "octabam",
        "blob": platform_build.SIGNATURE + packed,
        "stage": layout["stage"] + platform_build.UNCACHED,
        "dst": layout["base"] + platform_build.UNCACHED,
        "rawlen": len(raw),
        "rhash": platform_build.roll(raw),
        "backup": 0,
    }
    if runtime_payload["blob"] != blob0_path.read_bytes():
        die("reconstructed octabam runtime payload differs from the normal loader blob0.bin")
    if layout["stage_end"] != layout["stage"] + len(runtime_payload["blob"]):
        die("platform layout stage_end disagrees with reconstructed runtime payload")
    return layout, raw, runtime_payload


def check_preboot_disjoint(layout: dict, pres: list[dict]) -> None:
    runtime_end = max(layout["runtime_end"], layout.get("bss_end", layout["runtime_end"]))
    occupied = (
        ("runtime/.bss", layout["base"], runtime_end),
        ("runtime stage", layout["stage"], layout["stage_end"]),
    )
    for entry in pres:
        for role, length in (("dst", entry["rawlen"]), ("stage", len(entry["blob"]))):
            start = _cached(entry[role])
            end = start + length
            if not RESERVE[0] <= start < end <= RESERVE[0] + RESERVE[1]:
                die(
                    f"{entry['name']} {role} {start:#x}..{end:#x} lies outside "
                    f"PERKY reserve {RESERVE[0]:#x}..{RESERVE[0] + RESERVE[1]:#x}"
                )
            for what, lo, hi in occupied:
                if _overlap(start, end, lo, hi):
                    die(
                        f"{entry['name']} {role} {start:#x}..{end:#x} overlaps "
                        f"{what} {lo:#x}..{hi:#x}"
                    )


def build(image_path: Path, table_dir: Path, output: Path,
          platform_dir: Path | None = None, work: Path | None = None) -> None:
    platform_dir = platform_dir or ROOT / "out/platform"
    work = work or ROOT / "out/platform-perky-machine"
    if not image_path.exists():
        die(f"missing {image_path}; run the normal perky-machine build first")

    stock_len = len(dsp_modmap.IMG.read_bytes())
    expected_stock_len = platform_build.LOADER_AT - BASE
    if stock_len != expected_stock_len:
        die(
            f"stock image is {stock_len} B but LOADER_AT implies "
            f"{expected_stock_len} B"
        )
    built = image_path.read_bytes()
    if len(built) <= stock_len:
        die(
            f"{image_path} has no platform-loader append; the full PERKY "
            "machine must contain DRAM-linked machine/control units"
        )

    prefix = bytearray(built[:stock_len])
    verify_reservation(prefix)
    layout, _runtime_raw, runtime_payload = load_runtime(platform_dir)

    boot_written = b"\x4e\xb9" + platform_build.LOADER_AT.to_bytes(4, "big")
    if image_slice(prefix, 0x4000050C, 6) != boot_written:
        die("normal full-machine build does not already route boot to Octabam loader")

    pres, pokes, log, table_layout = perky_image.integrate(prefix, table_dir)
    check_preboot_disjoint(layout, pres)
    for address, expect, write, note in pokes:
        apply_write(prefix, address, expect, write, note)

    append, symbols, boot, names = platform_build.build(
        [], [runtime_payload], work,
        preboot=pres,
        preboot_reserve=RESERVE,
    )
    if symbols:
        die("repacked loader unexpectedly produced linked runtime symbols")
    # Prefix already contains the normal build's loader jump. The replacement
    # loader lives at exactly the same address, so its requested write must be
    # byte-identical to what is already installed.
    if boot[0] != 0x4000050C or boot[2] != boot_written:
        die("replacement platform loader requested an unexpected boot hook")
    if image_slice(prefix, boot[0], len(boot[2])) != boot[2]:
        die("existing boot hook is not the replacement loader hook")

    final = bytes(prefix) + append
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(final)
    digest = hashlib.sha256(final).hexdigest()
    output.with_suffix(".remix").write_text(f"perky-machine-canary {digest}\n")

    print("=== PERKY full-machine shared loader ===")
    for line in log:
        print("  " + line)
    print(
        f"  preserved runtime: {runtime_payload['rawlen']:,} B at "
        f"0x{layout['base']:08x}; stage 0x{layout['stage']:08x}.."
        f"0x{layout['stage_end']:08x}"
    )
    print(f"  loader payloads: {', '.join(names)}")
    print(
        f"{output}: {len(final):,} bytes; "
        f"X:{perky_image.X_BASE:04x}+{table_layout['x_init']['words']}; "
        f"Y:{perky_image.Y_BASE:04x}.."
        f"{perky_image.Y_BASE + table_layout['total_words'] - 1:04x}"
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("table_dir", type=Path,
                    help="packed directory from build_noise_tone_payload.py")
    ap.add_argument("--image", type=Path, default=ROOT / "out/mainos_bus.bin")
    ap.add_argument("--platform", type=Path, default=ROOT / "out/platform")
    ap.add_argument("--work", type=Path, default=ROOT / "out/platform-perky-machine")
    ap.add_argument("--out", type=Path, default=ROOT / "out/mainos_perky_machine.bin")
    args = ap.parse_args()
    build(args.image, args.table_dir, args.out, args.platform, args.work)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Execute the shipping pk_render integration in a fake Octatrack address map.

This gate compiles control_cf_final.c and the exact production renderer sources,
loads the already hash-verified v1.2.1 assets as link-time symbols, and exercises
all four admitted OT tracks through both source segments around the event split.
On Apple Silicon it builds the fixture as x86_64 with a small PAGEZERO so the
32-bit Octatrack addresses are mappable under Rosetta, matching older CF gates.
"""
from __future__ import annotations

import argparse
import platform
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRODUCTION = ("cf_fold", "cf_karplus", "cf_noise_tone", "cf_perky4", "control_cf_final")
ASSETS = (
    ("pk_asset_pitch", "pitch.bin"),
    ("pk_asset_chromatic", "chromatic.bin"),
    ("pk_asset_envelope1", "envelope1.bin"),
    ("pk_asset_envelope2", "envelope2.bin"),
    ("pk_asset_m1_wave", "m1.bin"),
    ("pk_asset_wave0", "w0.bin"),
    ("pk_asset_wave1", "w1.bin"),
    ("pk_asset_wave2", "w2.bin"),
    ("pk_asset_wave3", "w3.bin"),
)


def run(cmd) -> None:
    print("+ " + " ".join(map(str, cmd)), flush=True)
    subprocess.run(list(map(str, cmd)), cwd=ROOT, check=True)


def write_assets(asset_dir: Path, out: Path) -> None:
    with out.open("w") as f:
        f.write("#include <stdint.h>\n")
        for symbol, filename in ASSETS:
            data = (asset_dir / filename).read_bytes()
            f.write(f"const uint8_t {symbol}[{len(data)}] = {{\n")
            for i in range(0, len(data), 16):
                f.write("  " + ",".join(f"0x{x:02x}" for x in data[i:i + 16]) + ",\n")
            f.write("};\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("asset_dir", type=Path)
    ap.add_argument("--work", type=Path, default=ROOT / "out/perky/cf-production-render")
    args = ap.parse_args()
    asset_dir = args.asset_dir.resolve()
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    for _, filename in ASSETS:
        if not (asset_dir / filename).is_file():
            raise SystemExit(f"missing final asset {asset_dir / filename}")

    arch: list[str] = []
    link: list[str] = []
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        arch = ["-arch", "x86_64"]
        link = ["-Wl,-pagezero_size,0x1000"]

    cflags = [*arch, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
              "-I", ROOT / "modules/perky"]
    objects: list[Path] = []
    for name in PRODUCTION:
        obj = work / f"{name}.o"
        run(["cc", *cflags, "-c", ROOT / "modules/perky" / f"{name}.c", "-o", obj])
        objects.append(obj)

    asset_c = work / "host_assets.c"
    asset_o = work / "host_assets.o"
    write_assets(asset_dir, asset_c)
    run(["cc", *cflags, "-c", asset_c, "-o", asset_o])
    objects.append(asset_o)

    exe = work / "perky_cf_production_render_diff"
    run([
        "c++", *arch, "-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror",
        "-I", ROOT / "modules/perky",
        ROOT / "tools/verify/perky_cf_production_render_diff.cpp",
        *objects, *link, "-o", exe,
    ])
    run([exe])

    # Measured stock packer slot: 336 bytes/track. The source callback owns
    # exactly the first 160 bytes and must leave the trailing 176 untouched.
    slot_exe = work / "perky_cf_stock_slot_diff"
    run([
        "c++", *arch, "-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror",
        "-I", ROOT / "modules/perky",
        ROOT / "tools/verify/perky_cf_stock_slot_diff.cpp",
        *objects, *link, "-o", slot_exe,
    ])
    run([slot_exe])


if __name__ == "__main__":
    main()

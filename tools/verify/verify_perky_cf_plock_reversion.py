#!/usr/bin/env python3
"""Verify one-trig Algo/Mode locks revert to staged track defaults on the next trig."""
from __future__ import annotations

import argparse
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRODUCTION = ("cf_fold", "cf_karplus", "cf_noise_tone", "cf_perky4", "cf_resonant", "cf_noise_hat", "cf_simple_drum", "cf_complex_drum", "cf_slap", "cf_wavetable", "control_cf_final")
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
    ("pk_asset_res_interp_a", "interp_a.bin"),
    ("pk_asset_res_interp_b", "interp_b.bin"),
    ("pk_asset_wt_base", "wt_base.bin"),
    ("pk_asset_wt_bank", "wt_bank.bin"),
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
        # The shipping control path decodes the two Wavetable PCM assets from one
        # PKR1 stream at boot, into .bss buffers.  Provide the exact stream and
        # the decode destinations so pk_final_decode_pcm runs the real path.
        sys.path.insert(0, str(ROOT / "tools/perky"))
        import pcm_rice  # noqa: E402
        stream = pcm_rice.encode([
            (asset_dir / "wt_base.bin").read_bytes(),
            (asset_dir / "wt_bank.bin").read_bytes(),
        ])
        f.write(f"const uint8_t pk_asset_pcm_rice[{len(stream)}] = {{\n")
        for i in range(0, len(stream), 16):
            f.write("  " + ",".join(f"0x{x:02x}" for x in stream[i:i + 16]) + ",\n")
        f.write("};\n")
        f.write("const uint8_t pk_asset_pcm_rice_end[] = {0};\n")
        f.write("uint8_t pk_pcm_wt_base[4096];\n")
        f.write("uint8_t pk_pcm_wt_bank[196608];\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("asset_dir", type=Path)
    ap.add_argument("--work", type=Path, default=ROOT / "out/perky/cf-plock-reversion")
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

    exe = work / "perky_cf_plock_reversion_diff"
    run([
        "c++", *arch, "-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror",
        "-I", ROOT / "modules/perky",
        ROOT / "tools/verify/perky_cf_plock_reversion_diff.cpp",
        *objects, *link, "-o", exe,
    ])
    run([exe])


if __name__ == "__main__":
    main()

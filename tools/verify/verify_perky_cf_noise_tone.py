#!/usr/bin/env python3
"""Bit-exact ColdFire-C vs PerkyBits native Noise/Tone differential gate.

Uses the user's exact PĒRKONS v1.2.1 firmware for the authentic envelope/wave
bytes and the user's private PerkyBits checkout as the C++ oracle. No network,
GitHub Actions or generated firmware bytes are committed.
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/perky"))
from extract_noise_tone_tables import ENVELOPE1_ADDR, ENVELOPE2_ADDR, find_m7, parse_container

FIRMWARE_SHA = "adcdbc4a2c660ffb6477f202211ae3cb70170bfe6ddfaecc3df0e4cb7db398c6"
OUT = ROOT / "out/perky/cf-noise-tone-diff"


def die(msg: str) -> "NoReturn":
    raise SystemExit("verify-perky-cf-noise-tone: " + msg)


def run(cmd: list[str]) -> None:
    print("+ " + " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--firmware", type=Path, default=Path(os.environ.get(
        "PERKONS_FIRMWARE", Path.home() / "Downloads/perkons_both_v1.2.1-0-gbcccfd0.img")))
    ap.add_argument("--source", type=Path, default=Path(os.environ.get(
        "PERKYBITS_ROOT", Path.home() / "Downloads/perkybits")))
    a = ap.parse_args()
    firmware = a.firmware.expanduser().resolve()
    source = a.source.expanduser().resolve()
    if not firmware.is_file(): die(f"missing firmware {firmware}")
    if not (source / "Source/NativeV121NoiseTone.cpp").is_file():
        die(f"not the expected PerkyBits checkout: {source}")
    raw = firmware.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    if sha != FIRMWARE_SHA:
        die(f"firmware sha256 {sha}, expected {FIRMWARE_SHA}")

    _product, segments = parse_container(raw)
    m7 = find_m7(segments)
    assets = OUT / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    rows = (
        ("envelope1.bin", ENVELOPE1_ADDR, 4096),
        ("envelope2.bin", ENVELOPE2_ADDR, 4096),
        ("m1.bin", 0x080310E0, 4096),
        ("w0.bin", 0x080222A0, 512),
        ("w1.bin", 0x080224A0, 512),
        ("w2.bin", 0x080226A0, 512),
        ("w3.bin", 0x080228A0, 512),
    )
    for name, address, size in rows:
        (assets / name).write_bytes(m7.read(address, size))

    cc = shutil.which("clang") or shutil.which("cc")
    cxx = shutil.which("clang++") or shutil.which("c++")
    if not cc or not cxx: die("clang/clang++ (or cc/c++) required")
    obj = OUT / "cf_noise_tone.o"
    exe = OUT / "cf_noise_tone_diff"
    run([cc, "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror",
         "-I", str(ROOT / "modules/perky"), "-c",
         str(ROOT / "modules/perky/cf_noise_tone.c"), "-o", str(obj)])
    run([cxx, "-std=c++20", "-O2",
         "-I", str(ROOT / "modules/perky"), "-I", str(source / "Source"),
         str(ROOT / "tools/verify/perky_cf_noise_tone_diff.cpp"),
         str(source / "Source/NativeV121NoiseTone.cpp"),
         str(source / "Source/NativeV121NoiseToneShared.cpp"),
         str(obj), "-o", str(exe)])
    run([str(exe), str(assets)])


if __name__ == "__main__":
    main()

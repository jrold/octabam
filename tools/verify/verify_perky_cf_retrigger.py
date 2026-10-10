#!/usr/bin/env python3
"""ColdFire retrigger gate: a second trigger while the voice is still sounding.

Every other gate renders from a *resting* voice. The engine fixtures also carry
an active-retrigger capture per family — state just before a second trigger,
state just after it, and the 256 samples that follow. Nothing compared those,
which is exactly where "the first hit sounds right and later hits sound wrong"
would live if it were a trigger bug.

Runs: post-retrigger state and post-retrigger PCM versus the firmware's own
captures, for Fold 1, Fold 2 and Karplus.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tools/perky"),
                str(ROOT / "modules/perky")]
from extract_noise_tone_tables import find_m7, parse_container  # noqa:E402

FIRMWARE_SHA256 = "adcdbc4a2c660ffb6477f202211ae3cb70170bfe6ddfaecc3df0e4cb7db398c6"
ENV1 = (0x08022EA0, 4096)
ENV2 = (0x080236A2, 4096)
ASSETS = ("pitch.bin", "chromatic.bin", "envelope1.bin", "envelope2.bin",
          "m1.bin", "w0.bin", "w1.bin", "w2.bin", "w3.bin",
          "interp_a.bin", "interp_b.bin")


def run(cmd: list) -> None:
    print("+ " + " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], cwd=ROOT, check=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--firmware", type=pathlib.Path,
                    default=pathlib.Path(os.environ.get("PERKONS_FIRMWARE", "")))
    ap.add_argument("--fixtures", type=pathlib.Path,
                    default=ROOT / "out/perky/engine-fixtures")
    ap.add_argument("--work", type=pathlib.Path,
                    default=ROOT / "out/perky/cf-retrigger")
    args = ap.parse_args()

    firmware = args.firmware.expanduser().resolve()
    fixtures = args.fixtures.expanduser().resolve()
    if not firmware.is_file():
        raise SystemExit("set PERKONS_FIRMWARE or pass --firmware with exact PĒRKONS v1.2.1")
    for engine, name in ((1, "Fold1"), (4, "Fold2"), (9, "Karplus")):
        if not (fixtures / f"engine-{engine}-mode-1-corner-1" /
                "wrapper-window-retrigger-before.bin").is_file():
            raise SystemExit(f"missing retrigger captures for engine {engine}")
    got = hashlib.sha256(firmware.read_bytes()).hexdigest()
    if got != FIRMWARE_SHA256:
        raise SystemExit(f"firmware hash drift: {got} != {FIRMWARE_SHA256}")

    work = args.work.resolve()
    assets = work / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    segment = find_m7(parse_container(firmware.read_bytes())[1])
    (assets / "envelope1.bin").write_bytes(segment.read(*ENV1))
    (assets / "envelope2.bin").write_bytes(segment.read(*ENV2))
    shared = ROOT / "out/perky/cf-final-verify/fixtures/assets"
    for name in ASSETS:
        if name.startswith("envelope"):
            continue
        src = shared / name
        if not src.is_file():
            raise SystemExit(f"missing shared asset {src}; run verify_perky_cf_final.py once")
        (assets / name).write_bytes(src.read_bytes())

    objects = []
    for name in ("cf_fold", "cf_karplus", "cf_noise_tone", "cf_perky4",
                 "cf_resonant", "cf_noise_hat", "cf_simple_drum", "cf_complex_drum",
                 "cf_slap", "cf_wavetable", "cf_acoustic_hats"):
        obj = work / f"{name}.o"
        run(["gcc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
             "-I", ROOT / "modules/perky",
             "-c", ROOT / "modules/perky" / f"{name}.c", "-o", obj])
        objects.append(obj)
    exe = work / "perky4_retrigger_diff"
    run(["g++", "-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror",
         "-I", ROOT / "modules/perky",
         ROOT / "tools/verify/perky4_retrigger_diff.cpp", *objects, "-o", exe])
    run([exe, fixtures, assets])
    print("PERKY CF retrigger: PASS (second-trigger state and PCM vs firmware captures)")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Prove every PERKY control actually does something, for every Algo and Mode.

The whole-machine gates prove the audio path runs; this gate proves the *sound*
responds to the panel. For each of Fold1 / Fold2 / Karplus / Noise-Tone and each
of their three Modes it sweeps all 128 Octatrack knob positions of
TUNE, DECAY, PARAM1 and PARAM2 through the real production renderer and requires
that at least one position changes the rendered PCM by >=5% of the loudest
sample. It also requires MODE to select a different render and the four Algos to
stay distinct.

This is the check for the class of bug that produced the dead-DECAY drone: with
obj+8 stuck at zero the amplitude envelope never released, so DECAY only changed
a state the engine never reached and every DECAY value rendered identical PCM.

No firmware is flashed; everything runs host-side against the produced image's
own ColdFire sources and the SHA-pinned PĒRKONS assets.
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
                str(ROOT / "tools/build"), str(ROOT / "modules/perky")]
import generate_cf_final_fixtures as fixtures  # noqa:E402
import perky_cf_assets  # noqa:E402
from extract_noise_tone_tables import find_m7, parse_container  # noqa:E402

# The resonant family's two 257-entry interpolation tables.
INTERP_A = (0x0803237C, 514)
INTERP_B = (0x08032178, 514)

PRODUCTION_C = ("cf_fold", "cf_karplus", "cf_noise_tone", "cf_perky4",
                "cf_resonant", "cf_noise_hat", "cf_simple_drum")


def run(cmd: list) -> None:
    print("+ " + " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], cwd=ROOT, check=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--firmware", type=pathlib.Path,
                    default=pathlib.Path(os.environ.get("PERKONS_FIRMWARE", "")))
    ap.add_argument("--work", type=pathlib.Path,
                    default=ROOT / "out/perky/param-coverage")
    args = ap.parse_args()

    firmware = args.firmware.expanduser().resolve()
    if not firmware.is_file():
        raise SystemExit("set PERKONS_FIRMWARE or pass --firmware with exact PĒRKONS v1.2.1")
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)

    # The asset unit is emitted from the SHA-pinned image; perky_cf_assets
    # verifies the full-image hash and every embedded table before writing.
    assets = work / "assets"
    fixtures.write_assets(firmware, work)
    segment = find_m7(parse_container(firmware.read_bytes())[1])
    (assets / "interp_a.bin").write_bytes(segment.read(*INTERP_A))
    (assets / "interp_b.bin").write_bytes(segment.read(*INTERP_B))
    if not (assets / "pitch.bin").is_file():
        raise SystemExit(f"asset extraction failed under {work}")
    print(f"PERKY parameter-coverage assets: PASS "
          f"({len(list(assets.glob('*.bin')))} tables from "
          f"{hashlib.sha256(firmware.read_bytes()).hexdigest()[:16]})")

    objects = []
    for name in PRODUCTION_C:
        obj = work / f"{name}.o"
        run(["gcc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
             "-I", ROOT / "modules/perky",
             "-c", ROOT / "modules/perky" / f"{name}.c", "-o", obj])
        objects.append(obj)

    exe = work / "perky4_param_sweep"
    run(["g++", "-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror",
         "-I", ROOT / "modules/perky",
         ROOT / "tools/verify/perky4_param_sweep.cpp", *objects, "-o", exe,
         "-lm"])

    csv = work / "param-sweep.csv"
    result = subprocess.run([str(exe), str(assets), str(csv)],
                            cwd=ROOT, text=True, capture_output=True)
    print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    if result.returncode:
        raise SystemExit("PERKY parameter coverage: FAIL "
                         "(a control, Mode or Algo is not audible)")
    print(f"PERKY parameter coverage: PASS  "
        f"(7 algos x 3 modes x 4 controls x 128 positions = "
        f"{7 * 3 * 4 * 128} rendered blocks)")
    print("  every TUNE / DECAY / PARAM1 / PARAM2 changes the PCM by >=5% of peak")
    print("  every MODE selects a different render; all seven Algos stay distinct")
    print(f"  full sweep table: {csv}")


if __name__ == "__main__":
    main()

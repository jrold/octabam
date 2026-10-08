#!/usr/bin/env python3
"""Executable final qualification for ColdFire-only Perky Machines.

This is the release gate for the four-algorithm milestone. It rebuilds the exact
firmware-derived fixtures, compiles the production freestanding C core, compares
its prepared states and PCM to PerkyBits native v1.2.1 references, stresses four
independent tracks with per-event Algo/Mode changes, verifies split-frame p-lock
timing and production runtime lifecycle, and gates the final all-stock-DSP
module declaration.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "tools/perky")]
import generate_cf_final_fixtures as fixtures  # noqa:E402
import perky_cf_assets  # noqa:E402

PRODUCTION_C = ("cf_fold", "cf_karplus", "cf_noise_tone", "cf_perky4")
NATIVE_CPP = (
    "NativeV121FoldDrums.cpp",
    "NativeV121Karplus.cpp",
    "NativeV121NoiseTone.cpp",
    "NativeV121NoiseToneShared.cpp",
)


def run(cmd, cwd=ROOT) -> None:
    print("+ " + " ".join(map(str, cmd)), flush=True)
    subprocess.run(list(map(str, cmd)), cwd=cwd, check=True)


def compile_cpp(name: str, work: Path, objects: list[Path], pb: Path,
                *, native: bool = False) -> Path:
    exe = work / name
    cmd = [
        "g++", "-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror",
        "-I", ROOT / "modules/perky",
    ]
    if native:
        cmd += ["-I", pb / "Source"]
    cmd += [ROOT / "tools/verify" / f"{name}.cpp"]
    if native:
        cmd += [pb / "Source" / x for x in NATIVE_CPP]
    cmd += objects + ["-o", exe]
    run(cmd)
    return exe


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--firmware", type=Path,
        default=Path(os.environ.get("PERKONS_FIRMWARE", "")),
    )
    ap.add_argument(
        "--perkybits", type=Path,
        default=Path(os.environ.get("PERKYBITS_ROOT", Path.home() / "Downloads/perkybits")),
    )
    ap.add_argument("--work", type=Path, default=ROOT / "out/perky/cf-final-verify")
    args = ap.parse_args()

    if not str(args.firmware) or not args.firmware.is_file():
        raise SystemExit("set PERKONS_FIRMWARE or pass --firmware with exact PĒRKONS v1.2.1")
    pb = args.perkybits.resolve()
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    if not (pb / "Source/NativeV121FoldDrums.cpp").is_file():
        raise SystemExit(f"not a PerkyBits checkout: {pb}")
    if not shutil.which("gcc") or not shutil.which("g++"):
        raise SystemExit("gcc/g++ required")

    # Pin exact production/test bytes before accepting historical PCM counts.
    run([sys.executable, ROOT / "tools/verify/verify_perky_cf_qualified_sources.py"])

    # Static/final-architecture gates first.
    run([sys.executable, ROOT / "tools/verify/verify_perky_cf_final_control.py"])
    run([sys.executable, ROOT / "tools/verify/verify_perky_cf_freestanding.py"])
    run([sys.executable, ROOT / "tools/verify/verify_perky_cf_machine_module.py"])
    run([sys.executable, ROOT / "tools/verify/verify_perky_cf_final_remix.py"])
    # Directly verifies full firmware hash + every embedded asset hash.
    os.environ["PERKONS_FIRMWARE"] = str(args.firmware.resolve())
    run([sys.executable, ROOT / "tools/perky/perky_cf_assets.py"])

    generated = fixtures.generate(args.firmware.resolve(), work / "fixtures")
    asset = generated["assets"]
    fdir = generated["fixture_dir"]

    # The actual callback must at least compile as strict freestanding C on host;
    # the release builder separately cross-compiles it with m68k-elf-gcc.
    run([
        "gcc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
        "-I", ROOT / "modules/perky", "-fsyntax-only",
        ROOT / "modules/perky/control_cf_final.c",
    ])

    objects: list[Path] = []
    for name in PRODUCTION_C:
        obj = work / f"{name}.o"
        run([
            "gcc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
            "-I", ROOT / "modules/perky", "-c", ROOT / "modules/perky" / f"{name}.c",
            "-o", obj,
        ])
        objects.append(obj)

    # Exhaustive production state preparation against recovered original ARM laws.
    exe = compile_cpp("perky4_state_diff", work, objects, pb)
    run([exe, fdir / "fold_karp_control_fixtures.bin", asset])
    exe = compile_cpp("perky4_nt_state_diff", work, objects, pb)
    run([exe, fdir / "nt_control_fixtures.bin", asset])

    # Dynamic four-track p-lock sequence, including Algo and Mode every event.
    exe = compile_cpp("perky4_sequence_diff", work, objects, pb)
    run([exe, fdir / "perky4_sequence.bin", asset])

    # This is the headline end-to-end PCM gate: production pk4_prepare_event ->
    # production renderer versus PerkyBits native renderer for every OT position.
    exe = compile_cpp("perky4_control_pcm_diff", work, objects, pb, native=True)
    run([exe, asset, fdir])

    # Mixed-algorithm four-track rendering and source-record round-trip.
    exe = compile_cpp("perky4_render_stress", work, objects, pb, native=True)
    run([exe, asset])

    # Exact stock-frame event split: old Algo/state before event, all six new
    # p-lock values become active only at/after the event boundary.
    exe = compile_cpp("perky_cf_split_plock_timing", work, objects, pb)
    run([exe, asset])

    # Execute the actual shipping pk_render callback against a fixed-address
    # Octatrack memory fixture. This proves staging, split timing, cursor/span
    # accounting and stock FLEX record bytes around every event offset.
    run([
        sys.executable, ROOT / "tools/verify/verify_perky_cf_production_render.py",
        asset, "--work", work / "production-render",
    ])

    # Runtime state is global to the ColdFire patch but must never leak across
    # Parts/Banks. Exercise the actual shipping callback through A0->A1->A0 and
    # Bank A->B and compare every first event to a freshly initialized oracle.
    run([
        sys.executable, ROOT / "tools/verify/verify_perky_cf_runtime_reset.py",
        asset, "--work", work / "runtime-reset",
    ])

    print("PERKY CF FINAL QUALIFICATION: PASS")
    print("  tracks=4 independent (Octatrack T1/T2/T5/T6)")
    print("  SRC=A Decay,B Tune,C Param1,D Param2,E Mode,F Algo; all p-lock sequence/split gates passed")
    print("  supported Algo=Fold1,Fold2,Karplus,NoiseTone(M1/M2/M3)")
    print("  production control->PCM=196608 exact samples per Algo (786432 total)")
    print("  production pk_render=1024 simultaneous four-voice frames / 4096 voice events / 65536 samples; all 4x4 voice/algo pairs and all 16 split offsets")
    print("  runtime reset=16 voice/algo cases across Part A0->A1->A0 and Bank A->B; exact cold PCM")
    print("  stock DSP module declaration=no DSP section/ranges/arena; stock source record transport exact")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Build/run the local PerkyBits v1.2.1 control probes and analyze their state.

This is an external-evidence driver, not a normal Octabam gate.  The user's
PĒRKONS firmware and PerkyBits checkout remain outside this repository; probe
JSONL and reports are written only under ignored ``out/perky``.

Examples::

    python3 tools/perky/capture_control_probe.py noise-tone --pairwise \
      --firmware ~/Downloads/perkons_both_v1.2.1-0-gbcccfd0.img \
      --source ~/Downloads/perkybits

    python3 tools/perky/capture_control_probe.py karplus --pairwise \
      --firmware ~/Downloads/perkons_both_v1.2.1-0-gbcccfd0.img \
      --source ~/Downloads/perkybits

Both current probes expect the private PerkyBits
``codex/octabam-karplus-control-probe`` work (or a descendant).  Noise/Tone v2
captures all three physical panel modes, including the separate Waveform2 M1
path; the historical shared-only probe remains untouched for reproducibility.
This tool never clones, fetches, pushes, invokes GitHub Actions, or writes
firmware bytes into Git.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT_ROOT = ROOT / "out/perky/control-probes"

FAMILIES = {
    "noise-tone": {
        "target": "perkybits-noise-tone-control-probe",
        "source_marker": "NoiseToneControlProbe.cpp",
        "analyzer": ROOT / "tools/re/noise_tone_control_analyze.py",
        "stem": "noise-tone-control",
    },
    "karplus": {
        "target": "perkybits-karplus-control-probe",
        "source_marker": "KarplusControlProbe.cpp",
        "analyzer": ROOT / "tools/re/karplus_control_analyze.py",
        "stem": "karplus-control",
    },
}


def die(message: str) -> "NoReturn":
    raise SystemExit("capture-control-probe: " + message)


def run(command: list[str], *, cwd: Path | None = None) -> None:
    print("+ " + " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd or ROOT, check=True)


def executable(build: Path, target: str) -> Path:
    """Find a CMake-built probe without assuming one generator layout."""
    names = (target, target + ".exe")
    candidates = [build / name for name in names]
    for config in ("Release", "RelWithDebInfo", "Debug"):
        candidates.extend(build / config / name for name in names)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    die(
        f"CMake reported success but {target!r} was not found under {build}; "
        "looked in root and common multi-config directories"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("family", choices=sorted(FAMILIES))
    parser.add_argument(
        "--firmware",
        type=Path,
        default=Path(os.environ.get(
            "PERKONS_FIRMWARE",
            Path.home() / "Downloads/perkons_both_v1.2.1-0-gbcccfd0.img",
        )),
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=Path(os.environ.get(
            "PERKYBITS_ROOT",
            Path.home() / "Downloads/perkybits",
        )),
        help="local PerkyBits checkout containing the requested smoke probe",
    )
    parser.add_argument(
        "--build-dir",
        type=Path,
        help="CMake build directory (default: out/perky/control-probes/<family>-build)",
    )
    parser.add_argument(
        "--pairwise",
        action="store_true",
        help="also capture pairwise control corners (recommended before shipping)",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="delete only this probe's CMake build directory before configuring",
    )
    args = parser.parse_args()

    spec = FAMILIES[args.family]
    firmware = args.firmware.expanduser().resolve()
    source = args.source.expanduser().resolve()
    smoke = source / "smoke"
    marker = smoke / str(spec["source_marker"])
    analyzer = Path(spec["analyzer"])

    if not firmware.is_file():
        die(f"missing external PĒRKONS v1.2.1 image: {firmware}")
    if not (source / "Source/PerkonsVoices.cpp").is_file():
        die(f"not a PerkyBits checkout: {source}")
    if not marker.is_file():
        die(
            f"{args.family} probe source missing: {marker}; check out the PerkyBits "
            "'codex/octabam-karplus-control-probe' work first"
        )
    if not analyzer.is_file():
        die(f"missing Octabam analyzer: {analyzer}")

    out = OUT_ROOT / args.family
    out.mkdir(parents=True, exist_ok=True)
    build = (
        args.build_dir.expanduser().resolve()
        if args.build_dir
        else (OUT_ROOT / f"{args.family}-build").resolve()
    )
    if args.clean and build.exists():
        shutil.rmtree(build)
    build.mkdir(parents=True, exist_ok=True)

    cmake = shutil.which("cmake")
    if not cmake:
        die("cmake is required to build the local PerkyBits probe")

    target = str(spec["target"])
    run([
        cmake,
        "-S", str(smoke),
        "-B", str(build),
        "-DCMAKE_BUILD_TYPE=Release",
    ])
    run([cmake, "--build", str(build), "--target", target, "-j"])
    probe = executable(build, target)

    jsonl = out / f"{spec['stem']}.jsonl"
    report = out / f"{spec['stem']}-analysis.json"
    command = [str(probe), str(firmware), str(jsonl)]
    if args.pairwise:
        command.append("--pairwise")
    run(command, cwd=source)

    run([
        sys.executable,
        str(analyzer),
        str(jsonl),
        "--json", str(report),
    ])

    manifest = {
        "schema": "octabam.perky.external-control-probe.v1",
        "family": args.family,
        "target": target,
        "probe_source": str(marker),
        "firmware_path": str(firmware),
        "perkybits_root": str(source),
        "pairwise": bool(args.pairwise),
        "jsonl": str(jsonl),
        "analysis": str(report),
        "shipping_qualification": False,
        "note": (
            "External original-v1.2.1 control evidence only; do not enable a "
            "shipping control path until an executable Octabam transport/update "
            "gate consumes and reproduces this evidence."
        ),
    }
    manifest_path = out / "capture.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    print("\nPERKY external control capture complete")
    print("  family  :", args.family)
    print("  raw     :", jsonl)
    print("  analysis:", report)
    print("  record  :", manifest_path)
    print("  status  : evidence captured; shipping control transport still gated")


if __name__ == "__main__":
    main()

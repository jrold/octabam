#!/usr/bin/env python3
"""Run the local evidence chain needed to finish Fold Drum 2.

This is a developer-side driver only. It does not use GitHub Actions or any
network service. It consumes the user's existing PĒRKONS v1.2.1 firmware,
PerkyBits source tree and Unicorn build, regenerates the original-ARM corpus,
derives/verifies the Fold2 trigger contract, executes that trigger law on the
DSP56300 host, then runs the existing Fold2 control/renderer gates.

Defaults intentionally match the known local checkout used for PerkyBits work:
  firmware: ~/Downloads/perkons_both_v1.2.1-0-gbcccfd0.img
  source:   ~/Downloads/perkybits

The Unicorn build is auto-discovered by locating the existing libunicorn.a
beside libarm-softmmu.a and libunicorn-common.a under the PerkyBits tree. No
download or dependency installation is attempted.
"""
from __future__ import annotations

from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FIRMWARE = Path.home() / "Downloads/perkons_both_v1.2.1-0-gbcccfd0.img"
DEFAULT_SOURCE = Path.home() / "Downloads/perkybits"
FIX = ROOT / "out/perky/engine-fixtures"


def run(argv: list[str], env=None) -> None:
    print("+ " + " ".join(argv), flush=True)
    subprocess.run(argv, check=True, cwd=ROOT, env=env)


def find_unicorn_build(source: Path) -> Path:
    explicit = os.environ.get("UNICORN_BUILD")
    if explicit:
        path = Path(explicit).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"UNICORN_BUILD does not exist: {path}")
        return path

    matches = []
    for lib in source.rglob("libunicorn.a"):
        parent = lib.parent
        if ((parent / "libarm-softmmu.a").exists()
                and (parent / "libunicorn-common.a").exists()
                and (parent.parent / "unicorn-src/include").exists()):
            matches.append(parent)
    if not matches:
        raise FileNotFoundError(
            "Could not find an existing Unicorn static build under PerkyBits. "
            "Pass --unicorn-build or set UNICORN_BUILD."
        )
    # Prefer the newest existing build when old benchmark/build directories are
    # both present. This is only path discovery; capture_engine_fixtures.py
    # still hashes all reference inputs into its manifest.
    return max(matches, key=lambda p: (p / "libunicorn.a").stat().st_mtime_ns)


def require(path: Path, description: str) -> Path:
    path = path.expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"{description} does not exist: {path}")
    return path


def prepare_assets(firmware: Path) -> None:
    """Extract the shared Fold tables from this invocation's firmware."""
    from extract_simple_drum_assets import extract

    state = (FIX / 'engine-3-mode-1-corner-1/wrapper-window-before.bin').read_bytes()
    state_path = ROOT / 'out/perky/hw4-simple-state.bin'
    state_path.write_bytes(state[0xc4:0xc4 + 0x120])
    extract(firmware, state_path, ROOT / 'out/perky/simple-drum-assets',
            extra_waves=(0x080222a0, 0x080224a0, 0x080226a0, 0x080228a0))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--firmware", type=Path,
                    default=Path(os.environ.get("PERKONS_FIRMWARE", DEFAULT_FIRMWARE)))
    ap.add_argument("--source", type=Path,
                    default=Path(os.environ.get("PERKYBITS_ROOT", DEFAULT_SOURCE)))
    ap.add_argument("--unicorn-build", type=Path)
    ap.add_argument(
        "--reuse-fixtures", action="store_true",
        help="do not recapture ARM fixtures; analyze the existing local corpus",
    )
    ap.add_argument(
        "--analysis-only", action="store_true",
        help="permit unresolved trigger rules for inspection; emit no usable plan",
    )
    args = ap.parse_args()

    source = require(args.source, "PerkyBits source tree")
    firmware = require(args.firmware, "PĒRKONS v1.2.1 firmware")
    unicorn = require(args.unicorn_build, "Unicorn build") \
        if args.unicorn_build else find_unicorn_build(source)

    if not (source / "Source/PerkonsVoices.cpp").exists():
        raise FileNotFoundError(
            f"not a PerkyBits checkout (missing Source/PerkonsVoices.cpp): {source}"
        )

    print(f"firmware:      {firmware}")
    print(f"PerkyBits:     {source}")
    print(f"Unicorn build: {unicorn}")
    print()

    if not args.reuse_fixtures:
        run([
            sys.executable, "tools/perky/capture_engine_fixtures.py",
            str(firmware), "--source", str(source),
            "--unicorn-build", str(unicorn), "--out", str(FIX),
        ])

    manifest = json.loads((FIX / 'manifest.json').read_text())
    if manifest['firmware_sha256'] != hashlib.sha256(firmware.read_bytes()).hexdigest():
        raise RuntimeError('ARM fixture firmware differs from the requested firmware')
    for name, digest in manifest['source_sha256'].items():
        path = ROOT / name if name.startswith('tools/') else source / name
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise RuntimeError(f'ARM fixture source has changed: {path}; recapture without --reuse-fixtures')
    for name, digest in manifest['files'].items():
        if hashlib.sha256((FIX / name).read_bytes()).hexdigest() != digest:
            raise RuntimeError(f'ARM fixture differs from its capture manifest: {name}')
    prepare_assets(firmware)

    run([sys.executable, "tools/verify/verify_perky_hw4_control_update.py", "--firmware", str(firmware)])

    run([
        sys.executable, "tools/perky/analyze_fold2_trigger.py",
        "--fixtures", str(FIX),
    ])

    contract_cmd = [
        sys.executable, "tools/verify/verify_perky_fold2_trigger_contract.py",
    ]
    if args.analysis_only:
        contract_cmd.append("--allow-unresolved")
    run(contract_cmd)

    if args.analysis_only:
        print(
            "\nAnalysis-only run complete. The previous trigger plan, if any, "
            "was invalidated before this corpus was checked. DSP trigger and "
            "renderer/control qualification are intentionally skipped."
        )
        return

    # The trigger law is first executed in isolation on the actual DSP56300
    # emulator. Only then continue into transport/control/render qualification.
    env = os.environ.copy()
    env["PERKYBITS_SOURCE"] = str(source / "Source")
    for gate in (
        "tools/verify/verify_perky_fold2_trigger_exec.py",
        "tools/verify/verify_perky_fold2_transport.py",
        "tools/verify/verify_perky_fold2_seam_exec.py",
        "tools/verify/verify_perky_fold2_compact.py",
        "tools/verify/verify_perky_fold2_synthetic_exec.py",
        "tools/verify/verify_perky_fold2_dsp_exec.py",
    ):
        run([sys.executable, gate], env=env)

    print(
        "\nFold Drum 2 evidence chain: PASS through original-ARM trigger contract, "
        "executable DSP trigger law, production transport/control seam, compact "
        "model and DSP renderer.\n"
        "This still does NOT claim browser/production trigger-seam integration "
        "or Octatrack hardware qualification; those remain separate gates."
    )


if __name__ == "__main__":
    main()

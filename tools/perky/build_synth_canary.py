#!/usr/bin/env python3
"""Build the first complete synthetic PERKY Noise/Tone firmware canary.

One command performs the whole development build without mutating tracked
source files:

1. fabricate clearly-labelled synthetic Noise/Tone source assets;
2. pack Y tables and the deterministic 236-word X initializer;
3. generate the complete synth-seam DSP source and enforce the 2724-word
   PLATE/SPRING/DARK donor budget with the real dsp_asm;
4. temporarily replace PERKY PROBE's DspSection.asm IN MEMORY only;
5. run Octabam's normal build_bus for REMIX=perky-synth;
6. restore the registry entry even if the build fails;
7. append the standard preboot loader with the extended A/B DSP uploads.

The resulting image is a DEVELOPMENT CANARY with synthetic wave/envelope/state
fixtures. It is not a claim of PĒRKONS sonic equivalence and this script does
not flash hardware.
"""
from __future__ import annotations

import argparse
import dataclasses
import os
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [
    str(ROOT / "tools"),
    str(ROOT / "tools/perky"),
    str(ROOT / "tools/build"),
]

import fabricate_noise_tone_fixtures as fabricate  # noqa:E402
import build_noise_tone_payload as payload_builder  # noqa:E402
import build_noise_tone_synth_source as source_builder  # noqa:E402
import build_perky_tables  # noqa:E402
from remix import registry  # noqa:E402


DEFAULT_OUT = ROOT / "out/perky/synth-canary"


def die(msg: str) -> "NoReturn":
    raise SystemExit("build-perky-synth: " + msg)


def repo_relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        die(f"generated DSP source {path} must live under the repository root")


def build(out: Path, final_image: Path) -> None:
    source_dir = out / "synthetic-source"
    packed_dir = out / "packed"
    dsp_source = out / "perky_synth.asm"

    out.mkdir(parents=True, exist_ok=True)
    fabricate.emit_tables(source_dir)
    layout = payload_builder.build(source_dir, packed_dir)
    if layout.get("synthetic") is not True:
        die("canary fixture unexpectedly lost synthetic provenance")

    source = source_builder.generate(packed_dir / "layout.json")
    dsp_source.write_text(source)
    pwords = source_builder.measure(source, dsp_source)
    print(
        f"PERKY synthetic synth: generated {pwords}/"
        f"{source_builder.FULL_DONOR_WORDS} P words "
        f"(FREE {source_builder.FULL_DONOR_WORDS - pwords})"
    )

    mods = registry.modules()
    key = "PERKY PROBE"
    if key not in mods:
        die(f"registry has no {key!r}")
    original = mods[key]
    if original.dsp is None:
        die("PERKY PROBE has no DspSection")
    if original.dsp.asm != "modules/perky/probe_glue.asm":
        die(
            f"default PERKY source is {original.dsp.asm!r}, not the impulse "
            "probe; refusing an ambiguous override"
        )
    patched_dsp = dataclasses.replace(original.dsp, asm=repo_relative(dsp_source))
    patched = dataclasses.replace(original, dsp=patched_dsp)

    old_remix = os.environ.get("REMIX")
    try:
        # registry.modules() returns the cached dictionary. Replacing this one
        # value means both registry.remix() and build_bus's imported accessor
        # see the generated source, while the manifest file remains untouched.
        mods[key] = patched
        os.environ["REMIX"] = "perky-synth"
        print("=== PERKY synthetic synth: normal Octabam build ===")
        runpy.run_path(str(ROOT / "tools/build/build_bus.py"), run_name="__main__")
    finally:
        mods[key] = original
        if old_remix is None:
            os.environ.pop("REMIX", None)
        else:
            os.environ["REMIX"] = old_remix

    stock_length = ROOT / "out/mainos_bus.bin"
    if not stock_length.exists():
        die("build_bus returned without out/mainos_bus.bin")

    print("=== PERKY synthetic synth: append X/Y preboot data ===")
    build_perky_tables.build(stock_length, packed_dir, final_image)
    print()
    print("PERKY SYNTH CANARY BUILT")
    print(f"  image: {final_image}")
    print(f"  DSP correctness source: {pwords} P words")
    print("  X init: 236 words at X:$3800")
    print("  Y tables: 1975 words at Y:$0795")
    print("  provenance: SYNTHETIC DEVELOPMENT FIXTURE")
    print("  hardware status: NOT YET QUALIFIED / NOT FLASHED BY THIS SCRIPT")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", type=Path, default=DEFAULT_OUT,
                    help="canary working directory")
    ap.add_argument("--out", type=Path,
                    default=ROOT / "out/mainos_perky_synth.bin",
                    help="final loader-appended canary image")
    args = ap.parse_args()
    build(args.work, args.out)


if __name__ == "__main__":
    main()

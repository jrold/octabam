#!/usr/bin/env python3
"""Build the first full PERKY Noise/Tone machine development image.

One command performs the complete development build without mutating tracked
module manifests or generated ColdFire source files:

1. fabricate clearly-labelled synthetic Noise/Tone assets;
2. pack the 236-word X initializer + packed Y tables;
3. generate/deduplicate/assemble the complete Noise/Tone DSP source;
4. compile authoritative control.c to ColdFire assembly under out/;
5. upgrade tracked PERKY PROBE to the full source-machine declaration IN MEMORY;
6. run normal Octabam build_bus for REMIX=perky-machine;
7. restore the registry entry even if the build fails;
8. rebuild the SAME platform loader with the existing runtime + PERKY A/B
   preboot DSP uploads;
9. write out/mainos_perky_machine.bin.

The image is a SYNTHETIC DEVELOPMENT CANARY. It exercises the real machine/UI
and DSP plumbing but is not yet a claim of PĒRKONS sonic equivalence. Nothing
in this script flashes hardware.
"""
from __future__ import annotations

import argparse
import importlib.util
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
import perky_machine_module  # noqa:E402
import repack_machine_loader  # noqa:E402
from remix import registry  # noqa:E402

DEFAULT_WORK = ROOT / "out/perky/machine-canary"
DEFAULT_IMAGE = ROOT / "out/mainos_perky_machine.bin"


def die(msg: str) -> "NoReturn":
    raise SystemExit("build-perky-machine: " + msg)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        die(f"cannot import {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def repo_relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        die(f"generated source {path} must live under the repository root")


def build(work: Path, final_image: Path) -> None:
    source_dir = work / "synthetic-source"
    packed_dir = work / "packed"
    dsp_source = work / "perky_synth.asm"
    control_source = work / "control.s"

    work.mkdir(parents=True, exist_ok=True)

    print("=== PERKY machine 1/5: synthetic qualification assets ===")
    fabricate.emit_tables(source_dir)
    layout = payload_builder.build(source_dir, packed_dir)
    if layout.get("synthetic") is not True:
        die("machine canary fixture unexpectedly lost synthetic provenance")
    if layout.get("total_words") != 1975:
        die(f"synthetic Y payload is {layout.get('total_words')} words, expected 1975")
    xi = layout.get("x_init", {})
    if xi.get("words") != 236 or xi.get("base_word") != 0x3800:
        die(f"synthetic X initializer geometry drifted: {xi!r}")

    print("=== PERKY machine 2/5: generate DSP + ColdFire sources ===")
    dsp_text = source_builder.generate(packed_dir / "layout.json")
    dsp_source.write_text(dsp_text)
    pwords = source_builder.measure(dsp_text, dsp_source)
    print(
        f"  DSP source: {pwords}/{source_builder.FULL_DONOR_WORDS} donor P words "
        f"(FREE {source_builder.FULL_DONOR_WORDS - pwords})"
    )

    control_gen = load_module(
        "perky_machine_control_generate",
        ROOT / "modules/perky/generate.py",
    )
    control_gen.write(control_source)
    if not control_source.exists() or control_source.stat().st_size == 0:
        die("ColdFire generator returned no control assembly")
    print(f"  ColdFire control: {control_source}")

    mods = registry.modules()
    key = "PERKY PROBE"
    if key not in mods:
        die(f"registry has no {key!r}")
    original = mods[key]
    full = perky_machine_module.build(
        original,
        control_source=repo_relative(control_source),
        dsp_source=repo_relative(dsp_source),
    )

    old_remix = os.environ.get("REMIX")
    print("=== PERKY machine 3/5: normal Octabam build ===")
    try:
        mods[key] = full
        os.environ["REMIX"] = "perky-machine"
        runpy.run_path(str(ROOT / "tools/build/build_bus.py"), run_name="__main__")
    finally:
        mods[key] = original
        if old_remix is None:
            os.environ.pop("REMIX", None)
        else:
            os.environ["REMIX"] = old_remix

    normal_image = ROOT / "out/mainos_bus.bin"
    platform_dir = ROOT / "out/platform"
    if not normal_image.exists():
        die("build_bus returned without out/mainos_bus.bin")
    for path in (platform_dir / "runtime.raw", platform_dir / "layout.json"):
        if not path.exists():
            die(f"full machine build returned without {path}")

    print("=== PERKY machine 4/5: combine runtime + DSP preboot uploads ===")
    repack_machine_loader.build(
        normal_image,
        packed_dir,
        final_image,
        platform_dir=platform_dir,
        work=ROOT / "out/platform-perky-machine",
    )

    print("=== PERKY machine 5/5: result ===")
    print("PERKY FULL MACHINE CANARY BUILT")
    print(f"  image: {final_image}")
    print(f"  DSP correctness source: {pwords} P words")
    print("  ColdFire: machine.s + generated control.c runtime")
    print("  source UI: TUNE / DECAY / ENV / MIX / MODE")
    print("  family: 011 NOISE/TONE (development milestone only)")
    print("  X init: 236 words at X:$3800")
    print("  Y tables: 1975 words at Y:$0795")
    print("  provenance: SYNTHETIC DEVELOPMENT FIXTURE")
    print("  hardware status: NOT YET QUALIFIED / NOT FLASHED BY THIS SCRIPT")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", type=Path, default=DEFAULT_WORK,
                    help="development work directory")
    ap.add_argument("--out", type=Path, default=DEFAULT_IMAGE,
                    help="final full-machine canary image")
    args = ap.parse_args()
    build(args.work, args.out)


if __name__ == "__main__":
    main()

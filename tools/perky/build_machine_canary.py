#!/usr/bin/env python3
"""Build the first hardware-testable PERKY Noise/Tone machine image.

This command deliberately stops at an AUDIBLE SYNTHETIC development milestone:
it does not claim PĒRKONS sonic equivalence, but it will not emit a flashable
image until the current DSP control mapper and complete packed voice have run
through the local DSP56300 emulator gates.

Pipeline:

0. execute the critical PERKY machine/control/audio preflight gates;
1. fabricate clearly-labelled synthetic Noise/Tone assets;
2. pack the 236-word X initializer + 1,975-word Y table payload;
3. generate/deduplicate/assemble the complete Noise/Tone DSP source;
4. compile authoritative control.c to ColdFire assembly under out/;
5. upgrade tracked PERKY PROBE to the full source-machine declaration IN MEMORY;
6. run normal Octabam build_bus for REMIX=perky-machine;
7. restore the registry entry even if the build fails;
8. rebuild the SAME platform loader with the existing runtime + PERKY A/B
   preboot DSP uploads;
9. wrap that patched MAIN OS into Elektron's ELEK container and emit both a
   card-flashable ELUP .bin and a MIDI .syx with an explicit PERKY version;
10. write a small test manifest with hashes/revision.

Nothing in this script flashes hardware.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import os
from pathlib import Path
import runpy
import subprocess
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
DEFAULT_MAINOS = ROOT / "out/mainos_perky_machine.bin"
STOCK_SYX = ROOT / "downloads/extracted/OCTATRACK_OS1.40C.syx"
EFT = ROOT / "vendor/elektron-firmware-tool/elektron-firmware-tool"
MAKE_BIN = ROOT / "tools/build/make_bin.py"

# These are intentionally narrower than a full `make check`: they are the
# blockers between this branch and a first audible hardware canary.
PREFLIGHTS = (
    ("full-machine declaration", ROOT / "tools/verify/verify_perky_machine_module.py"),
    ("five-control DSP mapper", ROOT / "tools/verify/verify_perky_control_mapper_exec.py"),
    ("complete packed X-state voice", ROOT / "tools/verify/verify_perky_voice_xstate_exec.py"),
    ("generated complete synth source", ROOT / "tools/verify/verify_perky_synth_source_exec.py"),
    ("control -> complete voice -> PCM", ROOT / "tools/verify/verify_perky_controlled_voice_exec.py"),
)


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


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def revision() -> str:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        return r.stdout.strip() or "unknown"
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def run_preflights() -> None:
    print("=== PERKY audible machine 0/6: DSP + machine preflight ===")
    for label, script in PREFLIGHTS:
        if not script.exists():
            die(f"missing preflight {script}")
        print(f"  -> {label}")
        try:
            subprocess.run(
                [sys.executable, str(script)],
                cwd=ROOT,
                check=True,
            )
        except subprocess.CalledProcessError as exc:
            die(f"preflight failed: {label} ({script}, exit {exc.returncode})")
    print("  audible preflight: PASS")


def firmware_paths(version: str) -> tuple[Path, Path, Path, Path]:
    elek = ROOT / "out" / f"elek_{version}.bin"
    card = ROOT / "out" / f"OCTATRACK_{version}.bin"
    midi = ROOT / "out" / f"OCTATRACK_OS1.40C_{version}.syx"
    manifest = ROOT / "out" / f"{version}_PERKY_TEST.txt"
    return elek, card, midi, manifest


def wrap_flashable(mainos: Path, version: str) -> tuple[Path, Path, Path]:
    if not mainos.exists():
        die(f"missing patched MAIN OS {mainos}")
    if not STOCK_SYX.exists():
        die(f"missing {STOCK_SYX}; run `make os` first")
    if not EFT.exists() or not os.access(EFT, os.X_OK):
        die(f"missing executable {EFT}; run `make setup` first")

    elek, card, midi, manifest = firmware_paths(version)
    env = os.environ.copy()
    env["EFT_EMIT_CONTAINER"] = str(elek)
    print("=== PERKY audible machine 5/6: card/MIDI firmware wrapper ===")
    subprocess.run(
        [
            str(EFT),
            "-i", str(STOCK_SYX),
            "-c", "3", str(mainos),
            "-V", version,
            "-o", str(midi),
        ],
        cwd=ROOT,
        env=env,
        check=True,
    )
    if not elek.exists() or elek.read_bytes()[:4] != b"ELEK":
        die(
            "elektron-firmware-tool did not emit the ELEK container; rerun "
            "`make setup` so the pinned EFT patch is installed"
        )
    subprocess.run(
        [sys.executable, str(MAKE_BIN), str(elek), "-o", str(card)],
        cwd=ROOT,
        check=True,
    )
    if not card.exists() or not midi.exists():
        die("firmware wrapper returned without both card and MIDI images")
    return card, midi, manifest


def build(work: Path, mainos: Path, *, build_number: int, version: str) -> None:
    run_preflights()

    source_dir = work / "synthetic-source"
    packed_dir = work / "packed"
    dsp_source = work / "perky_synth.asm"
    control_source = work / "control.s"
    work.mkdir(parents=True, exist_ok=True)

    print("=== PERKY audible machine 1/6: synthetic qualification assets ===")
    fabricate.emit_tables(source_dir)
    layout = payload_builder.build(source_dir, packed_dir)
    if layout.get("synthetic") is not True:
        die("machine canary fixture unexpectedly lost synthetic provenance")
    if layout.get("total_words") != 1975:
        die(f"synthetic Y payload is {layout.get('total_words')} words, expected 1975")
    xi = layout.get("x_init", {})
    if xi.get("words") != 236 or xi.get("base_word") != 0x3800:
        die(f"synthetic X initializer geometry drifted: {xi!r}")

    print("=== PERKY audible machine 2/6: generate DSP + ColdFire sources ===")
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
    old_build = os.environ.get("BUILD")
    print("=== PERKY audible machine 3/6: normal Octabam full-machine build ===")
    try:
        mods[key] = full
        os.environ["REMIX"] = "perky-machine"
        os.environ["BUILD"] = str(build_number)
        runpy.run_path(str(ROOT / "tools/build/build_bus.py"), run_name="__main__")
    finally:
        mods[key] = original
        if old_remix is None:
            os.environ.pop("REMIX", None)
        else:
            os.environ["REMIX"] = old_remix
        if old_build is None:
            os.environ.pop("BUILD", None)
        else:
            os.environ["BUILD"] = old_build

    normal_image = ROOT / "out/mainos_bus.bin"
    platform_dir = ROOT / "out/platform"
    if not normal_image.exists():
        die("build_bus returned without out/mainos_bus.bin")
    for path in (platform_dir / "runtime.raw", platform_dir / "layout.json"):
        if not path.exists():
            die(f"full machine build returned without {path}")

    print("=== PERKY audible machine 4/6: runtime + DSP preboot uploads ===")
    repack_machine_loader.build(
        normal_image,
        packed_dir,
        mainos,
        platform_dir=platform_dir,
        work=ROOT / "out/platform-perky-machine",
    )

    card, midi, manifest = wrap_flashable(mainos, version)
    manifest.write_text(
        "PERKY AUDIBLE SYNTHETIC HARDWARE CANARY\n"
        f"version={version}\n"
        f"build={build_number}\n"
        f"git={revision()}\n"
        f"mainos={mainos.name} sha256={sha256(mainos)}\n"
        f"card={card.name} sha256={sha256(card)}\n"
        f"midi={midi.name} sha256={sha256(midi)}\n"
        "engine=011 NOISE/TONE\n"
        "controls=TUNE,DECAY,ENV,MIX,MODE\n"
        "provenance=SYNTHETIC DEVELOPMENT FIXTURE (NOT real PERKONS control/table data)\n"
    )

    print("=== PERKY audible machine 6/6: READY FOR FIRST SOUND TEST ===")
    print(f"  card image : {card}")
    print(f"  MIDI image : {midi}")
    print(f"  patched OS : {mainos}")
    print(f"  test record: {manifest}")
    print(f"  version    : {version}")
    print(f"  DSP source : {pwords}/{source_builder.FULL_DONOR_WORDS} P words")
    print("  source UI  : TUNE / DECAY / ENV / MIX / MODE")
    print("  family     : 011 NOISE/TONE")
    print("  X init     : 236 words at X:$3800")
    print("  Y tables   : 1975 words at Y:$0795")
    print("  status     : SYNTHETIC AUDIBLE CANARY; hardware not yet qualified")
    print()
    print("Next: follow remixes/test/perky-machine/README.md for the CF-card sound test.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", type=Path, default=DEFAULT_WORK,
                    help="development work directory")
    ap.add_argument("--mainos", type=Path, default=DEFAULT_MAINOS,
                    help="intermediate patched MAIN OS payload")
    ap.add_argument("--build", type=int, default=1,
                    help="one/two-digit Octabam build number stamped into the build")
    ap.add_argument("--version", default=None,
                    help="OS version label (default PERKY<build>, max 10 chars)")
    args = ap.parse_args()

    if not 0 <= args.build <= 99:
        die("--build must be 0..99 (one or two decimal digits)")
    version = args.version or f"PERKY{args.build}"
    if not (1 <= len(version) <= 10 and version.isascii()
            and not any(ch.isspace() for ch in version)):
        die("--version must be 1..10 ASCII non-whitespace characters")

    build(args.work, args.mainos, build_number=args.build, version=version)


if __name__ == "__main__":
    main()

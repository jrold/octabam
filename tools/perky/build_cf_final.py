#!/usr/bin/env python3
"""Build the final four-track ColdFire-only Perky Machines firmware.

Release path:
  1. run the complete production control/PCM/p-lock qualification suite;
  2. cross-compile the freestanding ColdFire Perky sources;
  3. dynamically replace tracked PERKY PROBE with the ColdFire-only declaration;
  4. build the dedicated perky-cf-final remix containing every stock FX;
  5. prove the complete stock DSP bootstrap+payload span is byte-identical;
  6. wrap the resulting MAIN OS as card and MIDI firmware.

No GitHub Actions/CI are used. PĒRKONS firmware bytes are never tracked; the
DRAM asset unit is emitted at link time from PERKONS_FIRMWARE after full-image
and per-table SHA verification. The final p-lock/source-record transport is
covered by verify_perky_cf_final.py, so no saved OT project is required merely
to package this ColdFire-only architecture.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tools/perky"), str(ROOT / "tools/build")]
from remix import registry  # noqa:E402
import generate_cf_final  # noqa:E402
import perky_cf_assets  # noqa:E402
import perky_cf_machine_module  # noqa:E402
import build_machine_canary as wrapper  # noqa:E402

WORK = ROOT / "out/perky/cf-final"
STOCK_MAIN = ROOT / "out/raw/section_3_MAIN_OS.bin"
FINAL_MAIN = ROOT / "out/mainos_bus.bin"


def die(message: str) -> "NoReturn":
    raise SystemExit("build-perky-cf-final: " + message)


def run(cmd) -> None:
    print("+ " + " ".join(map(str, cmd)), flush=True)
    subprocess.run(list(map(str, cmd)), cwd=ROOT, check=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--firmware", type=Path,
        default=Path(os.environ.get("PERKONS_FIRMWARE", "")),
        help="exact perkons_both_v1.2.1-0-gbcccfd0.img",
    )
    ap.add_argument(
        "--perkybits", type=Path,
        default=Path(os.environ.get("PERKYBITS_ROOT", "")),
        help="PerkyBits checkout containing Source/NativeV121*.cpp",
    )
    ap.add_argument("--build", type=int, default=6)
    ap.add_argument("--version", default="PK4CF1")
    ap.add_argument("--work", type=Path, default=WORK)
    args = ap.parse_args()

    firmware = args.firmware.expanduser().resolve()
    perkybits = args.perkybits.expanduser().resolve()
    if not firmware.is_file():
        die("set PERKONS_FIRMWARE or pass --firmware with exact PĒRKONS v1.2.1")
    if not (perkybits / "Source/NativeV121FoldDrums.cpp").is_file():
        die("set PERKYBITS_ROOT or pass --perkybits with the PerkyBits checkout")
    if not shutil.which("m68k-elf-gcc"):
        die("m68k-elf-gcc is required for the final ColdFire build")

    # The include callback reads this exact path later while build_bus links the DRAM unit.
    os.environ["PERKONS_FIRMWARE"] = str(firmware)
    os.environ["PERKYBITS_ROOT"] = str(perkybits)
    args.work.mkdir(parents=True, exist_ok=True)

    print("=== PERKY CF final 1/6: executable production qualification ===")
    run([
        sys.executable, ROOT / "tools/verify/verify_perky_cf_final.py",
        "--firmware", firmware,
        "--perkybits", perkybits,
        "--work", args.work / "qualification",
    ])

    print("=== PERKY CF final 2/6: cross-compile freestanding ColdFire units ===")
    generated = args.work / "generated"
    generate_cf_final.generate(generated)
    generated_rel = wrapper.repo_relative(generated)

    # Force the asset verification once before entering the linker too; asset_inc
    # verifies again when the tracked cf_assets.s includes remix.inc.
    perky_cf_assets.extract(firmware)

    print("=== PERKY CF final 3/6: build all-stock-FX remix ===")
    mods = registry.modules()
    key = "PERKY PROBE"
    if key not in mods:
        die("tracked PERKY PROBE module is missing")
    original = mods[key]
    final = perky_cf_machine_module.build(original, generated_dir=generated_rel)
    old_remix, old_build = os.environ.get("REMIX"), os.environ.get("BUILD")
    try:
        mods[key] = final
        os.environ["REMIX"] = "perky-cf-final"
        os.environ["BUILD"] = str(args.build)
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

    if not FINAL_MAIN.is_file():
        die("build_bus did not produce out/mainos_bus.bin")
    if not STOCK_MAIN.is_file():
        die("decoded stock MAIN OS is missing after build_bus")

    print("=== PERKY CF final 4/6: prove stock DSP is byte-identical ===")
    run([
        sys.executable, ROOT / "tools/verify/verify_perky_stock_dsp_identity.py",
        STOCK_MAIN, FINAL_MAIN,
    ])

    print("=== PERKY CF final 5/6: card/MIDI firmware wrapper ===")
    card, midi, manifest = wrapper.wrap_flashable(FINAL_MAIN, args.version)

    print("=== PERKY CF final 6/6: release manifest ===")
    manifest.write_text(
        "PERKY MACHINES FINAL FOUR-ALGORITHM COLDFIRE BUILD\n"
        "tracks=T1,T2,T5,T6 independent\n"
        "src=A:Decay,B:Tune,C:Param1,D:Param2,E:Mode,F:Algo; all six p-lockable\n"
        "algos=Fold1,Fold2,Karplus,NoiseTone(M1/M2/M3)\n"
        "production_pcm=196608 exact samples per Algo; 786432 total\n"
        "four_track_stress=16384 trigs / 262144 exact samples; zero cross-track mutation\n"
        "split_plock=2304 transitions / 36864 samples; exact event-boundary application\n"
        "production_pk_render=4096 events / 65536 samples; all 4x4 voice/algo pairs and all 16 split offsets; 160-byte FLEX span exact\n"
        "stock_fx=all stock FX retained by remix; Perky module has zero DSP section/ranges/arena\n"
        "stock_dsp=156948 bootstrap/payload bytes required byte-identical by release gate\n"
        f"perkons_firmware_sha256={perky_cf_assets.FIRMWARE_SHA256}\n"
        f"mainos_sha256={wrapper.sha256(FINAL_MAIN)}\n"
        f"card_sha256={wrapper.sha256(card)}\n"
        f"midi_sha256={wrapper.sha256(midi)}\n"
    )
    print("PERKY CF FINAL BUILD: PASS")
    print("  card :", card)
    print("  MIDI :", midi)
    print("  notes:", manifest)


if __name__ == "__main__":
    main()

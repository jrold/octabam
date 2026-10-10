#!/usr/bin/env python3
"""Build the final four-track ColdFire-only Perky Machines firmware.

Release path:
  0. self-test the stock-DSP and wrapper corruption guards;
  1. run the complete production control/PCM/p-lock qualification suite;
  2. cross-compile the freestanding ColdFire Perky sources;
  3. audit generated ColdFire assembly/object linkage;
  4. dynamically replace tracked PERKY PROBE with the ColdFire-only declaration
     and build the dedicated perky-cf-final remix containing every stock FX;
  5. boot that exact built image in ot_emu with a real staged project/card and
     require the full PERKY + stock FLEX sequencer user path to pass;
  6. prove the complete stock DSP bootstrap+payload span is byte-identical;
  7. only now wrap the MAIN OS as card and MIDI firmware;
  8. round-trip both wrappers;
  9. write the release manifest.

No GitHub Actions/CI are used. PĒRKONS firmware bytes are never tracked; the
DRAM asset unit is emitted at link time from PERKONS_FIRMWARE after full-image
and per-table SHA verification. A flashable artifact is not emitted unless both
the bit/exact PCM qualification and the whole-machine emulator user-path gate
pass in this same build invocation.
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
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tools/perky"), str(ROOT / "tools/build"), str(ROOT / "modules/perky")]
from remix import registry, dsp_ranges  # noqa:E402
import generate_cf_final  # noqa:E402
import perky_cf_assets  # noqa:E402
import perky_cf_machine_module  # noqa:E402
import build_machine_canary as wrapper  # noqa:E402

WORK = ROOT / "out/perky/cf-final"
STOCK_MAIN = ROOT / "out/raw/section_3_MAIN_OS.bin"
FINAL_MAIN = ROOT / "out/mainos_bus.bin"
EMU = ROOT / "out/emu/ot_emu"
EMU_PY = ROOT / ".venv/bin/python3"
TOOLCHAIN = ("m68k-elf-gcc", "m68k-elf-as", "m68k-elf-ld", "m68k-elf-objcopy", "m68k-elf-nm")


def die(message: str) -> "NoReturn":
    raise SystemExit("build-perky-cf-final: " + message)


def run(cmd) -> None:
    print("+ " + " ".join(map(str, cmd)), flush=True)
    subprocess.run(list(map(str, cmd)), cwd=ROOT, check=True)


def toolchain_preflight() -> str:
    missing = [name for name in TOOLCHAIN if not shutil.which(name)]
    if missing:
        die("missing ColdFire toolchain: " + ", ".join(missing))
    version = subprocess.run(
        ["m68k-elf-gcc", "-dumpfullversion"], cwd=ROOT, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    machine = subprocess.run(
        ["m68k-elf-gcc", "-dumpmachine"], cwd=ROOT, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    if machine != "m68k-elf":
        die(f"m68k-elf-gcc reports unexpected target {machine!r}; expected 'm68k-elf'")
    probe = subprocess.run(
        [
            "m68k-elf-gcc", "-mcpu=54455", "-msoft-float", "-O2",
            "-ffreestanding", "-fno-builtin", "-x", "c", "-S", "-",
            "-o", os.devnull,
        ],
        cwd=ROOT, input="int perky_cf_toolchain_probe(void){return 0;}\n",
        text=True, capture_output=True,
    )
    if probe.returncode:
        die(
            "m68k-elf-gcc exists but cannot compile -mcpu=54455/-msoft-float: "
            + probe.stderr.strip()
        )
    print(f"PERKY CF toolchain preflight: PASS (m68k-elf-gcc {version}; target={machine}; ColdFire 54455)")
    return version


def source_git_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def require_dsp_pristine_release(final, selected) -> None:
    """Prove the final CF-only remix may leave stock's DSP mailbox operands stock.

    General Octabam DSP remixes relocate the stock core mailbox from 0x38000 to
    0x37f00 and widen payload B's boot clear around it (six P-word operands in
    dsp_ranges.STOCK_PATCHES). Perky CF owns no DSP state/code/bus at all, so
    applying those historical remap pokes would violate the final requirement
    that the complete stock DSP bootstrap/payload remain byte-identical.
    """
    claims = final.claims
    final_dirty = (
        final.dsp is not None
        or final.arena is not None
        or claims is None
        or bool(claims.dsp_ranges)
        or bool(claims.reserved_private_y)
        or bool(claims.owns_fx2_buffers)
        or dsp_ranges.bus_member(final)
    )
    selected_dirty = any(
        m.dsp is not None
        or dsp_ranges.bus_member(m)
        or (m.claims is not None and (
            m.claims.dsp_ranges
            or m.claims.reserved_private_y
            or m.claims.owns_fx2_buffers
        ))
        for m in selected
        if not m.is_stock
    )
    if final_dirty or selected_dirty:
        die(
            "perky-cf-final is no longer DSP-pristine; refusing to suppress "
            "Octabam's historical DSP mailbox relocation"
        )


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
        help="PerkyBits checkout containing Source/NativeV121FoldDrums.cpp",
    )
    ap.add_argument(
        "--project", type=Path,
        default=Path(os.environ.get("OT_PROJECT", "")),
        help="real Octatrack project used only as the owned base for the emulator gate",
    )
    ap.add_argument("--build", type=int, default=6)
    ap.add_argument("--version", default="PK4CF1")
    ap.add_argument("--work", type=Path, default=WORK)
    args = ap.parse_args()

    firmware = args.firmware.expanduser().resolve()
    perkybits = args.perkybits.expanduser().resolve()
    project = args.project.expanduser().resolve()
    if not firmware.is_file():
        die("set PERKONS_FIRMWARE or pass --firmware with exact PĒRKONS v1.2.1")
    if not (perkybits / "Source/NativeV121FoldDrums.cpp").is_file():
        die("set PERKYBITS_ROOT or pass --perkybits with the PerkyBits checkout")
    if not (project / "project.work").is_file():
        die("set OT_PROJECT or pass --project with a real Octatrack project")
    if not EMU.is_file():
        die(f"missing {EMU}; run `make emu-cf` before building flashable PERKY firmware")
    if not EMU_PY.is_file():
        die(f"missing {EMU_PY}; run `make emu-setup` before building flashable PERKY firmware")

    args.work.mkdir(parents=True, exist_ok=True)
    print("=== PERKY CF final preflight: release guards corruption self-test ===")
    run([sys.executable, ROOT / "tools/verify/verify_perky_release_guards_selftest.py"])

    toolchain_version = toolchain_preflight()
    source_commit = source_git_commit()

    # The include callback reads this exact path later while build_bus links the DRAM unit.
    os.environ["PERKONS_FIRMWARE"] = str(firmware)
    os.environ["PERKYBITS_ROOT"] = str(perkybits)

    print("=== PERKY CF final 1/9: executable bit/exact PCM + control qualification ===")
    run([
        sys.executable, ROOT / "tools/verify/verify_perky_cf_final.py",
        "--firmware", firmware,
        "--perkybits", perkybits,
        "--work", args.work / "qualification",
    ])

    print("=== PERKY CF final 2/9: cross-compile freestanding ColdFire units ===")
    generated = args.work / "generated"
    generate_cf_final.generate(generated)
    generated_rel = wrapper.repo_relative(generated)

    print("=== PERKY CF final 3/9: audit generated ColdFire code/linkage ===")
    run([
        sys.executable, ROOT / "tools/verify/verify_perky_cf_codegen.py",
        generated,
    ])

    print("=== PERKY CF final 3c/9: voice silo (T1..T4 family map) ===")
    run([
        sys.executable, ROOT / "tools/verify/verify_perky_cf_voice_silo.py",
    ])

    print("=== PERKY CF final 3b/9: odd-address word/long audit ===")
    run([
        sys.executable, ROOT / "tools/verify/verify_perky_cf_odd_access.py",
        "--generated", generated,
    ])

    # Force the asset verification once before entering the linker too; asset_inc
    # verifies again when the tracked cf_assets.s includes remix.inc.
    perky_cf_assets.extract(firmware)

    print("=== PERKY CF final 4/9: build all-stock-FX remix ===")
    mods = registry.modules()
    key = "PERKY PROBE"
    if key not in mods:
        die("tracked PERKY PROBE module is missing")
    original = mods[key]
    final = perky_cf_machine_module.build(original, generated_dir=generated_rel)
    old_remix, old_build = os.environ.get("REMIX"), os.environ.get("BUILD")
    saved_stock_patches = dsp_ranges.STOCK_PATCHES
    try:
        mods[key] = final
        os.environ["REMIX"] = "perky-cf-final"
        os.environ["BUILD"] = str(args.build)
        selected_remix = registry.remix("perky-cf-final")
        selected = [mods[k] for k in selected_remix.modules]
        require_dsp_pristine_release(final, selected)
        # Final Perky is deliberately outside the DSP. Do not apply Octabam's
        # six legacy DSP mailbox/boot remap operands to an otherwise stock DSP
        # image; stage 6 below proves the entire span remains byte-identical.
        dsp_ranges.STOCK_PATCHES = ()
        runpy.run_path(str(ROOT / "tools/build/build_bus.py"), run_name="__main__")
    finally:
        dsp_ranges.STOCK_PATCHES = saved_stock_patches
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

    print("=== PERKY CF final 5/9: whole-machine Octatrack emulator user path ===")
    run([
        sys.executable, ROOT / "tools/verify/verify_perky_cf_userpath.py",
        "--image", FINAL_MAIN,
        "--project", project,
        "--work", args.work / "userpath",
    ])

    print("=== PERKY CF final 5b/9: ColdFire real-time frame budget ===")
    run([
        sys.executable, ROOT / "tools/verify/verify_perky_cf_realtime_budget.py",
        "--image", FINAL_MAIN,
        "--project", project,
        "--work", args.work / "cf-budget",
    ])

    # The pre-written fixture above manufactures an already-PERKY Part, so it
    # cannot see a broken machine chooser/commit path. This gate starts T1 as
    # ordinary FLEX and drives the real stock panel to select PERKY, then
    # requires nonzero source audio: the check that caught the shipped bug.
    print("=== PERKY CF final 5c/9: real-panel machine selection ===")
    run([
        sys.executable, ROOT / "tools/verify/verify_perky_cf_ui_userpath.py",
        "--image", FINAL_MAIN,
        "--project", project,
        "--work", args.work / "ui-userpath",
    ])

    # The gates above only require NONZERO PERKY audio; they cannot see a build
    # that keeps every hit but degrades them one after another. This one drives
    # the real sequencer with the bench pattern (trigs 1/7/11) and fails if the
    # per-frame source record loses its pre-event half (the 9 Oct 2026
    # "first hit good, later hits thinner" bug) or if six hits stop being level.
    print("=== PERKY CF final 5g/9: Slap DSP parity ===")
    run([
        sys.executable, ROOT / "tools/verify/verify_perky_cf_slap_dsp.py",
    ])

    print("=== PERKY CF final 5f/9: Complex Drum DSP parity ===")
    run([
        sys.executable, ROOT / "tools/verify/verify_perky_cf_complex_drum_dsp.py",
    ])

    print("=== PERKY CF final 5e/9: Simple Drum DSP parity ===")
    run([
        sys.executable, ROOT / "tools/verify/verify_perky_cf_simple_drum_dsp.py",
    ])

    print("=== PERKY CF final 5d/9: sequencer hit-over-hit drift ===")
    run([
        sys.executable, ROOT / "tools/verify/verify_perky_cf_seq_drift.py",
        "--image", FINAL_MAIN,
        "--project", project,
        "--work", args.work / "seq-drift",
    ])

    print("=== PERKY CF final 6/9: prove stock DSP is byte-identical ===")
    run([
        sys.executable, ROOT / "tools/verify/verify_perky_stock_dsp_identity.py",
        STOCK_MAIN, FINAL_MAIN,
    ])

    print("=== PERKY CF final 7/9: card/MIDI firmware wrapper ===")
    card, midi, manifest = wrapper.wrap_flashable(FINAL_MAIN, args.version)
    elek = wrapper.firmware_paths(args.version)[0]

    print("=== PERKY CF final 8/9: round-trip card/MIDI wrappers ===")
    run([
        sys.executable, ROOT / "tools/verify/verify_perky_final_wrappers.py",
        "--mainos", FINAL_MAIN,
        "--elek", elek,
        "--card", card,
        "--midi", midi,
        "--eft", wrapper.EFT,
        "--version", args.version,
        "--work", args.work / "wrapper-verify",
    ])

    print("=== PERKY CF final 9/9: release manifest ===")
    manifest.write_text(
        "PERKY MACHINES FINAL COLDFIRE BUILD\n"
        "tracks=T1,T2,T3,T4 independent\n"
        "src=A:Tune,B:Decay,C:Algo,D:Prm1,E:Prm2,F:Mode; all six p-lockable\n"
        "algos=Fold1,Fold2,Karplus,NoiseTone(M1/M2/M3),ResonantDrums(M1/M2/M3),NoiseHat(M1/M2/M3)\n"
        "production_pcm=196608 exact samples per Algo; 786432 total\n"
        "four_track_stress=16384 trigs / 262144 exact samples; zero cross-track mutation\n"
        "production_pk_render=1024 simultaneous four-voice frames / 4096 voice events / 65536 exact samples\n"
        "fixed_slot_transport=two-segment source PCM committed to measured 336-byte stock track slot\n"
        "runtime_reset=16 voice/algo cases across Part A0->A1->A0 and Bank A->B; exact cold PCM\n"
        "split_plock=2304 transitions / 36864 samples; exact event-boundary application\n"
        "emulator_user_path=real project load + sequencer + T1/T2/T3/T4 PERKY + T3/T7 stock FLEX required PASS\n"
        "stock_fx=all stock FX retained by remix; Perky module has zero DSP section/ranges/arena\n"
        "stock_dsp=156948 bootstrap/payload bytes required byte-identical by release gate\n"
        "wrapper_roundtrip=card ELUP -> emitted ELEK exact; MIDI section 3 -> final MAIN OS exact\n"
        f"source_git_commit={source_commit}\n"
        f"m68k_elf_gcc_version={toolchain_version}\n"
        f"qualification_manifest_sha256={wrapper.sha256(ROOT / 'tools/verify/verify_perky_cf_qualified_sources.py')}\n"
        f"perkons_firmware_sha256={perky_cf_assets.FIRMWARE_SHA256}\n"
        f"mainos_sha256={wrapper.sha256(FINAL_MAIN)}\n"
        f"card_sha256={wrapper.sha256(card)}\n"
        f"midi_sha256={wrapper.sha256(midi)}\n"
    )
    print("PERKY CF FINAL BUILD: PASS")
    print("  PCM qualification : PASS")
    print("  emulator user path: PASS")
    print("  card :", card)
    print("  MIDI :", midi)
    print("  notes:", manifest)


if __name__ == "__main__":
    main()

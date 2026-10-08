#!/usr/bin/env python3
"""Guarded entry point for the final Perky Machines ColdFire release.

This wrapper intentionally does not replace build_cf_final.py. It verifies the
byte-pinned qualified source set, validates the automatic platform DRAM reserve
and deterministic runtime memory/init contract, validates the ColdFire toolchain,
generates and audits the exact assembly once, then invokes the qualified final
builder. After the builder returns it proves both the stock DSP payload bytes
and the ColdFire DSP uploader/boot path remain stock-identical, then audits the
regenerated assembly again.
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
TOOLCHAIN = ("m68k-elf-gcc", "m68k-elf-as", "m68k-elf-ld", "m68k-elf-objcopy", "m68k-elf-nm")
STOCK_MAIN = ROOT / "out/raw/section_3_MAIN_OS.bin"
FINAL_MAIN = ROOT / "out/mainos_bus.bin"


def die(msg: str) -> "NoReturn":
    raise SystemExit("release-perky-cf-final: " + msg)


def run(cmd, *, env=None) -> None:
    print("+ " + " ".join(map(str, cmd)), flush=True)
    subprocess.run(list(map(str, cmd)), cwd=ROOT, env=env, check=True)


def toolchain_preflight() -> str:
    missing = [name for name in TOOLCHAIN if not shutil.which(name)]
    if missing:
        die(
            "missing ColdFire toolchain: " + ", ".join(missing)
            + " (Homebrew: brew install m68k-elf-gcc m68k-elf-binutils)"
        )
    p = subprocess.run(
        ["m68k-elf-gcc", "-dumpfullversion"], cwd=ROOT,
        check=True, capture_output=True, text=True,
    )
    version = p.stdout.strip()
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
        die("m68k-elf-gcc cannot target MCF54455: " + probe.stderr.strip())
    print(f"PERKY CF toolchain: PASS (m68k-elf-gcc {version}; -mcpu=54455 -msoft-float)")
    return version


def hashes(directory: Path) -> dict[str, str]:
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.glob("pk*.s"))
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--firmware", type=Path, required=True)
    ap.add_argument("--perkybits", type=Path, required=True)
    ap.add_argument("--build", type=int, default=6)
    ap.add_argument("--version", default="PK4CF1")
    ap.add_argument("--work", type=Path, default=ROOT / "out/perky/cf-final")
    ap.add_argument("--preflight-only", action="store_true")
    args = ap.parse_args()

    firmware = args.firmware.expanduser().resolve()
    perkybits = args.perkybits.expanduser().resolve()
    work = args.work.expanduser().resolve()
    if not firmware.is_file():
        die(f"firmware not found: {firmware}")
    if not (perkybits / "Source/NativeV121FoldDrums.cpp").is_file():
        die(f"not a PerkyBits checkout: {perkybits}")

    run([sys.executable, ROOT / "tools/verify/verify_perky_cf_qualified_sources.py"])
    run([sys.executable, ROOT / "tools/verify/verify_perky_cf_platform_reserve.py"])
    run([sys.executable, ROOT / "tools/verify/verify_perky_cf_runtime_memory_final.py"])
    toolchain_preflight()

    env = os.environ.copy()
    env["PERKONS_FIRMWARE"] = str(firmware)
    env["PERKYBITS_ROOT"] = str(perkybits)
    generated = work / "generated"
    run([sys.executable, ROOT / "modules/perky/generate_cf_final.py", "--out", generated], env=env)
    run([sys.executable, ROOT / "tools/verify/verify_perky_cf_codegen.py", generated], env=env)
    before = hashes(generated)
    if not before:
        die("generator produced no pk*.s units")

    if args.preflight_only:
        print("PERKY CF GUARDED PREFLIGHT: PASS")
        return

    run([
        sys.executable, ROOT / "tools/perky/build_cf_final.py",
        "--firmware", firmware,
        "--perkybits", perkybits,
        "--build", str(args.build),
        "--version", args.version,
        "--work", work,
    ], env=env)

    if not STOCK_MAIN.is_file() or not FINAL_MAIN.is_file():
        die("final builder did not leave stock/candidate MAIN OS images for release proof")
    run([sys.executable, ROOT / "tools/verify/verify_perky_stock_dsp_identity.py", STOCK_MAIN, FINAL_MAIN], env=env)
    run([sys.executable, ROOT / "tools/verify/verify_perky_stock_dsp_boot_path.py", STOCK_MAIN, FINAL_MAIN], env=env)

    after = hashes(generated)
    if before != after:
        changed = sorted(set(before) | set(after))
        details = [name for name in changed if before.get(name) != after.get(name)]
        die("generated assembly changed between preflight and final builder: " + ", ".join(details))
    run([sys.executable, ROOT / "tools/verify/verify_perky_cf_codegen.py", generated], env=env)
    print("PERKY CF GUARDED RELEASE: PASS")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Build and export the exact bytes/dependencies needed for remote ot_emu qualification.

This is NOT a release builder and it never emits/labels flashable firmware as
qualified. It exists only for environments that can inspect GitHub but cannot
clone Octabam's ignored third-party emulator/toolchain dependencies.

On the already-provisioned Octabam Mac it:
  1. runs the normal production PCM qualification and ColdFire image build;
  2. deliberately stops immediately before the normal whole-machine ot_emu gate;
  3. verifies the resulting MAIN image still has stock DSP bytes;
  4. packages that exact MAIN image, stock MAIN image, generated ColdFire
     assembly, the real Octatrack project files, and the pinned/apply-patched
     mc68k + dsp56300 source trees (including asmjit).

The receiving environment can then build its own native ot_emu and conduct all
whole-machine tests against the exact MAIN bytes produced here. No GitHub
Actions/CI are involved.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/perky"))
import build_cf_final as base  # noqa:E402


class ExportBoundary(RuntimeError):
    pass


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def add_tree(z: zipfile.ZipFile, source: Path, prefix: str) -> int:
    """Add source tree, excluding VCS/build/cache output but keeping submodules."""
    count = 0
    excluded = {".git", "build", "__pycache__", ".DS_Store"}
    for path in sorted(source.rglob("*")):
        rel = path.relative_to(source)
        if any(part in excluded for part in rel.parts):
            continue
        if not path.is_file():
            continue
        z.write(path, f"{prefix}/{rel.as_posix()}")
        count += 1
    return count


def git_head(path: Path) -> str:
    r = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        capture_output=True, text=True,
    )
    return r.stdout.strip() if r.returncode == 0 else "unknown"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--firmware", type=Path,
        default=Path(os.environ.get(
            "PERKONS_FIRMWARE",
            Path.home() / "Downloads/perkons_both_v1.2.1-0-gbcccfd0.img",
        )),
    )
    ap.add_argument(
        "--perkybits", type=Path,
        default=Path(os.environ.get("PERKYBITS_ROOT", Path.home() / "Downloads/perkybits")),
    )
    ap.add_argument(
        "--project", type=Path,
        default=Path(os.environ.get(
            "OT_PROJECT", Path.home() / "Documents/octatrack backup/##Scratch"
        )),
    )
    ap.add_argument("--build", type=int, default=80)
    ap.add_argument("--version", default="PK4CF80")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    firmware = args.firmware.expanduser().resolve()
    perkybits = args.perkybits.expanduser().resolve()
    project = args.project.expanduser().resolve()
    if not firmware.is_file():
        raise SystemExit(f"PERKY handoff export: missing PĒRKONS firmware: {firmware}")
    if not (perkybits / "Source/NativeV121FoldDrums.cpp").is_file():
        raise SystemExit(f"PERKY handoff export: missing PerkyBits checkout: {perkybits}")
    if not (project / "project.work").is_file():
        raise SystemExit(f"PERKY handoff export: missing Octatrack project: {project}")

    for vendor in (ROOT / "vendor/mc68k", ROOT / "vendor/dsp56300"):
        if not vendor.is_dir():
            raise SystemExit(
                f"PERKY handoff export: missing {vendor}; run scripts/vendor.sh mc68k dsp56300"
            )
    if not (ROOT / "vendor/dsp56300/source/asmjit").is_dir():
        raise SystemExit("PERKY handoff export: dsp56300 asmjit submodule is missing")

    # Re-pin and re-apply Octabam's exact emulator dependency revisions first.
    subprocess.run(
        [str(ROOT / "scripts/vendor.sh"), "mc68k", "dsp56300"], cwd=ROOT, check=True
    )

    original_run = base.run
    original_emu = base.EMU
    original_emu_py = base.EMU_PY
    original_argv = sys.argv[:]

    # This helper intentionally stops before whole-machine emulation, so do not
    # make an already-built emulator a prerequisite for merely exporting bytes.
    base.EMU = Path(__file__).resolve()
    base.EMU_PY = Path(sys.executable).resolve()

    def export_run(cmd) -> None:
        values = list(map(str, cmd))
        if any(v.endswith("tools/verify/verify_perky_cf_userpath.py") for v in values):
            print("=== PERKY handoff export: production MAIN complete; stop before ot_emu ===")
            raise ExportBoundary()
        original_run(cmd)

    base.run = export_run
    sys.argv = [
        str(ROOT / "tools/perky/build_cf_final.py"),
        "--firmware", str(firmware),
        "--perkybits", str(perkybits),
        "--project", str(project),
        "--build", str(args.build),
        "--version", args.version,
    ]
    try:
        try:
            base.main()
        except ExportBoundary:
            pass
    finally:
        base.run = original_run
        base.EMU = original_emu
        base.EMU_PY = original_emu_py
        sys.argv = original_argv

    final_main = ROOT / "out/mainos_bus.bin"
    stock_main = ROOT / "out/raw/section_3_MAIN_OS.bin"
    generated = ROOT / "out/perky/cf-final/generated"
    if not final_main.is_file():
        raise SystemExit("PERKY handoff export: production builder did not create out/mainos_bus.bin")
    if not stock_main.is_file():
        raise SystemExit("PERKY handoff export: missing stock decoded MAIN image")
    if not generated.is_dir():
        raise SystemExit("PERKY handoff export: missing generated ColdFire units")

    # Stage 6 normally runs after the emulator gate. It is safe and useful to
    # run it here before moving the bytes to another host.
    original_run([
        sys.executable,
        ROOT / "tools/verify/verify_perky_stock_dsp_identity.py",
        stock_main,
        final_main,
    ])

    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT,
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    name = args.out or (ROOT / "out" / f"PERKY_EMULATOR_HANDOFF_{commit[:8]}.zip")
    name = name.expanduser().resolve()
    name.parent.mkdir(parents=True, exist_ok=True)
    if name.exists():
        name.unlink()

    project_files = sorted(
        p for p in project.iterdir()
        if p.is_file() and p.suffix.lower() in (".work", ".strd")
    )
    if not project_files:
        raise SystemExit("PERKY handoff export: no .work/.strd project files found")

    meta = {
        "purpose": "unqualified emulator handoff; NOT hardware firmware",
        "source_git_commit": commit,
        "branch": "perky-machines",
        "version": args.version,
        "build": args.build,
        "mainos_sha256": sha256(final_main),
        "stock_main_sha256": sha256(stock_main),
        "perkons_firmware_sha256": sha256(firmware),
        "mc68k_head": git_head(ROOT / "vendor/mc68k"),
        "dsp56300_head": git_head(ROOT / "vendor/dsp56300"),
        "project_file_count": len(project_files),
    }

    with zipfile.ZipFile(name, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        z.writestr("HANDOFF.json", json.dumps(meta, indent=2, sort_keys=True) + "\n")
        z.write(final_main, "image/mainos_bus.bin")
        z.write(stock_main, "image/section_3_MAIN_OS.bin")
        for p in project_files:
            z.write(p, f"project/{p.name}")
        add_tree(z, generated, "generated")
        mc_count = add_tree(z, ROOT / "vendor/mc68k", "vendor/mc68k")
        dsp_count = add_tree(z, ROOT / "vendor/dsp56300", "vendor/dsp56300")

    print("PERKY EMULATOR HANDOFF EXPORT: PASS")
    print(f"  source commit : {commit}")
    print(f"  MAIN sha256   : {meta['mainos_sha256']}")
    print(f"  mc68k files   : {mc_count}")
    print(f"  dsp56300 files: {dsp_count}")
    print(f"  project files : {len(project_files)}")
    print(f"  bundle        : {name}")
    print("  NOTE: bundle is intentionally unqualified for hardware until ot_emu gates pass")


if __name__ == "__main__":
    main()

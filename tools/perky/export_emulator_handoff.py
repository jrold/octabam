#!/usr/bin/env python3
"""Export the exact local bytes/dependencies needed for remote ot_emu qualification.

This is NOT a release builder and does not ask the operator to run the emulator
or repeat the long PCM differential. It exists only because some execution
sandboxes cannot clone Octabam's ignored third-party emulator dependencies or
run the macOS m68k cross-toolchain.

On the already-provisioned Octabam Mac it:
  1. verifies the production source files are the exact byte-pinned set that
     already passed the PerkyBits PCM qualification;
  2. cross-compiles/links the current ColdFire PERKY MAIN image;
  3. verifies the complete stock DSP bootstrap/payload remains byte-identical;
  4. packages that exact MAIN image, stock MAIN image, generated ColdFire
     assembly, real Octatrack project files, and the pinned/apply-patched
     mc68k + dsp56300 source trees (including asmjit).

The receiving environment then builds its own native ot_emu and performs the
whole-machine four-voice and real-panel user-path tests. No GitHub Actions/CI
are involved, and this exporter never creates a flashable card/MIDI wrapper.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [
    str(ROOT / "tools"),
    str(ROOT / "tools/perky"),
    str(ROOT / "tools/build"),
    str(ROOT / "modules/perky"),
]
import build_cf_final as base  # noqa:E402


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
    project = args.project.expanduser().resolve()
    if not firmware.is_file():
        raise SystemExit(f"PERKY handoff export: missing PĒRKONS firmware: {firmware}")
    if not (project / "project.work").is_file():
        raise SystemExit(f"PERKY handoff export: missing Octatrack project: {project}")

    for vendor in (ROOT / "vendor/mc68k", ROOT / "vendor/dsp56300"):
        if not vendor.is_dir():
            raise SystemExit(
                f"PERKY handoff export: missing {vendor}; run scripts/vendor.sh mc68k dsp56300"
            )
    if not (ROOT / "vendor/dsp56300/source/asmjit").is_dir():
        raise SystemExit("PERKY handoff export: dsp56300 asmjit submodule is missing")

    # Re-pin/re-apply Octabam's exact emulator dependency revisions first.
    subprocess.run(
        [str(ROOT / "scripts/vendor.sh"), "mc68k", "dsp56300"], cwd=ROOT, check=True
    )

    if not base.STOCK_MAIN.is_file():
        raise SystemExit(
            "PERKY handoff export: missing out/raw/section_3_MAIN_OS.bin; run make recon"
        )

    print("=== PERKY handoff 1/6: verify PCM-qualified source identity ===")
    base.run([sys.executable, ROOT / "tools/verify/verify_perky_cf_qualified_sources.py"])

    print("=== PERKY handoff 2/6: ColdFire toolchain preflight ===")
    toolchain_version = base.toolchain_preflight()
    os.environ["PERKONS_FIRMWARE"] = str(firmware)

    work = ROOT / "out/perky/cf-final"
    generated = work / "generated"
    work.mkdir(parents=True, exist_ok=True)

    print("=== PERKY handoff 3/6: generate/audit ColdFire units ===")
    base.generate_cf_final.generate(generated)
    generated_rel = base.wrapper.repo_relative(generated)
    base.run([
        sys.executable, ROOT / "tools/verify/verify_perky_cf_codegen.py", generated,
    ])
    base.perky_cf_assets.extract(firmware)

    print("=== PERKY handoff 4/6: build exact all-stock-FX MAIN image ===")
    mods = base.registry.modules()
    key = "PERKY PROBE"
    if key not in mods:
        raise SystemExit("PERKY handoff export: tracked PERKY PROBE module is missing")
    original = mods[key]
    final = base.perky_cf_machine_module.build(original, generated_dir=generated_rel)
    old_remix, old_build = os.environ.get("REMIX"), os.environ.get("BUILD")
    saved_stock_patches = base.dsp_ranges.STOCK_PATCHES
    try:
        mods[key] = final
        os.environ["REMIX"] = "perky-cf-final"
        os.environ["BUILD"] = str(args.build)
        selected_remix = base.registry.remix("perky-cf-final")
        selected = [mods[k] for k in selected_remix.modules]
        base.require_dsp_pristine_release(final, selected)
        base.dsp_ranges.STOCK_PATCHES = ()
        runpy.run_path(str(ROOT / "tools/build/build_bus.py"), run_name="__main__")
    finally:
        base.dsp_ranges.STOCK_PATCHES = saved_stock_patches
        mods[key] = original
        if old_remix is None:
            os.environ.pop("REMIX", None)
        else:
            os.environ["REMIX"] = old_remix
        if old_build is None:
            os.environ.pop("BUILD", None)
        else:
            os.environ["BUILD"] = old_build

    if not base.FINAL_MAIN.is_file():
        raise SystemExit("PERKY handoff export: build did not create out/mainos_bus.bin")

    print("=== PERKY handoff 5/6: prove stock DSP identity ===")
    base.run([
        sys.executable,
        ROOT / "tools/verify/verify_perky_stock_dsp_identity.py",
        base.STOCK_MAIN,
        base.FINAL_MAIN,
    ])

    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT,
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    out = args.out or (ROOT / "out" / f"PERKY_EMULATOR_HANDOFF_{commit[:8]}.zip")
    out = out.expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()

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
        "mainos_sha256": sha256(base.FINAL_MAIN),
        "stock_main_sha256": sha256(base.STOCK_MAIN),
        "perkons_firmware_sha256": sha256(firmware),
        "mc68k_head": git_head(ROOT / "vendor/mc68k"),
        "dsp56300_head": git_head(ROOT / "vendor/dsp56300"),
        "m68k_elf_gcc_version": toolchain_version,
        "project_file_count": len(project_files),
    }

    print("=== PERKY handoff 6/6: package emulator inputs ===")
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        z.writestr("HANDOFF.json", json.dumps(meta, indent=2, sort_keys=True) + "\n")
        z.write(base.FINAL_MAIN, "image/mainos_bus.bin")
        z.write(base.STOCK_MAIN, "image/section_3_MAIN_OS.bin")
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
    print(f"  bundle        : {out}")
    print("  NOTE: bundle is intentionally unqualified for hardware until ot_emu gates pass")


if __name__ == "__main__":
    main()

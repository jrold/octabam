#!/usr/bin/env python3
"""MEMORY's gate: nothing but stock writes the arena pages a remix's reserve
no longer takes.

    python3 tools/verify/verify_reserve_writes.py <remix> [--frames N]

Until 11 Oct 2026 every remix with a DRAM unit reserved 1,707 pages,
0x40a955e0..0x41495de0; MEMORY (modules/memory) now reserves what the
remix claims. A module that writes DRAM it never declared (a DramRegion, an
ArenaReserve, a unit's .bss) would write over the samples and recorders
stock keeps in the pages given back, and the build cannot see that. This
builds the remix, reads its reserve's ceiling (out/platform/layout.json),
and runs verify_set (the gate project, or OT_PROJECT; the load, the
sequencer playing, MIDI) under the port with every write into
ceiling..0x41495de0 recorded whose PC lies outside stock's own code: the
OS image less its zero runs, where the ROM caves are placed. Any such write
fails, by PC.

What it cannot see:
  - a write the set's load and playback do not reach (a menu, a sample
    load, a recorder take, a switch);
  - a module that calls a stock routine (memset 0x40020984, memcpy
    0x40020898) or pokes stock code into writing there: the PC is stock's;
  - a write below the ceiling, into the reserve itself, or above 0x41495de0.
"""
import argparse
import json
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from remix import platform_build  # noqa: E402

OLD_TOP = 0x41495de0                 # the fixed 1,707-page reserve's end
# Stock's code: the OS image (0x40000400 .. the loader) less the zero runs
# the build places ROM caves in (tools/build/build_bus.py OVERFLOW_RUN,
# CLONE_BASE .. ZERO_RUN_END and the window below it; verify_menu ISL_LO).
STOCK = ((0x40000400, 0x400c45b0), (0x400c4702, 0x400d24d0),
         (0x400d2ce0, 0x400d64da), (0x400d7c3c, platform_build.LOADER_AT))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("remix", nargs="?", default=os.environ.get("REMIX"))
    ap.add_argument("--frames", type=int, default=900)
    ap.add_argument("--project", default=os.environ.get("OT_PROJECT") or (
        pathlib.Path("~/.octabam_project").expanduser().read_text().strip()
        if pathlib.Path("~/.octabam_project").expanduser().is_file() else ""))
    a = ap.parse_args()
    if not a.remix:
        sys.exit("verify_reserve_writes: no remix (argument or REMIX=)")
    env = dict(os.environ, REMIX=a.remix, XBUS="1", SPEC="1")
    r = subprocess.run([sys.executable, str(ROOT / "tools/build/build_bus.py")], cwd=ROOT, env=env,
                       capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"verify_reserve_writes: {a.remix} does not build\n{r.stdout[-1500:]}{r.stderr[-1500:]}")
    lay = ROOT / "out/platform" / platform_build.LAYOUT
    ceiling = json.loads(lay.read_text()).get("ceiling") if lay.exists() else None
    if ceiling is None:
        print(f"  [SKIP] verify_reserve_writes: {a.remix} carries no DRAM unit, so no reserve was given back")
        return 0
    if ceiling >= OLD_TOP:
        print(f"  [ok] verify_reserve_writes: {a.remix}'s reserve ends at 0x{ceiling:08x}, at or past "
              f"0x{OLD_TOP:08x}: no page given back")
        return 0
    if not a.project:
        print("  [SKIP] verify_reserve_writes: no project (OT_PROJECT=<dir> or ~/.octabam_project)")
        return 0
    out = ROOT / "out/reserve_writes"
    out.mkdir(parents=True, exist_ok=True)
    rec = out / f"{pathlib.PurePath(a.remix).name}.txt"
    rec.unlink(missing_ok=True)
    image = out / f"{pathlib.PurePath(a.remix).name}.bin"
    image.write_bytes((ROOT / "out/mainos_bus.bin").read_bytes())
    extra = (f"--foreign-writes 0x{ceiling:x},0x{OLD_TOP - ceiling:x},{rec} "
             f"--stock-code " + ";".join(f"0x{lo:x}-0x{hi:x}" for lo, hi in STOCK))
    r = subprocess.run([sys.executable, str(ROOT / "tools/verify/verify_set.py"), a.remix,
                        "--frames", str(a.frames), "--project", a.project,
                        "--image", str(image), "--extra", extra], cwd=ROOT, capture_output=True, text=True)
    print(r.stdout, end="")
    if r.returncode:
        print(r.stderr[-1500:], end="")
        print(f"  [FAIL] verify_reserve_writes: verify_set exit {r.returncode}")
        return 1
    if "[SKIP] verify_set" in r.stdout:
        print("  [SKIP] verify_reserve_writes: verify_set skipped")
        return 0
    if not rec.exists():
        print(f"  [FAIL] verify_reserve_writes: the port wrote no record ({rec}): is out/emu/ot_emu current (make emu-cf)?")
        return 1
    lines = rec.read_text().splitlines()
    count = int(lines[0].split()[1])
    span = f"0x{ceiling:08x}..0x{OLD_TOP:08x} ({(OLD_TOP - ceiling) // 6144:,} pages)"
    if count:
        pcs = sorted({l.split()[1] for l in lines[1:]})
        print(f"  [FAIL] verify_reserve_writes: {count:,} write(s) into {span} from outside stock's code, "
              f"PCs {' '.join(pcs[:12])}; first: {lines[1]}")
        return 1
    print(f"  [ok] verify_reserve_writes: no write into {span} from outside stock's code over the set")
    return 0


if __name__ == "__main__":
    sys.exit(main())

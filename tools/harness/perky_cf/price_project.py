#!/usr/bin/env python3
"""Price a real project's ColdFire frame against the unit's frame deadline.

The optimisation work needs one number to steer by: how much of the 362.8 us
16-sample frame the ColdFire actually spends, and whether the frame handler
overruns it.  Both come out of `ot_emu`:

  * `--cf-frame-budget-us` reports the average per-frame cost in model cycles;
  * `--cf-frame-deadline 1.7` reports the frame handler's lateness on the
    frames that overrun -- the unit's own deadline, at the project's measured
    model-to-hardware factor.

This stages a project directory onto a card image and runs both, optionally
with Perky voices or pattern trigs removed, so a result can be attributed to
the machines, the pattern, or neither.

    python tools/harness/perky_cf/price_project.py "G:/PRESETS MKII/PROJECT 261010" \
        --set "PRESETS MKII" --name "PROJECT 261010"
    ... --drop-machine T3            # one fewer Perky voice
    ... --no-trigs                   # same machines, every trig erased

A Perky track is marked 'P','K',1 in bank01's part 1, 30 bytes per track, the
first track's mark at 0x8ef1b (tools/hw/ot_project.py knows the pattern file
layout; the marks and the trig masks are the two handles here).
"""
from __future__ import annotations

import argparse
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tools/hw")]
import ot_project as otp  # noqa:E402

EMU = ROOT / "out/emu/ot_emu"
DEFAULT_IMAGE = ROOT / "out/mainos_bus.bin"
SIG0, SIG_STRIDE = 0x8EF1B, 30          # bank01 part 1, PERKY marks
TRACK_RECORD = {t: t - 1 for t in range(1, 9)}


def env() -> dict:
    e = dict(os.environ)
    e["PATH"] = (r"C:\msys64\ucrt64\bin;"
                 r"C:\temp4495\perky-deepseek-20261009-072423\perkybits\build-smoke\_deps\unicorn-build;"
                 + e.get("PATH", ""))
    return e


def edit(project: pathlib.Path, drop: list[int], no_trigs: bool) -> None:
    for fname in ("bank01.work", "bank01.strd"):
        p = project / fname
        if not p.is_file():
            continue
        d = bytearray(p.read_bytes())
        for track in drop:
            at = SIG0 + TRACK_RECORD[track] * SIG_STRIDE
            if d[at:at + 3] == b"PK\x01":
                d[at:at + 3] = b"\x00\x00\x00"
        if no_trigs:
            for pattern in range(16):
                for track in range(8):
                    base = otp.trac_off(pattern, track)
                    for m in range(otp.NMASKS):
                        d[base + m * 8:base + m * 8 + 8] = b"\x00" * 8
        p.write_bytes(bytes(d))


def run(project: pathlib.Path, setname: str, name: str, image: pathlib.Path,
        frames: int, work: pathlib.Path, label: str, extra: list[str]) -> str:
    card = work / f"card_{label}.img"
    subprocess.run([sys.executable, ROOT / "tools/emu/ot_emu/stage_card.py",
                    str(project), setname, name, "--tree", str(work / f"tree_{label}"),
                    "--out", str(card)], cwd=ROOT, check=True,
                   capture_output=True, env=env())
    cmd = [str(EMU), "--image", str(image), "--card", str(card),
           "--set", setname, "--project", name, "--load-ms", "90000",
           "--sequencer", "--internal-clock", "--bank", "0", "--frames", str(frames),
           "--dsp", "--dsp-dirty", "123", "--main-level", "64", *extra]
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, env=env())
    return r.stdout + r.stderr


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project", type=pathlib.Path)
    ap.add_argument("--set", dest="setname", default="OCTABAM")
    ap.add_argument("--name", default=None, help="project name (default: the directory name)")
    ap.add_argument("--image", type=pathlib.Path, default=DEFAULT_IMAGE)
    ap.add_argument("--frames", type=int, default=1500)
    ap.add_argument("--factor", type=float, default=1.7,
                    help="model-to-hardware cycle factor for the deadline run")
    ap.add_argument("--drop-machine", action="append", default=[], type=int,
                    metavar="T", help="remove this Perky machine (repeatable)")
    ap.add_argument("--no-trigs", action="store_true", help="erase every pattern trig")
    a = ap.parse_args()

    if not EMU.is_file():
        raise SystemExit(f"missing {EMU}; run `make emu-cf`")
    if not a.image.is_file():
        raise SystemExit(f"missing image {a.image}")
    name = a.name or a.project.name

    work = pathlib.Path(tempfile.mkdtemp(prefix="price-project-"))
    try:
        staged = work / "project"
        shutil.copytree(a.project, staged)
        edit(staged, a.drop_machine, a.no_trigs)
        label = "run"
        budget = run(staged, a.setname, name, a.image, a.frames, work, label,
                     ["--cf-frame-budget-us", "10000"])
        deadline = run(staged, a.setname, name, a.image, a.frames, work, label,
                       ["--cf-frame-deadline", str(a.factor)])
    finally:
        shutil.rmtree(work, ignore_errors=True)

    m = re.search(r"\((\d+) per frame of [\d.]+ samples = ([\d.]+) us at", budget)
    if m:
        print(f"average   : {m.group(2)} us/frame of 362.8 "
              f"({float(m.group(2)) / 362.811 * 100:.1f}%)")
    else:
        print("average   : no budget line -- see the emulator output")
    late = re.findall(r"still in its exchange ([\d.]+) us", deadline)
    if late:
        print(f"deadline  : OVER -- frame handler still busy {float(late[0]):.1f} us "
              f"after the frame began (x{a.factor:g}); {len(late)} overrun frame(s)")
    else:
        print(f"deadline  : fits (no overrun at x{a.factor:g})")


if __name__ == "__main__":
    main()

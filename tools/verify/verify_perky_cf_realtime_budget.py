#!/usr/bin/env python3
"""ColdFire real-time frame budget gate for the Perky CF image.

The lock-step emulator runs far faster than real time and cannot observe a
frame overrun, so a firmware whose per-frame ColdFire work exceeds the machine's
16-sample frame period can pass every functional gate and still wedge the unit
(the PERKY1/PERKY2 "briefly sounds then the sequencer stalls" failure).

This gate stages the same real project/card the user-path gate uses, runs the
image under ot_emu with --cf-frame-budget-us, and fails unless the ColdFire's
measured per-frame cycles fit the budget.

The budget is the frame period divided by a safety factor. The vendored core's
cycle model under-counts hardware (on the stock image it prices the frame at
126 us against the 213.5 us the CF METER measured on hardware, ~1.7x), and the
project's own convention for this uncertainty is "twice the model"
(modules/perky/HANDOFF.md). So the default factor is 2: the model must fit the
frame with the same conservatism the DSP budget gates use.

FAIL CLOSED: a missing project/emulator/image, a non-zero ot_emu exit, or any
over-budget measurement is an error.
"""
from __future__ import annotations

import argparse
import pathlib
import re
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tools/hw"), str(ROOT / "tools/harness")]

import verify_perky_cf_userpath as up  # noqa: E402  (staging helpers, re-used verbatim)

EMU = ROOT / "out/emu/ot_emu"
PY = ROOT / ".venv/bin/python3"
FRAME_US = 16.0 / 44100.0 * 1e6            # one 16-sample frame period, 362.811 us


def fail(message: str) -> "NoReturn":
    raise SystemExit("perky cf realtime budget: FAIL: " + message)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--image", type=pathlib.Path, required=True)
    ap.add_argument("--project", type=pathlib.Path, required=True)
    ap.add_argument("--work", type=pathlib.Path, default=ROOT / "out/perky/cf-budget")
    ap.add_argument("--frames", type=int, default=12000)
    ap.add_argument("--safety", type=float, default=2.0,
                    help="model-to-hardware safety factor; budget = frame_period / safety")
    args = ap.parse_args()

    image = args.image.expanduser().resolve()
    project = args.project.expanduser().resolve()
    work = args.work.expanduser().resolve()
    if not image.is_file():
        fail(f"missing built MAIN OS {image}")
    if not (project / "project.work").is_file():
        fail(f"{project} is not an Octatrack project")
    if not EMU.is_file():
        fail(f"missing {EMU}; run `make emu-cf`")
    if not PY.is_file():
        fail(f"missing {PY}; run `make emu-setup`")
    if args.safety <= 0.0:
        fail("--safety must be positive")

    budget_us = FRAME_US / args.safety

    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    tone = work / "PERKY_BUDGET_440.wav"
    up.make_tone(tone)
    fixture = up.configure_fixture(project, work / "project")
    card = work / "card.img"
    tree = work / "tree"
    subprocess.run(
        [str(PY), str(ROOT / "tools/emu/ot_emu/stage_card.py"), str(fixture),
         "OCTABAM", "RIG", "--tree", str(tree), "--out", str(card),
         "--audio", f"{tone}:{up.SAMPLE_REL}"],
        cwd=ROOT, check=True)

    log = work / "port.log"
    cmd = [
        str(EMU), "--image", str(image), "--card", str(card),
        "--set", "OCTABAM", "--project", "RIG",
        "--load-ms", "90000", "--sequencer", "--internal-clock",
        "--bank", "0", "--frames", str(args.frames),
        "--dsp", "--dsp-dirty", "123", "--main-level", "64",
        "--cf-frame-budget-us", f"{budget_us:.3f}",
    ]
    with log.open("w") as fh:
        fh.write(" ".join(cmd) + "\n")
        fh.flush()
        result = subprocess.run(cmd, cwd=ROOT, stdout=fh, stderr=subprocess.STDOUT, timeout=900)
    text = log.read_text(errors="replace")

    raw = re.search(r"cf budget\s*:\s*\d+ ColdFire cycles over the frames "
                    r"\((\d+) per frame of [\d.]+ samples = ([\d.]+) us at", text)
    if not raw:
        fail(f"emulator printed no cf budget line; see {log}")
    per_frame = int(raw.group(1))
    measured_us = float(raw.group(2))

    verdict = re.search(r"us/frame .*?:\s+(PASS|OVER)\b", text)
    if not verdict:
        fail(f"emulator printed no budget verdict; see {log}")
    if verdict.group(1) != "PASS":
        fail(f"image is over the ColdFire real-time frame budget: "
             f"{measured_us:.1f} us/frame measured, {budget_us:.1f} us allowed "
             f"({FRAME_US:.1f} us frame / {args.safety:g}); see {log}")
    if result.returncode != 0:
        fail(f"ot_emu exited {result.returncode} though the budget line passed; see {log}")

    print(f"PERKY CF real-time frame budget: PASS")
    print(f"  ColdFire {per_frame} cycles/frame = {measured_us:.1f} us at 266 MHz; "
          f"budget {budget_us:.1f} us (frame {FRAME_US:.1f} us / safety {args.safety:g})")
    print(f"  headroom {budget_us - measured_us:.1f} us of the {budget_us:.1f} us model budget "
          f"({measured_us / budget_us * 100.0:.1f}% used)")
    print(f"  evidence: {log}")


if __name__ == "__main__":
    main()

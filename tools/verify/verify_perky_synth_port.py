#!/usr/bin/env python3
"""Exercise the complete synthetic PERKY Noise/Tone canary on both DSP cores.

This is intentionally separate from verify_perky_probe_port.py. The impulse
probe proves transport; this gate proves the table-loaded complete synth image
produces a sustained multi-sample source through the stock AMP/FX continuation.

Requires:
  * OT_PROJECT=<stock project fixture>
  * out/mainos_perky_synth.bin, normally built with
      python3 tools/perky/build_synth_canary.py

No hardware is flashed by this script.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "tools/hw"), str(ROOT / "tools/harness")]

import ot_project as otp  # noqa:E402
import blockdump as bd  # noqa:E402
import recloop as rl  # noqa:E402
from ab_fixture import prepare  # noqa:E402

OUT = ROOT / "out/perky/synth-port"
TRACKS = (1, 5)
DEFAULT_IMAGE = ROOT / "out/mainos_perky_synth.bin"
SIGNIFICANT = 100
MIN_SIGNIFICANT_SAMPLES = 16
MIN_DISTINCT_VALUES = 5


def fail(msg: str) -> None:
    raise AssertionError(f"PERKY synth port: {msg}")


def signed_records(classes, core: int):
    addrs = {
        1: (0x80001C90, 0x80002710),
        0: (0x800021D0, 0x80002C50),
    }[core]
    records = sorted(sum((classes.get((">", 0, core, addr), []) for addr in addrs), []))
    return [words for _, words in records
            if len(words) >= 4 and words[0] == 0x504B and words[2] == 0x5931]


def configure_fixture(project: str) -> Path:
    fixture = prepare(project, OUT / "project")
    for bank in fixture.glob("bank*.work"):
        def mutate(data):
            for part in range(8):
                base = otp.PART_BASE + part * otp.PART_STRIDE + 9
                for track in (0, 4):
                    data[base + 0x22 + track] = 1  # FLEX transport donor
                    data[base + track] = 0         # FX1 NONE
                    data[base + 8 + track] = 0     # FX2 NONE
            for track in (0, 4):
                at = otp.trac_off(0, track)
                data[at:at + 8] = (1).to_bytes(8, "big")  # one trig at step 0

        otp._bank_write(fixture, int(bank.stem[4:]), mutate, guard=False)
    return fixture


def main() -> None:
    project = os.environ.get("OT_PROJECT")
    if not project:
        print("[SKIP] PERKY synth port: set OT_PROJECT to a stock project fixture")
        return

    image_src = Path(os.environ.get("PERKY_SYNTH_IMAGE", DEFAULT_IMAGE))
    if not image_src.exists():
        fail(
            f"missing {image_src}; build it first with "
            "`python3 tools/perky/build_synth_canary.py`"
        )

    OUT.mkdir(parents=True, exist_ok=True)
    fixture = configure_fixture(project)
    card = OUT / "card.img"
    subprocess.run([
        sys.executable,
        str(ROOT / "tools/emu/ot_emu/stage_card.py"),
        str(fixture),
        "OCTABAM",
        "RIG",
        "--tree",
        str(OUT / "tree"),
        "--out",
        str(card),
    ], check=True, cwd=ROOT)

    image = OUT / "image.bin"
    shutil.copy2(image_src, image)
    dump = OUT / "blocks.bin"
    basewav = OUT / "audio"
    log_path = OUT / "port.log"

    cmd = [
        os.environ.get("PERKY_EMU", str(ROOT / "out/emu/ot_emu")),
        "--image", str(image),
        "--card", str(card),
        "--set", "OCTABAM",
        "--project", "RIG",
        "--load-ms", "20000",
        "--sequencer",
        "--internal-clock",
        "--bank", "0",
        "--frames", "260",
        "--dsp",
        "--main-level", "64",
        "--audio-out", str(basewav),
        "--block-dump", str(dump),
    ]

    with log_path.open("w") as log:
        log.write(" ".join(cmd) + "\n")
        log.flush()
        subprocess.run(cmd, cwd=ROOT, check=True, timeout=600,
                       stdout=log, stderr=subprocess.STDOUT)

    log = log_path.read_text()
    if "ILLEGAL" in log:
        fail("emulator hit ILLEGAL")
    if not re.search(r"frames run\s*:\s*260", log):
        fail("emulator did not complete all 260 frames")

    classes = bd.classes(bd.read(dump))
    summaries = []
    for track, core in ((1, 1), (5, 0)):
        packets = signed_records(classes, core)
        if not packets:
            fail(f"T{track}/core {core}: no PK/Y1 transport records")
        if not any((packet[3] & 0xFFFF) == 1 for packet in packets):
            fail(f"T{track}/core {core}: PK/Y1 records never carried a trig")

        left = rl.readback_audio(classes, track)
        right = rl.readback_audio(classes, track, True)
        if not left or not right:
            fail(f"T{track}/core {core}: no post-chain readback")
        if left != right:
            fail(f"T{track}/core {core}: mono synth source diverged L/R")

        significant = [sample for sample in left if abs(sample) > SIGNIFICANT]
        if len(significant) < MIN_SIGNIFICANT_SAMPLES:
            fail(
                f"T{track}/core {core}: only {len(significant)} samples exceed "
                f"{SIGNIFICANT}; looks like silence/impulse, not the synth"
            )
        distinct = len(set(significant))
        if distinct < MIN_DISTINCT_VALUES:
            fail(
                f"T{track}/core {core}: only {distinct} distinct significant "
                "values; source does not look synthesized"
            )
        peak = max(map(abs, left))
        summaries.append((track, core, len(significant), distinct, peak))
        print(
            f"PASS T{track}/core {core}: {len(significant)} significant samples, "
            f"{distinct} distinct values, peak {peak}"
        )

    if len(summaries) != 2:
        fail("did not qualify both DSP cores")
    print(
        "PASS PERKY synth canary: both DSP cores received PK/Y1 trigs and "
        "produced sustained varying stereo-matched post-chain audio"
    )


if __name__ == "__main__":
    main()

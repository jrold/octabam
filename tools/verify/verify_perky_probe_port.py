#!/usr/bin/env python3
"""Exercise the PERKY source-seam canary through both emulated DSP cores.

The isolated perky-probe remix temporarily turns ordinary FLEX tracks into the
PK/Y1 diagnostic source.  T1 (DSP core 1) and T5 (DSP core 0) each receive a
single trig.  No audio sample is staged: audible readback can only come from
the DSP canary impulse.

This is an image-stage gate.  It skips when OT_PROJECT is not supplied, exactly
like the Analog BD port/UI gates, because the emulator needs a user-owned stock
project fixture to stage a card image.
"""
from __future__ import annotations

import os
import pathlib
import re
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "tools/hw"), str(ROOT / "tools/harness")]

import ot_project as otp  # noqa: E402
import blockdump as bd  # noqa: E402
import recloop as rl  # noqa: E402
from ab_fixture import prepare  # noqa: E402

OUT = ROOT / "out/perky/probe-port"
TRACKS = (1, 5)  # one position-0 track on each DSP core


def fail(msg: str) -> None:
    raise AssertionError(f"PERKY probe port: {msg}")


def signed_records(classes, core: int):
    """Return PK/Y1 source packets captured at the two ping addresses."""
    addrs = {
        1: (0x80001C90, 0x80002710),
        0: (0x800021D0, 0x80002C50),
    }[core]
    records = sorted(sum((classes.get((">", 0, core, addr), []) for addr in addrs), []))
    return [words for _, words in records
            if len(words) >= 4 and words[0] == 0x504B and words[2] == 0x5931]


def main() -> None:
    project = os.environ.get("OT_PROJECT")
    if not project:
        print("[SKIP] PERKY probe port: set OT_PROJECT to a stock project fixture")
        return

    OUT.mkdir(parents=True, exist_ok=True)
    fixture = prepare(project, OUT / "project")

    # The probe deliberately hijacks ordinary FLEX in this isolated remix, so
    # no PK/1 Part signature is needed yet.  T1 and T5 cover the first voice
    # position on each DSP core.  Leave every sample slot empty: the only
    # possible source is the diagnostic impulse produced by probe_glue.asm.
    for bank in fixture.glob("bank*.work"):
        def mutate(data):
            for part in range(8):
                base = otp.PART_BASE + part * otp.PART_STRIDE + 9
                for track in (0, 4):
                    data[base + 0x22 + track] = 1  # FLEX
                    data[base + track] = 0         # FX1 NONE
                    data[base + 8 + track] = 0     # FX2 NONE
            for track in (0, 4):
                at = otp.trac_off(0, track)
                data[at:at + 8] = (1).to_bytes(8, "big")

        otp._bank_write(fixture, int(bank.stem[4:]), mutate, guard=False)

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
    shutil.copy2(os.environ.get("PERKY_IMAGE", ROOT / "out/mainos_bus.bin"), image)
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

    # Core 1 carries T1; core 0 carries T5.  Both must see PK/Y1 and at least
    # one record with the trigger flag.  This proves the ColdFire writer,
    # transport packing, both DspHook sites and the per-frame event flag.
    for track, core in ((1, 1), (5, 0)):
        packets = signed_records(classes, core)
        if not packets:
            fail(f"T{track}/core {core}: no PK/Y1 transport records")
        if not any((packet[3] & 0xFFFF) == 1 for packet in packets):
            fail(f"T{track}/core {core}: PK/Y1 records never carried a trig")

        left = rl.readback_audio(classes, track)
        right = rl.readback_audio(classes, track, True)
        if not left or not right:
            fail(f"T{track}/core {core}: no chain readback")
        if max(map(abs, left)) <= 100:
            fail(f"T{track}/core {core}: post-AMP source is silent")
        if left != right:
            fail(f"T{track}/core {core}: stereo canary diverged L/R")

        print(
            f"PASS T{track}/core {core}: PK/Y1 trig reached DSP and stereo "
            f"impulse survived stock AMP/FX ({max(map(abs, left))} peak)"
        )

    print("PASS PERKY probe: both DSP cores, transport signature, trig and stereo post-chain audio")


if __name__ == "__main__":
    main()

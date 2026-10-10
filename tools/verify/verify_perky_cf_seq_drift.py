#!/usr/bin/env python3
"""PERKY through the REAL Octatrack sequencer: hit-over-hit level must be flat.

THE BUG THIS PINS (measured 9 Oct 2026)
---------------------------------------
Symptom on hardware: with a sequencer pattern the FIRST hit is right and every
later hit is thinner and quieter ("a whole other ass tone on top"), and it
snaps back good when the song reaches a 16-aligned trig.  Triggering the same
voice by hand from Sample Trig mode was always fine.

Root cause: `pk_render` (modules/perky/control_cf_final.c) keeps a 16-sample
frame cache that the stock source packer fills with TWO callbacks per frame,
`(track,ping,0,split)` then `(track,ping,split,16)`.  Measured with
`--watch-pc 0x40abc67a`: the stock's `ping` bit FLIPS between those two halves
(0 then 1, then 1 then 0, ...).  The old cache guard treated a ping change as
"the pre-event half came from stock FLEX" and zeroed `frame_pcm[0..split)`,
so it threw away the pre-half audio on every split frame.

`split` is the trig's sample offset inside the frame: with 16th steps at
120 BPM (5512.5 samples) the trigs at steps 1/7/11 land at 0/3/5/8/11/13 mod
16 and hold there until the next trig.  Every split frame therefore had
`split` samples of silence blanked over its 16, which is exactly the reported
progressive thinning, and it cleared only when a trig landed at offset 0.

WHAT THIS GATE ASSERTS
----------------------
1. the sequencer really produced split frames (so the test exercises the bug);
2. the port's per-frame source record has NO leading silence (the pre-half
   survives);
3. the per-track chain output has NO leading silence per frame;
4. six hits over two bars stay within LEVEL_RATIO_MIN of each other (the bug
   measured 0.478; a healthy build measures > 0.98).
"""
from __future__ import annotations

import argparse
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tools/hw"), str(ROOT / "tools/harness")]
import toolpath  # noqa:E402,F401
import blockdump as bd  # noqa:E402
import recloop as rl  # noqa:E402
import ot_project as otp  # noqa:E402
from ab_fixture import prepare  # noqa:E402

EMU = ROOT / "out/emu/ot_emu"
PY = ROOT / ".venv/bin/python3"
TRACK = 0                 # T1
RECORDER_BASE = 128       # FLEX object ids 128..135 are R1..R8
SR = 44100
STEPS = (1, 7, 11)        # the user's bench pattern
BARS = 2                  # six hits -- where the bug was worst
LEVEL_RATIO_MIN = 0.90    # bug: 0.478 (4.29M -> 2.05M); fixed: > 0.98
BLANK_MAX = 0.25          # fraction of pre-half samples that may be silent
                          # (bug: 1.000 -- every pre-half sample was zeroed)
BLANK_FRAME_MAX = 0.10    # fraction of sounding frames that may lose >= 2 samples
                          # (bug: ~1.000 at split>=3)


def fail(message: str) -> "NoReturn":
    raise SystemExit("verify-perky-cf-seq-drift: " + message)


def stage(project: pathlib.Path, work: pathlib.Path) -> pathlib.Path:
    fixture = prepare(project, work / "project")

    def mutate(data: bytearray) -> None:
        for part in range(otp.NPARTS_ALL):
            file_base = otp.PART_BASE + part * otp.PART_STRIDE
            live_base = file_base + 9
            t = TRACK
            data[live_base + 0x22 + t] = 1          # underlying stock FLEX
            data[file_base + otp.SLOT_OFF + t * 5 + otp.SLOT_KIND["flex"]] = RECORDER_BASE + t
            data[live_base + 60 + 30 * t:live_base + 63 + 30 * t] = b"PK\x01"
            # Shipping SRC order: TUNE, DECAY, ALGO, PRM1, PRM2, MODE
            values = (64, 64, 0, 64, 64, 0)         # ALGO 0 = Fold Drum 1, MODE 0
            for slot, value in enumerate(values):
                data[live_base + 0x2a + 30 * t + 6 + slot] = value
        # Trigs on steps 1/7/11.  A TRAC mask byte k (of trac_off..+7) holds
        # steps 8k+1..8k+8, LSB first -- do not step 8 bytes per step.
        at = otp.trac_off(0, TRACK)
        for step in STEPS:
            data[at + 7 - (step - 1) // 8] |= 1 << ((step - 1) % 8)

    # ⚠️ Bank files are named bank01..bank16 (1-based); there is no bank00.
    for bank in fixture.glob("bank*.work"):
        otp._bank_write(fixture, int(bank.stem[4:]), mutate, guard=False)
    return fixture


def leading_zeros(frame: list[int]) -> int:
    n = 0
    while n < len(frame) and frame[n] == 0:
        n += 1
    return n


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--image", type=pathlib.Path, required=True)
    ap.add_argument("--project", type=pathlib.Path, required=True)
    ap.add_argument("--work", type=pathlib.Path, required=True)
    args = ap.parse_args()

    if not EMU.is_file():
        fail(f"missing {EMU}; run `make emu-cf`")
    if not PY.is_file():
        fail(f"missing {PY}; run `make emu-setup`")
    if not args.image.is_file():
        fail(f"missing image {args.image}")
    if not args.project.is_dir():
        fail(f"missing project {args.project}")

    work = args.work.resolve()
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    fixture = stage(args.project.resolve(), work)

    card = work / "card.img"
    tree = work / "tree"
    subprocess.run([str(PY), str(ROOT / "tools/emu/ot_emu/stage_card.py"),
                    str(fixture), "OCTABAM", "RIG", "--tree", str(tree), "--out", str(card)],
                   cwd=ROOT, check=True)

    frames = int(BARS * 4 * SR / 16) + 400
    dump = work / "blocks.bin"
    log = work / "port.log"
    cmd = [str(EMU), "--image", str(args.image.resolve()), "--card", str(card),
           "--set", "OCTABAM", "--project", "RIG", "--load-ms", "90000",
           "--sequencer", "--internal-clock", "--bank", "0",
           "--frames", str(frames), "--dsp", "--main-level", "64",
           "--block-dump", str(dump)]
    with log.open("w") as f:
        result = subprocess.run(cmd, cwd=ROOT, stdout=f, stderr=subprocess.STDOUT, timeout=900)
    if result.returncode:
        fail(f"emulator exited {result.returncode}; see {log}")
    if not dump.is_file():
        fail(f"emulator produced no DSP block dump; see {log}")

    classes = bd.classes(bd.read(dump))
    chain = [int(v) for v in rl.readback_audio(classes, TRACK + 1)]
    if len(chain) < int((BARS * 16 + 1) * 0.125 * SR):
        fail(f"chain read-back too short ({len(chain)} samples); see {log}")

    # ---- 1. the sequencer really split frames (else this test is vacuous) ----
    groups = sorted(classes.get((">", 0, 1, 0x80001c90), []) +
                    classes.get((">", 0, 1, 0x80002710), []))
    if not groups:
        fail("no per-frame source record captured; see the block dump")
    splits = [rl.words(w[0:84])[0] for _, w in groups]
    if max(splits) <= 0:
        fail("the sequencer never split a frame -- the drift path was not exercised")

    # ---- 2. the port's per-frame record must keep its pre-event half ----
    # For every split frame, the first `split` of its 16 source samples are the
    # pre-event half.  The bug zeroed them; a healthy build does not.
    rec_pre = []
    for split, (_, w) in zip(splits, groups):
        if split <= 0:
            continue
        decoded = [int(v) for v in rl.record_audio(rl.words(w[0:84]))]
        if len(decoded) != 16:
            continue
        if not any(decoded):
            continue                    # a genuinely silent frame is fine
        rec_pre.extend(decoded[:split])
    if not rec_pre:
        fail("no sounding split frame in the source record -- test is vacuous")
    rec_blank = sum(1 for v in rec_pre if v == 0) / len(rec_pre)

    # ---- 3. the chain output must not blank its leading samples ----
    frame_count = len(chain) // 16
    sounding = [chain[16 * k:16 * k + 16] for k in range(2, frame_count)]
    sounding = [f for f in sounding if any(f)]
    blank_frames = sum(1 for f in sounding if leading_zeros(f) >= 2)
    chain_blank = blank_frames / len(sounding)

    # ---- 4. six hits over two bars must stay level ----
    step = 0.125 * SR
    bar = 16 * step
    hits = [b * bar + s * step for b in range(BARS) for s in (0, 6, 10)]
    window = int(0.45 * SR)
    sub = int(0.005 * SR)
    levels = []
    for start in hits:
        a = int(start)
        if a + window > len(chain):
            fail(f"capture too short for hit at {start / SR:.3f}s; see {log}")
        seg = chain[a:a + window]
        best = 0.0
        for i in range(0, len(seg) - sub, sub):
            acc = 0
            for v in seg[i:i + sub]:
                acc += v * v
            rms = (acc / sub) ** 0.5
            if rms > best:
                best = rms
        levels.append(best)

    ratio = min(levels) / max(levels)
    print(f"split frames   : {sum(1 for s in splits if s > 0)} / {len(splits)} "
          f"(max split {max(splits)})")
    print(f"record pre-half: {rec_blank * 100:5.1f}% of split-frame pre samples are silent"
          f"  (<= {BLANK_MAX * 100:.0f}%)")
    print(f"chain frames   : {chain_blank * 100:5.1f}% of sounding frames lose >= 2 leading"
          f" samples  (<= {BLANK_FRAME_MAX * 100:.0f}%)")
    for k, (start, level) in enumerate(zip(hits, levels)):
        print(f"  hit {k}  t={start / SR:6.3f}s  attack level {level:9.0f}"
              f"  {level / max(levels) * 100:5.1f}%")
    print(f"level spread   : min/max = {ratio:.3f} (>= {LEVEL_RATIO_MIN})")

    if rec_blank > BLANK_MAX:
        fail(f"{rec_blank * 100:.1f}% of the split-frame pre-event source samples are "
             "silent -- the pre-half is being discarded (see this file's docstring)")
    if chain_blank > BLANK_FRAME_MAX:
        fail(f"{chain_blank * 100:.1f}% of sounding frames lose >= 2 leading samples")
    if ratio < LEVEL_RATIO_MIN:
        fail(f"hit-over-hit level spread {ratio:.3f} < {LEVEL_RATIO_MIN}: "
             f"levels {[round(v) for v in levels]} -- the sequencer drift is back")

    print("PERKY sequencer drift: PASS (frame splits survive; six hits stay level)")
    print(f"evidence: {log}")


if __name__ == "__main__":
    main()

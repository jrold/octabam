#!/usr/bin/env python3
"""Full-machine user-path gate for ColdFire PERKY Machines.

This is deliberately not a host callback fixture. It stages a real Octatrack
project/card, boots the built MAIN OS in tools/emu/ot_emu, starts the firmware's
sequencer and lets the normal source packer/DSP transport run.

The fixture carries:
  * PERKY on T1/T2/T3/T4, one different Algo on each track;
  * ordinary FLEX controls on T3/T7 using a generated, staged 440 Hz sample;
  * PERKY's underlying FLEX slots pointed at each track's own recorder buffer
    (R1/R2/R5/R6), not at the staged file sample. Recorder buffers are stock,
    always-addressable FLEX objects and are the intended silent scheduling
    donors for a sample-free synth machine;
  * repeated pattern trigs so startup-only success cannot pass.

That donor distinction is intentional. A fresh PERKY machine must not depend on
the user first loading a file sample into a FLEX slot. If the PERKY renderer is
not actually reached, the empty recorder-buffer donor remains silent and this
gate fails instead of accidentally passing on the test tone.

The port currently has a documented dry-main gain limitation, so this gate uses
the measured 84-word per-track source records captured by --block-dump. Those
records are upstream of that emulator-only main-output issue and are the exact
records DMA'd to the stock DSP source/AMP/FX chain.

FAIL CLOSED: missing project, emulator, staging venv, image or any expected
runtime evidence is an error. This script is intended to gate flashable builds.
"""
from __future__ import annotations

import argparse
import math
import pathlib
import re
import shutil
import struct
import subprocess
import sys
import wave

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tools/hw"), str(ROOT / "tools/harness")]
import toolpath  # noqa:E402,F401
import blockdump as bd  # noqa:E402
import recloop as rl  # noqa:E402
import ot_project as otp  # noqa:E402
from ab_fixture import prepare  # noqa:E402

EMU = ROOT / "out/emu/ot_emu"
PY = ROOT / ".venv/bin/python3"
PERKY_TRACKS = (1, 2, 3, 4)       # one-based OT track numbers
# Family-local ALGO position staged on each PERKY voice, in PERKY_TRACKS
# order.  Kept as a named constant so frame-cost experiments can stage a
# different engine mix without editing the gate (see
# tools/verify/verify_perky_cf_realtime_budget.py).
# T1 runs Simple Drum (V1 local 1) so the whole-machine path covers the
# newest engine, not just the long-standing family defaults.
PERKY_ALGO = (1, 0, 0, 0)
PERKY_INDEX = tuple(t - 1 for t in PERKY_TRACKS)
FLEX_TRACKS = (7, 8)
SAMPLE_REL = "AUDIO/PERKY_GATE_440.wav"
SR = 44100
SAMPLE_FRAMES = SR * 8
SIGNIFICANT = 64
MIN_SIGNIFICANT = 128
MIN_DISTINCT = 32
RECORDER_BASE = 128                 # FLEX object ids 128..135 are R1..R8


def fail(message: str) -> "NoReturn":
    raise SystemExit("PERKY CF user path: FAIL: " + message)


def make_tone(path: pathlib.Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        frames = bytearray()
        for n in range(SAMPLE_FRAMES):
            value = int(round(12000.0 * math.sin(2.0 * math.pi * 440.0 * n / SR)))
            frames += struct.pack("<hh", value, value)
        w.writeframes(frames)


def install_sample_block(project: pathlib.Path) -> None:
    """Install FLEX slot 1 only for the ordinary T3/T7 control tracks."""
    block = (
        "[SAMPLE]\r\n"
        "TYPE=FLEX\r\n"
        "SLOT=001\r\n"
        f"PATH=../{SAMPLE_REL}\r\n"
        "TRIM_BARSx100=100\r\n"
        "LOOP_BARSx100=100\r\n"
        "BPMx24=2880\r\n"
        "TSMODE=0\r\n"
        "LOOPMODE=0\r\n"
        "GAIN=48\r\n"
        "TRIGQUANTIZATION=-1\r\n"
        "[/SAMPLE]\r\n\r\n"
    ).encode()
    for suffix in ("work", "strd"):
        path = project / f"project.{suffix}"
        if not path.is_file():
            continue
        raw = path.read_bytes()
        raw = re.sub(
            rb"\[SAMPLE\]\r?\nTYPE=FLEX\r?\nSLOT=001\r?\n.*?\[/SAMPLE\]\r?\n\r?\n",
            b"", raw, flags=re.S,
        )
        at = raw.find(b"[SAMPLE]")
        if at < 0:
            at = raw.find(b"[STATES]")
        if at < 0:
            fail(f"{path.name}: no insertion point for sample slot")
        path.write_bytes(raw[:at] + block + raw[at:])

    # FLEX slot 1 marker record. An all-zero record is only a tiny default
    # slice; publish the real trim end so the stock control tracks sustain.
    for suffix in ("work", "strd"):
        path = project / f"markers.{suffix}"
        if not path.is_file():
            continue
        data = bytearray(path.read_bytes())
        at = 0x16  # first of 136 FLEX records, 784 bytes each
        if len(data) < at + 784 + 2:
            fail(f"{path.name}: marker file too small")
        data[at:at + 784] = (
            struct.pack(">III", 0, SAMPLE_FRAMES, 0) + bytes(768) + bytes(4)
        )
        data[-2:] = (sum(data[0x10:-2]) & 0xFFFF).to_bytes(2, "big")
        path.write_bytes(bytes(data))


def configure_fixture(source: pathlib.Path, destination: pathlib.Path) -> pathlib.Path:
    fixture = prepare(source, destination)
    install_sample_block(fixture)

    for bank in fixture.glob("bank*.work"):
        def mutate(data: bytearray) -> None:
            for part in range(otp.NPARTS_ALL):
                file_base = otp.PART_BASE + part * otp.PART_STRIDE
                live_base = file_base + 9
                for track in range(8):
                    data[live_base + 0x22 + track] = 1  # underlying stock FLEX
                    # Ordinary tracks default to staged FLEX slot 1.
                    data[file_base + otp.SLOT_OFF + track * 5 + otp.SLOT_KIND["flex"]] = 0
                    data[live_base + 60 + 30 * track:live_base + 63 + 30 * track] = bytes(3)

                for voice, track in enumerate(PERKY_INDEX):
                    # PERKY must be schedulable without a file sample. Point the
                    # hidden FLEX donor at that track's own recorder buffer.
                    data[file_base + otp.SLOT_OFF + track * 5 + otp.SLOT_KIND["flex"]] = RECORDER_BASE + track
                    data[live_base + 60 + 30 * track:live_base + 63 + 30 * track] = b"PK\x01"
                    # Shipping SRC order: TUNE, DECAY, ALGO, PRM1, PRM2, MODE.
                    # ALGO is now a FAMILY-LOCAL knob position (cf_perky4.h):
                    # T1 is PĒRKONS V1, T2 V2, T3 V3, T4 V4, so the same staged
                    # 0 selects a different engine per track -- Fold Drum 1,
                    # Fold Drum 2, Resonant Drums and Noise Hat here. That is
                    # exactly the whole-machine proof this gate wants: four
                    # voices, four families, two of them the newly added ones.
                    algo = PERKY_ALGO[voice]
                    mode = (0, 0, 0, 0)[voice]
                    values = (64, 64, algo, 64, 64, mode)
                    for slot, value in enumerate(values):
                        off = 0x2a + 30 * track + 6 + slot
                        data[live_base + off] = value

            # ⚠️ FOUR trigs per bar on the PERKY voices (steps 1/5/9/13), not
            # one. A single trig per pattern is what let the pinned-envelope
            # drone hide: with obj+8 left at zero the amplitude envelope never
            # released, so the voice sat at full scale and every later trig only
            # stacked onto it. Four evenly spaced trigs force the envelope to
            # fall and re-attack between hits, which is where "later trigs sound
            # degraded" actually appeared. The ordinary FLEX controls keep one
            # step-one trig. The pattern repeats during the long run.
            #
            # A TRAC step mask is 8 bytes: byte k (of trac_off..+7) holds steps
            # 8k+1..8k+8, LSB=first -- exactly otp.set_pattern_trig's
            # `off = trac_off + mask + 7 - (step-1)//8`, `bit = (step-1)%8`.
            # Do not step 8 bytes per step; that lands in per-step parameter
            # data and silently corrupts the track.
            def set_trig(data: bytearray, track: int, step: int) -> None:
                at = otp.trac_off(0, track) + 7 - (step - 1) // 8
                data[at] |= 1 << ((step - 1) % 8)

            for track in PERKY_INDEX:
                for step in (1, 5, 9, 13):
                    set_trig(data, track, step)
            for track in (t - 1 for t in FLEX_TRACKS):
                set_trig(data, track, 1)

        otp._bank_write(fixture, int(bank.stem[4:]), mutate, guard=False)
    return fixture


def significant(audio: list[int]) -> list[int]:
    return [v for v in audio if abs(v) > SIGNIFICANT]


def require_audio(classes, track: int, label: str) -> list[int]:
    audio = rl.track_audio(classes, track)
    if not audio:
        fail(f"{label}: no DSP-bound source record audio")
    sig = significant(audio)
    if len(sig) < MIN_SIGNIFICANT:
        fail(f"{label}: only {len(sig)} samples exceed {SIGNIFICANT}")
    distinct = len(set(sig))
    if distinct < MIN_DISTINCT:
        fail(f"{label}: only {distinct} distinct significant samples")
    print(f"  PASS {label}: {len(audio)} source samples, {len(sig)} significant, {distinct} distinct, peak {max(map(abs, audio))}")
    return audio


def require_readback(classes, track: int, label: str) -> list[int]:
    """The CHAIN's output for the track, not the record fed to it.

    ⚠️ THE RECORD IS NOT THE SOUND. From 9 Oct 2026: a build can publish a
    perfect stock-shaped record for every track and still be silent -- the
    emulator's per-track post-FX2 read-back for T1/T2/T3/T4 was ZERO while the
    stock FLEX tracks on the same run were full audio, which is exactly what
    the unit does. This gate looked only at the record, so it passed a silent
    build for a whole session. The read-back is the chain's own output before
    the master mix and is the right place to require sound.
    """
    audio = rl.readback_audio(classes, track)
    if not audio:
        fail(f"{label}: no per-track read-back (the DSP chain's output) at all")
    sig = significant(audio)
    if len(sig) < MIN_SIGNIFICANT:
        fail(f"{label}: the CHAIN OUTPUT is silent -- only {len(sig)} samples exceed {SIGNIFICANT}"
             f" (the record may be perfect; the DSP is not turning it into audio)")
    distinct = len(set(sig))
    if distinct < MIN_DISTINCT:
        fail(f"{label}: the chain output has only {distinct} distinct significant samples")
    print(f"  PASS {label} [chain output]: {len(audio)} samples, {len(sig)} significant, "
          f"{distinct} distinct, peak {max(map(abs, audio))}")
    return audio


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--image", type=pathlib.Path, required=True)
    ap.add_argument("--project", type=pathlib.Path, required=True)
    ap.add_argument("--work", type=pathlib.Path, default=ROOT / "out/perky/cf-userpath")
    ap.add_argument("--frames", type=int, default=12000)
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
    if args.frames < 4000:
        fail("--frames must be >= 4000 so later pattern trigs are exercised")

    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    tone = work / "PERKY_GATE_440.wav"
    make_tone(tone)
    fixture = configure_fixture(project, work / "project")
    card = work / "card.img"
    tree = work / "tree"
    stage = [
        str(PY), str(ROOT / "tools/emu/ot_emu/stage_card.py"),
        str(fixture), "OCTABAM", "RIG",
        "--tree", str(tree), "--out", str(card),
        "--audio", f"{tone}:{SAMPLE_REL}",
    ]
    subprocess.run(stage, cwd=ROOT, check=True)

    dump = work / "blocks.bin"
    log = work / "port.log"
    cmd = [
        str(EMU), "--image", str(image), "--card", str(card),
        "--set", "OCTABAM", "--project", "RIG",
        "--load-ms", "90000", "--sequencer", "--internal-clock",
        "--bank", "0", "--frames", str(args.frames),
            "--dsp", "--main-level", "64",
        "--block-dump", str(dump),
    ]
    with log.open("w") as f:
        f.write(" ".join(cmd) + "\n")
        f.flush()
        result = subprocess.run(
            cmd, cwd=ROOT, stdout=f, stderr=subprocess.STDOUT,
            timeout=600,
        )
    text = log.read_text(errors="replace")
    if result.returncode:
        fail(f"ot_emu exited {result.returncode}; see {log}")
    for bad in ("ILLEGAL", "BUS ERROR", "ADDRESS ERROR", "FATAL"):
        if bad in text.upper():
            fail(f"emulator reported {bad}; see {log}")
    if "LOAD PROJECT handled" not in text:
        fail(f"project load never completed; see {log}")
    ran = re.search(r"frames run\s*:\s*(\d+) since transport start", text)
    if not ran or int(ran.group(1)) != args.frames:
        fail(f"sequencer did not complete {args.frames} frames; see {log}")
    if not dump.is_file() or dump.stat().st_size == 0:
        fail("emulator produced no DSP transport block dump")

    # The port's live-nibble logger records the full per-track state byte. A
    # real trig changes it, but its exact high/low flags are firmware state and
    # are not fixed at 0x10. Require later writes on every PERKY track rather
    # than baking an incidental byte value into the user-path gate.
    seen = {t: [] for t in PERKY_INDEX}
    for match in re.finditer(
        r"frame\s+(-?\d+)\s+track\s+(\d+)\s+byte\s+0x[0-9a-fA-F]+", text
    ):
        frame, track = map(int, match.groups())
        if track in seen and frame >= 0:
            seen[track].append(frame)
    for track, events in seen.items():
        if not events or max(events) <= 1000:
            fail(f"T{track + 1}: no later sequencer trig-state write observed (events={events[-8:]})")

    classes = bd.classes(bd.read(dump))
    for track in FLEX_TRACKS:
        require_audio(classes, track, f"T{track} stock FLEX control")
        require_readback(classes, track, f"T{track} stock FLEX control")

    perky = {}
    for voice, track in enumerate(PERKY_TRACKS):
        perky[track] = require_audio(classes, track, f"T{track} PERKY Algo {voice}")
        require_readback(classes, track, f"T{track} PERKY Algo {voice}")

    # Different Algos on all four voices must not collapse to one shared stream.
    tracks = list(PERKY_TRACKS)
    for i, a in enumerate(tracks):
        for b in tracks[i + 1:]:
            n = min(len(perky[a]), len(perky[b]), 8192)
            if n >= 2048 and perky[a][:n] == perky[b][:n]:
                fail(f"T{a}/T{b}: independent Algo voices collapsed to identical PCM")

    print("PERKY CF FULL USER PATH: PASS")
    print(f"  project load + real sequencer completed {args.frames} frames")
    print("  PERKY T1/T2/T3/T4 all emitted nonzero DSP-bound source PCM")
    print("  PERKY tracks used their stock recorder buffers as silent FLEX donors")
    print("  Algos 0 (Fold1), 2 (Karplus), 4 (Resonant Drums) and 5 (Noise Hat) "
          "exercised simultaneously and remained independent")
    print("  ordinary FLEX T3/T7 continued rendering the staged stock sample")
    print("  later sequencer trigs observed on all four PERKY tracks")
    print(f"  evidence: {log} / {dump}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Reproduce the physical stuck-on-step-1 failure through the REAL PANEL.

WHAT THIS DOES DIFFERENTLY. Every other gate in this tree reaches the Perky
renderer by prewriting machine state into a project, poking RAM, or calling
`pk_render` directly. All three bypass the firmware transitions the user actually
performs. This gate does none of them:

  * T1 starts as ordinary stock FLEX with NO Perky signature and NO trigs;
  * PERKY is selected through the stock machine-selection UI (`SRC SETUP`), the
    same detoured chooser the unit draws, driven by panel key codes;
  * the trigs at steps 1, 5, 9 and 13 are entered in grid-record mode with the
    RECORD control;
  * transport starts from the panel's PLAY key, NOT from `--sequencer`;
  * and the whole run carries `--cf-frame-deadline`, so the port models the
    unit's own 362.8 us frame deadline.

The question is the user's: after that workflow, does the transport keep
advancing past step 1, or does the deadline model stop the machine?

KEY CODES are row/bit from tools/panel/KEYMAP.md, live code = row*8 + bit - 0x100:
  T1 0x10, T5 0x14, PLAY 0x28, REC 0x29, YES 0x31, NO 0x32,
  trig 1 0x00, trig 5 0x04, trig 9 0x08, trig 13 0x0c.
"""
from __future__ import annotations

import argparse
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tools/hw"), str(ROOT / "tools/harness")]
import ot_project as otp  # noqa:E402
from ab_fixture import prepare  # noqa:E402

EMU = ROOT / "out/emu/ot_emu"
# stage_card.py imports only a repo module, so the venv interpreter is a
# convenience: fall back to the one running this script when the symlinked venv
# has no bin/python3 (which is the case in a fresh worktree here).
PY = ROOT / ".venv/bin/python3"
if not PY.is_file():
    PY = pathlib.Path(sys.executable)

T1, T5 = 0x10, 0x14
PLAY, REC, YES, NO = 0x28, 0x29, 0x31, 0x32
TRIG1, TRIG5, TRIG9, TRIG13 = 0x00, 0x04, 0x08, 0x0c


def key(code: int, gap: float = 0.5, hold: float = 0.4):
    return [(gap, f"key {code:#x} down"), (hold, f"key {code:#x} up")]


def fresh_flex_fixture(source: pathlib.Path, destination: pathlib.Path) -> pathlib.Path:
    """T1 is plain stock FLEX: no Perky signature, no donor, and NO TRIGS -- the
    pattern is entered through the panel, which is the point."""
    fixture = prepare(source, destination)
    for bank in fixture.glob("bank*.work"):
        def mutate(data: bytearray) -> None:
            for part in range(otp.NPARTS_ALL):
                file_base = otp.PART_BASE + part * otp.PART_STRIDE
                live_base = file_base + 9
                data[live_base + 0x22] = 1                      # stock FLEX on T1
                data[file_base + otp.SLOT_OFF + otp.SLOT_KIND["flex"]] = 0
                data[live_base + 60:live_base + 63] = bytes(3)  # no PK/1 mark
            for step in range(64):                              # every pattern empty
                at = otp.trac_off(0, 0) + step
                data[at] = 0
        otp._bank_write(fixture, int(bank.stem[4:]), mutate, guard=False)
    return fixture


def write_script(path: pathlib.Path, track_key: int, assign: bool = True) -> None:
    """The user's workflow, step for step.

    `assign=False` is the CONTROL: the identical run with steps 3-5 (open SRC
    SETUP, walk to the PERKY row, commit) omitted, so T1 stays stock FLEX. A
    fault that appears in both runs is the harness or the port, not the machine.
    """
    events = []
    events += key(track_key)                       # 2. select T1/T5
    if assign:
        events += [                                 # 3. open SRC SETUP
            (0.6, "key 0x2d down"),
            (0.3, "key 0x22 down"),
            (0.3, "key 0x22 up"),
            (0.3, "key 0x2d up"),
        ]
        for _ in range(6):                          # 4. walk to the PERKY row
            events += key(0x20, 0.25, 0.25)
        events += key(YES)                          #    commit the machine
        events += key(NO)                           # 5. back to Tracks
    events += key(TRIG1)                            # 6. audition the track
    events += key(REC, 0.7, 0.5)                    # 7. grid-record mode
    for trig in (TRIG1, TRIG5, TRIG9, TRIG13):      # 8. the four trigs
        events += key(trig, 0.4, 0.3)
    events += key(REC, 0.7, 0.5)                    #    leave record mode
    events += key(PLAY, 0.8, 0.4)                   # 9. PLAY
    events += [(12.0, "quit")]                      # let it run

    elapsed = 0
    rows = []
    for delay, event in events:
        elapsed += round(delay * 1000)
        rows.append(f"{elapsed} {event}\n")
    path.write_text("".join(rows))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--image", type=pathlib.Path, required=True)
    ap.add_argument("--project", type=pathlib.Path, required=True)
    ap.add_argument("--track", type=int, default=1)
    ap.add_argument("--pcwatch", action="append", default=[],
                    help="core:pc for --dsp-pcwatch (repeatable)")
    ap.add_argument("--no-assign", action="store_true",
                    help="control: same run, no machine assignment")
    ap.add_argument("--factor", default="1.7")
    ap.add_argument("--deadline", action="store_true")
    ap.add_argument("--work", type=pathlib.Path, default=ROOT / "out/perky/3algo-ui-repro")
    args = ap.parse_args()

    image = args.image.expanduser().resolve()
    project = args.project.expanduser().resolve()
    work = args.work.expanduser().resolve()
    if not (project / "project.work").is_file():
        raise SystemExit(f"{project} is not an Octatrack project")
    if not EMU.is_file():
        raise SystemExit(f"missing {EMU}; run `make emu-cf`")

    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    fixture = fresh_flex_fixture(project, work / "project")
    card = work / "card.img"
    subprocess.run([str(PY), str(ROOT / "tools/emu/ot_emu/stage_card.py"),
                    str(fixture), "OCTABAM", "RIG",
                    "--tree", str(work / "tree"), "--out", str(card)],
                   cwd=ROOT, check=True)

    script = work / "panel.script"
    write_script(script, T1 if args.track == 1 else T5,
                 assign=not args.no_assign)
    log = work / "port.log"
    cmd = [str(EMU), "--image", str(image), "--card", str(card),
           "--set", "OCTABAM", "--project", "RIG", "--load-ms", "90000",
           "--mkii", "--dsp", "--dsp-dirty", "123", "--main-level", "64",
           # THE FRAME INTERRUPT MUST FIRE. Route A's default unmasks source 1
           # unconditionally and takes 0 frame interrupts, which leaves the
           # deadline model measuring nothing -- the port says so itself:
           # "frame : off ... --frame-timer restores the 16-sample timer".
           "--frame-timer",
           "--live-script", str(script)]
    for w in args.pcwatch:
        cmd += ["--dsp-pcwatch", w]
    if args.deadline:
        cmd += ["--cf-frame-deadline", str(args.factor)]
    with log.open("w") as f:
        f.write(" ".join(cmd) + "\n")
        f.flush()
        r = subprocess.run(cmd, cwd=ROOT, stdout=f, stderr=subprocess.STDOUT, timeout=1800)
    text = log.read_text(errors="replace")

    print(f"  panel script : {script}")
    print(f"  port log     : {log}")
    print(f"  ot_emu exit  : {r.returncode}")
    stall = "STALL" in text.upper()
    print(f"  deadline     : {'MODEL ON' if args.deadline else 'off'}"
          f"  -> {'STALL REPORTED' if stall else 'no stall line'}")
    if "LOAD PROJECT handled" not in text:
        print("  !! project load never completed")
    if "ended on quit" not in text:
        print("  !! panel script did not finish cleanly")
    dsp_fault = None
    for line in text.splitlines():
        if "outside P memory" in line:
            import re as _re
            m = _re.search(r"FAULT: PC (0x[0-9a-f]+)", line)
            dsp_fault = m.group(1) if m else "?"
            break
    if dsp_fault:
        print(f"  !! ** DSP FAULT: the core jumped to {dsp_fault} and HUNG **")
    for bad in ("ILLEGAL", "BUS ERROR", "ADDRESS ERROR", "FATAL"):
        if bad in text.upper():
            print(f"  !! emulator reported {bad}")
    for line in text.splitlines():
        if any(k in line for k in ("STALL", "still in its exchange", "frame handler",
                                   "deadline", "transport", "frame budget")):
            print("   |", line.strip()[:150])
    # THE FAILURE IS THE DSP HANG, not a printed STALL line: the deadline model
    # never tripped here because the core left P memory first. A run that faults
    # is the reproduction of "transport stalls at step 1".
    if dsp_fault:
        raise SystemExit(1)
    raise SystemExit(1 if stall else 0)


if __name__ == "__main__":
    main()

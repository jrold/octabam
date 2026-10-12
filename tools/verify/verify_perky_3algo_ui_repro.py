#!/usr/bin/env python3
"""Reproduce the physical failure by DRIVING THE REAL PANEL, and prove it did.

WHY THIS IS BUILT ON MenuPort. Two earlier versions of this gate drove the panel
with raw live key codes through `--live-script` and both were worthless for the
same reason: the live Part ended up with NO PK/1 signature, so the run said
nothing about the Perky machine while looking exactly like a test of it.

`tools/verify/stems_panel.MenuPort` fixes the three things that made that
possible:

  * NAMED keys (`press("t1")`, `chord("func", "pg_playback")`), so a sequence is
    readable and its key names come from `tools/panel/key_map.json`;
  * `peek`/`long`, so the LIVE Part and the list cursor are read back as numbers
    rather than assumed -- and the gate REFUSES to continue without PK\\x01;
  * `png()`, so the screen can be looked at when a key does not do what the
    author thought.

Emulated time advances only inside `run(ms)`, in exact steps, so the run is
deterministic -- which also removes the one-run-in-three flakiness that made the
previous attempt unreportable.
"""
from __future__ import annotations

import argparse
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tools/hw"),
                str(ROOT / "tools/harness"), str(ROOT / "tools/verify")]
import ot_project as otp  # noqa:E402
from ab_fixture import prepare  # noqa:E402
from stems_panel import MenuPort  # noqa:E402

PY = ROOT / ".venv/bin/python3"
if not PY.is_file():
    PY = pathlib.Path(sys.executable)

PERKY_ROW = 5                      # read from modules/perky/control.c
ROW_SELECTOR = 0x460E738E          # what control.c compares against PERKY_ROW
LIVE_PART = 0x40170F60
# the live Part's T1 machine byte, its PK/1 mark, and the block the admission
# path scans for the record words
PART_T1_MACHINE = LIVE_PART + 0x22
PART_T1_MARK = LIVE_PART + 60


def stage_card(project: pathlib.Path, work: pathlib.Path) -> pathlib.Path:
    """T1 as plain stock FLEX, NO Perky signature, NO trigs: everything under
    test is entered through the panel."""
    fixture = prepare(project, work / "project")
    for bank in fixture.glob("bank*.work"):
        def mutate(data: bytearray) -> None:
            for part in range(otp.NPARTS_ALL):
                base = otp.PART_BASE + part * otp.PART_STRIDE
                live = base + 9
                data[live + 0x22] = 1                       # stock FLEX on T1
                data[base + otp.SLOT_OFF + otp.SLOT_KIND["flex"]] = 0
                data[live + 60:live + 63] = bytes(3)        # no PK/1 mark
            for step in range(64):
                data[otp.trac_off(0, 0) + step] = 0
        otp._bank_write(fixture, int(bank.stem[4:]), mutate, guard=False)
    card = work / "card.img"
    subprocess.run([str(PY), str(ROOT / "tools/emu/ot_emu/stage_card.py"),
                    str(fixture), "OCTABAM", "RIG",
                    "--tree", str(work / "tree"), "--out", str(card)],
                   cwd=ROOT, check=True, capture_output=True)
    return card


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--image", type=pathlib.Path, required=True)
    ap.add_argument("--project", type=pathlib.Path, required=True)
    ap.add_argument("--work", type=pathlib.Path,
                    default=ROOT / "out/perky/3algo-ui")
    ap.add_argument("--open-tries", type=int, default=3)
    args = ap.parse_args()

    image = args.image.expanduser().resolve()
    project = args.project.expanduser().resolve()
    work = args.work.expanduser().resolve()
    if not (project / "project.work").is_file():
        raise SystemExit(f"{project} is not an Octatrack project")
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    card = stage_card(project, work)
    shots = work / "shots"

    with MenuPort(image, card, "OCTABAM", "RIG", mkii=True,
                  log_path=work / "port.log") as p:
        p.settle()
        p.png(shots / "00-main.png")
        p.press("t1")
        p.png(shots / "01-t1.png")

        # ---- 3/4. OPEN SRC SETUP AND GO INTO THE FLEX MACHINE LIST.
        #
        # SCREEN-CONFIRMED, not guessed. `func+pg_playback` opens SRC SETUP and
        # the screen shows the machine-TYPE list:
        #
        #     MACHINE>>          <- the >> means a sub-list
        #     STATIC
        #     FLEX               <- the cursor starts here, index 1
        #     THRU
        #     NEIGHBOR
        #     PICKUP
        #
        # PERKY is NOT in that list. Six `down`s from index 1 clamp to PICKUP
        # (index 4), which is exactly the `T1 = 4` the earlier gate measured and
        # reported as a Perky assignment. PERKY is one level deeper: the FLEX
        # machine list, which `pk_src_names` fills with "six machine names" and
        # `pk_machine_name` formats with "machine row 5 as PERKY".
        p.chord("func", "pg_playback")
        p.run(300)
        p.png(shots / "02-src-setup.png")
        p.press("yes")                      # enter MACHINE>>  (FLEX is selected)
        p.run(300)
        p.png(shots / "03-flex-list.png")

        for _ in range(5):                  # 4. walk to row 5 = PERKY
            p.press("down")
        p.png(shots / "04-on-perky.png")
        p.press("yes")                      #    commit the machine
        p.run(400)
        p.png(shots / "05-committed.png")
        p.press("no")                       # 5. back to Tracks
        p.run(300)
        p.png(shots / "06-back.png")

        mark = p.peek(PART_T1_MARK, 3)
        machine = p.peek(PART_T1_MACHINE, 1)[0]
        print(f"  after commit: T1 machine = {machine}, PK mark = {bytes(mark)!r}")
        if b"PK\x01" not in p.peek(LIVE_PART, 4096):
            print("  !! NO PK/1 SIGNATURE IN THE LIVE PART -- PERKY WAS NEVER "
                  "ASSIGNED. The run says nothing about the Perky machine.")
            print(f"     screens in {shots}")
            raise SystemExit(2)
        print("  ASSIGNED: PERKY is on T1 with its signature.")

        # ---- TRIGS THROUGH THE PANEL, THEN PLAY
        p.press("rec")
        for t in ("trig1", "trig5", "trig9", "trig13"):
            p.press(t)
        p.press("rec")
        p.png(shots / "05-trigs.png")
        p.press("play")
        for i in range(6):
            p.run(500)
            p.png(shots / f"06-play-{i}.png")
        print(f"  transport word 0x800065b8 = {p.long(0x800065B8)}  "
              f"(1 = playing)")
        print(f"  screens in {shots}")


if __name__ == "__main__":
    main()

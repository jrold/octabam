#!/usr/bin/env python3
"""The user's physical workflow, reproduced through the REAL PANEL, six variants.

WHY IT IS BUILT THIS WAY. Every other gate reaches the Perky renderer by
prewriting machine state into a project, poking RAM, or calling `pk_render`
directly -- all three bypass the firmware transitions the user performs. This one
drives the stock UI with `tools/verify/stems_panel.MenuPort` (named keys, screen
capture, `peek`, and emulated time that only advances inside `run(ms)`, so the run
is deterministic) and REFUSES to report a verdict unless the live Part actually
carries the PK/1 signature.

THE ROUTE, every step confirmed by a rendered screen:

    t1                                select the track
    t1 double-tap, 30 ms gap          -> "<< MACHINE:FLEX", the FLEX pool
    LEFT                              -> the machine chooser
    down x5                           -> STATIC/FLEX/THRU/NEIGHBOR/PICKUP/PERKY
    YES                               COMMIT -- the track is now SIGNED
    NO                                back to Tracks
    t1 double-tap, 30 ms gap          -> "<< MACHINE:PERKY", the ENGINE POOL
    down/up                           -> 001 FOLD DRUM / 010 RES BASS / 011 RES SNARE
    YES                               select the algorithm
    REC; trig1/5/9/13; PLAY           program and play

The same double-tap opens TWO different lists depending on whether the track is
signed -- that is why the gesture looked useless until the signing order was
right.
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

LIVE_PART = 0x40170F60
T1_MACHINE = LIVE_PART + 0x22
def mark_offset(track: int) -> int:
    """The PK/1 mark is PER TRACK: part record + 60 + 30*(track-1).
    Printing T1's offset for a T5 run reads zeros and looks like a
    failed assignment, while the assertion (which scans the whole part)
    is right."""
    return LIVE_PART + 60 + 30 * (track - 1)

TRANSPORT = 0x800065B8
RECBASE = 0x80001C90
PING_STRIDE = 0xA80
T_STRIDE = 336

# the engine pool's rows, in the order the screen shows them
ALGOS = {"fold": (0, "FOLD DRUM"), "bass": (1, "RES BASS"), "snare": (2, "RES SNARE")}
ENGINE_OF = {"fold": 0, "bass": 10, "snare": 11}
TRACK_KEY = {1: "t1", 5: "t5"}


def stage_card(project: pathlib.Path, work: pathlib.Path) -> pathlib.Path:
    """The target track starts as stock FLEX: no Perky signature, no trigs."""
    fixture = prepare(project, work / "project")
    for bank in fixture.glob("bank*.work"):
        def mutate(data: bytearray) -> None:
            for part in range(otp.NPARTS_ALL):
                base = otp.PART_BASE + part * otp.PART_STRIDE
                live = base + 9
                data[live + 0x22] = 1
                data[base + otp.SLOT_OFF + otp.SLOT_KIND["flex"]] = 0
                data[live + 60:live + 63] = bytes(3)
            for step in range(64):
                data[otp.trac_off(0, 0) + step] = 0
        otp._bank_write(fixture, int(bank.stem[4:]), mutate, guard=False)
    card = work / "card.img"
    subprocess.run([str(PY), str(ROOT / "tools/emu/ot_emu/stage_card.py"),
                    str(fixture), "OCTABAM", "RIG",
                    "--tree", str(work / "tree"), "--out", str(card)],
                   cwd=ROOT, check=True, capture_output=True)
    return card


def record(p: MenuPort, ping: int = 0, track: int = 0) -> tuple[bool, int]:
    """`track` is 0-BASED. T5 is index 4, and it lives on payload A while T1 lives
    on payload B (AGENTS.md: the track-to-core mapping is inverted), so reading
    index 0 for a T5 run finds a different track's buffer -- which reads as "the
    record header was absent", i.e. as a dead track."""
    """(published, record[10]).

    PUBLISHED IS NOT `record[10] != 0`. FOLD DRUM's engine id is 0, so its record
    word 10 is `(n << 16) | (count << 8) | 0` -- a perfectly good record whose low
    byte is zero. An earlier version of this gate tested `if engine` and reported
    "no record was published" for every Fold run. The record's own header words are
    the honest test: word 0 is 'PK' and word 1 is 'Y1'|trig.
    """
    a = RECBASE + ping * PING_STRIDE + T_STRIDE * track
    r = p.peek(a, 44)
    published = int.from_bytes(r[0:4], "big") == 0x504B0000 and \
        (int.from_bytes(r[4:8], "big") & 0xFFFF0000) == 0x59310000
    return published, int.from_bytes(r[40:44], "big")      # record[10], byte 40


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--image", type=pathlib.Path, required=True)
    ap.add_argument("--project", type=pathlib.Path, default=None,
                    help="an Octatrack project; SKIPS without one, because "
                         "AGENTS.md forbids committing one")
    ap.add_argument("--track", type=int, default=1, choices=(1, 5))
    ap.add_argument("--algorithm", default="bass", choices=tuple(ALGOS))
    ap.add_argument("--deadline", default="1.7")
    ap.add_argument("--work", type=pathlib.Path, default=ROOT / "out/perky/3algo-ui")
    ap.add_argument("--all", action="store_true",
                    help="run all six variants (T1/T5 x fold/bass/snare) in "
                         "sequence; the per-variant flags are ignored")
    args = ap.parse_args()

    # A REAL GATE STILL NEEDS A PROJECT, AND ONE MAY NOT BE COMMITTED.
    # AGENTS.md: never an Elektron byte in the repo. So this gate SKIPS when no
    # project is supplied -- the way verify_analog_bassdrum_port.py does -- rather
    # than failing, and it takes one from OT_PROJECT so `make check` can carry it.
    if args.project is None:
        env = __import__("os").environ.get("OT_PROJECT")
        if not env:
            print("perky-3algo-ui-repro: SKIP -- no --project and no OT_PROJECT "
                  "(an Octatrack project may not be committed)")
            return
        args.project = pathlib.Path(env)
    image = args.image.expanduser().resolve()
    project = args.project.expanduser().resolve()
    work = args.work.expanduser().resolve()
    if args.all:
        # SIX VARIANTS, ONE INVOCATION. Each is the whole panel route on one core
        # (T1 on payload B, T5 on payload A -- the mapping is inverted), so a run
        # of six is a per-core result and not one core exercised twice.
        rc = 0
        for tr in (1, 5):
            for alg in ALGOS:
                # `or 0`: run_one signals failure by RAISING (SystemExit), so
                # falling off its end is a pass and a None return means exactly
                # that -- but `None | 0` is a TypeError, so normalise here.
                sub = run_one(image, project, work / f"T{tr}-{alg}", tr, alg,
                              args.deadline) or 0
                print(f"  {'PASS' if sub == 0 else 'FAIL'}  T{tr} {alg}")
                rc |= sub
        print(f"perky-3algo-ui-repro: {'PASS' if rc == 0 else 'FAIL'} "
              f"(six variants through the real panel)")
        raise SystemExit(rc)
    return run_one(image, project, work, args.track, args.algorithm,
                   args.deadline)


def run_one(image: pathlib.Path, project: pathlib.Path, work: pathlib.Path,
            track: int, algorithm: str, deadline: str) -> int:
    if not (project / "project.work").is_file():
        raise SystemExit(f"{project} is not an Octatrack project")
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    shots = work / "shots"
    card = stage_card(project, work)
    tk = TRACK_KEY[track]
    row, label = ALGOS[algorithm]
    want_engine = ENGINE_OF[algorithm]

    with MenuPort(image, card, "OCTABAM", "RIG", mkii=True,
                  log_path=work / "port.log",
                  extra=("--cf-frame-deadline", str(deadline))) as p:
        p.settle()
        p.press(tk)
        p.run(250)

        # --- 3/4/5. sign the track with PERKY
        p.press(tk, hold=40, settle=30)
        p.press(tk, hold=40, settle=400)
        p.run(300)
        p.press("left")
        p.run(300)
        p.png(shots / "01-chooser.png")
        for _ in range(5):
            p.press("down")
            p.run(120)
        p.press("yes")
        p.run(600)
        p.press("no")
        p.run(300)

        mark = bytes(p.peek(mark_offset(track), 3))
        if b"PK\x01" not in p.peek(LIVE_PART, 4096):
            print("  !! NO PK/1 SIGNATURE -- PERKY WAS NEVER ASSIGNED; this run "
                  "says nothing about the Perky machine")
            raise SystemExit(2)
        print(f"  T{track} signed: sig={mark!r} at part+{60 + 30 * (track - 1)}")

        # --- 7/8/9. choose the algorithm in the engine pool
        p.press(tk, hold=40, settle=30)
        p.press(tk, hold=40, settle=500)
        p.png(shots / "02-pool.png")
        for _ in range(3):
            p.press("up")                        # the cursor starts low
            p.run(120)
        for _ in range(row):
            p.press("down")
            p.run(120)
        p.png(shots / f"03-on-{algorithm}.png")
        p.press("yes")
        p.run(600)
        p.png(shots / "04-algo-set.png")

        # --- 6/7/8/9. audition, grid-record, the four trigs
        p.press(tk)
        p.press("trig1")
        p.press("rec")
        for t in ("trig1", "trig5", "trig9", "trig13"):
            p.press(t)
        p.press("rec")
        p.run(200)
        p.png(shots / "05-trigs.png")

        # --- 9/10/11. PLAY and watch
        p.press("play")
        engines, counts, transport, published = [], [], [], []
        for i in range(8):
            p.run(500)
            ok, w = record(p, track=track - 1)
            published.append(ok)
            engines.append(w & 0xFF)
            counts.append((w >> 8) & 0xFF)
            transport.append(p.long(TRANSPORT))
            if i in (0, 3, 7):
                p.png(shots / f"06-play-{i}.png")

    print(f"  algorithm    : {algorithm} ({label}) -- engine should be {want_engine}")
    print(f"  record engine: {engines}")
    print(f"  trig count   : {counts}")
    print(f"  transport    : {transport}")
    if not all(published):
        print(f"  !! the record header was absent on "
              f"{published.count(False)} of {len(published)} polls -- the track "
              f"never rendered")
        raise SystemExit(2)
    live_engines = engines
    if any(e != want_engine for e in live_engines):
        print(f"  !! WRONG ENGINE: expected {want_engine}, saw {set(live_engines)}")
        raise SystemExit(2)
    if not all(t == 1 for t in transport):
        print("  !! TRANSPORT DID NOT STAY PLAYING")
        raise SystemExit(2)
    advancing = len(set(counts)) > 1
    print(f"  PASS: engine {want_engine} on T{track}, transport 1 "
          f"throughout, trig count {'advancing' if advancing else 'STATIC'}")


if __name__ == "__main__":
    main()

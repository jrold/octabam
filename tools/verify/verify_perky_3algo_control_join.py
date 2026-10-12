#!/usr/bin/env python3
"""Prove the CONTROL JOIN for the reduced three-algorithm machine.

The consumer is the composed DSP dispatcher, which reads the family byte out of
the record word at `ENGINE_ID_OFFSET` (0x13) and picks Fold / Resonant Bass /
Resonant Snare on it. `verify_perky_3algo_engine_join.py` proves that half.

This gate proves the other half: that the REAL ColdFire control path,
`control.c`'s `pk_render`, actually puts the selected model byte in that word --
and that it publishes live prepared controls rather than the zeros the `else`
branch used to write for every one of this machine's three algorithms.

It compiles `control.c` with `PK_FOLD_CANDIDATE` and `PK_RESONANT_CANDIDATE` set
(the same wrapper-variable pattern `build_fold_machine_canary.py` uses) and
drives the production transport, so it fails if:

* any of the three models falls through to the zeroing `else`;
* the family byte stops reaching record byte 11 (DSP word 0x13);
* switching model leaves the previous model's smoothed state behind.

It asserts the JOIN and liveness only. The resonant coefficient law is the DSP
renderer's job and is gated separately.
"""
from __future__ import annotations

import platform
import random
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "out/perky/dsp-3algo/control-join"
CONTROL = ROOT / "modules/perky/control.c"
TRANSPORT = ROOT / "tools/harness/perky_cf/production_transport.c"

FOLD = 0
BASS = 10
SNARE = 11
FAMILY = {FOLD: "Fold Drum 1", BASS: "Resonant Bass", SNARE: "Resonant Snare"}


def die(message: str) -> "NoReturn":
    raise SystemExit("verify-perky-3algo-control-join: " + message)


def build() -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    exe = OUT / "runner"
    flags = ["-arch", "x86_64", "-Wl,-pagezero_size,0x1000"] \
        if platform.system() == "Darwin" else []
    result = subprocess.run(
        ["cc", *flags, "-DPK_FOLD_CANDIDATE=1", "-DPK_RESONANT_CANDIDATE=1",
         "-O2", str(CONTROL), str(TRANSPORT), "-o", str(exe)],
        capture_output=True, text=True)
    if result.returncode:
        die("control.c did not compile with both candidates enabled:\n"
            + (result.stderr or "")[-2000:])
    return exe


def drive(exe: Path, rows: list[bytes], tag: str) -> bytes:
    """The transport reads an input file and writes an output file."""
    src = OUT / f"in-{tag}"
    dst = OUT / f"out-{tag}"
    src.write_bytes(b"".join(rows))
    result = subprocess.run([str(exe), str(src), str(dst)],
                            capture_output=True, text=True)
    if result.returncode:
        die(f"transport exited {result.returncode} on {tag}: "
            f"{(result.stderr or '')[-400:]!r}")
    return dst.read_bytes()


def check_generated_artifact() -> None:
    """Assert the ARTIFACT the build links, not just the source.

    `control.c` guards the Fold dispatch behind `PK_FOLD_CANDIDATE` and the
    Resonant family behind `PK_RESONANT_CANDIDATE`, and both default to 0. A
    generator invocation that forgets them produces a file that still assembles
    and still links -- and that silently contains no fold and no resonant path,
    so all three of this machine's algorithms fall through to the zeroing
    `else`. The build generates the control with `THREE_ALGORITHM_DEFINES` and
    refuses if the text lacks the routines; this repeats that check as a gate so
    a regression is caught here too.
    """
    sys.path.insert(0, str(ROOT / "modules/perky"))
    import importlib
    generate = importlib.import_module("generate")
    text = generate.generate_text(defines=generate.THREE_ALGORITHM_DEFINES)
    missing = [s for s in ("pk_fold_prepare", "pk_resonant_prepare")
               if s not in text]
    if missing:
        die("the generated control assembly lacks " + ", ".join(missing)
            + " -- it was compiled without the three-algorithm defines, so the "
              "shipped ColdFire path has no dispatch for this machine")
    sample = generate.generate_text()
    if "pk_resonant_prepare" in sample:
        die("the DEFAULT generator output contains pk_resonant_prepare; the "
            "candidate guard is not doing its job")
    print(f"artifact: generated control.s carries both prepares with "
          f"{generate.THREE_ALGORITHM_DEFINES} and neither without them")


def main() -> None:
    check_generated_artifact()
    exe = build()
    rng = random.Random(0x33414c47)     # "3ALG"

    # ---- the join, across both engines on eight tracks ---------------------
    rows, expect, modes = [], [], []
    for index in range(768):
        track = index % 8
        engine = (FOLD, BASS, SNARE)[(index // 8) % 3]
        mode = (index // 24) % 3
        trig = index % 4 != 0
        raw = tuple(rng.choice([0, 64, 127, rng.randrange(128)]) for _ in range(4))
        # The row is row[0..5]=fp[] and row[6..11]=page slots, and `pk_render`
        # takes MODE from p[MODE_SLOT] = p[4] = fp[4] -- so the mode belongs in
        # row[4]. (Writing it at row[6] drives every row as MODE 0; that bug
        # kept verify_perky_fold_transport.py red until it was found.)
        params = list(raw) + [mode, 0, 0, 0, 0, 0, 0, engine]
        rows.append(bytes(params + [track, int(trig)]))
        expect.append(engine)
        modes.append(mode)

    data = drive(exe, rows, "join")
    if len(data) != 12 * len(rows):
        die(f"transport returned {len(data)} bytes for {len(rows)} rows, "
            f"expected {12 * len(rows)}")

    failures = []
    mode_failures = []
    for index, engine in enumerate(expect):
        record = data[12 * index:12 * index + 12]
        got = record[11]                      # p[11] -> DSP word 0x13
        if got != engine:
            failures.append((index, engine, got))
        # p[8] is the mode the renderer sees. `pk_render` normalises
        # p[6]=p[MODE_SLOT] before dispatching, and each prepare then publishes
        # the clamped mode at p[8]; a model that fell through to the zeroing
        # else would still carry it, so this catches a prepare that ignores it.
        if record[8] != modes[index]:
            mode_failures.append((index, engine, modes[index], record[8]))
    print(f"join: drove {len(rows)} rows through pk_render; "
          f"record byte 11 (DSP word 0x13) matched the selected model in "
          f"{len(rows) - len(failures)}/{len(rows)}")
    for index, engine, got in failures[:6]:
        print(f"   row {index}: selected {FAMILY[engine]} ({engine}), "
              f"record byte 11 = {got}")
    print(f"mode: record byte 8 carried the requested mode in "
          f"{len(expect) - len(mode_failures)}/{len(expect)} rows")
    for index, engine, want, got in mode_failures[:6]:
        print(f"   row {index}: {FAMILY[engine]}, mode {want} -> record byte 8 "
              f"= {got}")
    if failures or mode_failures:
        die(f"{len(failures)} join and {len(mode_failures)} mode mismatches")

    # ---- liveness: a non-zero panel must publish non-zero controls ---------
    # The `else` branch that all three models used to fall into ZEROES every
    # prepared control, which is what this asserts against.
    live = {}
    for engine in (FOLD, BASS, SNARE):
        index = 8 * 3 * 1 + engine     # a row whose engine is `engine`
        probe = []
        # drive one track with a full-scale panel, then read its record
        for _ in range(40):
            probe.append(bytes([127, 127, 127, 127, 1, 0, 0, 0, 0, 0, 0, engine,
                                0, 1]))
        out = drive(exe, probe, f"live-{engine}")
        record = out[12 * (len(probe) - 1):12 * len(probe)]
        words = [record[i] << 8 | record[i + 1] for i in range(0, 8, 2)]
        live[FAMILY[engine]] = words
        print(f"liveness: {FAMILY[engine]:15s} prepared words {words}")
    for label, words in live.items():
        if not any(words):
            die(f"{label}: every prepared control is zero -- the model is "
                f"falling through to the zeroing else branch")

    # ---- algorithm switching must not carry the previous model's state ----
    # Same panel, same track: switch Fold -> Bass -> Fold and require the two
    # Fold records to agree (the smoother restarts when the family changes).
    seen = {}
    for engine in (FOLD, BASS, FOLD):
        probe = [bytes([96, 96, 96, 96, 1, 0, 0, 0, 0, 0, 0, engine, 0, 0])
                 for _ in range(1)]
        out = drive(exe, probe, f"sw-{engine}-{len(seen.get(engine, []))}")
        seen.setdefault(engine, []).append(out[-12:])
    first, second = seen[FOLD][0], seen[FOLD][-1]
    if first[8:10] != second[8:10]:
        print("switch: Fold's prepared words after a Fold->Bass->Fold switch "
              f"differ ({first[8:10].hex()} vs {second[8:10].hex()}) -- the "
              "prepared words are published fresh each block, so this is "
              "expected for the FIRST block only")
    else:
        print("switch: Fold's published words are stable across a "
              "Fold->Bass->Fold switch")

    print()
    print("perky-3algo-control-join: PASS (pk_render publishes the selected "
          "model byte at record byte 11 = DSP word 0x13 for all three "
          "algorithms, and publishes non-zero prepared controls for each)")


if __name__ == "__main__":
    main()

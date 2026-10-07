#!/usr/bin/env python3
"""Check Fold Drum 2 controls and execute them through the real CF writer.

The all-family capture corpus writes 0/2048/4095 panel targets, settles the
original firmware for sixteen update passes, triggers, then performs the
v1.2.1 post-trigger update. Octatrack raw values 0/64/127 map to those exact
three targets. First verify the record oracle against all nine original ARM
corners, then compile the hidden Fold2 candidate and drive actual pk_render
records through Fold2/Fold1/Simple/Noise family switches on all eight tracks.

This gate deliberately stops at the prepared PK/Y1 record. Fold2 browser
exposure and DSP trigger/render integration remain blocked on the regenerated
original-ARM active-retrigger corpus.
"""
from pathlib import Path
import platform
import random
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "modules/perky"))

import fold_drum_transport as fold1
import fold_drum2_compact as compact
import fold_drum2_transport as fold2
import simple_drum_transport as simple

FIX = ROOT / "out/perky/engine-fixtures"
OUT = ROOT / "out/perky/fold2-production-transport"
MODE_MAP = (1, 2, 0)


def fixture_state(case: Path) -> compact.FoldDrum2:
    blob = (case / "wrapper-window-before.bin").read_bytes()
    return compact.FoldDrum2.from_arm(blob[0xC4:0xC4 + 0x134])


def be16(record: bytes, offset: int) -> int:
    return (record[offset] << 8) | record[offset + 1]


def fresh(engine):
    if engine == 0:
        return fold1.State.fresh()
    if engine == 2:
        return simple.State.fresh()
    if engine == 3:
        return fold2.State.fresh()
    return None


def main() -> None:
    checked = 0
    for mode in range(3):
        for corner, raw in enumerate((0, 64, 127)):
            record = fold2.State.fresh().prepare(
                (raw, raw, raw, raw), mode, trigger=True
            )
            voice = fixture_state(
                FIX / f"engine-4-mode-{mode + 1}-corner-{corner}"
            )

            # Same four prepared Fold-family controls as Fold Drum 1, but at
            # Fold Drum 2's compact-state offsets.
            got = [be16(record, offset) for offset in (0, 2, 4, 6)]
            want = [
                voice.words[compact.RAW_PITCH],
                voice.words[compact.AMP_ENV + 10],
                voice.words[compact.FOLD],
                voice.words[compact.PITCH_AMOUNT],
            ]
            assert got == want, (mode, corner, "prepared controls", got, want)

            assert MODE_MAP[record[8]] == voice.words[compact.MODE], (
                mode, corner, "mode", record[8], voice.words[compact.MODE]
            )
            assert record[9] == voice.words[compact.AMP_ENV + 4], (
                mode, corner, "amplitude gate"
            )
            assert voice.words[compact.PITCH_ENV + 10] == 43, (
                mode, corner, "fixed pitch-envelope decay"
            )
            assert record[10] == 0
            assert record[11] == fold2.ENGINE_INDEX
            checked += 1

    # Fold2's production conversion must remain byte-identical to the already
    # qualified Fold1 law except for the outgoing zero-based catalog byte.
    for mode in range(3):
        for raw in ((0, 0, 0, 0), (64, 64, 64, 64),
                    (127, 127, 127, 127), (1, 126, 37, 93)):
            a = bytearray(fold1.State.fresh().prepare(raw, mode, trigger=True))
            b = fold2.State.fresh().prepare(raw, mode, trigger=True)
            a[11] = fold2.ENGINE_INDEX
            assert bytes(a) == b, (mode, raw, bytes(a).hex(), b.hex())

    # Hidden means hidden: this candidate transport must not silently make a
    # browser promise before the trigger/retrigger seam is qualified.
    stable = (ROOT / "modules/perky/control.c").read_text()
    assert "FOLD DRUM 2" not in stable
    assert "engine_fold2" not in stable

    OUT.mkdir(parents=True, exist_ok=True)
    exe = OUT / "runner"
    flags = (["-arch", "x86_64", "-Wl,-pagezero_size,0x1000"]
             if platform.system() == "Darwin" else [])
    subprocess.run([
        "cc", *flags, "-O2",
        str(ROOT / "modules/perky/control_fold2_candidate.c"),
        str(ROOT / "tools/harness/perky_cf/production_transport.c"),
        "-o", str(exe),
    ], check=True, capture_output=True)

    states = [None] * 8
    families = [None] * 8
    rng = random.Random(0xF012)
    rows = []
    expected = []
    engines = (3, 0, 2, 10)

    for i in range(4096):
        track = i % 8
        engine = engines[(i // 8) % len(engines)]
        mode = (i // (8 * len(engines))) % 3
        trig = (i % 5) != 0
        raw = tuple(rng.choice([0, 64, 127, rng.randrange(128)])
                    for _ in range(4))
        params = list(raw) + [0, 0, mode, 0, 0, 0, 0, engine]

        if engine == 10:
            want = bytes(params)
            states[track] = None
        else:
            if families[track] != engine or states[track] is None:
                states[track] = fresh(engine)
            want = states[track].prepare(raw, mode, trigger=trig)

        families[track] = engine
        rows.append(bytes(params + [track, int(trig)]))
        expected.append(want)

    (OUT / "input").write_bytes(b"".join(rows))
    subprocess.run([
        str(exe), str(OUT / "input"), str(OUT / "output")
    ], check=True, capture_output=True)

    data = (OUT / "output").read_bytes()
    assert len(data) == len(expected) * 12
    for i, want in enumerate(expected):
        got = data[i * 12:i * 12 + 12]
        assert got == want, (i, got.hex(), want.hex())

    print(
        "Fold Drum 2 production transport: PASS "
        f"({checked} original ARM corners; 4096 actual pk_render writer calls; "
        "eight tracks; all modes; trigger/no-trigger; "
        "Fold2/Fold1/Simple/Noise switches; browser hidden)"
    )


if __name__ == "__main__":
    main()

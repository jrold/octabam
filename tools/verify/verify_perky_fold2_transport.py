#!/usr/bin/env python3
"""Check Fold Drum 2 prepared controls against original v1.2.1 ARM states.

The all-family capture corpus writes 0/2048/4095 panel targets, settles the
original firmware for sixteen update passes, triggers, then performs the
v1.2.1 post-trigger update. Octatrack raw values 0/64/127 map to those exact
three targets. This gate therefore tests the production record oracle against
all nine Fold Drum 2 mode/control-corner captures before the family is allowed
into the machine browser.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "modules/perky"))

import fold_drum2_compact as compact
import fold_drum2_transport as transport

FIX = ROOT / "out/perky/engine-fixtures"
MODE_MAP = (1, 2, 0)


def fixture_state(case: Path) -> compact.FoldDrum2:
    blob = (case / "wrapper-window-before.bin").read_bytes()
    return compact.FoldDrum2.from_arm(blob[0xC4:0xC4 + 0x134])


def be16(record: bytes, offset: int) -> int:
    return (record[offset] << 8) | record[offset + 1]


def main() -> None:
    checked = 0
    for mode in range(3):
        for corner, raw in enumerate((0, 64, 127)):
            record = transport.State.fresh().prepare(
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
            # The Fold-family amplitude gate is the same original update field
            # used by Fold Drum 1; pitch-envelope decay stays at init value 43.
            assert record[9] == voice.words[compact.AMP_ENV + 4], (
                mode, corner, "amplitude gate"
            )
            assert voice.words[compact.PITCH_ENV + 10] == 43, (
                mode, corner, "fixed pitch-envelope decay"
            )
            assert record[10] == 0
            assert record[11] == transport.ENGINE_INDEX
            checked += 1

    print(
        "Fold Drum 2 transport oracle: PASS "
        f"({checked} original ARM mode/control corners; exact prepared "
        "TUNE/DECAY/FOLD/PENV, mode and gate fields)"
    )


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Execute Fold Drum 2's control-only PK/Y1 seam on the DSP56300 host.

This gate deliberately stops before trigger/render.  It proves that the actual
assembly seam decodes the prepared PK/Y1 bytes into the seven Fold Drum 2 state
fields already established by the original v1.2.1 control law, while leaving
all oscillator, transient/noise, crossfade, selector, scratch and guard words
untouched.

Active trigger/retrigger state is a separate gate and must come from the
original-ARM capture corpus before Fold Drum 2 is exposed in the machine
browser.
"""
from __future__ import annotations

from pathlib import Path
import sys

import verify_perky_controlled_voice_exec as c

ROOT = c.ROOT
PERKY = ROOT / "modules/perky"
OUT = ROOT / "out/perky/fold2-seam"
sys.path.insert(0, str(PERKY))

import fold_drum2_transport as transport

VOICE_WORDS = 51
VISIBLE_WORDS = 64
KNOWN_WRITES = {14, 20, 31, 32, 33, 42, 44}
MODE_MAP = (1, 2, 0)

WRAPPER = r"""
pk_controlled_voice_exec:
        ; Host script words X:$100..$10b are the twelve PK/Y1 record bytes.
        ; r4=$f8 therefore presents them to the seam at record offsets +8..+19.
        move    #>$0000f8,r4
        move    #>$000200,r6
        jsr     pk_fold2_apply_controls
        rts
"""


def be16(record: bytes, offset: int) -> int:
    return (record[offset] << 8) | record[offset + 1]


def initial_state(seed: int) -> list[int]:
    # Unique deterministic 16-bit values make any accidental write outside the
    # seven allowed state words visible.  The extra thirteen words include the
    # Fold2 renderer's +$34/+35 base-frequency scratch and allocation guards.
    return [((0x4100 + seed * 0x071 + i * 0x101) & 0xFFFF)
            for i in range(VISIBLE_WORDS)]


def expected_after(before: list[int], record: bytes) -> list[int]:
    want = list(before)
    want[32] = be16(record, 0)       # raw pitch
    want[20] = be16(record, 2)       # amp envelope decay
    want[44] = be16(record, 4)       # fold
    want[33] = be16(record, 6)       # pitch-envelope amount
    want[31] = 43                    # fixed pitch-envelope decay
    want[42] = MODE_MAP[min(2, record[8] & 0xFF)]
    want[14] = record[9] & 1         # amp gate/hold
    return want


def main() -> None:
    c.OUT = OUT
    OUT.mkdir(parents=True, exist_ok=True)
    # c.HOST is intentionally a shared compiled harness path rather than a
    # per-gate binary; make sure its parent exists for a clean setup.
    c.HOST.parent.mkdir(parents=True, exist_ok=True)
    c.build_host()

    seam = (PERKY / "fold_drum2_seam.asm").read_text()
    source = c.source_builder.force_long_local_jsr(WRAPPER + "\n" + seam)
    binary, entry = c.assemble(source)

    def write_data(path: Path, state_words: list[int], _tables: list[int]):
        if len(state_words) != VISIBLE_WORDS:
            raise AssertionError(("visible state size", len(state_words)))
        path.write_text(
            "X 100 " + " ".join(["000000"] * 13) + "\n"
            + "X 200 " + " ".join(f"{v:06x}" for v in state_words) + "\n"
        )
        return []

    c.write_data = write_data

    records: list[tuple[str, bytes]] = []
    raw_rows = (
        (0, 0, 0, 0),
        (64, 64, 64, 64),
        (127, 127, 127, 127),
        (1, 126, 37, 93),
    )
    for mode in range(3):
        for raw in raw_rows:
            record = transport.State.fresh().prepare(raw, mode, trigger=True)
            records.append((f"transport-m{mode}-{'-'.join(map(str, raw))}", record))

    # Independent byte-order stress case. These values need not be reachable
    # panel values; the seam contract is to decode a prepared record exactly.
    records.append((
        "byte-order-stress",
        bytes((0x12, 0x34, 0xAB, 0xCD, 0x56, 0x78,
               0xFE, 0xDC, 0x02, 0x01, 0xA5, transport.ENGINE_INDEX)),
    ))

    for case_index, (tag, record) in enumerate(records):
        if len(record) != 12:
            raise AssertionError((tag, "record size", len(record)))
        before = initial_state(case_index)
        # The host accepts twelve script words plus one event word. Each record
        # byte is written verbatim to X:$100..$10b; the event is ignored here.
        _audio, states, _ = c.run(
            binary, entry, tag, before, [], [(tuple(record), -1)]
        )
        got = states[0][:VISIBLE_WORDS]
        want = expected_after(before, record)
        if got != want:
            diffs = [
                (i, before[i], got[i], want[i])
                for i in range(VISIBLE_WORDS)
                if got[i] != want[i]
            ]
            raise AssertionError((tag, "state mismatch", diffs))

        mutated = {i for i, (a, b) in enumerate(zip(before, got)) if a != b}
        unexpected = mutated - KNOWN_WRITES
        if unexpected:
            raise AssertionError((tag, "unexpected writes", sorted(unexpected)))
        # Even if a prepared value happens to equal the seeded word, every
        # observable mutation must remain within the seven proven fields.
        for i in range(VOICE_WORDS, VISIBLE_WORDS):
            if got[i] != before[i]:
                raise AssertionError((tag, "scratch/guard write", i))

    print(
        "Fold Drum 2 control seam executable gate: PASS "
        f"({len(records)} records; exact prepared fields/mode/gate; "
        "oscillator/fade/selector/scratch/guards untouched)"
    )


if __name__ == "__main__":
    main()

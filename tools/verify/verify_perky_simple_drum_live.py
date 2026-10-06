#!/usr/bin/env python3
"""Gate Simple Drum live compact state against authentic v1.2.1 captures.

No firmware RAM blobs are committed. The final SHA256 is over the 34 little-
endian u16 compact words projected from all 27 authentic pre-render captures in
lexicographic filename order:

  M1/M2/M3 x midpoint + each TUNE/DECAY/ENV/MIX at min/max.

Only three raw-pitch points occur in that capture grid, so their exact v1.2.1
pitch-table values are pinned explicitly rather than committing the table.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
PERKY = ROOT / "modules" / "perky"
sys.path.insert(0, str(PERKY))

import simple_drum_compact as compact  # noqa: E402
import simple_drum_live as live  # noqa: E402
import simple_drum_transport as transport  # noqa: E402

AUTHENTIC_27_COMPACT_SHA256 = (
    "2f05bdc18e1ace53d5daa21c184638536ec247cee01483f479098afe7a1ba96d"
)
PITCH_INCREMENT = {
    0: 178,
    2046: 2849,
    4092: 45475,
}


def make_cases():
    cases = []
    for physical_mode in range(3):
        mode_name = f"m{physical_mode + 1}"
        cases.append((f"simple_drum_{mode_name}_mid.bin", physical_mode, (64, 64, 64, 64)))
        for label, slot in (("tune", 0), ("decay", 1), ("env", 2), ("mix", 3)):
            for suffix, value in (("0", 0), ("4095", 127)):
                controls = [64, 64, 64, 64]
                controls[slot] = value
                cases.append((
                    f"simple_drum_{mode_name}_{label}{suffix}.bin",
                    physical_mode,
                    tuple(controls),
                ))
    return sorted(cases)


def exact_pitch_increment(raw_pitch: int) -> int:
    try:
        return PITCH_INCREMENT[raw_pitch]
    except KeyError as exc:
        raise AssertionError(f"capture grid introduced unpinned raw pitch {raw_pitch}") from exc


def main() -> None:
    blob = bytearray()
    for _name, mode, controls in make_cases():
        record_state = transport.State.fresh()
        record = record_state.prepare(controls, mode, trigger=True)
        voice = live.LiveSimpleDrum.fresh()
        voice.trigger_with_record(record, pitch_increment=exact_pitch_increment)
        blob += struct.pack("<34H", *voice.voice.words)

    digest = hashlib.sha256(blob).hexdigest()
    if digest != AUTHENTIC_27_COMPACT_SHA256:
        raise AssertionError(
            f"27-capture compact state SHA256 {digest} != authentic "
            f"{AUTHENTIC_27_COMPACT_SHA256}"
        )

    # Retrigger is envelope-only: preserve oscillator phase/current identity,
    # reset both envelope values, set state/hold, then install the new deferred
    # target and prepared controls. This is recovered from the original ARM
    # trigger helper, not inferred from a fresh voice.
    state = live.LiveSimpleDrum.fresh()
    state.voice.set_u32(compact.OSC_PHASE, 0x00054321)
    state.voice.set_u32(compact.OSC_CURRENT, 0x080222A0)
    state.voice.set_u32(compact.AMP_ENV + compact.ENV_VALUE, 0x000abcde)
    state.voice.set_u32(compact.PITCH_ENV + compact.ENV_VALUE, 0x00012345)
    record = transport.State.fresh().prepare((64, 64, 64, 64), 1, trigger=True)
    state.trigger_with_record(record, pitch_increment=exact_pitch_increment)

    if state.voice.u32(compact.OSC_PHASE) != 0x00054321:
        raise AssertionError("Simple Drum retrigger incorrectly reset oscillator phase")
    if state.voice.u32(compact.OSC_CURRENT) != 0x080222A0:
        raise AssertionError("Simple Drum retrigger incorrectly reset current wave")
    if state.voice.u32(compact.OSC_NEXT) != 0x080226A0:
        raise AssertionError("Simple Drum retrigger lost deferred M2 wave target")
    for base in (compact.AMP_ENV, compact.PITCH_ENV):
        if state.voice.words[base + compact.ENV_STATE] != 1:
            raise AssertionError("retrigger did not restart envelope state")
        if state.voice.u32(base + compact.ENV_HOLD) != 1:
            raise AssertionError("retrigger did not set envelope hold")
        if state.voice.u32(base + compact.ENV_VALUE) != 0:
            raise AssertionError("retrigger did not clear reset-on-trigger envelope value")

    # The authentic max-DECAY edge preserves the AMP gate byte; the pitch
    # envelope gate remains zero.
    edge = live.LiveSimpleDrum.fresh()
    edge_record = transport.State.fresh().prepare((64, 127, 64, 64), 0, trigger=True)
    edge.trigger_with_record(edge_record, pitch_increment=exact_pitch_increment)
    if edge.voice.words[compact.AMP_ENV + compact.ENV_TRIGGER] != 1:
        raise AssertionError("max-DECAY amplitude gate edge was lost")
    if edge.voice.words[compact.PITCH_ENV + compact.ENV_TRIGGER] != 0:
        raise AssertionError("pitch envelope unexpectedly acquired gate byte")

    print(
        "PERKY Simple Drum live state: PASS "
        "(27/27 authentic 34-word states, retrigger phase continuity, "
        "envelope reset/hold and max-DECAY gate edge)"
    )


if __name__ == "__main__":
    main()

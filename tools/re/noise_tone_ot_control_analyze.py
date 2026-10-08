#!/usr/bin/env python3
"""Reduce the exact 128-position Noise/Tone ARM grid to renderer compact words.

Input is emitted by PerkyBits ``perkybits-noise-tone-ot-control-probe``.  The
probe runs original HD-01 v1.2.1 update() for every physical Octatrack value of
TUNE/DECAY/ENV/MIX in all three PĒRKONS modes:

* M1 -> firmware mode 1 -> Waveform2 state at 0x200036e4;
* M2 -> firmware mode 0 -> shared Noise/Tone state at 0x200034dc;
* M3 -> firmware mode 2 -> shared Noise/Tone state at 0x200034dc.

This analyzer does not fit curves.  It extracts only fields the independently
qualified renderers actually read/mutate, then records the exact 128-entry value
sequence for every compact word owned by each control.  That is the source data
for the eventual small DSP control tables.

The resulting JSON is evidence, not by itself a shipping qualification.  A
pairwise/cross-term gate and executable DSP A/B test must still pass before the
synthetic T6 control path can be removed.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import struct
import sys
from typing import NoReturn

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "modules/perky"))

import noise_tone_compact as shared

SCHEMA = "perkybits-noise-tone-ot-control-v1"
OUT_SCHEMA = "octabam.perky.noise-tone-ot-control-analysis.v1"
STATE_BYTES = 0x120
PANEL_TO_FIRMWARE = (1, 0, 2)
STATE_ADDRESSES = ("0x200036e4", "0x200034dc", "0x200034dc")
PARAMETERS = ("TUNE", "DECAY", "ENV", "MIX")
BASELINE_OT = 64
BASELINE_PREPARED = 2048

# Compact Waveform2 ABI.  Keep this explicit and flat so the future DSP seam can
# use immediate offsets exactly as the existing 41-word shared renderer does.
W2_FIELDS = (
    "VEL",
    "BYPASS",
    "ENV_STATE",
    "ENV_SHAPE",
    "ENV_FLAG4",
    "ENV_FLAG6",
    "ENV_TRIGGER",
    "ENV_VALUE_LO",
    "ENV_VALUE_HI",
    "ENV_HOLD_LO",
    "ENV_HOLD_HI",
    "ENV_ATTACK",
    "ENV_DECAY",
    "PHASE_REDUCTION_LO",
    "PHASE_REDUCTION_HI",
    "OSC_PHASE_LO",
    "OSC_PHASE_HI",
    "OSC_INCREMENT_LO",
    "OSC_INCREMENT_HI",
    "OSC_PHASE_OFFSET_LO",
    "OSC_PHASE_OFFSET_HI",
    "OSC_CURRENT_LO",
    "OSC_CURRENT_HI",
    "OSC_NEXT_LO",
    "OSC_NEXT_HI",
)

SHARED_NAMES = [f"WORD_{i}" for i in range(shared.WORDS_PER_VOICE)]
for name in (
    "VEL ENV_STATE ENV_SHAPE ENV_FLAG4 ENV_FLAG6 ENV_TRIGGER ENV_VALUE ENV_HOLD "
    "ENV_ATTACK ENV_DECAY NOISE_COUNT NOISE_RELOAD NOISE_HELD FILTER_DAMPING "
    "FILTER_COEFF FILTER_FIRST FILTER_SECOND FILTER_VELOCITY OSC1_PHASE "
    "OSC1_INCREMENT OSC1_CURRENT OSC1_NEXT OSC2_PHASE OSC2_INCREMENT "
    "OSC2_CURRENT OSC2_NEXT MIX"
).split():
    offset = getattr(shared, name)
    SHARED_NAMES[offset] = name + ("_LO" if name in {
        "ENV_VALUE", "ENV_HOLD", "FILTER_FIRST", "FILTER_SECOND",
        "FILTER_VELOCITY", "OSC1_PHASE", "OSC1_INCREMENT", "OSC1_CURRENT",
        "OSC1_NEXT", "OSC2_PHASE", "OSC2_INCREMENT", "OSC2_CURRENT",
        "OSC2_NEXT", "MIX",
    } else "")
    if name in {
        "ENV_VALUE", "ENV_HOLD", "FILTER_FIRST", "FILTER_SECOND",
        "FILTER_VELOCITY", "OSC1_PHASE", "OSC1_INCREMENT", "OSC1_CURRENT",
        "OSC1_NEXT", "OSC2_PHASE", "OSC2_INCREMENT", "OSC2_CURRENT",
        "OSC2_NEXT", "MIX",
    }:
        SHARED_NAMES[offset + 1] = name + "_HI"


def die(message: str) -> NoReturn:
    raise SystemExit("noise-tone-ot-control-analyze: " + message)


def u16(raw: bytes, offset: int) -> int:
    return raw[offset] | (raw[offset + 1] << 8)


def u32_words(raw: bytes, offset: int) -> tuple[int, int]:
    return u16(raw, offset), u16(raw, offset + 2)


def prepared(raw: int) -> int:
    return 4095 if raw == 127 else raw << 5


def decode_hex(record: dict, key: str, size: int) -> bytes:
    try:
        value = bytes.fromhex(record[key])
    except (KeyError, TypeError, ValueError) as exc:
        die(f"bad {key}: {exc}")
    if len(value) != size:
        die(f"{key} is {len(value)} bytes, expected {size}")
    return value


def waveform2_words(raw: bytes) -> list[int]:
    if len(raw) != STATE_BYTES:
        raise ValueError("Waveform2 ARM state geometry")
    words: list[int] = [
        raw[6],
        raw[0xB8],
        raw[0x74],
        raw[0x75],
        raw[0x78],
        raw[0x7A],
        raw[0x7B],
    ]
    words += list(u32_words(raw, 0x80))     # envelope value
    words += list(u32_words(raw, 0x84))     # envelope hold
    words += [u16(raw, 0x94), u16(raw, 0x96)]
    words += list(u32_words(raw, 0xC8))     # phase reduction
    words += list(u32_words(raw, 0xD8))     # phase
    words += list(u32_words(raw, 0xDC))     # increment
    words += list(u32_words(raw, 0xE0))     # phase offset
    words += list(u32_words(raw, 0xE4))     # current wave address
    words += list(u32_words(raw, 0xE8))     # next wave address
    if len(words) != len(W2_FIELDS):
        raise AssertionError(f"Waveform2 compact words {len(words)} != {len(W2_FIELDS)}")
    return [value & 0xFFFF for value in words]


def compact(panel: int, raw: bytes) -> tuple[list[str], list[int]]:
    if panel == 0:
        return list(W2_FIELDS), waveform2_words(raw)
    voice = shared.CompactVoice.from_arm(raw)
    return SHARED_NAMES, list(voice.words)


def load(path: Path) -> tuple[dict, list[dict]]:
    header = None
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                die(f"{path}:{number}: {exc}")
            if record.get("type") == "header":
                if header is not None:
                    die("multiple headers")
                header = record
            elif record.get("type") == "snapshot":
                rows.append(record)
            else:
                die(f"{path}:{number}: unknown record type")
    if header is None:
        die("missing header")
    if header.get("schema") != SCHEMA:
        die(f"schema {header.get('schema')!r}, expected {SCHEMA!r}")
    if tuple(header.get("panel_mode_to_firmware", ())) != PANEL_TO_FIRMWARE:
        die("physical MODE map drifted")
    if header.get("state_bytes") != STATE_BYTES:
        die("state geometry drifted")
    if header.get("settle_iterations") != 16:
        die("expected 16 original update() settle iterations")
    return header, rows


def validate(rows: list[dict]) -> dict[tuple[int, int, int], dict]:
    expected_count = 3 * 4 * 128
    if len(rows) != expected_count:
        die(f"expected {expected_count} snapshots, got {len(rows)}")

    grid: dict[tuple[int, int, int], dict] = {}
    for index, row in enumerate(rows):
        try:
            panel = int(row["panel_mode"])
            parameter = int(row["parameter"])
            ot = int(row["ot_value"])
            pvalue = int(row["prepared_value"])
        except (KeyError, TypeError, ValueError) as exc:
            die(f"row {index}: malformed coordinates: {exc}")
        if not 0 <= panel < 3 or not 0 <= parameter < 4 or not 0 <= ot < 128:
            die(f"row {index}: coordinate out of range")
        if int(row.get("firmware_mode", -1)) != PANEL_TO_FIRMWARE[panel]:
            die(f"row {index}: firmware MODE mismatch")
        if row.get("state_address") != STATE_ADDRESSES[panel]:
            die(f"row {index}: state address mismatch")
        if pvalue != prepared(ot):
            die(f"row {index}: prepared value {pvalue} != OT law {prepared(ot)}")
        controls = tuple(int(value) for value in row.get("controls", ()))
        if len(controls) != 4:
            die(f"row {index}: control tuple geometry")
        wanted = [BASELINE_PREPARED] * 4
        wanted[parameter] = pvalue
        if controls != tuple(wanted):
            die(f"row {index}: controls {controls} != {tuple(wanted)}")
        control_ram = decode_hex(row, "control_ram", 16)
        if struct.unpack("<4I", control_ram) != controls:
            die(f"row {index}: control RAM != requested values")
        decode_hex(row, "wrapper", 0x40)
        decode_hex(row, "state", STATE_BYTES)
        key = (panel, parameter, ot)
        if key in grid:
            die(f"duplicate grid coordinate {key}")
        grid[key] = row

    if len(grid) != expected_count:
        die("grid is not complete")
    return grid


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("probe", type=Path)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()

    header, rows = load(args.probe)
    grid = validate(rows)
    result: dict[str, object] = {
        "schema": OUT_SCHEMA,
        "source": str(args.probe),
        "header": header,
        "panels": {},
        "shipping_qualification": False,
        "remaining_gates": [
            "pairwise control separability against original ARM update()",
            "original first/active trigger state contract",
            "DSP executable control A/B across M1/M2/M3",
            "two-voice/core realtime budget after authentic T6 integration",
        ],
    }

    for panel in range(3):
        renderer = "Waveform2" if panel == 0 else "NoiseToneShared"
        names, baseline_words = compact(
            panel, decode_hex(grid[(panel, 0, BASELINE_OT)], "state", STATE_BYTES)
        )
        panel_result: dict[str, object] = {
            "panel_mode": panel,
            "firmware_mode": PANEL_TO_FIRMWARE[panel],
            "state_address": STATE_ADDRESSES[panel],
            "renderer": renderer,
            "compact_words": len(baseline_words),
            "compact_names": names,
            "parameters": {},
        }

        print(
            f"M{panel + 1}: firmware {PANEL_TO_FIRMWARE[panel]} / {renderer} / "
            f"{len(baseline_words)} compact words"
        )
        for parameter, pname in enumerate(PARAMETERS):
            all_words: list[list[int]] = []
            arm_states: list[bytes] = []
            for ot in range(128):
                raw = decode_hex(grid[(panel, parameter, ot)], "state", STATE_BYTES)
                row_names, words = compact(panel, raw)
                if row_names != names or len(words) != len(baseline_words):
                    die(f"M{panel + 1} {pname} compact ABI changed at OT {ot}")
                all_words.append(words)
                arm_states.append(raw)

            owned_words = [
                word for word in range(len(baseline_words))
                if any(values[word] != baseline_words[word] for values in all_words)
            ]
            baseline_arm = arm_states[BASELINE_OT]
            owned_bytes = [
                offset for offset in range(STATE_BYTES)
                if any(state[offset] != baseline_arm[offset] for state in arm_states)
            ]
            tables = {
                str(word): [values[word] for values in all_words]
                for word in owned_words
            }
            parameter_result = {
                "parameter": parameter,
                "name": pname,
                "owned_compact_words": owned_words,
                "owned_compact_names": [names[word] for word in owned_words],
                "owned_arm_bytes": owned_bytes,
                "tables_u16": tables,
            }
            panel_result["parameters"][pname] = parameter_result
            print(
                f"  {pname:5s}: compact "
                + (", ".join(f"{w}:{names[w]}" for w in owned_words) or "(none)")
                + f"; ARM bytes={len(owned_bytes)}"
            )

        result["panels"][f"M{panel + 1}"] = panel_result

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        print(f"wrote {args.json}")

    print(
        "Noise/Tone exact OT grid: PASS (1536 original-ARM settled states; "
        "M1 Waveform2 + M2/M3 shared compact ownership extracted)"
    )
    print("status: evidence only; pairwise/trigger/executable gates still required")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Reduce the exact 128-position Noise/Tone ARM grid to renderer compact words.

Input is emitted by PerkyBits ``perkybits-noise-tone-ot-control-probe``. The
probe runs original HD-01 v1.2.1 update() for every physical Octatrack value of
TUNE/DECAY/ENV/MIX in all three PĒRKONS modes:

* M1 -> firmware mode 1 -> Waveform2 state at 0x200036e4;
* M2 -> firmware mode 0 -> shared Noise/Tone state at 0x200034dc;
* M3 -> firmware mode 2 -> shared Noise/Tone state at 0x200034dc.

This analyzer does not fit curves. It extracts only fields the independently
qualified renderers actually read/mutate, then records the exact 128-entry value
sequence for every compact word owned by each control. M1 uses the repository's
single authoritative ``noise_tone_wave2_compact.NoiseToneWave2`` ABI rather
than duplicating its field order here.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
import sys
from typing import NoReturn

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "modules/perky"))

import noise_tone_compact as shared
import noise_tone_wave2_compact as wave2
import resonator_compact as rc

SCHEMA = "perkybits-noise-tone-ot-control-v1"
OUT_SCHEMA = "octabam.perky.noise-tone-ot-control-analysis.v1"
STATE_BYTES = 0x120
PANEL_TO_FIRMWARE = (1, 0, 2)
STATE_ADDRESSES = ("0x200036e4", "0x200034dc", "0x200034dc")
PARAMETERS = ("TUNE", "DECAY", "ENV", "MIX")
BASELINE_OT = 64
BASELINE_PREPARED = 2048


def _word_names(words: int) -> list[str]:
    return [f"WORD_{index}" for index in range(words)]


def _name_u32(names: list[str], offset: int, stem: str) -> None:
    names[offset] = stem + "_LO"
    names[offset + 1] = stem + "_HI"


W2_NAMES = _word_names(wave2.WORDS)
W2_NAMES[wave2.VELOCITY] = "VEL"
W2_NAMES[wave2.MUTE] = "BYPASS"
for offset, name in (
    (rc.ENV_STATE, "ENV_STATE"),
    (rc.ENV_SHAPE, "ENV_SHAPE"),
    (rc.ENV_FLAG4, "ENV_FLAG4"),
    (rc.ENV_FLAG6, "ENV_FLAG6"),
    (rc.ENV_TRIGGER, "ENV_TRIGGER"),
    (rc.ENV_ATTACK, "ENV_ATTACK"),
    (rc.ENV_DECAY, "ENV_DECAY"),
):
    W2_NAMES[wave2.ENV + offset] = name
_name_u32(W2_NAMES, wave2.ENV + rc.ENV_VALUE, "ENV_VALUE")
_name_u32(W2_NAMES, wave2.ENV + rc.ENV_HOLD, "ENV_HOLD")
for offset, name in (
    (wave2.PHASE, "OSC_PHASE"),
    (wave2.INCREMENT, "OSC_INCREMENT"),
    (wave2.OFFSET, "OSC_PHASE_OFFSET"),
    (wave2.CURRENT, "OSC_CURRENT"),
    (wave2.NEXT, "OSC_NEXT"),
    (wave2.REDUCTION, "PHASE_REDUCTION"),
):
    _name_u32(W2_NAMES, offset, name)

SHARED_NAMES = _word_names(shared.WORDS_PER_VOICE)
for offset, name in (
    (shared.VEL, "VEL"),
    (shared.ENV_STATE, "ENV_STATE"),
    (shared.ENV_SHAPE, "ENV_SHAPE"),
    (shared.ENV_FLAG4, "ENV_FLAG4"),
    (shared.ENV_FLAG6, "ENV_FLAG6"),
    (shared.ENV_TRIGGER, "ENV_TRIGGER"),
    (shared.ENV_ATTACK, "ENV_ATTACK"),
    (shared.ENV_DECAY, "ENV_DECAY"),
    (shared.NOISE_COUNT, "NOISE_COUNT"),
    (shared.NOISE_RELOAD, "NOISE_RELOAD"),
    (shared.NOISE_HELD, "NOISE_HELD"),
    (shared.FILTER_DAMPING, "FILTER_DAMPING"),
    (shared.FILTER_COEFF, "FILTER_COEFF"),
):
    SHARED_NAMES[offset] = name
for offset, name in (
    (shared.ENV_VALUE, "ENV_VALUE"),
    (shared.ENV_HOLD, "ENV_HOLD"),
    (shared.FILTER_FIRST, "FILTER_FIRST"),
    (shared.FILTER_SECOND, "FILTER_SECOND"),
    (shared.FILTER_VELOCITY, "FILTER_VELOCITY"),
    (shared.OSC1_PHASE, "OSC1_PHASE"),
    (shared.OSC1_INCREMENT, "OSC1_INCREMENT"),
    (shared.OSC1_CURRENT, "OSC1_CURRENT"),
    (shared.OSC1_NEXT, "OSC1_NEXT"),
    (shared.OSC2_PHASE, "OSC2_PHASE"),
    (shared.OSC2_INCREMENT, "OSC2_INCREMENT"),
    (shared.OSC2_CURRENT, "OSC2_CURRENT"),
    (shared.OSC2_NEXT, "OSC2_NEXT"),
    (shared.MIX, "MIX"),
):
    _name_u32(SHARED_NAMES, offset, name)


def die(message: str) -> NoReturn:
    raise SystemExit("noise-tone-ot-control-analyze: " + message)


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


def compact(panel: int, raw: bytes) -> tuple[list[str], list[int]]:
    if panel == 0:
        voice = wave2.NoiseToneWave2.from_arm(raw)
        return W2_NAMES, list(voice.words)
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
            panel_result["parameters"][pname] = {
                "parameter": parameter,
                "name": pname,
                "owned_compact_words": owned_words,
                "owned_compact_names": [names[word] for word in owned_words],
                "owned_arm_bytes": owned_bytes,
                "tables_u16": tables,
            }
            print(
                f"  {pname:5s}: compact "
                + (", ".join(f"{word}:{names[word]}" for word in owned_words) or "(none)")
                + f"; ARM bytes={len(owned_bytes)}"
            )
        result["panels"][f"M{panel + 1}"] = panel_result

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        print(f"wrote {args.json}")

    print(
        "Noise/Tone exact OT grid: PASS (1536 original-ARM settled states; "
        "authoritative M1 Waveform2 + M2/M3 shared compact ownership extracted)"
    )
    print("status: evidence only; pairwise/trigger/executable gates still required")


if __name__ == "__main__":
    main()

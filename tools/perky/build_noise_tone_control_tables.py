#!/usr/bin/env python3
"""Pack exact original-ARM Noise/Tone control maps into DSP Y-memory tables.

Consumes:

* ``noise-tone-ot-control-analysis.json`` from the exact 128-position analyzer;
* ``noise-tone-baselines/manifest.json`` from the authentic baseline builder.

For every renderer compact word that changes when one OT control is swept, the
builder stores the exact 128 u16 values. Identical maps are deduplicated across
modes/fields. A compact word may be owned by only one of TUNE/DECAY/ENV/MIX per
mode; overlapping ownership is rejected here because it would require a proven
multi-dimensional law rather than a one-axis table.

This is still not sufficient to ship T6: pairwise original-ARM evidence must
also show no cross-term state, and the composed DSP source must pass executable
fresh-trigger/live-change A/B and realtime gates.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import NoReturn

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "modules/perky"), str(ROOT / "tools/perky")]

import hw4_memory as memory
import simple_drum_tables as packed_u16
from build_noise_tone_payload import words24_bytes

ANALYSIS_SCHEMA = "octabam.perky.noise-tone-ot-control-analysis.v1"
BASELINE_SCHEMA = "octabam.perky.noise-tone-baselines.v1"
OUT_SCHEMA = "octabam.perky.noise-tone-control-tables.v1"
DEFAULT_ANALYSIS = (
    ROOT / "out/perky/control-probes/noise-tone-grid/noise-tone-ot-control-analysis.json"
)
DEFAULT_BASELINES = ROOT / "out/perky/noise-tone-baselines/manifest.json"
DEFAULT_OUT = ROOT / "out/perky/noise-tone-live-control"
PARAMETERS = ("TUNE", "DECAY", "ENV", "MIX")
TABLE_ENTRIES = 128


def die(message: str) -> NoReturn:
    raise SystemExit("build-noise-tone-control-tables: " + message)


def load_json(path: Path, schema: str) -> dict:
    if not path.is_file():
        die(f"missing {path}")
    try:
        value = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        die(f"{path}: {exc}")
    if value.get("schema") != schema:
        die(f"{path}: schema {value.get('schema')!r}, expected {schema!r}")
    return value


def table_payload(values: list[int]) -> tuple[bytes, int]:
    if len(values) != TABLE_ENTRIES:
        die(f"table has {len(values)} values, expected {TABLE_ENTRIES}")
    if any(not isinstance(value, int) or isinstance(value, bool)
           or not 0 <= value <= 0xFFFF for value in values):
        die("control table escaped u16")
    words = packed_u16.pack_u16(values)
    payload = words24_bytes(words)
    return payload, len(words)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", type=Path, default=DEFAULT_ANALYSIS)
    parser.add_argument("--baselines", type=Path, default=DEFAULT_BASELINES)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    memory.validate()
    analysis_path = args.analysis.expanduser().resolve()
    baselines_path = args.baselines.expanduser().resolve()
    out = args.out.expanduser().resolve()
    analysis = load_json(analysis_path, ANALYSIS_SCHEMA)
    baselines = load_json(baselines_path, BASELINE_SCHEMA)

    cursor = int(baselines["end_exclusive"])
    if not memory.HW4_Y_END <= cursor <= memory.HW4_Y_BOOT_CLEAR:
        die(f"authentic baseline end Y:${cursor:04x} is outside HW4 Y arena")

    # Build ownership first. A word controlled by two different knobs is not a
    # valid one-dimensional LUT even if the baseline-axis captures look sane.
    assignments: list[dict] = []
    for panel_name in ("M1", "M2", "M3"):
        panel = analysis.get("panels", {}).get(panel_name)
        if not isinstance(panel, dict):
            die(f"analysis missing {panel_name}")
        owners: dict[int, str] = {}
        for parameter in PARAMETERS:
            row = panel.get("parameters", {}).get(parameter)
            if not isinstance(row, dict):
                die(f"analysis missing {panel_name}/{parameter}")
            tables = row.get("tables_u16", {})
            for word_text, values in tables.items():
                try:
                    word = int(word_text)
                except ValueError:
                    die(f"{panel_name}/{parameter}: bad compact word {word_text!r}")
                previous = owners.get(word)
                if previous is not None and previous != parameter:
                    die(
                        f"{panel_name} compact word {word} is owned by both "
                        f"{previous} and {parameter}; needs proven multi-control law"
                    )
                owners[word] = parameter
                names = panel.get("compact_names", [])
                if not 0 <= word < len(names):
                    die(f"{panel_name}: compact word {word} outside named ABI")
                if not isinstance(values, list):
                    die(f"{panel_name}/{parameter}/word{word}: table is not a list")
                assignments.append({
                    "panel": panel_name,
                    "firmware_mode": int(panel["firmware_mode"]),
                    "renderer": panel["renderer"],
                    "parameter": parameter,
                    "compact_word": word,
                    "compact_name": names[word],
                    "values": [int(value) for value in values],
                })

    out.mkdir(parents=True, exist_ok=True)

    # Deduplicate identical maps. Shared M2/M3 commonly have identical control
    # laws, and duplicated Y tables buy us nothing.
    by_values: dict[tuple[int, ...], dict] = {}
    tables: list[dict] = []
    for assignment in assignments:
        values = assignment.pop("values")
        key = tuple(values)
        table = by_values.get(key)
        if table is None:
            payload, words = table_payload(values)
            table_id = len(tables)
            path = out / f"table-{table_id:02d}.bin"
            path.write_bytes(payload)
            table = {
                "id": table_id,
                "file": path.name,
                "base_word": cursor,
                "entries": TABLE_ENTRIES,
                "words": words,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "first": values[0],
                "middle": values[64],
                "last": values[-1],
            }
            cursor += words
            if cursor > memory.HW4_Y_BOOT_CLEAR:
                die(
                    f"Noise/Tone control tables exceed boot-clear boundary: "
                    f"Y:${cursor:04x} > Y:${memory.HW4_Y_BOOT_CLEAR:04x}"
                )
            by_values[key] = table
            tables.append(table)
        assignment["table_id"] = int(table["id"])
        assignment["base_word"] = int(table["base_word"])

    if len(tables) > 24:
        die(f"exact Noise/Tone control path needs {len(tables)} unique tables (>24)")

    report = {
        "schema": OUT_SCHEMA,
        "analysis": str(analysis_path),
        "baselines": str(baselines_path),
        "mode_map": [1, 0, 2],
        "entries_per_table": TABLE_ENTRIES,
        "lookup_index": "prepared >> 5",
        "tables": tables,
        "assignments": assignments,
        "end_exclusive": cursor,
        "boot_clear": memory.HW4_Y_BOOT_CLEAR,
        "free_words": memory.HW4_Y_BOOT_CLEAR - cursor,
        "shipping_qualification": False,
        "remaining_gates": [
            "original ARM pairwise/cross-term proof",
            "original first/active trigger contract",
            "composed DSP fresh-trigger/live-change PCM A/B",
            "two-voice/core realtime cycle budget",
        ],
    }
    (out / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")

    print("Noise/Tone exact OT control tables: generated")
    print(f"  assignments : {len(assignments)} compact-word mappings")
    print(f"  unique LUTs : {len(tables)}")
    for table in tables:
        print(
            f"    table {table['id']:02d}: Y:${table['base_word']:04x}, "
            f"{table['words']} words"
        )
    print(
        f"  end Y:${cursor:04x}; "
        f"{memory.HW4_Y_BOOT_CLEAR - cursor} words remain before boot clear"
    )
    print("  status: packed exactly; pairwise/trigger/executable gates still required")


if __name__ == "__main__":
    main()

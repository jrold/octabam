#!/usr/bin/env python3
"""Gate the original-ARM evidence required for authentic live T6 controls.

Requires two independent local captures:

1. detailed anchor/smoothing/trigger/pairwise analysis (v3);
2. exact 128-position Octatrack compact-word analysis (v1).

The gate is intentionally stronger than "the knob changes some bytes": every
continuous control must own at least one renderer-read compact word in all three
physical modes, DECAY must own the actual envelope-decay word, and every tested
pairwise corner must introduce no state outside the union of the two individual
single-axis ownership sets.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import NoReturn

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DETAIL = (
    ROOT / "out/perky/control-probes/noise-tone/noise-tone-control-analysis.json"
)
DEFAULT_GRID = (
    ROOT / "out/perky/control-probes/noise-tone-grid/noise-tone-ot-control-analysis.json"
)
DETAIL_SCHEMA = "octabam.perky.noise-tone-control-analysis.v3"
GRID_SCHEMA = "octabam.perky.noise-tone-ot-control-analysis.v1"
PARAMETERS = ("TUNE", "DECAY", "ENV", "MIX")


def die(message: str) -> NoReturn:
    raise SystemExit("verify-perky-noise-tone-control-evidence: " + message)


def load(path: Path, schema: str) -> dict:
    if not path.is_file():
        die(f"missing {path}")
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        die(f"{path}: {exc}")
    if data.get("schema") != schema:
        die(f"{path}: schema {data.get('schema')!r}, expected {schema!r}")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--detail", type=Path, default=DEFAULT_DETAIL)
    parser.add_argument("--grid", type=Path, default=DEFAULT_GRID)
    args = parser.parse_args()

    detail = load(args.detail.expanduser().resolve(), DETAIL_SCHEMA)
    grid = load(args.grid.expanduser().resolve(), GRID_SCHEMA)

    if detail.get("header", {}).get("panel_mode_to_firmware") != [1, 0, 2]:
        die("detailed probe physical MODE map drifted")
    if grid.get("header", {}).get("panel_mode_to_firmware") != [1, 0, 2]:
        die("exact-grid physical MODE map drifted")

    pairwise = detail.get("pairwise", {})
    expected_pairs = 3 * 6
    if len(pairwise) != expected_pairs:
        die(
            f"pairwise analysis has {len(pairwise)} pairs, expected {expected_pairs}; "
            "rerun noise-tone probe with --pairwise"
        )
    for key, row in pairwise.items():
        if row.get("records") != 9:
            die(f"{key}: expected 9 pairwise corner records, got {row.get('records')}")
        extra = row.get("extra_cross_term_offsets")
        if extra:
            die(f"{key}: unmodeled cross-term ARM state at offsets {extra}")

    panels = grid.get("panels", {})
    if set(panels) != {"M1", "M2", "M3"}:
        die(f"exact grid panel set is {sorted(panels)}, expected M1/M2/M3")

    total_owned = 0
    total_tables = 0
    for panel_name in ("M1", "M2", "M3"):
        panel = panels[panel_name]
        params = panel.get("parameters", {})
        for parameter in PARAMETERS:
            row = params.get(parameter)
            if not isinstance(row, dict):
                die(f"{panel_name}: missing {parameter}")
            owned = row.get("owned_compact_words")
            names = row.get("owned_compact_names")
            tables = row.get("tables_u16")
            if not owned or not names or not isinstance(tables, dict):
                die(f"{panel_name}/{parameter}: control owns no renderer compact state")
            if len(owned) != len(names) or len(tables) != len(owned):
                die(f"{panel_name}/{parameter}: compact ownership/table geometry mismatch")
            varying = 0
            for word in owned:
                values = tables.get(str(word))
                if not isinstance(values, list) or len(values) != 128:
                    die(f"{panel_name}/{parameter}/word{word}: expected 128 exact OT values")
                if any(not isinstance(value, int) or isinstance(value, bool)
                       or not 0 <= value <= 0xFFFF for value in values):
                    die(f"{panel_name}/{parameter}/word{word}: table escaped u16")
                if len(set(values)) > 1:
                    varying += 1
            if varying == 0:
                die(f"{panel_name}/{parameter}: renderer-owned tables are all constant")
            if parameter == "DECAY" and "ENV_DECAY" not in names:
                die(
                    f"{panel_name}/DECAY does not own ENV_DECAY; "
                    f"observed compact fields are {names}"
                )
            total_owned += len(owned)
            total_tables += len(tables)

    # The detailed probe also records trigger ownership. It is not the active
    # retrigger oracle (that is analyze_noise_tone_trigger.py), but every mode
    # must at least have fresh-trigger evidence present.
    trigger = detail.get("trigger", {})
    for panel in range(3):
        for sweep in ("velocity", "note"):
            key = f"m{panel}-{sweep}"
            row = trigger.get(key)
            if not isinstance(row, dict) or not row.get("values"):
                die(f"missing detailed trigger sweep {key}")

    print(
        "Noise/Tone original control evidence: PASS "
        f"(3 modes x 4 controls x 128 exact OT positions; {total_owned} "
        f"renderer compact-word assignments; {expected_pairs} pairwise control "
        "pairs x 9 corners; no cross-term state; DECAY owns ENV_DECAY in M1/M2/M3)"
    )


if __name__ == "__main__":
    main()

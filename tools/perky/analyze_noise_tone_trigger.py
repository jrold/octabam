#!/usr/bin/env python3
"""Derive exact v1.2.1 Noise/Tone raw first-trigger/retrigger compact contracts.

Consumes the existing all-engine ARM fixture corpus. Noise/Tone is engine 11
(one-based) on Voice 4. Physical M1 uses the separate Waveform2 object at
wrapper +0x2b8c; physical M2/M3 use the shared Noise/Tone object at +0x2984.

Each case compares only the original raw trigger mutation:

* fresh prepared state -> trigger-only state;
* state after 512 original samples -> active-retrigger-only state.

The mandatory firmware update() that normally follows trigger is deliberately
NOT folded into this contract. HW4 uses the same architecture as Karplus:
raw original trigger -> reapply current endpoint-exact live OT controls -> render.
That prevents a retrigger fixture from snapping p-locked controls back to the
captured corner used to derive the trigger delta.

Compact conversion is shared with the exact OT-grid analyzer so M1 field
ordering has one repository authority.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "modules/perky"), str(ROOT / "tools/re")]

import noise_tone_ot_control_analyze as ot_grid

FIX_DEFAULT = ROOT / "out/perky/engine-fixtures"
OUT_DEFAULT = ROOT / "out/perky/noise-tone-trigger-contract.json"
ENGINE = 11
ARM_STATE_SIZE = 0x120
ARM_OFFSETS = (0x2B8C, 0x2984, 0x2984)
RENDERERS = ("Waveform2", "NoiseToneShared", "NoiseToneShared")


def die(message: str) -> "NoReturn":
    raise SystemExit("analyze-noise-tone-trigger: " + message)


def compact_state(path: Path, panel: int) -> tuple[list[str], list[int]]:
    if not path.is_file():
        die(
            f"missing {path}; regenerate all-engine fixtures with "
            "tools/perky/capture_engine_fixtures.py"
        )
    blob = path.read_bytes()
    offset = ARM_OFFSETS[panel]
    raw = blob[offset:offset + ARM_STATE_SIZE]
    if len(raw) != ARM_STATE_SIZE:
        die(f"{path}: short state at wrapper +0x{offset:x}")
    return ot_grid.compact(panel, raw)


def cases(fixtures: Path, pre_name: str, post_name: str) -> dict[int, list[dict]]:
    result: dict[int, list[dict]] = {0: [], 1: [], 2: []}
    for panel in range(3):
        for corner in range(3):
            case = fixtures / f"engine-{ENGINE}-mode-{panel + 1}-corner-{corner}"
            names_a, pre = compact_state(case / pre_name, panel)
            names_b, post = compact_state(case / post_name, panel)
            if names_a != names_b or len(pre) != len(post):
                die(f"M{panel + 1}/corner{corner}: compact ABI changed")
            result[panel].append({
                "case": f"m{panel + 1}/c{corner}",
                "corner": corner,
                "names": names_a,
                "pre": pre,
                "post": post,
            })
    return result


def classify(pairs: list[tuple[int, int]], all_pre: list[list[int]], index: int) -> dict:
    posts = [post for _pre, post in pairs]
    if len(set(posts)) == 1:
        return {"kind": "CONST", "value": posts[0]}
    sources = [
        source for source in range(len(all_pre[0]))
        if source != index
        and all(posts[case] == all_pre[case][source] for case in range(len(pairs)))
    ]
    if sources:
        return {"kind": "COPY", "sources": sources}
    if all(post == (pre ^ 1) for pre, post in pairs):
        return {"kind": "TOGGLE", "mask": 1}
    if all(((post - pre) & 0xFFFF) == ((pairs[0][1] - pairs[0][0]) & 0xFFFF)
           for pre, post in pairs):
        return {"kind": "ADD16", "delta": (pairs[0][1] - pairs[0][0]) & 0xFFFF}
    return {
        "kind": "CASES",
        "values": [{"before": pre, "after": post} for pre, post in pairs],
    }


def phase(title: str, grouped: dict[int, list[dict]]) -> dict:
    print(title)
    print("=" * len(title))
    out: dict[str, dict] = {}
    for panel in range(3):
        rows = grouped[panel]
        if len(rows) != 3:
            die(f"M{panel + 1}: expected 3 control corners")
        names = rows[0]["names"]
        for row in rows:
            if row["names"] != names:
                die(f"M{panel + 1}: compact names drifted")
        all_pre = [row["pre"] for row in rows]
        by_word: dict[int, list[tuple[int, int]]] = defaultdict(list)
        for row in rows:
            for index, pair in enumerate(zip(row["pre"], row["post"])):
                by_word[index].append(pair)
        changed = [
            index for index, pairs in by_word.items()
            if any(before != after for before, after in pairs)
        ]
        words = []
        for index in changed:
            words.append({
                "index": index,
                "name": names[index],
                "rule": classify(by_word[index], all_pre, index),
            })
        print(
            f"M{panel + 1} {RENDERERS[panel]}: "
            f"{len(changed)}/{len(names)} compact words changed -> {changed}"
        )
        out[f"M{panel + 1}"] = {
            "panel_mode": panel,
            "renderer": RENDERERS[panel],
            "arm_state_offset": ARM_OFFSETS[panel],
            "compact_words": len(names),
            "compact_names": names,
            "changed_indices": changed,
            "words": words,
            "cases": [
                {"case": row["case"], "pre": row["pre"], "post": row["post"]}
                for row in rows
            ],
        }
    print()
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", type=Path, default=FIX_DEFAULT)
    parser.add_argument("--json", type=Path, default=OUT_DEFAULT)
    args = parser.parse_args()

    first = cases(
        args.fixtures,
        "wrapper-window-pre-trigger.bin",
        "wrapper-window-trigger-only.bin",
    )
    active = cases(
        args.fixtures,
        "wrapper-window-retrigger-pre.bin",
        "wrapper-window-retrigger-only.bin",
    )
    first_contract = phase("Noise/Tone original ARM raw first-trigger delta", first)
    active_contract = phase("Noise/Tone original ARM raw active-retrigger delta", active)

    comparison = {}
    for panel in ("M1", "M2", "M3"):
        first_set = set(first_contract[panel]["changed_indices"])
        active_set = set(active_contract[panel]["changed_indices"])
        comparison[panel] = {
            "first_only": sorted(first_set - active_set),
            "active_only": sorted(active_set - first_set),
            "shared": sorted(first_set & active_set),
        }
        print(
            f"{panel}: first-only={comparison[panel]['first_only']} "
            f"active-only={comparison[panel]['active_only']} "
            f"shared={comparison[panel]['shared']}"
        )

    contract = {
        "schema": "octabam.perky.noise-tone-trigger.v1",
        "engine_zero_based": 10,
        "engine_one_based": ENGINE,
        "mode_map": [1, 0, 2],
        "trigger_scope": "raw trigger only; live controls reapplied after trigger",
        "arm_state_offsets": {
            "M1": ARM_OFFSETS[0], "M2": ARM_OFFSETS[1], "M3": ARM_OFFSETS[2]
        },
        "first_trigger": first_contract,
        "active_retrigger": active_contract,
        "comparison": comparison,
        "notes": [
            "Derived only from original v1.2.1 ARM trigger-only fixture snapshots.",
            "Mandatory firmware update() is intentionally separate from this contract.",
            "HW4 reapplies current exact OT-domain controls immediately after raw trigger.",
            "M1 and M2/M3 intentionally use different compact renderer ABIs.",
            "CASES rules remain un-generalized until a deterministic compiler can prove them.",
        ],
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(contract, indent=2) + "\n")
    print("contract:", args.json)


if __name__ == "__main__":
    main()

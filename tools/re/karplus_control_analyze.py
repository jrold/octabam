#!/usr/bin/env python3
"""Analyze the v1.2.1 Karplus control-state probe from PerkyBits.

Input is emitted by ``perkybits-karplus-control-probe`` on the private
PerkyBits ``codex/octabam-karplus-control-probe`` branch.  The fixture contains
numeric RAM state only; no firmware code or table blobs are copied here.

The report answers the hardware-port questions that renderer parity alone
cannot answer:

* which Karplus object bytes are owned by TUNE, DECAY, EDGE and TWANG;
* how many original update() passes keep each byte moving;
* whether pairwise control changes create additional cross-term state;
* which bytes are trigger/note/velocity owned;
* whether trigger mutations intersect continuously updated control state.

That last point is important before Octabam is allowed to replace the current
frozen-control HW4 audition with a live control transport.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import struct
from typing import Iterable, NoReturn

SCHEMA = "perkybits-karplus-control-v1"
STATE_BYTES = 0x10E0
EXPECTED_ANCHORS = (
    0, 1, 512, 1024, 1536, 2047, 2048,
    2049, 2560, 3072, 3584, 4094, 4095,
)
PARAMETER_NAMES = ("TUNE", "DECAY", "EDGE", "TWANG")
PANEL_TO_FIRMWARE = (1, 0, 2)

# Raw-object locations recovered by the independently qualified update model.
# These labels make the analyzer useful without assuming that ONLY these bytes
# may move: unexpected ownership is reported rather than discarded.
KNOWN_REGIONS = (
    ("control history", 0x01C, 0x02C),
    ("oscillator/base pitch", 0x034, 0x038),
    ("amp envelope", 0x074, 0x09C),
    ("filter", 0x0A8, 0x0B8),
    ("common prepared controls", 0x0BA, 0x0C2),
    ("Karplus excitation", 0x0C2, 0x0C6),
    ("delay ring", 0x0C6, 0x10C6),
    ("fractional delay", 0x10C8, 0x10CC),
    ("write index / age", 0x10D4, 0x10DC),
    ("Karplus update flag", 0x10DC, 0x10DD),
)


def die(message: str) -> NoReturn:
    raise SystemExit("karplus-control-analyze: " + message)


def hex_blob(record: dict, key: str, expected: int | None = None) -> bytes:
    try:
        value = bytes.fromhex(record[key])
    except (KeyError, TypeError, ValueError) as exc:
        die(f"bad {key!r} in snapshot: {exc}")
    if expected is not None and len(value) != expected:
        die(f"{key} is {len(value)} bytes, expected {expected}")
    return value


def changed(a: bytes, b: bytes) -> set[int]:
    if len(a) != len(b):
        die(f"cannot diff blobs of {len(a)} and {len(b)} bytes")
    return {i for i, (left, right) in enumerate(zip(a, b)) if left != right}


def ranges(offsets: Iterable[int]) -> list[tuple[int, int]]:
    values = sorted(set(offsets))
    if not values:
        return []
    out: list[tuple[int, int]] = []
    start = previous = values[0]
    for value in values[1:]:
        if value != previous + 1:
            out.append((start, previous + 1))
            start = value
        previous = value
    out.append((start, previous + 1))
    return out


def fmt_ranges(offsets: Iterable[int]) -> str:
    return ", ".join(
        f"0x{start:04x}" if end == start + 1
        else f"0x{start:04x}..0x{end - 1:04x}"
        for start, end in ranges(offsets)
    ) or "(none)"


def region_names(offsets: Iterable[int]) -> list[str]:
    values = set(offsets)
    return [
        name for name, start, end in KNOWN_REGIONS
        if any(start <= value < end for value in values)
    ]


def load(path: Path) -> tuple[dict, list[dict]]:
    header: dict | None = None
    snapshots: list[dict] = []
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                die(f"{path}:{line_number}: invalid JSON: {exc}")
            if record.get("type") == "header":
                if header is not None:
                    die("more than one header")
                header = record
            elif record.get("type") == "snapshot":
                snapshots.append(record)
            else:
                die(f"{path}:{line_number}: unknown record type")

    if header is None:
        die("missing header")
    if header.get("schema") != SCHEMA:
        die(f"schema {header.get('schema')!r}, expected {SCHEMA!r}")
    if header.get("state_bytes") != STATE_BYTES:
        die(f"state_bytes {header.get('state_bytes')!r}, expected {STATE_BYTES}")
    if tuple(header.get("panel_mode_to_firmware", ())) != PANEL_TO_FIRMWARE:
        die("panel MODE mapping is not the qualified 1/0/2 order")
    if not snapshots:
        die("no snapshots")
    return header, snapshots


def validate(records: list[dict]) -> None:
    for number, record in enumerate(records):
        state = hex_blob(record, "state", STATE_BYTES)
        del state
        hex_blob(record, "wrapper", 0x40)
        raw = hex_blob(record, "control_ram", 16)
        words = struct.unpack("<4I", raw)
        requested = tuple(record.get("controls", ()))
        if words != requested:
            die(f"snapshot {number}: control RAM {words} != requested {requested}")
        panel_mode = int(record.get("panel_mode", -1))
        firmware_mode = int(record.get("firmware_mode", -1))
        if not 0 <= panel_mode < 3:
            die(f"snapshot {number}: bad panel_mode {panel_mode}")
        if firmware_mode != PANEL_TO_FIRMWARE[panel_mode]:
            die(f"snapshot {number}: MODE map drift")


def control_groups(records: list[dict]) -> dict[tuple[int, int, int], dict[int, dict]]:
    groups: dict[tuple[int, int, int], dict[int, dict]] = defaultdict(dict)
    for record in records:
        if record.get("sweep") != "control":
            continue
        key = (
            int(record["panel_mode"]),
            int(record["sweep_parameter"]),
            int(record["sweep_value"]),
        )
        iteration = int(record["iteration"])
        if iteration in groups[key]:
            die(f"duplicate control snapshot {key} iteration {iteration}")
        groups[key][iteration] = record
    return groups


def analyze_controls(records: list[dict]) -> tuple[dict, dict[int, set[int]]]:
    groups = control_groups(records)
    report: dict[str, dict] = {}
    owned_by_parameter: dict[int, set[int]] = defaultdict(set)

    for mode in range(3):
        for parameter, name in enumerate(PARAMETER_NAMES):
            baseline_key = (mode, parameter, 2048)
            if baseline_key not in groups or 16 not in groups[baseline_key]:
                die(f"missing settled baseline {baseline_key}")
            baseline = hex_blob(groups[baseline_key][16], "state", STATE_BYTES)
            baseline_wrapper = hex_blob(groups[baseline_key][16], "wrapper", 0x40)

            owned: set[int] = set()
            wrapper_owned: set[int] = set()
            latest_motion: dict[int, int] = {}
            anchors_seen: list[int] = []

            for value in EXPECTED_ANCHORS:
                history = groups.get((mode, parameter, value))
                if history is None:
                    continue
                anchors_seen.append(value)
                if set(history) != set(range(17)):
                    die(
                        f"mode {mode} {name}={value}: iterations "
                        f"{sorted(history)}, expected 0..16"
                    )
                settled = hex_blob(history[16], "state", STATE_BYTES)
                owned |= changed(baseline, settled)
                wrapper_owned |= changed(
                    baseline_wrapper,
                    hex_blob(history[16], "wrapper", 0x40),
                )

                previous = hex_blob(history[0], "state", STATE_BYTES)
                for iteration in range(1, 17):
                    current = hex_blob(history[iteration], "state", STATE_BYTES)
                    for offset in changed(previous, current):
                        latest_motion[offset] = max(
                            latest_motion.get(offset, 0), iteration
                        )
                    previous = current

            owned_by_parameter[parameter] |= owned
            key = f"m{mode}-p{parameter}"
            report[key] = {
                "panel_mode": mode,
                "firmware_mode": PANEL_TO_FIRMWARE[mode],
                "parameter": parameter,
                "parameter_name": name,
                "anchors": anchors_seen,
                "state_offsets": sorted(owned),
                "state_ranges": ranges(owned),
                "known_regions": region_names(owned),
                "wrapper_offsets": sorted(wrapper_owned),
                "wrapper_ranges": ranges(wrapper_owned),
                "latest_motion": {
                    str(offset): iteration
                    for offset, iteration in sorted(latest_motion.items())
                },
            }

            print(
                f"PANEL M{mode + 1} / firmware {PANEL_TO_FIRMWARE[mode]} "
                f"/ {name}"
            )
            print(f"  settled state:   {fmt_ranges(owned)}")
            print(f"  known regions:   {', '.join(region_names(owned)) or '(none)'}")
            print(f"  wrapper state:   {fmt_ranges(wrapper_owned)}")
            if latest_motion:
                final_iteration = max(latest_motion.values())
                moving_at_16 = sorted(
                    offset for offset, iteration in latest_motion.items()
                    if iteration == 16
                )
                print(f"  latest movement: update {final_iteration}")
                if moving_at_16:
                    print(
                        "  still moving @16: " + fmt_ranges(moving_at_16)
                    )
            else:
                print("  no state movement across update() calls")

    return report, owned_by_parameter


def analyze_triggers(records: list[dict], control_owned: set[int]) -> dict:
    grouped: dict[tuple[int, str, int], dict[str, dict]] = defaultdict(dict)
    for record in records:
        sweep = str(record.get("sweep"))
        if sweep not in ("velocity", "note"):
            continue
        key = (int(record["panel_mode"]), sweep, int(record["sweep_value"]))
        grouped[key][str(record["phase"])] = record

    result: dict[str, dict] = {}
    for mode in range(3):
        for sweep in ("velocity", "note"):
            state_union: set[int] = set()
            wrapper_union: set[int] = set()
            values: list[int] = []
            for (group_mode, group_sweep, value), pair in sorted(grouped.items()):
                if (group_mode, group_sweep) != (mode, sweep):
                    continue
                if "pre-trigger" not in pair or "post-trigger" not in pair:
                    die(f"incomplete trigger pair for M{mode + 1} {sweep}={value}")
                values.append(value)
                before, after = pair["pre-trigger"], pair["post-trigger"]
                state_union |= changed(
                    hex_blob(before, "state", STATE_BYTES),
                    hex_blob(after, "state", STATE_BYTES),
                )
                wrapper_union |= changed(
                    hex_blob(before, "wrapper", 0x40),
                    hex_blob(after, "wrapper", 0x40),
                )

            overlap = state_union & control_owned
            key = f"m{mode}-{sweep}"
            result[key] = {
                "panel_mode": mode,
                "firmware_mode": PANEL_TO_FIRMWARE[mode],
                "sweep": sweep,
                "values": values,
                "state_offsets": sorted(state_union),
                "state_ranges": ranges(state_union),
                "known_regions": region_names(state_union),
                "wrapper_offsets": sorted(wrapper_union),
                "wrapper_ranges": ranges(wrapper_union),
                "control_overlap_offsets": sorted(overlap),
                "control_overlap_ranges": ranges(overlap),
            }
            print(f"M{mode + 1} TRIGGER {sweep.upper()}")
            print(f"  changed:         {fmt_ranges(state_union)}")
            print(f"  control overlap: {fmt_ranges(overlap)}")
    return result


def analyze_pairwise(records: list[dict], controls: dict) -> dict:
    pairwise = [record for record in records if record.get("sweep") == "pairwise"]
    if not pairwise:
        print("PAIRWISE: not present (rerun probe with --pairwise for cross-term proof)")
        return {}

    groups = control_groups(records)
    baselines = {
        mode: hex_blob(groups[(mode, 0, 2048)][16], "state", STATE_BYTES)
        for mode in range(3)
    }
    out: dict[str, dict] = {}

    for mode in range(3):
        for a in range(4):
            for b in range(a + 1, 4):
                normal = (
                    set(controls[f"m{mode}-p{a}"]["state_offsets"])
                    | set(controls[f"m{mode}-p{b}"]["state_offsets"])
                )
                extra: set[int] = set()
                count = 0
                for record in pairwise:
                    if int(record["panel_mode"]) != mode:
                        continue
                    if int(record["sweep_parameter"]) != a * 10 + b:
                        continue
                    count += 1
                    delta = changed(
                        baselines[mode],
                        hex_blob(record, "state", STATE_BYTES),
                    )
                    extra |= delta - normal

                key = f"m{mode}-p{a}p{b}"
                out[key] = {
                    "panel_mode": mode,
                    "parameters": [a, b],
                    "parameter_names": [PARAMETER_NAMES[a], PARAMETER_NAMES[b]],
                    "records": count,
                    "extra_cross_term_offsets": sorted(extra),
                    "extra_cross_term_ranges": ranges(extra),
                    "known_regions": region_names(extra),
                }
                print(
                    f"M{mode + 1} PAIR {PARAMETER_NAMES[a]}+{PARAMETER_NAMES[b]}: "
                    f"extra {fmt_ranges(extra)}"
                )
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("probe", type=Path,
                        help="JSONL from perkybits-karplus-control-probe")
    parser.add_argument("--json", type=Path,
                        help="write machine-readable ownership report")
    args = parser.parse_args()

    header, records = load(args.probe)
    validate(records)
    print(
        f"schema {header['schema']} -- {len(records)} snapshots -- "
        "control RAM and MODE mapping: OK"
    )

    controls, owned_by_parameter = analyze_controls(records)
    all_control_owned = set().union(*owned_by_parameter.values())
    triggers = analyze_triggers(records, all_control_owned)
    pairwise = analyze_pairwise(records, controls)

    print("CONTROL OWNERSHIP UNION")
    for parameter, name in enumerate(PARAMETER_NAMES):
        offsets = owned_by_parameter[parameter]
        print(f"  {name:5s}: {fmt_ranges(offsets)}")
    print(f"  ALL  : {fmt_ranges(all_control_owned)}")

    if args.json:
        payload = {
            "schema": "octabam.perky.karplus-control-analysis.v1",
            "source": str(args.probe),
            "header": header,
            "control": controls,
            "trigger": triggers,
            "pairwise": pairwise,
            "control_owned_offsets": {
                PARAMETER_NAMES[parameter]: sorted(offsets)
                for parameter, offsets in owned_by_parameter.items()
            },
        }
        args.json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        print(f"wrote {args.json}")


if __name__ == "__main__":
    main()

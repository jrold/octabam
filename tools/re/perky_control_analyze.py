#!/usr/bin/env python3
"""Analyze PerkyBits' v1.2.1 Noise/Tone control-state JSONL probe.

Input is produced by the `perkybits-control-probe` target on the private
PerkyBits `octabam-control-probe` branch.  This script deliberately consumes
numeric input/output state only: no PĒRKONS firmware, code or table blobs enter
the Octabam repository.

The first job is structural, not curve fitting:

* prove the four control words in RAM are exactly the requested 0..4095 values;
* find renderer-state bytes affected by each control after 16 update() passes;
* identify bytes still moving on each smoothing iteration;
* separate trigger-owned velocity/note deltas from continuous controls;
* report cross-term bytes when a --pairwise probe is present.

Once those ownership sets are stable, a later fitter can translate only the
small integer recurrences that actually matter to the 0x120-byte renderer.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import struct
import sys
from typing import Iterable

SCHEMA = "perkybits-control-v1"
STATE_BYTES = 0x120
EXPECTED_ANCHORS = (0, 1, 512, 1024, 1536, 2047, 2048, 2049,
                    2560, 3072, 3584, 4094, 4095)


def die(message: str) -> "NoReturn":
    raise SystemExit(f"perky-control-analyze: {message}")


def hex_blob(record: dict, key: str, expected: int | None = None) -> bytes:
    try:
        value = bytes.fromhex(record[key])
    except (KeyError, TypeError, ValueError) as exc:
        die(f"bad {key!r} in snapshot: {exc}")
    if expected is not None and len(value) != expected:
        die(f"{key} is {len(value)} bytes, expected {expected}")
    return value


def ranges(offsets: Iterable[int]) -> list[tuple[int, int]]:
    seq = sorted(set(offsets))
    if not seq:
        return []
    out: list[tuple[int, int]] = []
    start = previous = seq[0]
    for value in seq[1:]:
        if value != previous + 1:
            out.append((start, previous + 1))
            start = value
        previous = value
    out.append((start, previous + 1))
    return out


def fmt_ranges(offsets: Iterable[int]) -> str:
    return ", ".join(
        f"0x{a:03x}" if b == a + 1 else f"0x{a:03x}..0x{b - 1:03x}"
        for a, b in ranges(offsets)
    ) or "(none)"


def changed(a: bytes, b: bytes) -> set[int]:
    if len(a) != len(b):
        die(f"cannot diff blobs of {len(a)} and {len(b)} bytes")
    return {i for i, (x, y) in enumerate(zip(a, b)) if x != y}


def load(path: Path) -> tuple[dict, list[dict]]:
    header: dict | None = None
    snapshots: list[dict] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_number, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                die(f"{path}:{line_number}: invalid JSON: {exc}")
            if record.get("type") == "header":
                if header is not None:
                    die("more than one header record")
                header = record
            elif record.get("type") == "snapshot":
                snapshots.append(record)
            else:
                die(f"{path}:{line_number}: unknown record type {record.get('type')!r}")

    if header is None:
        die("missing header")
    if header.get("schema") != SCHEMA:
        die(f"schema is {header.get('schema')!r}, expected {SCHEMA!r}")
    if header.get("state_bytes") != STATE_BYTES:
        die(f"state_bytes is {header.get('state_bytes')!r}, expected {STATE_BYTES}")
    if not snapshots:
        die("no snapshots")
    return header, snapshots


def validate_control_ram(records: list[dict]) -> None:
    for index, record in enumerate(records):
        raw = hex_blob(record, "control_ram", 16)
        words = struct.unpack("<4I", raw)
        requested = tuple(record.get("controls", ()))
        if words != requested:
            die(f"snapshot {index}: control RAM {words} != requested {requested}")
        hex_blob(record, "state", STATE_BYTES)
        hex_blob(record, "wrapper", 0x40)


def control_groups(records: list[dict]):
    groups: dict[tuple[int, int, int], dict[int, dict]] = defaultdict(dict)
    for record in records:
        if record.get("sweep") != "control":
            continue
        key = (int(record["mode"]),
               int(record["sweep_parameter"]),
               int(record["sweep_value"]))
        iteration = int(record["iteration"])
        if iteration in groups[key]:
            die(f"duplicate control snapshot {key} iteration {iteration}")
        groups[key][iteration] = record
    return groups


def analyze_controls(records: list[dict]) -> dict:
    groups = control_groups(records)
    result: dict[str, dict] = {}

    for mode in (0, 2):
        for parameter in range(4):
            key_name = f"m{mode}-p{parameter}"
            base_key = (mode, parameter, 2048)
            if base_key not in groups or 16 not in groups[base_key]:
                die(f"missing settled baseline {base_key}")
            baseline = hex_blob(groups[base_key][16], "state", STATE_BYTES)
            baseline_wrapper = hex_blob(groups[base_key][16], "wrapper", 0x40)

            owned: set[int] = set()
            wrapper_owned: set[int] = set()
            latest_motion: dict[int, int] = {}
            anchors_seen: list[int] = []

            for value in EXPECTED_ANCHORS:
                key = (mode, parameter, value)
                history = groups.get(key)
                if history is None:
                    continue
                anchors_seen.append(value)
                if set(history) != set(range(17)):
                    die(f"{key}: iterations are {sorted(history)}, expected 0..16")

                settled = hex_blob(history[16], "state", STATE_BYTES)
                owned |= changed(baseline, settled)
                wrapper_owned |= changed(
                    baseline_wrapper, hex_blob(history[16], "wrapper", 0x40))

                previous = hex_blob(history[0], "state", STATE_BYTES)
                for iteration in range(1, 17):
                    current = hex_blob(history[iteration], "state", STATE_BYTES)
                    for offset in changed(previous, current):
                        latest_motion[offset] = max(latest_motion.get(offset, 0), iteration)
                    previous = current

            result[key_name] = {
                "mode": mode,
                "parameter": parameter,
                "anchors": anchors_seen,
                "state_offsets": sorted(owned),
                "state_ranges": ranges(owned),
                "wrapper_offsets": sorted(wrapper_owned),
                "wrapper_ranges": ranges(wrapper_owned),
                "latest_motion": {str(k): v for k, v in sorted(latest_motion.items())},
            }

            print(f"MODE {mode} PARAM {parameter}")
            print(f"  settled renderer bytes: {fmt_ranges(owned)}")
            print(f"  settled wrapper bytes:  {fmt_ranges(wrapper_owned)}")
            if latest_motion:
                by_iteration: dict[int, list[int]] = defaultdict(list)
                for offset, iteration in latest_motion.items():
                    by_iteration[iteration].append(offset)
                print("  last update movement:")
                for iteration in sorted(by_iteration):
                    print(f"    iter {iteration:2d}: {fmt_ranges(by_iteration[iteration])}")
            else:
                print("  no renderer-state movement across update() calls")

    return result


def analyze_triggers(records: list[dict]) -> dict:
    grouped: dict[tuple[int, str, int], dict[str, dict]] = defaultdict(dict)
    for record in records:
        sweep = record.get("sweep")
        if sweep not in ("velocity", "note"):
            continue
        key = (int(record["mode"]), str(sweep), int(record["sweep_value"]))
        grouped[key][str(record["phase"])] = record

    result: dict[str, dict] = {}
    for mode in (0, 2):
        for sweep in ("velocity", "note"):
            state_union: set[int] = set()
            wrapper_union: set[int] = set()
            values: list[int] = []
            for (m, s, value), pair in sorted(grouped.items()):
                if (m, s) != (mode, sweep):
                    continue
                if "pre-trigger" not in pair or "post-trigger" not in pair:
                    die(f"trigger pair incomplete for mode {mode} {sweep}={value}")
                values.append(value)
                before, after = pair["pre-trigger"], pair["post-trigger"]
                state_union |= changed(
                    hex_blob(before, "state", STATE_BYTES),
                    hex_blob(after, "state", STATE_BYTES))
                wrapper_union |= changed(
                    hex_blob(before, "wrapper", 0x40),
                    hex_blob(after, "wrapper", 0x40))

            key = f"m{mode}-{sweep}"
            result[key] = {
                "mode": mode,
                "sweep": sweep,
                "values": values,
                "state_offsets": sorted(state_union),
                "state_ranges": ranges(state_union),
                "wrapper_offsets": sorted(wrapper_union),
                "wrapper_ranges": ranges(wrapper_union),
            }
            print(f"MODE {mode} TRIGGER {sweep.upper()}")
            print(f"  renderer trigger bytes: {fmt_ranges(state_union)}")
            print(f"  wrapper trigger bytes:  {fmt_ranges(wrapper_union)}")
    return result


def analyze_pairwise(records: list[dict], controls: dict) -> dict:
    pairwise = [r for r in records if r.get("sweep") == "pairwise"]
    if not pairwise:
        return {}

    # A pairwise byte is interesting when it changes from the all-2048 settled
    # baseline but belongs to neither parameter's univariate ownership set.
    baseline_by_mode: dict[int, bytes] = {}
    control = control_groups(records)
    for mode in (0, 2):
        baseline_by_mode[mode] = hex_blob(control[(mode, 0, 2048)][16],
                                          "state", STATE_BYTES)

    out: dict[str, dict] = {}
    for mode in (0, 2):
        for a in range(4):
            for b in range(a + 1, 4):
                normal = (set(controls[f"m{mode}-p{a}"]["state_offsets"])
                          | set(controls[f"m{mode}-p{b}"]["state_offsets"]))
                extra: set[int] = set()
                count = 0
                for record in pairwise:
                    if int(record["mode"]) != mode:
                        continue
                    pair = int(record["sweep_parameter"])
                    if pair != a * 10 + b:
                        continue
                    count += 1
                    delta = changed(baseline_by_mode[mode],
                                    hex_blob(record, "state", STATE_BYTES))
                    extra |= delta - normal

                key = f"m{mode}-p{a}p{b}"
                out[key] = {
                    "mode": mode,
                    "parameters": [a, b],
                    "records": count,
                    "extra_cross_term_offsets": sorted(extra),
                    "extra_cross_term_ranges": ranges(extra),
                }
                print(f"MODE {mode} PAIR {a}+{b}: "
                      f"extra cross-term bytes {fmt_ranges(extra)}")
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("probe", type=Path,
                        help="JSONL from perkybits-control-probe")
    parser.add_argument("--json", type=Path,
                        help="also write machine-readable ownership summary")
    args = parser.parse_args()

    header, records = load(args.probe)
    validate_control_ram(records)
    print(f"schema {header['schema']} -- {len(records)} snapshots -- control RAM: OK")

    controls = analyze_controls(records)
    triggers = analyze_triggers(records)
    pairwise = analyze_pairwise(records, controls)

    if args.json:
        payload = {
            "schema": "perky-control-analysis-v1",
            "source": str(args.probe),
            "control": controls,
            "trigger": triggers,
            "pairwise": pairwise,
        }
        args.json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        print(f"wrote {args.json}")


if __name__ == "__main__":
    main()

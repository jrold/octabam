#!/usr/bin/env python3
"""Analyze all three original v1.2.1 Noise/Tone control modes.

Input is emitted by ``perkybits-noise-tone-control-probe``.  Physical panel
M1/M2/M3 are captured explicitly and mapped to firmware modes 1/0/2; firmware
mode 1 is the separate Waveform2 renderer, while 0/2 use NoiseToneShared.

This is state ownership evidence, not a curve fitter.  It identifies exactly
which 0x120-byte engine fields TUNE/DECAY/ENV/MIX own, how long update()
smoothing continues to mutate them, trigger overlap, and optional pairwise
cross-terms before Octabam replaces the synthetic PERKY2 control law.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import struct
from typing import Iterable, NoReturn

SCHEMA = "perkybits-noise-tone-control-v2"
STATE_BYTES = 0x120
PANEL_TO_FIRMWARE = (1, 0, 2)
PARAMETER_NAMES = ("TUNE", "DECAY", "ENV", "MIX")
EXPECTED_ANCHORS = (
    0, 1, 512, 1024, 1536, 2047, 2048,
    2049, 2560, 3072, 3584, 4094, 4095,
)

# Descriptive only: ownership is always derived from the captured bytes.
KNOWN_REGIONS = (
    ("control history", 0x01C, 0x02C),
    ("oscillator/common pitch A", 0x02C, 0x040),
    ("noise state", 0x060, 0x072),
    ("amplitude envelope", 0x074, 0x09C),
    ("resonant filter", 0x09C, 0x0B8),
    ("common prepared controls", 0x0BA, 0x0C4),
    ("shared renderer oscillator B", 0x0C4, 0x0DC),
    ("Waveform2 oscillator", 0x0D4, 0x0EC),
    ("renderer mix/output control", 0x0F8, 0x100),
)


def die(message: str) -> NoReturn:
    raise SystemExit("noise-tone-control-analyze: " + message)


def blob(record: dict, key: str, size: int) -> bytes:
    try:
        raw = bytes.fromhex(record[key])
    except (KeyError, TypeError, ValueError) as exc:
        die(f"bad {key!r}: {exc}")
    if len(raw) != size:
        die(f"{key} is {len(raw)} bytes, expected {size}")
    return raw


def changed(left: bytes, right: bytes) -> set[int]:
    if len(left) != len(right):
        die("cannot diff unequal blobs")
    return {i for i, (a, b) in enumerate(zip(left, right)) if a != b}


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


def fmt(offsets: Iterable[int]) -> str:
    return ", ".join(
        f"0x{a:03x}" if b == a + 1 else f"0x{a:03x}..0x{b - 1:03x}"
        for a, b in ranges(offsets)
    ) or "(none)"


def regions(offsets: Iterable[int]) -> list[str]:
    values = set(offsets)
    return [
        name for name, start, end in KNOWN_REGIONS
        if any(start <= value < end for value in values)
    ]


def load(path: Path) -> tuple[dict, list[dict]]:
    header = None
    snapshots: list[dict] = []
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
                snapshots.append(record)
            else:
                die(f"{path}:{number}: unknown record type")
    if header is None:
        die("missing header")
    if header.get("schema") != SCHEMA:
        die(f"schema {header.get('schema')!r}, expected {SCHEMA!r}")
    if header.get("state_bytes") != STATE_BYTES:
        die("unexpected Noise/Tone state size")
    if tuple(header.get("panel_mode_to_firmware", ())) != PANEL_TO_FIRMWARE:
        die("panel MODE mapping is not 1/0/2")
    if not snapshots:
        die("no snapshots")
    return header, snapshots


def validate(records: list[dict]) -> None:
    for number, record in enumerate(records):
        blob(record, "state", STATE_BYTES)
        blob(record, "wrapper", 0x40)
        control_ram = blob(record, "control_ram", 16)
        requested = tuple(record.get("controls", ()))
        if struct.unpack("<4I", control_ram) != requested:
            die(f"snapshot {number}: control RAM does not equal requested controls")
        panel = int(record.get("panel_mode", -1))
        firmware = int(record.get("firmware_mode", -1))
        if not 0 <= panel < 3 or firmware != PANEL_TO_FIRMWARE[panel]:
            die(f"snapshot {number}: MODE mapping drift")


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
            die(f"duplicate {key} iteration {iteration}")
        groups[key][iteration] = record
    return groups


def analyze_controls(records: list[dict]):
    groups = control_groups(records)
    report: dict[str, dict] = {}
    ownership: dict[int, set[int]] = defaultdict(set)

    for panel in range(3):
        renderer = "Waveform2" if PANEL_TO_FIRMWARE[panel] == 1 else "NoiseToneShared"
        for parameter, name in enumerate(PARAMETER_NAMES):
            baseline_group = groups.get((panel, parameter, 2048))
            if baseline_group is None or 16 not in baseline_group:
                die(f"missing M{panel + 1} {name} baseline")
            baseline = blob(baseline_group[16], "state", STATE_BYTES)
            baseline_wrapper = blob(baseline_group[16], "wrapper", 0x40)
            owned: set[int] = set()
            wrapper_owned: set[int] = set()
            latest: dict[int, int] = {}
            seen: list[int] = []

            for value in EXPECTED_ANCHORS:
                history = groups.get((panel, parameter, value))
                if history is None:
                    continue
                seen.append(value)
                if set(history) != set(range(17)):
                    die(f"M{panel + 1} {name}={value}: expected iterations 0..16")
                owned |= changed(baseline, blob(history[16], "state", STATE_BYTES))
                wrapper_owned |= changed(
                    baseline_wrapper, blob(history[16], "wrapper", 0x40)
                )
                previous = blob(history[0], "state", STATE_BYTES)
                for iteration in range(1, 17):
                    current = blob(history[iteration], "state", STATE_BYTES)
                    for offset in changed(previous, current):
                        latest[offset] = max(latest.get(offset, 0), iteration)
                    previous = current

            ownership[parameter] |= owned
            key = f"m{panel}-p{parameter}"
            report[key] = {
                "panel_mode": panel,
                "firmware_mode": PANEL_TO_FIRMWARE[panel],
                "renderer": renderer,
                "parameter": parameter,
                "parameter_name": name,
                "anchors": seen,
                "state_offsets": sorted(owned),
                "state_ranges": ranges(owned),
                "known_regions": regions(owned),
                "wrapper_offsets": sorted(wrapper_owned),
                "wrapper_ranges": ranges(wrapper_owned),
                "latest_motion": {str(k): v for k, v in sorted(latest.items())},
            }
            print(
                f"M{panel + 1} / firmware {PANEL_TO_FIRMWARE[panel]} / "
                f"{renderer} / {name}"
            )
            print(f"  settled state: {fmt(owned)}")
            print(f"  regions:       {', '.join(regions(owned)) or '(none)'}")
            print(f"  wrapper:       {fmt(wrapper_owned)}")
            if latest:
                print(f"  latest update: {max(latest.values())}")
                still = [offset for offset, when in latest.items() if when == 16]
                if still:
                    print(f"  moving @16:    {fmt(still)}")
    return report, ownership


def analyze_triggers(records: list[dict], control_owned: set[int]) -> dict:
    grouped: dict[tuple[int, str, int], dict[str, dict]] = defaultdict(dict)
    for record in records:
        sweep = str(record.get("sweep"))
        if sweep not in ("velocity", "note"):
            continue
        key = (int(record["panel_mode"]), sweep, int(record["sweep_value"]))
        grouped[key][str(record["phase"])] = record

    out: dict[str, dict] = {}
    for panel in range(3):
        for sweep in ("velocity", "note"):
            state: set[int] = set()
            wrapper: set[int] = set()
            values: list[int] = []
            for (p, kind, value), pair in sorted(grouped.items()):
                if (p, kind) != (panel, sweep):
                    continue
                if set(pair) != {"pre-trigger", "post-trigger"}:
                    die(f"incomplete M{panel + 1} {sweep}={value} trigger pair")
                values.append(value)
                state |= changed(
                    blob(pair["pre-trigger"], "state", STATE_BYTES),
                    blob(pair["post-trigger"], "state", STATE_BYTES),
                )
                wrapper |= changed(
                    blob(pair["pre-trigger"], "wrapper", 0x40),
                    blob(pair["post-trigger"], "wrapper", 0x40),
                )
            overlap = state & control_owned
            key = f"m{panel}-{sweep}"
            out[key] = {
                "panel_mode": panel,
                "firmware_mode": PANEL_TO_FIRMWARE[panel],
                "sweep": sweep,
                "values": values,
                "state_offsets": sorted(state),
                "state_ranges": ranges(state),
                "wrapper_offsets": sorted(wrapper),
                "wrapper_ranges": ranges(wrapper),
                "control_overlap_offsets": sorted(overlap),
                "control_overlap_ranges": ranges(overlap),
            }
            print(f"M{panel + 1} TRIGGER {sweep.upper()}: {fmt(state)}")
            print(f"  control overlap: {fmt(overlap)}")
    return out


def analyze_pairwise(records: list[dict], controls: dict) -> dict:
    pairwise = [record for record in records if record.get("sweep") == "pairwise"]
    if not pairwise:
        print("PAIRWISE: not present (use --pairwise for cross-term proof)")
        return {}
    groups = control_groups(records)
    baseline = {
        panel: blob(groups[(panel, 0, 2048)][16], "state", STATE_BYTES)
        for panel in range(3)
    }
    out: dict[str, dict] = {}
    for panel in range(3):
        for a in range(4):
            for b in range(a + 1, 4):
                expected = (
                    set(controls[f"m{panel}-p{a}"]["state_offsets"])
                    | set(controls[f"m{panel}-p{b}"]["state_offsets"])
                )
                extra: set[int] = set()
                count = 0
                for record in pairwise:
                    if int(record["panel_mode"]) != panel:
                        continue
                    if int(record["sweep_parameter"]) != a * 10 + b:
                        continue
                    count += 1
                    delta = changed(
                        baseline[panel], blob(record, "state", STATE_BYTES)
                    )
                    extra |= delta - expected
                key = f"m{panel}-p{a}p{b}"
                out[key] = {
                    "panel_mode": panel,
                    "parameters": [a, b],
                    "parameter_names": [PARAMETER_NAMES[a], PARAMETER_NAMES[b]],
                    "records": count,
                    "extra_cross_term_offsets": sorted(extra),
                    "extra_cross_term_ranges": ranges(extra),
                    "known_regions": regions(extra),
                }
                print(
                    f"M{panel + 1} PAIR {PARAMETER_NAMES[a]}+{PARAMETER_NAMES[b]}: "
                    f"extra {fmt(extra)}"
                )
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("probe", type=Path)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()

    header, records = load(args.probe)
    validate(records)
    print(f"{len(records)} snapshots; control RAM and physical MODE map: PASS")
    controls, ownership = analyze_controls(records)
    all_control = set().union(*ownership.values())
    triggers = analyze_triggers(records, all_control)
    pairwise = analyze_pairwise(records, controls)

    print("CONTROL OWNERSHIP UNION")
    for parameter, name in enumerate(PARAMETER_NAMES):
        print(f"  {name:5s}: {fmt(ownership[parameter])}")
    print(f"  ALL  : {fmt(all_control)}")

    if args.json:
        payload = {
            "schema": "octabam.perky.noise-tone-control-analysis.v2",
            "source": str(args.probe),
            "header": header,
            "control": controls,
            "trigger": triggers,
            "pairwise": pairwise,
            "control_owned_offsets": {
                PARAMETER_NAMES[i]: sorted(ownership[i]) for i in range(4)
            },
        }
        args.json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        print(f"wrote {args.json}")


if __name__ == "__main__":
    main()

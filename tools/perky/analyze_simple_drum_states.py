#!/usr/bin/env python3
"""Analyze authentic Simple Drum prepared-state captures from PerkyBits.

Input is the 27-file capture set produced by the isolated PerkyBits
``perkybits-simple-state`` helper: three physical MODE positions times midpoint
plus TUNE/DECAY/ENV/MIX low/high corners. The report is intentionally byte-level
first. It highlights known renderer-owned fields, but does not infer a control
law from names or nearby addresses.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
PERKY = ROOT / "modules" / "perky"
TOOLS = ROOT / "tools" / "perky"
sys.path.insert(0, str(PERKY))
sys.path.insert(0, str(TOOLS))

import extract_simple_drum_assets as assets  # noqa: E402
import simple_drum_compact as compact  # noqa: E402

PRESETS = (
    "mid",
    "tune0", "tune4095",
    "decay0", "decay4095",
    "env0", "env4095",
    "mix0", "mix4095",
)

KNOWN_FIELDS = (
    (0x06, 0x07, "velocity"),
    (0x30, 0x34, "osc.phase"),
    (0x34, 0x38, "osc.increment"),
    (0x38, 0x3C, "osc.current_wave"),
    (0x3C, 0x40, "osc.next_wave"),
    (0x74, 0x75, "amp_env.state"),
    (0x75, 0x76, "amp_env.shape"),
    (0x78, 0x79, "amp_env.flag4"),
    (0x7A, 0x7B, "amp_env.flag6"),
    (0x7B, 0x7C, "amp_env.trigger"),
    (0x80, 0x84, "amp_env.value"),
    (0x84, 0x88, "amp_env.hold"),
    (0x94, 0x96, "amp_env.attack"),
    (0x96, 0x98, "amp_env.decay"),
    (0xB8, 0xB9, "mute"),
    (0xBA, 0xBC, "raw_pitch"),
    (0xC4, 0xC5, "pitch_env.state"),
    (0xC5, 0xC6, "pitch_env.shape"),
    (0xC8, 0xC9, "pitch_env.flag4"),
    (0xCA, 0xCB, "pitch_env.flag6"),
    (0xCB, 0xCC, "pitch_env.trigger"),
    (0xD0, 0xD4, "pitch_env.value"),
    (0xD4, 0xD8, "pitch_env.hold"),
    (0xE4, 0xE6, "pitch_env.attack"),
    (0xE6, 0xE8, "pitch_env.decay"),
    (0xEC, 0xEE, "pitch_env.amount"),
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_capture(directory: Path, mode: int, preset: str) -> bytes:
    path = directory / f"simple_drum_m{mode}_{preset}.bin"
    data = path.read_bytes()
    if len(data) != assets.STATE_BYTES:
        raise ValueError(
            f"{path}: expected 0x{assets.STATE_BYTES:x} bytes, got 0x{len(data):x}"
        )
    return data


def changed_offsets(a: bytes, b: bytes) -> list[int]:
    if len(a) != len(b):
        raise ValueError("state lengths differ")
    return [i for i, (x, y) in enumerate(zip(a, b)) if x != y]


def ranges(offsets: list[int]) -> list[list[int]]:
    if not offsets:
        return []
    out: list[list[int]] = []
    start = prev = offsets[0]
    for value in offsets[1:]:
        if value == prev + 1:
            prev = value
            continue
        out.append([start, prev + 1])
        start = prev = value
    out.append([start, prev + 1])
    return out


def field_names(offsets: list[int]) -> list[str]:
    touched: list[str] = []
    offset_set = set(offsets)
    for start, end, name in KNOWN_FIELDS:
        if any(i in offset_set for i in range(start, end)):
            touched.append(name)
    return touched


def compact_changed_words(a: bytes, b: bytes) -> list[int]:
    wa = compact.CompactSimpleDrum.from_arm(a).words
    wb = compact.CompactSimpleDrum.from_arm(b).words
    return [i for i, (x, y) in enumerate(zip(wa, wb)) if x != y]


def comparison(base: bytes, other: bytes) -> dict:
    offsets = changed_offsets(base, other)
    return {
        "changed_byte_count": len(offsets),
        "changed_byte_ranges": ranges(offsets),
        "known_fields": field_names(offsets),
        "compact_changed_words": compact_changed_words(base, other),
    }


def analyze(directory: Path) -> dict:
    captures: dict[int, dict[str, bytes]] = {}
    for mode in (1, 2, 3):
        captures[mode] = {
            preset: load_capture(directory, mode, preset)
            for preset in PRESETS
        }

    report: dict = {
        "state_bytes": assets.STATE_BYTES,
        "compact_words": compact.WORDS_PER_VOICE,
        "modes": {},
        "mode_midpoint_comparisons": {},
    }

    for mode in (1, 2, 3):
        midpoint = captures[mode]["mid"]
        mode_report = {
            "mid_sha256": sha256(midpoint),
            "mid_metadata": assets.state_metadata(midpoint),
            "captures": {},
        }
        for preset in PRESETS:
            data = captures[mode][preset]
            mode_report["captures"][preset] = {
                "sha256": sha256(data),
                "metadata": assets.state_metadata(data),
                "vs_mid": comparison(midpoint, data),
            }
        report["modes"][f"M{mode}"] = mode_report

    m1 = captures[1]["mid"]
    for mode in (2, 3):
        report["mode_midpoint_comparisons"][f"M1_vs_M{mode}"] = comparison(
            m1, captures[mode]["mid"]
        )

    # Cross-mode intersection/union for each physical control corner. This
    # quickly separates stable renderer fields from mode-specific preparation.
    control_summary: dict[str, dict] = {}
    for control in ("tune", "decay", "env", "mix"):
        low = f"{control}0"
        high = f"{control}4095"
        low_sets = []
        high_sets = []
        for mode in (1, 2, 3):
            mid = captures[mode]["mid"]
            low_sets.append(set(changed_offsets(mid, captures[mode][low])))
            high_sets.append(set(changed_offsets(mid, captures[mode][high])))
        low_union = sorted(set().union(*low_sets))
        high_union = sorted(set().union(*high_sets))
        low_intersection = sorted(set.intersection(*low_sets))
        high_intersection = sorted(set.intersection(*high_sets))
        control_summary[control] = {
            "low_union_ranges": ranges(low_union),
            "low_intersection_ranges": ranges(low_intersection),
            "high_union_ranges": ranges(high_union),
            "high_intersection_ranges": ranges(high_intersection),
            "low_known_fields": field_names(low_union),
            "high_known_fields": field_names(high_union),
        }
    report["control_summary"] = control_summary
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("capture_dir", type=Path,
                    help="directory containing 27 simple_drum_m*_*.bin captures")
    ap.add_argument("--out", type=Path,
                    help="write JSON report here (stdout if omitted)")
    args = ap.parse_args()

    report = analyze(args.capture_dir)
    text = json.dumps(report, indent=2) + "\n"
    if args.out is None:
        print(text, end="")
    else:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text)
        print(args.out)


if __name__ == "__main__":
    main()

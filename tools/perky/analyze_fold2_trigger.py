#!/usr/bin/env python3
"""Derive the exact PĒRKONS v1.2.1 Fold Drum 2 trigger contract.

This consumes the all-family capture corpus produced by
``tools/perky/capture_engine_fixtures.py`` after the harness gained both
first-trigger and active-retrigger snapshots. For each of the nine Voice-2/A1
mode/control-corner cases it compares:

* fresh control state -> first trigger + mandatory v1.2.1 post-trigger update;
* state after 512 original-ARM samples -> active retrigger + the same update.

Besides the human-readable report, this writes a normalized JSON contract to
``out/perky/fold2-trigger-contract.json`` by default. Absolute ARM oscillator
pointers are already represented by the compact model's PRIMARY selector bit,
so the contract contains only portable 16-bit compact-state mutations.

Rules are classified as CONST, COPY, TOGGLE, or CASES. CASES preserves every
observed before/after pair instead of guessing a formula. The shipping DSP seam
must therefore be derived from evidence even when the original ARM operation
cannot yet be reduced to a simpler rule.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "modules/perky"))

import fold_drum2_compact as compact

FIX_DEFAULT = ROOT / "out/perky/engine-fixtures"
OUT_DEFAULT = ROOT / "out/perky/fold2-trigger-contract.json"
ENGINE = 4  # one-based catalog number; Fold Drum 2 is zero-based family 3
ARM_STATE_OFFSET = 0xC4
ARM_STATE_SIZE = 0x134

NAMES = {
    compact.VELOCITY: "velocity",
    compact.MUTE: "mute",
    compact.OSC_A + 0: "osc_a.phase.lo",
    compact.OSC_A + 1: "osc_a.phase.hi",
    compact.OSC_A + 2: "osc_a.frequency.lo",
    compact.OSC_A + 3: "osc_a.frequency.hi",
    compact.OSC_A + 4: "osc_a.wave_ptr.lo",
    compact.OSC_A + 5: "osc_a.wave_ptr.hi",
    compact.OSC_A + 6: "osc_a.last.lo",
    compact.OSC_A + 7: "osc_a.last.hi",
    compact.RAW_PITCH: "raw_pitch",
    compact.PITCH_AMOUNT: "pitch_amount",
    compact.OSC_B + 0: "osc_b.phase.lo",
    compact.OSC_B + 1: "osc_b.phase.hi",
    compact.OSC_B + 2: "osc_b.frequency.lo",
    compact.OSC_B + 3: "osc_b.frequency.hi",
    compact.OSC_B + 4: "osc_b.wave_ptr.lo",
    compact.OSC_B + 5: "osc_b.wave_ptr.hi",
    compact.OSC_B + 6: "osc_b.last.lo",
    compact.OSC_B + 7: "osc_b.last.hi",
    compact.MODE: "mode",
    compact.COUNTER: "transient_counter",
    compact.FOLD: "fold",
    compact.NOISE_COUNT: "noise_count",
    compact.NOISE_RATE: "noise_rate",
    compact.NOISE_SAMPLE: "noise_sample",
    compact.FADE_SAVED: "fade_saved",
    compact.FADE: "fade",
    compact.PRIMARY: "primary",
}

for base, prefix in ((compact.AMP_ENV, "amp_env"),
                     (compact.PITCH_ENV, "pitch_env")):
    for rel in range(11):
        NAMES.setdefault(base + rel, f"{prefix}[{rel}]")


def _voice(path: Path) -> compact.FoldDrum2:
    blob = path.read_bytes()
    raw = blob[ARM_STATE_OFFSET:ARM_STATE_OFFSET + ARM_STATE_SIZE]
    if len(raw) != ARM_STATE_SIZE:
        raise RuntimeError(f"short Fold Drum 2 wrapper snapshot: {path}")
    return compact.FoldDrum2.from_arm(raw)


def _fixture_error(path: Path) -> None:
    print("Fold Drum 2 trigger analysis needs regenerated engine fixtures.",
          file=sys.stderr)
    print("The capture tool requires the same external firmware, PerkyBits",
          file=sys.stderr)
    print("source tree and Unicorn build arguments used for the existing",
          file=sys.stderr)
    print("local corpus. Re-run tools/perky/capture_engine_fixtures.py with",
          file=sys.stderr)
    print("those arguments, then run this analyzer again.", file=sys.stderr)
    print(f"First missing file: {path}", file=sys.stderr)
    raise SystemExit(2)


def _load_cases(fix: Path, pre_name: str, post_name: str):
    cases: list[tuple[str, compact.FoldDrum2, compact.FoldDrum2]] = []
    for mode in range(3):
        for corner in range(3):
            case = fix / f"engine-{ENGINE}-mode-{mode + 1}-corner-{corner}"
            pre_path = case / pre_name
            post_path = case / post_name
            if not pre_path.exists():
                _fixture_error(pre_path)
            if not post_path.exists():
                _fixture_error(post_path)
            cases.append((f"m{mode + 1}/c{corner}",
                          _voice(pre_path), _voice(post_path)))
    return cases


def _rule(pairs: list[tuple[int, int]], all_pre: list[list[int]],
          index: int, labels: list[str]) -> dict:
    posts = [post for _pre, post in pairs]
    if len(set(posts)) == 1:
        return {"kind": "CONST", "value": posts[0]}

    sources = []
    for source in range(compact.WORDS):
        if source == index:
            continue
        if all(posts[case] == all_pre[case][source]
               for case in range(len(pairs))):
            sources.append(source)
    if sources:
        return {
            "kind": "COPY",
            "sources": [
                {"index": source,
                 "name": NAMES.get(source, f"word[{source}]")}
                for source in sources
            ],
        }

    if all(post == (pre ^ 1) for pre, post in pairs):
        return {"kind": "TOGGLE", "mask": 1}

    return {
        "kind": "CASES",
        "values": [
            {"case": label, "before": before, "after": after}
            for label, (before, after) in zip(labels, pairs)
        ],
    }


def _rule_text(rule: dict) -> str:
    kind = rule["kind"]
    if kind == "CONST":
        return f"CONST 0x{rule['value']:04x}"
    if kind == "COPY":
        rendered = ", ".join(
            f"{source['index']}:{source['name']}" for source in rule["sources"]
        )
        return f"COPY pre[{rendered}]"
    if kind == "TOGGLE":
        return f"TOGGLE mask 0x{rule['mask']:04x}"
    return "CASE-DEPENDENT"


def _analyze(title: str, cases) -> dict:
    if len(cases) != 9:
        raise RuntimeError(f"expected 9 Fold Drum 2 cases, got {len(cases)}")

    labels = [label for label, _pre, _post in cases]
    all_pre = [pre.words for _label, pre, _post in cases]
    by_word: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for _label, pre, post in cases:
        for index, (before, after) in enumerate(zip(pre.words, post.words)):
            by_word[index].append((before, after))

    changed = {
        index: pairs for index, pairs in by_word.items()
        if any(before != after for before, after in pairs)
    }

    print(title)
    print("=" * len(title))
    print(f"cases: {len(cases)}")
    print(f"changed compact words: {len(changed)} / {compact.WORDS}")
    print()

    words = []
    for index in sorted(changed):
        pairs = changed[index]
        name = NAMES.get(index, f"word[{index}]")
        rule = _rule(pairs, all_pre, index, labels)
        print(f"{index:02d}  {name:<24} {_rule_text(rule)}")
        print("    " + "  ".join(
            f"{label}: {before:04x}->{after:04x}"
            for (label, _pre, _post), (before, after)
            in zip(cases, pairs)
        ))
        words.append({"index": index, "name": name, "rule": rule})

    print("\nTRIGGER_RULES")
    for word in words:
        print(f"{word['index']}:{word['name']}:{_rule_text(word['rule'])}")
    print()

    # Preserve complete normalized states as a backstop. This makes the JSON a
    # lossless compact-state oracle, not merely a best-effort rule classifier.
    normalized_cases = []
    for label, pre, post in cases:
        normalized_cases.append({
            "case": label,
            "pre": pre.words,
            "post": post.words,
        })

    return {
        "title": title,
        "case_count": len(cases),
        "changed_indices": sorted(changed),
        "words": words,
        "cases": normalized_cases,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fixtures", type=Path, default=FIX_DEFAULT)
    ap.add_argument("--json", type=Path, default=OUT_DEFAULT,
                    help="machine-readable normalized trigger contract")
    args = ap.parse_args()

    first = _load_cases(
        args.fixtures,
        "wrapper-window-pre-trigger.bin",
        "wrapper-window-before.bin",
    )
    retrigger = _load_cases(
        args.fixtures,
        "wrapper-window-retrigger-pre.bin",
        "wrapper-window-retrigger-before.bin",
    )

    first_contract = _analyze(
        "Fold Drum 2 original ARM first-trigger delta",
        first,
    )
    retrigger_contract = _analyze(
        "Fold Drum 2 original ARM active-retrigger delta",
        retrigger,
    )

    first_changed = set(first_contract["changed_indices"])
    retrigger_changed = set(retrigger_contract["changed_indices"])
    only_active = sorted(retrigger_changed - first_changed)
    only_first = sorted(first_changed - retrigger_changed)
    shared = sorted(first_changed & retrigger_changed)

    print("DELTA_SET_COMPARISON")
    print("active-only: " + (", ".join(map(str, only_active)) or "none"))
    print("first-only: " + (", ".join(map(str, only_first)) or "none"))
    print("shared: " + ", ".join(map(str, shared)))

    contract = {
        "schema": "octabam.perky.fold2-trigger.v1",
        "engine_zero_based": 3,
        "engine_one_based": ENGINE,
        "arm_state_offset": ARM_STATE_OFFSET,
        "arm_state_size": ARM_STATE_SIZE,
        "compact_words": compact.WORDS,
        "notes": [
            "Derived only from original v1.2.1 ARM before/after snapshots.",
            "PRIMARY is a normalized oscillator selector, not an ARM pointer.",
            "CASES rules are intentionally not generalized without evidence.",
            "No firmware bytes or audio are embedded in this contract.",
        ],
        "first_trigger": first_contract,
        "active_retrigger": retrigger_contract,
        "comparison": {
            "active_only": only_active,
            "first_only": only_first,
            "shared": shared,
        },
    }

    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(contract, indent=2) + "\n")
    print(f"contract: {args.json}")


if __name__ == "__main__":
    main()

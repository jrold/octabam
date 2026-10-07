#!/usr/bin/env python3
"""Report exact PĒRKONS v1.2.1 Fold Drum 2 trigger/retrigger mutations.

This consumes the all-family capture corpus produced by
``tools/perky/capture_engine_fixtures.py`` after the harness gained both
first-trigger and active-retrigger snapshots. For each of the nine Voice-2/A1
mode/control-corner cases it reports:

* fresh control state -> first trigger + mandatory v1.2.1 post-trigger update;
* state after 512 original-ARM samples -> active retrigger + the same update.

The second delta is the critical one for Fold Drum 2 because its renderer owns
two oscillators plus a crossfade/primary selector. The report is evidence, not
a shipping implementation: it prints every compact word changed by the
original ARM path so the Octatrack seam can reproduce the trigger law without
guessing hidden envelope, oscillator, transient, crossfade, or selector state.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "modules/perky"))

import fold_drum2_compact as compact

FIX = ROOT / "out/perky/engine-fixtures"
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


def _load_cases(pre_name: str, post_name: str):
    cases: list[tuple[str, compact.FoldDrum2, compact.FoldDrum2]] = []
    for mode in range(3):
        for corner in range(3):
            case = FIX / f"engine-{ENGINE}-mode-{mode + 1}-corner-{corner}"
            pre_path = case / pre_name
            post_path = case / post_name
            if not pre_path.exists():
                _fixture_error(pre_path)
            if not post_path.exists():
                _fixture_error(post_path)
            cases.append((f"m{mode + 1}/c{corner}",
                          _voice(pre_path), _voice(post_path)))
    return cases


def _classify(pairs: list[tuple[int, int]], all_pre: list[list[int]], index: int) -> str:
    posts = [post for _pre, post in pairs]
    if len(set(posts)) == 1:
        return f"CONST 0x{posts[0]:04x}"

    # Detect exact copies from another compact pre-trigger word. Requiring all
    # nine cases prevents a one-case coincidence from becoming a trigger rule.
    sources = []
    for source in range(compact.WORDS):
        if source == index:
            continue
        if all(posts[case] == all_pre[case][source]
               for case in range(len(pairs))):
            sources.append(source)
    if sources:
        rendered = ", ".join(
            f"{source}:{NAMES.get(source, f'word[{source}]')}"
            for source in sources
        )
        return f"COPY pre[{rendered}]"

    if all(post == (pre ^ 1) for pre, post in pairs):
        return "TOGGLE bit0"

    return "CASE-DEPENDENT"


def _report(title: str, cases) -> set[int]:
    if len(cases) != 9:
        raise RuntimeError(f"expected 9 Fold Drum 2 cases, got {len(cases)}")

    all_pre = [pre.words for _label, pre, _post in cases]
    changed: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for _label, pre, post in cases:
        for index, (before, after) in enumerate(zip(pre.words, post.words)):
            changed[index].append((before, after))

    changed = {
        index: pairs
        for index, pairs in changed.items()
        if any(before != after for before, after in pairs)
    }

    print(title)
    print("=" * len(title))
    print(f"cases: {len(cases)}")
    print(f"changed compact words: {len(changed)} / {compact.WORDS}")
    print()

    for index in sorted(changed):
        pairs = changed[index]
        name = NAMES.get(index, f"word[{index}]")
        classification = _classify(pairs, all_pre, index)
        print(f"{index:02d}  {name:<24} {classification}")
        print("    " + "  ".join(
            f"{label}: {before:04x}->{after:04x}"
            for (label, _pre, _post), (before, after)
            in zip(cases, pairs)
        ))

    print("\nTRIGGER_RULES")
    for index in sorted(changed):
        pairs = changed[index]
        name = NAMES.get(index, f"word[{index}]")
        print(f"{index}:{name}:{_classify(pairs, all_pre, index)}")
    print()
    return set(changed)


def main() -> None:
    first = _load_cases(
        "wrapper-window-pre-trigger.bin",
        "wrapper-window-before.bin",
    )
    retrigger = _load_cases(
        "wrapper-window-retrigger-pre.bin",
        "wrapper-window-retrigger-before.bin",
    )

    first_changed = _report(
        "Fold Drum 2 original ARM first-trigger delta",
        first,
    )
    retrigger_changed = _report(
        "Fold Drum 2 original ARM active-retrigger delta",
        retrigger,
    )

    only_active = sorted(retrigger_changed - first_changed)
    only_first = sorted(first_changed - retrigger_changed)
    print("DELTA_SET_COMPARISON")
    print("active-only: " + (", ".join(map(str, only_active)) or "none"))
    print("first-only: " + (", ".join(map(str, only_first)) or "none"))
    print("shared: " + ", ".join(map(str, sorted(first_changed & retrigger_changed))))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Validate the evidence-derived Fold Drum 2 trigger contract.

The contract is emitted by ``tools/perky/analyze_fold2_trigger.py`` from the
original PĒRKONS v1.2.1 ARM snapshots.  This verifier is intentionally stricter
than the analyzer: shipping qualification succeeds only when every changed
compact-state word is explained by one unambiguous deterministic primitive.

By default unresolved CASES rules and ambiguous COPY rules are fatal.  Use
``--allow-unresolved`` only while investigating a freshly regenerated corpus;
it never makes the contract shippable.

When the contract is fully resolved, a normalized operation plan is written to
``out/perky/fold2-trigger-plan.json``.  That plan is deliberately architecture
neutral; DSP56300 assembly is a separate executable gate so copy/swap ordering
cannot be hidden by a code generator.
"""
from __future__ import annotations

from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
CONTRACT_DEFAULT = ROOT / "out/perky/fold2-trigger-contract.json"
PLAN_DEFAULT = ROOT / "out/perky/fold2-trigger-plan.json"
SCHEMA = "octabam.perky.fold2-trigger.v1"
WORDS = 51
PHASES = ("first_trigger", "active_retrigger")


def die(message: str) -> "NoReturn":
    raise AssertionError(message)


def u16(value, where: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        die(f"{where}: expected integer, got {value!r}")
    if not 0 <= value <= 0xFFFF:
        die(f"{where}: 16-bit value out of range: {value!r}")
    return value


def word_index(value, where: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        die(f"{where}: expected word index, got {value!r}")
    if not 0 <= value < WORDS:
        die(f"{where}: word index out of range: {value!r}")
    return value


def validate_state(values, where: str) -> list[int]:
    if not isinstance(values, list) or len(values) != WORDS:
        die(f"{where}: expected {WORDS} compact words")
    return [u16(value, f"{where}[{i}]") for i, value in enumerate(values)]


def evaluate(rule: dict, pre: list[int], index: int, where: str) -> int:
    if not isinstance(rule, dict):
        die(f"{where}: rule must be an object")
    kind = rule.get("kind")

    if kind == "CONST":
        return u16(rule.get("value"), f"{where}.value")

    if kind == "COPY":
        sources = rule.get("sources")
        if not isinstance(sources, list) or not sources:
            die(f"{where}: COPY has no sources")
        indices = []
        for n, source in enumerate(sources):
            if not isinstance(source, dict):
                die(f"{where}.sources[{n}]: expected object")
            indices.append(word_index(source.get("index"),
                                      f"{where}.sources[{n}].index"))
        if len(set(indices)) != 1:
            # Multiple source words may happen to hold equal values in all nine
            # capture cases.  That is evidence of equality, not evidence of
            # which ARM source was copied, so it is deliberately unresolved.
            raise ValueError(
                f"{where}: ambiguous COPY sources {sorted(set(indices))}"
            )
        return pre[indices[0]]

    if kind == "TOGGLE":
        mask = u16(rule.get("mask"), f"{where}.mask")
        return (pre[index] ^ mask) & 0xFFFF

    # The verifier understands these exact primitives so the analyzer can grow
    # without weakening the shipping gate.  They are not inferred here.
    if kind == "XOR":
        mask = u16(rule.get("mask"), f"{where}.mask")
        return (pre[index] ^ mask) & 0xFFFF

    if kind == "ADD16":
        delta = u16(rule.get("delta"), f"{where}.delta")
        return (pre[index] + delta) & 0xFFFF

    if kind in ("COPY_XOR", "COPY_ADD16"):
        source = word_index(rule.get("source"), f"{where}.source")
        if kind == "COPY_XOR":
            mask = u16(rule.get("mask"), f"{where}.mask")
            return (pre[source] ^ mask) & 0xFFFF
        delta = u16(rule.get("delta"), f"{where}.delta")
        return (pre[source] + delta) & 0xFFFF

    if kind == "CASES":
        raise ValueError(f"{where}: case-dependent rule")

    die(f"{where}: unsupported rule kind {kind!r}")


def normalized_operation(word: dict, rule: dict) -> dict:
    op = {
        "dst": word_index(word.get("index"), "operation.dst"),
        "name": str(word.get("name", "")),
        "op": rule["kind"],
    }
    kind = rule["kind"]
    if kind == "CONST":
        op["value"] = rule["value"]
    elif kind == "COPY":
        op["src"] = rule["sources"][0]["index"]
    elif kind in ("TOGGLE", "XOR"):
        op["mask"] = rule["mask"]
    elif kind == "ADD16":
        op["delta"] = rule["delta"]
    elif kind == "COPY_XOR":
        op["src"] = rule["source"]
        op["mask"] = rule["mask"]
    elif kind == "COPY_ADD16":
        op["src"] = rule["source"]
        op["delta"] = rule["delta"]
    else:
        die(f"cannot normalize unresolved rule {kind!r}")
    return op


def validate_phase(name: str, phase: dict, allow_unresolved: bool) -> tuple[list[dict], list[str]]:
    if not isinstance(phase, dict):
        die(f"{name}: phase must be an object")
    cases = phase.get("cases")
    if not isinstance(cases, list) or len(cases) != 9:
        die(f"{name}: expected exactly 9 original-ARM cases")

    labels = []
    normalized_cases = []
    recomputed_changed = set()
    for n, case in enumerate(cases):
        if not isinstance(case, dict):
            die(f"{name}.cases[{n}]: expected object")
        label = case.get("case")
        if not isinstance(label, str) or not label:
            die(f"{name}.cases[{n}]: missing case label")
        if label in labels:
            die(f"{name}: duplicate case label {label!r}")
        labels.append(label)
        pre = validate_state(case.get("pre"), f"{name}.{label}.pre")
        post = validate_state(case.get("post"), f"{name}.{label}.post")
        recomputed_changed.update(
            i for i, (before, after) in enumerate(zip(pre, post))
            if before != after
        )
        normalized_cases.append((label, pre, post))

    changed = phase.get("changed_indices")
    if not isinstance(changed, list):
        die(f"{name}.changed_indices: expected list")
    declared_changed = [
        word_index(value, f"{name}.changed_indices[{n}]")
        for n, value in enumerate(changed)
    ]
    if declared_changed != sorted(set(declared_changed)):
        die(f"{name}.changed_indices: must be sorted and unique")
    if set(declared_changed) != recomputed_changed:
        die(
            f"{name}: changed-index mismatch; declared={declared_changed} "
            f"recomputed={sorted(recomputed_changed)}"
        )

    words = phase.get("words")
    if not isinstance(words, list):
        die(f"{name}.words: expected list")
    by_index = {}
    for n, word in enumerate(words):
        if not isinstance(word, dict):
            die(f"{name}.words[{n}]: expected object")
        index = word_index(word.get("index"), f"{name}.words[{n}].index")
        if index in by_index:
            die(f"{name}: duplicate rule for word {index}")
        by_index[index] = word
    if set(by_index) != recomputed_changed:
        die(
            f"{name}: rule-word mismatch; rules={sorted(by_index)} "
            f"changed={sorted(recomputed_changed)}"
        )

    operations = []
    unresolved = []
    for index in sorted(by_index):
        word = by_index[index]
        rule = word.get("rule")
        where = f"{name}.word[{index}]"

        if isinstance(rule, dict) and rule.get("kind") == "CASES":
            values = rule.get("values")
            if not isinstance(values, list) or len(values) != len(normalized_cases):
                die(f"{where}: CASES must preserve all 9 observations")
            for n, ((label, pre, post), observed) in enumerate(
                    zip(normalized_cases, values)):
                if not isinstance(observed, dict):
                    die(f"{where}.values[{n}]: expected object")
                if observed.get("case") != label:
                    die(f"{where}.values[{n}]: case-label mismatch")
                before = u16(observed.get("before"), f"{where}.values[{n}].before")
                after = u16(observed.get("after"), f"{where}.values[{n}].after")
                if before != pre[index] or after != post[index]:
                    die(f"{where}.values[{n}]: not lossless against case state")
            unresolved.append(f"{where}: CASES")
            continue

        try:
            for label, pre, post in normalized_cases:
                got = evaluate(rule, pre, index, where)
                if got != post[index]:
                    die(
                        f"{where}: rule fails {label}: "
                        f"got=0x{got:04x} want=0x{post[index]:04x}"
                    )
            operations.append(normalized_operation(word, rule))
        except ValueError as exc:
            unresolved.append(str(exc))

    if unresolved and not allow_unresolved:
        raise RuntimeError(
            f"{name}: trigger contract is not shippable:\n  - "
            + "\n  - ".join(unresolved)
        )

    return operations, unresolved


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--contract", type=Path, default=CONTRACT_DEFAULT)
    ap.add_argument("--plan", type=Path, default=PLAN_DEFAULT)
    ap.add_argument("--allow-unresolved", action="store_true")
    args = ap.parse_args()

    if not args.contract.exists():
        print(
            "Fold Drum 2 trigger contract is missing. Regenerate the local "
            "original-ARM engine fixtures, then run "
            "tools/perky/analyze_fold2_trigger.py first.",
            file=sys.stderr,
        )
        raise SystemExit(2)

    contract = json.loads(args.contract.read_text())
    if contract.get("schema") != SCHEMA:
        die(f"unexpected schema {contract.get('schema')!r}; expected {SCHEMA!r}")
    if contract.get("engine_zero_based") != 3:
        die("contract is not Fold Drum 2 / zero-based engine 3")
    if contract.get("compact_words") != WORDS:
        die(f"contract compact word count is not {WORDS}")

    phase_plans = {}
    all_unresolved = []
    for phase_name in PHASES:
        operations, unresolved = validate_phase(
            phase_name, contract.get(phase_name), args.allow_unresolved
        )
        phase_plans[phase_name] = operations
        all_unresolved.extend(f"{phase_name}: {item}" for item in unresolved)

    comparison = contract.get("comparison")
    if not isinstance(comparison, dict):
        die("comparison: expected object")
    first = set(contract["first_trigger"]["changed_indices"])
    active = set(contract["active_retrigger"]["changed_indices"])
    expected_comparison = {
        "active_only": sorted(active - first),
        "first_only": sorted(first - active),
        "shared": sorted(first & active),
    }
    for key, want in expected_comparison.items():
        got = comparison.get(key)
        if got != want:
            die(f"comparison.{key}: got {got!r}, want {want!r}")

    if all_unresolved:
        print("Fold Drum 2 trigger contract: ANALYSIS ONLY")
        for item in all_unresolved:
            print(f"UNRESOLVED {item}")
        print("No shipping trigger plan emitted.")
        return

    plan = {
        "schema": "octabam.perky.fold2-trigger-plan.v1",
        "source_contract": SCHEMA,
        "engine_zero_based": 3,
        "compact_words": WORDS,
        "semantics": [
            "All COPY-like operations read the pre-trigger state.",
            "Writes therefore require snapshot/temporary handling for cycles or swaps.",
            "The DSP56300 executable seam gate remains authoritative for ordering.",
        ],
        "first_trigger": phase_plans["first_trigger"],
        "active_retrigger": phase_plans["active_retrigger"],
    }
    args.plan.parent.mkdir(parents=True, exist_ok=True)
    args.plan.write_text(json.dumps(plan, indent=2) + "\n")
    print(
        "Fold Drum 2 trigger contract: PASS "
        f"(9 first-trigger + 9 active-retrigger ARM cases; "
        f"{len(phase_plans['first_trigger'])} first-trigger writes; "
        f"{len(phase_plans['active_retrigger'])} active-retrigger writes; "
        "all deterministic and unambiguous)"
    )
    print(f"plan: {args.plan}")


if __name__ == "__main__":
    main()

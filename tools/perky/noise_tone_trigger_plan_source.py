#!/usr/bin/env python3
"""Validate and emit DSP56300 source for Noise/Tone trigger contracts.

Consumes ``out/perky/noise-tone-trigger-contract.json`` produced from original
v1.2.1 ARM snapshots.  Only directly proven primitive rules are compilable:
CONST, COPY, TOGGLE and ADD16.  Any CASES rule is a hard stop; three observed
corners are not generalized into a shipping formula.

M1/Waveform2 has a 25-word compact state. M2/M3 share the existing 41-word
Noise/Tone compact ABI. All fit in the common 128-word renderer scratch used as
a frozen pre-trigger snapshot during the short trigger routine.
"""
from __future__ import annotations

import json
from pathlib import Path

SCHEMA = "octabam.perky.noise-tone-trigger.v1"
PANELS = ("M1", "M2", "M3")
PHASES = ("first_trigger", "active_retrigger")
EXPECTED_WORDS = {"M1": 25, "M2": 41, "M3": 41}


def fail(message: str) -> "NoReturn":
    raise AssertionError("Noise/Tone trigger plan: " + message)


def u16(value, where: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 0xFFFF:
        fail(f"{where}: invalid u16 {value!r}")
    return value


def validate_rule(rule: dict, words: int, where: str) -> None:
    kind = rule.get("kind")
    if kind == "CONST":
        u16(rule.get("value"), where + ".value")
        return
    if kind == "COPY":
        sources = rule.get("sources")
        if not isinstance(sources, list) or len(sources) != 1:
            fail(f"{where}: COPY must have one unambiguous source, got {sources!r}")
        source = sources[0]
        if not isinstance(source, int) or isinstance(source, bool) or not 0 <= source < words:
            fail(f"{where}: invalid COPY source {source!r}")
        return
    if kind == "TOGGLE":
        if rule.get("mask") != 1:
            fail(f"{where}: only proven one-bit TOGGLE is supported")
        return
    if kind == "ADD16":
        u16(rule.get("delta"), where + ".delta")
        return
    if kind == "CASES":
        fail(f"{where}: CASES rule is not generalized; more evidence required")
    fail(f"{where}: unsupported rule {kind!r}")


def validate_contract(contract: dict) -> dict:
    if contract.get("schema") != SCHEMA:
        fail(f"schema {contract.get('schema')!r}, expected {SCHEMA!r}")
    if contract.get("engine_zero_based") != 10 or contract.get("engine_one_based") != 11:
        fail("wrong engine identity")
    if contract.get("mode_map") != [1, 0, 2]:
        fail("physical mode map drifted")

    normalized = {}
    for phase in PHASES:
        phases = contract.get(phase)
        if not isinstance(phases, dict):
            fail(f"missing {phase}")
        normalized[phase] = {}
        for panel in PANELS:
            row = phases.get(panel)
            if not isinstance(row, dict):
                fail(f"missing {phase}/{panel}")
            words = EXPECTED_WORDS[panel]
            if row.get("compact_words") != words:
                fail(f"{phase}/{panel}: compact geometry drift")
            changed = row.get("changed_indices")
            rules = row.get("words")
            if not isinstance(changed, list) or not isinstance(rules, list):
                fail(f"{phase}/{panel}: missing changed/rules")
            if [item.get("index") for item in rules] != changed:
                fail(f"{phase}/{panel}: rule destinations != changed list")
            for item in rules:
                index = item.get("index")
                if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < words:
                    fail(f"{phase}/{panel}: bad destination {index!r}")
                validate_rule(item.get("rule", {}), words,
                              f"{phase}/{panel}/word{index}")
            normalized[phase][panel] = rules
    return normalized


def load_contract(path: Path) -> tuple[dict, dict]:
    if not path.is_file():
        raise FileNotFoundError(
            f"Noise/Tone trigger contract missing: {path}; run "
            "tools/perky/analyze_noise_tone_trigger.py first"
        )
    contract = json.loads(path.read_text())
    return contract, validate_contract(contract)


def emit_snapshot(words: int, *, live: str = "r6", frozen: str = "r5") -> str:
    lines = []
    for index in range(words):
        lines += [
            f"        move    x:({live}+${index:x}),a",
            f"        move    a1,x:({frozen}+${index:x})",
        ]
    return "\n".join(lines) + ("\n" if lines else "")


def emit_rule(item: dict, *, live: str = "r6", frozen: str = "r5") -> list[str]:
    index = item["index"]
    rule = item["rule"]
    kind = rule["kind"]
    dst = f"x:({live}+${index:x})"
    pre = f"x:({frozen}+${index:x})"
    if kind == "CONST":
        return [f"        move    #>${rule['value'] & 0xFFFF:06x},a", f"        move    a1,{dst}"]
    if kind == "COPY":
        source = rule["sources"][0]
        return [f"        move    x:({frozen}+${source:x}),a", f"        move    a1,{dst}"]
    if kind == "TOGGLE":
        return [f"        move    {pre},a", "        eor     #>$000001,a",
                "        and     #>$00ffff,a", f"        move    a1,{dst}"]
    if kind == "ADD16":
        return [f"        move    {pre},a", f"        add     #>${rule['delta'] & 0xFFFF:06x},a",
                "        and     #>$00ffff,a", f"        move    a1,{dst}"]
    fail(f"cannot emit {kind!r}")


def emit_routine(rules: list[dict], *, label: str, words: int,
                 scratch: int, prefix: str) -> str:
    if not 0 <= scratch <= 0xFFFF:
        fail("scratch outside X memory")
    lines = [label + ":", f"        move    #>${scratch:06x},r5"]
    text = "\n".join(lines) + "\n"
    text += emit_snapshot(words)
    for item in rules:
        text += "\n".join(emit_rule(item)) + "\n"
    text += "        rts\n"
    return text


def emit_all(contract_path: Path, *, scratch: int = 0x3900) -> str:
    _contract, plans = load_contract(contract_path)
    chunks = []
    for phase in PHASES:
        short = "first" if phase == "first_trigger" else "active"
        for panel in PANELS:
            label = f"pk_noise_tone_trigger_{short}_{panel.lower()}"
            chunks.append(emit_routine(
                plans[phase][panel],
                label=label,
                words=EXPECTED_WORDS[panel],
                scratch=scratch,
                prefix=f"nt_{short}_{panel.lower()}",
            ))
    return "\n".join(chunks)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("contract", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    source = emit_all(args.contract)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(source)
        print(args.out)
    else:
        print(source, end="")

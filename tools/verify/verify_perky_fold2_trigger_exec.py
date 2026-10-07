#!/usr/bin/env python3
"""Execute the evidence-derived Fold Drum 2 trigger plan on DSP56300.

This gate intentionally consumes only local ``out/`` artifacts generated from
the user's original PĒRKONS v1.2.1 ARM corpus.  No firmware-derived state is
committed.  It proves that the architecture-neutral trigger plan emitted by
``verify_perky_fold2_trigger_contract.py`` can be translated into actual 56300
instructions without changing any word that belongs to the separately-qualified
control/update seam.

All trigger reads and PRIMARY conditions are taken from a frozen pre-trigger
snapshot at X:$300. Writes go to the live compact state at X:$200. This makes
copy/swap ordering explicit and preserves the contract's pre-state semantics.
"""
from __future__ import annotations

from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
PERKY = ROOT / "modules/perky"
OUT = ROOT / "out/perky/fold2-trigger-exec"
CONTRACT = ROOT / "out/perky/fold2-trigger-contract.json"
PLAN = ROOT / "out/perky/fold2-trigger-plan.json"

sys.path.insert(0, str(ROOT / "tools/verify"))
import verify_perky_controlled_voice_exec as c

WORDS = 51
VISIBLE_WORDS = 64
VOICE_X = 0x200
SNAPSHOT_X = 0x300
PRIMARY = 50
PLAN_SCHEMA = "octabam.perky.fold2-trigger-plan.v2"
CONTRACT_SCHEMA = "octabam.perky.fold2-trigger.v1"
PHASES = ("first_trigger", "active_retrigger")


def fail(message: str) -> "NoReturn":
    raise AssertionError("Fold2 trigger DSP gate: " + message)


def h(value: int) -> str:
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 0xFFFF:
        fail(f"invalid u16 value {value!r}")
    return f"{value:06x}"


def validate_primitive(op: dict, where: str) -> None:
    kind = op.get("op")
    if kind == "SAME":
        return
    if kind == "CONST":
        h(op.get("value"))
        return
    if kind == "COPY":
        src = op.get("src")
        if not isinstance(src, int) or isinstance(src, bool) or not 0 <= src < WORDS:
            fail(f"{where}: bad COPY source {src!r}")
        return
    if kind == "XOR":
        h(op.get("mask"))
        return
    if kind == "ADD16":
        h(op.get("delta"))
        return
    fail(f"{where}: unsupported primitive {kind!r}")


def validate_plan(plan: dict) -> list[dict]:
    if plan.get("schema") != PLAN_SCHEMA:
        fail(f"unexpected plan schema {plan.get('schema')!r}")
    if plan.get("source_contract") != CONTRACT_SCHEMA:
        fail("plan does not name the expected ARM contract")
    if plan.get("engine_zero_based") != 3 or plan.get("compact_words") != WORDS:
        fail("plan geometry/engine drifted")
    if plan.get("primary_word") != PRIMARY:
        fail("PRIMARY word drifted")
    if plan.get("observations") != 18:
        fail("plan was not derived from all 18 ARM observations")

    trigger_words = plan.get("trigger_changed_words")
    operations = plan.get("operations")
    if not isinstance(trigger_words, list) or not isinstance(operations, list):
        fail("plan is missing trigger word/operation lists")
    if len(operations) != len(trigger_words):
        fail("operation count does not match trigger_changed_words")
    if [op.get("dst") for op in operations] != trigger_words:
        fail("operation destinations do not exactly follow trigger_changed_words")
    if len(set(trigger_words)) != len(trigger_words):
        fail("duplicate trigger destination")

    control_owned = set(plan.get("control_owned_words", []))
    if control_owned & set(trigger_words):
        fail("trigger plan overlaps control-owned state")

    for n, op in enumerate(operations):
        dst = op.get("dst")
        if not isinstance(dst, int) or isinstance(dst, bool) or not 0 <= dst < WORDS:
            fail(f"operation {n}: bad destination {dst!r}")
        if op.get("op") == "BY_PRIMARY":
            branches = op.get("branches")
            if not isinstance(branches, dict) or set(branches) != {"0", "1"}:
                fail(f"operation {n}: BY_PRIMARY must have exact 0/1 branches")
            validate_primitive(branches["0"], f"operation {n}/PRIMARY=0")
            validate_primitive(branches["1"], f"operation {n}/PRIMARY=1")
        else:
            validate_primitive(op, f"operation {n}")
    return operations


def emit_primitive(op: dict, dst: int, indent: str = "        ") -> list[str]:
    kind = op["op"]
    live = f"x:(r6+${dst:x})"
    frozen_dst = f"x:(r5+${dst:x})"
    if kind == "SAME":
        return []
    if kind == "CONST":
        return [
            f"{indent}move    #>${h(op['value'])},a",
            f"{indent}move    a1,{live}",
        ]
    if kind == "COPY":
        return [
            f"{indent}move    x:(r5+${op['src']:x}),a",
            f"{indent}move    a1,{live}",
        ]
    if kind == "XOR":
        return [
            f"{indent}move    {frozen_dst},a",
            f"{indent}eor     #>${h(op['mask'])},a",
            f"{indent}and     #>$00ffff,a",
            f"{indent}move    a1,{live}",
        ]
    if kind == "ADD16":
        return [
            f"{indent}move    {frozen_dst},a",
            f"{indent}add     #>${h(op['delta'])},a",
            f"{indent}and     #>$00ffff,a",
            f"{indent}move    a1,{live}",
        ]
    fail(f"cannot emit primitive {kind!r}")


def build_source(operations: list[dict]) -> str:
    lines = [
        "; Generated locally from the verified Fold2 trigger operation plan.",
        "; X:$200 = live compact state; X:$300 = frozen pre-trigger snapshot.",
        "pk_controlled_voice_exec:",
        f"        move    #>${VOICE_X:06x},r6",
        f"        move    #>${SNAPSHOT_X:06x},r5",
    ]

    # Deliberately unrolled. This is a qualification seam, and explicit copies
    # make it impossible for a loop pointer or write ordering bug to alias state.
    for i in range(WORDS):
        lines.extend((
            f"        move    x:(r6+${i:x}),a",
            f"        move    a1,x:(r5+${i:x})",
        ))

    for n, op in enumerate(operations):
        dst = op["dst"]
        if op["op"] != "BY_PRIMARY":
            lines.extend(emit_primitive(op, dst))
            continue

        zero = f"pkf2t_op{n}_primary0"
        done = f"pkf2t_op{n}_done"
        lines.extend((
            f"        move    x:(r5+${PRIMARY:x}),a",
            "        tst     a",
            f"        beq     {zero}",
        ))
        lines.extend(emit_primitive(op["branches"]["1"], dst))
        lines.append(f"        bra     {done}")
        lines.append(zero + ":")
        lines.extend(emit_primitive(op["branches"]["0"], dst))
        lines.append(done + ":")
        lines.append("        nop")

    lines.extend(("        rts", ""))
    return "\n".join(lines)


def apply_primitive(op: dict, pre: list[int], dst: int) -> int:
    kind = op["op"]
    if kind == "SAME":
        return pre[dst]
    if kind == "CONST":
        return op["value"] & 0xFFFF
    if kind == "COPY":
        return pre[op["src"]] & 0xFFFF
    if kind == "XOR":
        return (pre[dst] ^ op["mask"]) & 0xFFFF
    if kind == "ADD16":
        return (pre[dst] + op["delta"]) & 0xFFFF
    fail(f"cannot apply primitive {kind!r}")


def apply_plan(pre: list[int], operations: list[dict]) -> list[int]:
    out = list(pre)
    selector = pre[PRIMARY]
    if selector not in (0, 1):
        fail(f"pre-trigger PRIMARY is {selector}, expected 0/1")
    for op in operations:
        actual = op
        if op["op"] == "BY_PRIMARY":
            actual = op["branches"][str(selector)]
        out[op["dst"]] = apply_primitive(actual, pre, op["dst"])
    return out


def load_cases(contract: dict, operations: list[dict], control_owned: set[int]):
    if contract.get("schema") != CONTRACT_SCHEMA:
        fail("unexpected ARM contract schema")
    if contract.get("compact_words") != WORDS or contract.get("engine_zero_based") != 3:
        fail("ARM contract geometry/engine drifted")

    trigger_words = {op["dst"] for op in operations}
    cases = []
    for phase in PHASES:
        rows = contract.get(phase, {}).get("cases", [])
        if len(rows) != 9:
            fail(f"{phase}: expected 9 ARM observations")
        for n, row in enumerate(rows):
            pre = row.get("pre")
            post = row.get("post")
            if not isinstance(pre, list) or not isinstance(post, list) or len(pre) != WORDS or len(post) != WORDS:
                fail(f"{phase}[{n}]: malformed state")
            if any(not isinstance(v, int) or isinstance(v, bool) or not 0 <= v <= 0xFFFF for v in pre + post):
                fail(f"{phase}[{n}]: non-u16 state")

            expected = list(pre)
            for dst in trigger_words:
                expected[dst] = post[dst]

            # The architecture-neutral plan itself must recreate exactly the
            # isolated trigger-owned portion of the ARM transition.
            modeled = apply_plan(pre, operations)
            if modeled != expected:
                diffs = [(i, expected[i], modeled[i]) for i in range(WORDS) if expected[i] != modeled[i]]
                fail(f"{phase}[{n}]: plan/ARM mismatch {diffs[:12]}")

            # ARM update-owned mutations may coexist in the source snapshot,
            # but this isolated trigger seam must never absorb them.
            for i in control_owned:
                if expected[i] != pre[i]:
                    fail(f"{phase}[{n}]: isolated expectation changed control-owned word {i}")

            cases.append((f"{phase}-{n}-{row.get('case', 'case')}", pre, expected))
    if len(cases) != 18:
        fail(f"expected 18 ARM cases, got {len(cases)}")
    return cases


def main() -> None:
    if not PLAN.exists() or not CONTRACT.exists():
        print(
            "Fold2 trigger DSP gate: SKIP (local ARM-derived contract/plan missing; "
            "run tools/perky/qualify_fold2_trigger.py first)",
            file=sys.stderr,
        )
        raise SystemExit(2)

    plan = json.loads(PLAN.read_text())
    contract = json.loads(CONTRACT.read_text())
    operations = validate_plan(plan)
    control_owned = set(plan["control_owned_words"])
    cases = load_cases(contract, operations, control_owned)

    c.OUT = OUT
    OUT.mkdir(parents=True, exist_ok=True)
    c.HOST.parent.mkdir(parents=True, exist_ok=True)
    c.build_host()
    source = build_source(operations)
    binary, entry = c.assemble(source)

    def write_data(path: Path, state_words: list[int], _tables: list[int]):
        if len(state_words) != VISIBLE_WORDS:
            fail(f"host visible state is {len(state_words)} words, expected {VISIBLE_WORDS}")
        path.write_text(
            "X 100 " + " ".join(["000000"] * 13) + "\n"
            + f"X {VOICE_X:x} " + " ".join(f"{v & 0xffff:06x}" for v in state_words) + "\n"
            + f"X {SNAPSHOT_X:x} " + " ".join(["000000"] * 100) + "\n"
        )
        return []

    c.write_data = write_data

    zero_record = tuple([0] * 12)
    for tag, pre, expected in cases:
        initial = list(pre) + [0] * (VISIBLE_WORDS - WORDS)
        _audio, states, _rng = c.run(
            binary, entry, tag, initial, [], [(zero_record, -1)]
        )
        got = states[0][:WORDS]
        if got != expected:
            diffs = [
                (i, pre[i], expected[i], got[i])
                for i in range(WORDS) if got[i] != expected[i]
            ]
            fail(f"{tag}: executable state mismatch {diffs[:16]}")
        if states[0][WORDS:VISIBLE_WORDS] != [0] * (VISIBLE_WORDS - WORDS):
            fail(f"{tag}: write escaped the {WORDS}-word Fold2 allocation")

    print(
        "Fold Drum 2 trigger DSP executable gate: PASS "
        f"({len(cases)} ARM observations; {len(operations)} trigger operations; "
        "pre-state copy/swap semantics; control-owned words untouched)"
    )


if __name__ == "__main__":
    main()

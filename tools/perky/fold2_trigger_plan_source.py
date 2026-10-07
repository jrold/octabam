#!/usr/bin/env python3
"""Validate and emit DSP56300 source for a qualified Fold Drum 2 trigger plan.

The plan itself is firmware-derived and lives only under ``out/``.  This tracked
module is the single translation layer used by both the isolated executable
oracle gate and the hidden production candidate.  Every source read and every
PRIMARY decision is made from a frozen pre-trigger snapshot so COPY/swap
semantics cannot depend on write ordering.
"""
from __future__ import annotations

from pathlib import Path
import json

WORDS = 51
PRIMARY = 50
PLAN_SCHEMA = "octabam.perky.fold2-trigger-plan.v2"
CONTRACT_SCHEMA = "octabam.perky.fold2-trigger.v1"


def _fail(message: str) -> "NoReturn":
    raise AssertionError("Fold2 trigger plan: " + message)


def _u16(value, where: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 0xFFFF:
        _fail(f"{where}: invalid u16 {value!r}")
    return value


def _validate_primitive(op: dict, where: str) -> None:
    kind = op.get("op")
    if kind == "SAME":
        return
    if kind == "CONST":
        _u16(op.get("value"), where + ".value")
        return
    if kind == "COPY":
        src = op.get("src")
        if not isinstance(src, int) or isinstance(src, bool) or not 0 <= src < WORDS:
            _fail(f"{where}: invalid COPY source {src!r}")
        return
    if kind == "XOR":
        _u16(op.get("mask"), where + ".mask")
        return
    if kind == "ADD16":
        _u16(op.get("delta"), where + ".delta")
        return
    _fail(f"{where}: unsupported primitive {kind!r}")


def validate_plan(plan: dict) -> list[dict]:
    if plan.get("schema") != PLAN_SCHEMA:
        _fail(f"unexpected schema {plan.get('schema')!r}")
    if plan.get("source_contract") != CONTRACT_SCHEMA:
        _fail("unexpected source contract")
    if plan.get("engine_zero_based") != 3:
        _fail("wrong engine index")
    if plan.get("compact_words") != WORDS or plan.get("primary_word") != PRIMARY:
        _fail("state geometry drifted")
    if plan.get("observations") != 18:
        _fail("plan is not based on all 18 ARM observations")

    trigger_words = plan.get("trigger_changed_words")
    operations = plan.get("operations")
    if not isinstance(trigger_words, list) or not isinstance(operations, list):
        _fail("missing operation lists")
    if len(trigger_words) != len(operations):
        _fail("operation count mismatch")
    if [op.get("dst") for op in operations] != trigger_words:
        _fail("operation destinations do not match trigger_changed_words")
    if len(trigger_words) != len(set(trigger_words)):
        _fail("duplicate destination")

    control = set(plan.get("control_owned_words", []))
    if control & set(trigger_words):
        _fail("trigger/control ownership overlap")

    for n, op in enumerate(operations):
        dst = op.get("dst")
        if not isinstance(dst, int) or isinstance(dst, bool) or not 0 <= dst < WORDS:
            _fail(f"operation {n}: invalid destination {dst!r}")
        if op.get("op") == "BY_PRIMARY":
            branches = op.get("branches")
            if not isinstance(branches, dict) or set(branches) != {"0", "1"}:
                _fail(f"operation {n}: BY_PRIMARY needs exact 0/1 branches")
            _validate_primitive(branches["0"], f"operation {n}/primary0")
            _validate_primitive(branches["1"], f"operation {n}/primary1")
        else:
            _validate_primitive(op, f"operation {n}")
    return operations


def load_plan(path: Path) -> tuple[dict, list[dict]]:
    if not path.exists():
        raise FileNotFoundError(
            f"qualified Fold2 trigger plan missing: {path}; run "
            "tools/perky/qualify_fold2_trigger.py first"
        )
    plan = json.loads(path.read_text())
    return plan, validate_plan(plan)


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
    _fail(f"cannot apply {kind!r}")


def apply_plan(pre: list[int], operations: list[dict]) -> list[int]:
    if len(pre) != WORDS:
        _fail(f"pre-state has {len(pre)} words")
    selector = pre[PRIMARY]
    if selector not in (0, 1):
        _fail(f"PRIMARY is {selector}, expected 0/1")
    out = list(pre)
    for op in operations:
        actual = op
        if op["op"] == "BY_PRIMARY":
            actual = op["branches"][str(selector)]
        out[op["dst"]] = apply_primitive(actual, pre, op["dst"])
    return out


def _hex16(value: int) -> str:
    return f"{_u16(value, 'immediate'):06x}"


def _emit_primitive(op: dict, dst: int, live: str, frozen: str) -> list[str]:
    kind = op["op"]
    live_dst = f"x:({live}+${dst:x})"
    frozen_dst = f"x:({frozen}+${dst:x})"
    if kind == "SAME":
        return []
    if kind == "CONST":
        return [f"        move #>${_hex16(op['value'])},a", f"        move a1,{live_dst}"]
    if kind == "COPY":
        return [f"        move x:({frozen}+${op['src']:x}),a", f"        move a1,{live_dst}"]
    if kind == "XOR":
        return [f"        move {frozen_dst},a", f"        eor #>${_hex16(op['mask'])},a",
                "        and #>$00ffff,a", f"        move a1,{live_dst}"]
    if kind == "ADD16":
        return [f"        move {frozen_dst},a", f"        add #>${_hex16(op['delta'])},a",
                "        and #>$00ffff,a", f"        move a1,{live_dst}"]
    _fail(f"cannot emit {kind!r}")


def emit_apply(operations: list[dict], *, live_reg: str = "r6",
               snapshot_reg: str = "r5", label_prefix: str = "pkf2t") -> str:
    """Emit only plan application; caller must have frozen all 51 words first."""
    lines: list[str] = []
    for n, op in enumerate(operations):
        dst = op["dst"]
        if op["op"] != "BY_PRIMARY":
            lines.extend(_emit_primitive(op, dst, live_reg, snapshot_reg))
            continue
        zero = f"{label_prefix}_op{n}_primary0"
        done = f"{label_prefix}_op{n}_done"
        lines += [f"        move x:({snapshot_reg}+${PRIMARY:x}),a", "        tst a", f"        beq {zero}"]
        lines += _emit_primitive(op["branches"]["1"], dst, live_reg, snapshot_reg)
        lines += [f"        bra {done}", zero + ":"]
        lines += _emit_primitive(op["branches"]["0"], dst, live_reg, snapshot_reg)
        lines += [done + ":", "        nop"]
    return "\n".join(lines) + ("\n" if lines else "")


def emit_snapshot(*, live_reg: str = "r6", snapshot_reg: str = "r5") -> str:
    lines = []
    for i in range(WORDS):
        lines += [f"        move x:({live_reg}+${i:x}),a", f"        move a1,x:({snapshot_reg}+${i:x})"]
    return "\n".join(lines) + "\n"


def emit_routine(operations: list[dict], *, label: str,
                 live_reg: str = "r6", snapshot_reg: str = "r5",
                 snapshot_address: int | None = None) -> str:
    """Emit snapshot + apply + RTS. Optionally initialize snapshot_reg."""
    lines = [label + ":"]
    if snapshot_address is not None:
        if not 0 <= snapshot_address <= 0xFFFF:
            _fail(f"snapshot address out of X range: {snapshot_address:#x}")
        lines.append(f"        move #>${snapshot_address:06x},{snapshot_reg}")
    text = "\n".join(lines) + "\n"
    text += emit_snapshot(live_reg=live_reg, snapshot_reg=snapshot_reg)
    text += emit_apply(operations, live_reg=live_reg, snapshot_reg=snapshot_reg,
                       label_prefix=label)
    text += "        rts\n"
    return text

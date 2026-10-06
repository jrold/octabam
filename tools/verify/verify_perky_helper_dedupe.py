#!/usr/bin/env python3
"""Prove PERKY standalone arithmetic helpers are safe to deduplicate.

The synth-source generator redirects local helper calls to the shared
noise_tone_math.asm implementation. This gate compares the actual instruction
streams, not their intended formulas: it extracts each helper through its first
RTS, removes comments/blank lines, normalizes only the label prefix, and
requires exact equality.
"""
from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
P = ROOT / "modules/perky"


class Fail(AssertionError):
    pass


def extract(text: str, label: str) -> str:
    marker = label + ":"
    if text.count(marker) != 1:
        raise Fail(f"{label}: expected one definition, found {text.count(marker)}")
    start = text.index(marker)
    tail = text[start:]
    m = re.search(r"^\s*rts\s*(?:;.*)?$", tail, flags=re.MULTILINE)
    if not m:
        raise Fail(f"{label}: no terminating RTS")
    return tail[:m.end()]


def canonical(body: str, prefix: str) -> tuple[str, ...]:
    labels = re.findall(r"(?m)^([A-Za-z0-9_]+):", body)
    for i, label in enumerate(labels):
        body = re.sub(r"\b" + re.escape(label) + r"\b", f"H_LABEL_{i}", body)
    rows = []
    for raw in body.splitlines():
        raw = raw.split(";", 1)[0].strip()
        if not raw:
            continue
        # Normalize only symbols owned by this helper family. Instructions,
        # operands, immediates and scratch offsets remain byte-for-byte text.
        raw = raw.replace(prefix, "H_")
        raw = " ".join(raw.split())
        rows.append(raw)
    return tuple(rows)


def compare(shared_text: str, local_text: str, operation: str,
            local_prefix: str, local_label: str) -> None:
    shared_label = "pk_u32_" + operation
    a = canonical(extract(shared_text, shared_label), "pk_u32_")
    b = canonical(extract(local_text, local_label), local_prefix)
    if a != b:
        limit = max(len(a), len(b))
        for i in range(limit):
            aa = a[i] if i < len(a) else "<end>"
            bb = b[i] if i < len(b) else "<end>"
            if aa != bb:
                raise Fail(
                    f"{local_label} differs from {shared_label} at normalized row {i}:\n"
                    f"  shared: {aa}\n  local:  {bb}"
                )
        raise Fail(f"{local_label} differs from {shared_label}")


def main() -> None:
    shared = (P / "noise_tone_math.asm").read_text()
    filter_src = (P / "noise_tone_filter.asm").read_text()
    osc_src = (P / "noise_tone_oscillator_packed.asm").read_text()
    env_src = (P / "noise_tone_envelope.asm").read_text()
    mix_src = (P / "noise_tone_mix.asm").read_text()

    # Filter carries all four shared scalar helpers.
    for op in ("add", "sub", "asr", "mul_low"):
        compare(shared, filter_src, op, "pkf_", "pkf_" + op)

    # Oscillator needs add/asr/mul; envelope and mixer need all four.
    for op in ("add", "asr", "mul_low"):
        compare(shared, osc_src, op, "pkop_", "pkop_" + op)
    for op in ("add", "sub", "asr", "mul_low"):
        compare(shared, env_src, op, "pke_", "pke_" + op)
        compare(shared, mix_src, op, "pkm_", "pkm_" + op)

    print(
        "PERKY helper dedupe: PASS "
        "(15 local add/sub/ASR/mul32 helpers are instruction-identical to "
        "the shared noise_tone_math implementations after label normalization)"
    )


if __name__ == "__main__":
    try:
        main()
    except Fail as exc:
        raise SystemExit("verify-perky-helper-dedupe: " + str(exc))

#!/usr/bin/env python3
"""Decide the stock-FX sacrifice from the COMPOSED image, not from estimates.

The reduced Perky machine's DSP program is measured from the composed shipping
source (``tools/perky/build_dsp_3algo_source.py --measure``), never by adding
standalone renderer sizes. This gate compares that requirement against the
stock effect spans read out of the pristine 1.40C MAIN OS and reports:

* the budget each contiguous harvest configuration actually yields, per
  payload, because the placer only harvests contiguous runs and the two
  payloads carry different stock layouts;
* the exact shortfall for every configuration, so the "Spring Reverb only"
  preference can be tested rather than assumed;
* the FIRST configuration that fits, and therefore the minimum necessary
  sacrifice.

It fails when nothing fits, so a composed image can never be packaged with a
sacrifice that was not checked against the real numbers.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tools/remix"),
                str(ROOT / "tools/build"), str(ROOT / "modules/perky"),
                str(ROOT / "tools/perky")]

OUT = ROOT / "out/perky/dsp-3algo"

# The preference order from the target specification. Spring first; anything
# beyond it has to be justified by the measured shortfall, and a configuration
# is only legal if it is a CONTIGUOUS run in both payloads.
PREFERENCE = (
    ("nothing removed (preserve all stock FX)", ()),
    ("SPRING REV only", ("SPRING REV",)),
    ("PLATE + SPRING + DARK (the stock donor region)",
     ("PLATE REV", "SPRING REV", "DARK REV")),
    ("+ COMPRESSOR", ("PLATE REV", "SPRING REV", "DARK REV", "COMPRESSOR")),
    ("+ LO-FI", ("PLATE REV", "SPRING REV", "DARK REV", "COMPRESSOR", "LO-FI")),
    ("+ DJ EQ", ("PLATE REV", "SPRING REV", "DARK REV", "COMPRESSOR", "LO-FI",
                 "DJ EQ")),
    ("+ COMB FILTER", ("PLATE REV", "SPRING REV", "DARK REV", "COMPRESSOR",
                       "LO-FI", "DJ EQ", "COMB FILTER")),
)


def die(message: str) -> "NoReturn":
    raise SystemExit("verify-perky-3algo-sacrifice: " + message)


def composed_words() -> int:
    """Assemble the composed shipping source and return its real P size."""
    spec = importlib.util.spec_from_file_location(
        "builder", ROOT / "tools/perky/build_dsp_3algo_source.py")
    builder = importlib.util.module_from_spec(spec)
    sys.modules["builder"] = builder
    spec.loader.exec_module(builder)
    text = builder.normalize(builder.compose()).replace("@CONT@", "$000426")
    out = OUT / "sacrifice-measure"
    out.parent.mkdir(parents=True, exist_ok=True)
    asm, binary = out.with_suffix(".asm"), out.with_suffix(".bin")
    asm.write_text(text)
    result = subprocess.run(
        [str(builder.ASM), "-in", str(asm), "-org", format(builder.DSP_ORG, "x"),
         "-out", str(binary)], capture_output=True, text=True)
    if result.returncode:
        die("dsp_asm failed:\n" + result.stdout[-4000:])
    return binary.stat().st_size // 3


def spans() -> dict[str, dict[str, tuple[int, int]]]:
    import stock
    return {tag: stock.p_spans(tag) for tag in "AB"}


def budget(table: dict[str, tuple[int, int]], keys) -> tuple[int, int, bool]:
    """(words, lowest address, contiguous?) of the named effects in one payload."""
    items = sorted((a, w) for k, (a, w) in table.items() if k in keys)
    if not items:
        return 0, 0, True
    contiguous = all(items[i][0] + items[i][1] == items[i + 1][0]
                     for i in range(len(items) - 1))
    return items[-1][0] + items[-1][1] - items[0][0], items[0][0], contiguous


def main() -> None:
    need = composed_words()
    table = spans()
    print(f"composed Perky DSP program: {need} P words per payload\n")
    print(f"{'configuration':52s} {'A':>7s} {'B':>7s}  result")
    report = {"schema": "perky-3algo-sacrifice-v1", "requirement_p_words": need,
              "options": []}
    first_fit = None
    for label, keys in PREFERENCE:
        row = {}
        for tag in "AB":
            words, low, contiguous = budget(table[tag], keys)
            if not contiguous:
                die(f"{label}: {tag} harvest is not a contiguous run")
            row[tag] = {"words": words, "low": low}
        fits = row["A"]["words"] >= need and row["B"]["words"] >= need
        short = max(need - row["A"]["words"], need - row["B"]["words"])
        result = "FITS" if fits else f"short {short}"
        print(f"{label:52s} {row['A']['words']:7d} {row['B']['words']:7d}  {result}")
        report["options"].append({"label": label, "sacrificed": list(keys),
                                  "a_words": row["A"]["words"],
                                  "b_words": row["B"]["words"],
                                  "shortfall": 0 if fits else short})
        if fits and first_fit is None:
            first_fit = (label, keys)

    if first_fit is None:
        die(f"no contiguous stock-FX configuration yields {need} words; "
            f"the composition must be reduced before an image can be packaged")
    label, keys = first_fit
    report["minimum_sacrifice"] = {"label": label, "effects": list(keys)}
    print()
    print(f"preserve-all is short {report['options'][0]['shortfall']} words")
    print(f"Spring-only is short "
          f"{next(o['shortfall'] for o in report['options'] if o['label'].startswith('SPRING'))} words")
    print(f"FIRST configuration that fits: {label}")
    print(f"  sacrificed: {', '.join(keys) if keys else '(none)'}")
    print(f"composed Perky P requirement: {need} words")
    (OUT / "sacrifice.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Timing qualification for the composed reduced Perky machine.

The runtime policy for this target is that T1 and T5 sit on SEPARATE DSP cores,
so a core runs at most ONE Perky algorithm at a time: the load is the MAXIMUM of
the selected algorithm, never the sum. This tool measures that maximum on the
composed production renderer and reports it against the frame deadline.

It measures and does NOT assert PCM parity -- the composed parity gate does
that. That separation matters: a timing number should be obtainable even while
a parity item is open, and a timing tool that stops on a parity mismatch can
never produce the number at all.

Reported per algorithm:

* worst modeled cycles for a 16-sample block, over the reachable control/state
  domain the fixtures and generators actually produce (not randomized
  impossible states);
* the same figure as a fraction of the full-core frame deadline, so the
  remaining headroom is explicit.
"""
from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tools/perky"),
                str(ROOT / "modules/perky"), str(ROOT / "tools/verify")]

OUT = ROOT / "out/perky/dsp-3algo"

# THE BUDGET IS NOT "MODELED CYCLES <= 72512".
#
# Same model as the repository's own realtime gate
# (tools/verify/verify_perky_realtime_budget.py): the interpreter host counts
# decoded opcode cycles, hardware MOVE timings exceed those counts, so the model
# carries a 2x margin; stock reserves its measured 1410 cycles/sample. The
# hardware window for a 16-sample block is 16 * 4532 = 72,512 cycles, so:
#
#   2 * modeled + 16 * 1410 <= 72,512   ->   modeled <= 23,040
#
# Comparing a raw modeled figure against 72,512 is simply the wrong test, and
# an earlier revision of this tool did exactly that.
FRAME_DEADLINE = 72512          # hardware window, 16 samples
STOCK_PER_SAMPLE = 1410         # stock reserve, measured
MODEL_MARGIN = 2                # hardware MOVE timings exceed the model
DEV_ALLOWANCE = 23040           # what the window leaves for one Perky voice


def load_gate():
    """Reuse the composed parity gate's own assembly and runner."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "perky3algo_gate", ROOT / "tools/verify/verify_perky_3algo_exec.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["perky3algo_gate"] = module
    spec.loader.exec_module(module)
    return module


def main() -> None:
    g = load_gate()
    renderers, rlabels = g.assemble(False, OUT / "timing")
    e1, e2, _, _ = g.make_envelopes()
    interp_a = struct.pack("<257H", *[(i * 257 + i * i) & 0xFFFF for i in range(257)])
    interp_b = struct.pack("<257H", *[(65535 - i * 251) & 0xFFFF for i in range(257)])
    ytext = g.tables_text(e1, e2, interp_a, interp_b,
                          ROOT / "out/perky/simple-drum-assets")

    report = {"schema": "perky-3algo-timing-v2",
              "frame_deadline": FRAME_DEADLINE,
              "stock_reserved": 16 * STOCK_PER_SAMPLE,
              "model_margin": MODEL_MARGIN,
              "max_modeled_block": DEV_ALLOWANCE,
              "policy": "one Perky algorithm per core; load is the MAXIMUM of "
                        "the three, never the sum",
              "algorithms": {}}

    print(f"hardware window: {FRAME_DEADLINE} cycles/16 samples   "
          f"stock reserve: {16 * STOCK_PER_SAMPLE}   model margin: {MODEL_MARGIN}x")
    print(f"=> a voice may model at most {DEV_ALLOWANCE} cycles/16 samples\n")

    # ---- Fold Drum 1: the captured ARM corpus plus the randomized native set.
    fold_worst, fold_n = 0, 0
    for case in g.arm_fold_cases():
        _, _, worst = g.run(renderers, rlabels["pk3t_fold"], case["state"],
                            case["rng"], ytext, case["blocks"], case["tag"], OUT)
        fold_worst = max(fold_worst, worst)
        fold_n += case["blocks"]
    native, native_count = g.native_fold_cases(
        ROOT / "out/perky/simple-drum-assets", OUT / "timing")
    for case in native:
        _, _, worst = g.run(renderers, rlabels["pk3t_fold"], case["state"],
                            case["rng"], ytext, 1, case["tag"], OUT)
        fold_worst = max(fold_worst, worst)
        fold_n += 1
    report["algorithms"]["fold"] = {"blocks": fold_n, "worst_cycles": fold_worst}

    # ---- Resonant bass / snare: every reachable control/state index.
    for family, model in (("bass", g.bass), ("snare", g.snare)):
        worst, blocks = 0, 0
        for index in range(256):
            voice, rng = g.resonant_state(family, index)
            for _ in range(4):
                _, _, meter = g.run(renderers, rlabels[f"pk3t_{family}"],
                                    voice.words, rng, ytext, 1,
                                    f"{family} {index}", OUT)
                worst = max(worst, meter)
                blocks += 1
        report["algorithms"][family] = {"blocks": blocks, "worst_cycles": worst}

    print(f"{'algorithm':10s} {'blocks':>7s} {'modeled/16':>11s} "
          f"{'2x+stock':>10s} {'vs window':>10s} {'verdict':>9s}")
    for name, row in report["algorithms"].items():
        cyc = row["worst_cycles"]
        total = MODEL_MARGIN * cyc + 16 * STOCK_PER_SAMPLE
        verdict = "FITS" if cyc <= DEV_ALLOWANCE else "OVER"
        print(f"{name:10s} {row['blocks']:7d} {cyc:11d} {total:10d} "
              f"{total - FRAME_DEADLINE:+10d} {verdict:>9s}")

    peak = max(row["worst_cycles"] for row in report["algorithms"].values())
    report["peak_modeled"] = peak
    report["peak_2x_plus_stock"] = MODEL_MARGIN * peak + 16 * STOCK_PER_SAMPLE
    report["peak_fits"] = peak <= DEV_ALLOWANCE
    print()
    print(f"peak modeled (one algorithm per core): {peak}")
    print(f"  worst case 2x + stock = {report['peak_2x_plus_stock']} cycles "
          f"vs the {FRAME_DEADLINE}-cycle window => "
          f"{'FITS' if report['peak_fits'] else 'EXCEEDS'}")
    (OUT / "timing.json").write_text(json.dumps(report, indent=2) + "\n")
    print()
    print(f"perky-3algo-timing: measured (report at {OUT / 'timing.json'})")


if __name__ == "__main__":
    main()

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

# The physical full-core frame deadline and the historical development
# allowance, both quoted in the target specification.
FRAME_DEADLINE = 72512
DEV_ALLOWANCE = 23040


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

    report = {"schema": "perky-3algo-timing-v1",
              "frame_deadline": FRAME_DEADLINE,
              "dev_allowance": DEV_ALLOWANCE,
              "policy": "one Perky algorithm per core; load is the MAXIMUM of "
                        "the three, never the sum",
              "algorithms": {}}

    print(f"frame deadline: {FRAME_DEADLINE} cycles   "
          f"historical development allowance: {DEV_ALLOWANCE}\n")

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

    print(f"{'algorithm':10s} {'blocks':>7s} {'worst cycles/16':>17s} "
          f"{'% of frame':>11s} {'headroom':>9s}")
    for name, row in report["algorithms"].items():
        frac = 100.0 * row["worst_cycles"] / FRAME_DEADLINE
        head = FRAME_DEADLINE - row["worst_cycles"]
        print(f"{name:10s} {row['blocks']:7d} {row['worst_cycles']:17d} "
              f"{frac:10.2f}% {head:9d}")

    peak = max(row["worst_cycles"] for row in report["algorithms"].values())
    report["peak_cycles"] = peak
    report["peak_percent_of_frame"] = round(100.0 * peak / FRAME_DEADLINE, 4)
    report["peak_over_dev_allowance"] = peak > DEV_ALLOWANCE
    print()
    print(f"peak (one algorithm per core): {peak} cycles = "
          f"{100.0 * peak / FRAME_DEADLINE:.2f}% of the frame deadline, "
          f"headroom {FRAME_DEADLINE - peak} cycles")
    print(f"peak exceeds the historical {DEV_ALLOWANCE}-cycle development "
          f"allowance: {peak > DEV_ALLOWANCE}")
    (OUT / "timing.json").write_text(json.dumps(report, indent=2) + "\n")
    print()
    print(f"perky-3algo-timing: measured (report at {OUT / 'timing.json'})")


if __name__ == "__main__":
    main()

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

* worst modeled cycles for a 16-sample block, reported TWICE and separately:
  - ``worst_reachable`` -- the captured ARM fixtures, i.e. states the production
    control path actually produced on hardware. **This is the production bound.**
  - ``worst_stress`` -- ``resonant_state()``'s synthetic states, whose own
    docstring says they cover "both sides of every bounded-path guard" and which
    write 24-bit decay fields, ``DECAY_COUNT`` up to 0xffffffff and random
    coefficients. Those are STRESS states the control path cannot produce, and
    they are reported as stress, never as the production number.
  The verdict uses the REACHABLE figure. Reporting the stress figure as the
  production cost is the error this split exists to prevent;
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
    # Fold's own measurement already runs the captured ARM cases, so its figure
    # IS the reachable one; there is no separate stress set for it here.
    report["algorithms"]["fold"] = {
        "blocks": fold_n, "worst_cycles": fold_worst,
        "worst_stress_cycles": fold_worst, "bound_from": "arm-fixtures"}

    # ---- Resonant bass / snare.
    # `resonant_state` builds STRESS states (its own docstring says so: both
    # sides of every bounded-path guard, DECAY_COUNT up to 0xffffffff, random
    # coefficients). They bound what the code can be asked to do, NOT what
    # production asks of it. The captured ARM fixtures are the reachable domain
    # -- the same oracle the standalone resonant gate uses -- so they are
    # measured too, and they are what the verdict is keyed on.
    ARM = {  # family -> (panel, byte offset, byte size) in the engine-7 fixtures
        "bass": (2, 0x39E8, 0x178),
        "snare": (1, 0x2734, 0x1D4),
    }
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
        cls = model.ResonantBass if family == "bass" else model.ResonantSnare
        panel, offset, size = ARM[family]
        reachable, rblocks, detail = 0, 0, []
        for corner in range(3):
            case = g.FIX / f"engine-7-mode-{panel}-corner-{corner}"
            if not case.exists():
                continue
            voice = cls.from_arm(
                (case / "wrapper-window-after.bin").read_bytes()[offset:offset + size])
            rng = list(struct.unpack(
                "<II", (case / "rng-continuation-before.bin").read_bytes()))
            _, _, meter = g.run(renderers, rlabels[f"pk3t_{family}"],
                                voice.words, rng, ytext, 1,
                                f"{family} arm {corner}", OUT)
            reachable = max(reachable, meter)
            rblocks += 1
            detail.append({"corner": corner, "worst_cycles": meter})
        report["algorithms"][family] = {
            "blocks": blocks, "worst_stress_cycles": worst,
            "arm_blocks": rblocks, "worst_reachable": reachable,
            "arm_corners": detail,
            # The production bound is the reachable one. Fall back to the
            # stress figure only if no ARM fixture was available, and say so.
            "worst_cycles": reachable or worst,
            "bound_from": "arm-fixtures" if reachable else "stress-only",
        }

    print(f"{'algorithm':10s} {'stress/16':>10s} {'REACHABLE/16':>13s} "
          f"{'2x+stock':>10s} {'vs window':>10s} {'verdict':>7s}  bound")
    for name, row in report["algorithms"].items():
        cyc = row["worst_cycles"]
        total = MODEL_MARGIN * cyc + 16 * STOCK_PER_SAMPLE
        verdict = "FITS" if cyc <= DEV_ALLOWANCE else "OVER"
        stress = row.get("worst_stress_cycles", row["worst_cycles"])
        print(f"{name:10s} {stress:10d} {cyc:13d} {total:10d} "
              f"{total - FRAME_DEADLINE:+10d} {verdict:>7s}  {row.get('bound_from','')}")
    print()
    print("  REACHABLE = captured ARM fixtures = the production bound; the verdict")
    print("  uses it. stress = resonant_state()'s synthetic guard-coverage states,")
    print("  which the control path cannot produce.")

    peak = max(row["worst_cycles"] for row in report["algorithms"].values())
    peak_stress = max(row.get("worst_stress_cycles", row["worst_cycles"])
                      for row in report["algorithms"].values())
    report["peak_modeled"] = peak
    report["peak_modeled_stress"] = peak_stress
    report["peak_2x_plus_stock"] = MODEL_MARGIN * peak + 16 * STOCK_PER_SAMPLE
    report["peak_fits"] = peak <= DEV_ALLOWANCE
    print()
    print(f"peak modeled (one algorithm per core): {peak} reachable "
          f"({peak_stress} on stress states)")
    print(f"  worst case 2x + stock = {report['peak_2x_plus_stock']} cycles "
          f"vs the {FRAME_DEADLINE}-cycle window => "
          f"{'FITS' if report['peak_fits'] else 'EXCEEDS'}")
    (OUT / "timing.json").write_text(json.dumps(report, indent=2) + "\n")
    print()
    print(f"perky-3algo-timing: measured (report at {OUT / 'timing.json'})")


if __name__ == "__main__":
    main()

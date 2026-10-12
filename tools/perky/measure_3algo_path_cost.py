#!/usr/bin/env python3
"""Measure what the production dispatch path costs over the renderer alone.

Item 2 of the timing directive asks for the dispatcher/wrapper overhead that the
renderer-only timing figure omits. This is that measurement, built as ONE
harness, ONE seeded state, ONE assembly, with entries differing only in what they
call -- because two measurements taken in different setups disagreed by 6,919
cycles for a 12-instruction routine, which is how a bogus 3x ratio almost got
published.

The harness validates itself: `quoted` adds exactly the gate's 12-instruction RNG
dump over `render`. A small, known difference must come out small; if that delta
is not tens of cycles, the run is not measuring what it claims.

Reported per engine:

  render    base + voice                    -- what verify_perky_3algo_timing quotes
  quoted    render + the gate's RNG dump    -- the quoted figure's exact basis
  dispatch  pk3d_source                     -- production: admission, dispatch,
                                               mode delivery, the x256 scale

NOTE the instruction form: an immediate to a REGISTER is `#$0038e8`; `#>` is for
accumulators. `#>` here is InvalidInstruction, the assembler exits non-zero, and
a driver that ignores that reads a STALE meter file from a previous run -- which
is exactly what happened once and produced the bogus number.

LABEL NAMES MATTER: an entry called `d_bass` is SUBSTITUTED INTO `pk3d_bass_voice`
-- the assembler resolves a defined symbol appearing inside another token, so
`jsrl pk3d_bass_voice` became `jsrl pk3$1037_voice` and failed as InvalidAddress.
All probe labels here carry a `meas_` prefix for that reason.

The Resonant states are `resonant_state`'s synthetic STRESS states. That is
deliberate and legitimate here: the quantity being measured is a DELTA between
two entries over the SAME state, so the state's reachability does not enter. The
absolute figures are stress figures and are not production numbers.
"""
from __future__ import annotations

import importlib.util
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tools/perky"),
                str(ROOT / "modules/perky"), str(ROOT / "tools/verify")]

ENGINES = (("FOLD DRUM", 0, "fold"), ("RES BASS", 10, "bass"), ("RES SNARE", 11, "snare"))


def load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main() -> None:
    join = load("join", "tools/verify/verify_perky_3algo_engine_join.py")
    g = load("g", "tools/verify/verify_perky_3algo_exec.py")
    composer = join.load_composer()
    import fold_drum_compact as fold

    e1, e2, _, _ = g.make_envelopes()
    ia = struct.pack("<257H", *[(i * 257 + i * i) & 0xFFFF for i in range(257)])
    ib = struct.pack("<257H", *[(65535 - i * 251) & 0xFFFF for i in range(257)])
    ytext = g.tables_text(e1, e2, ia, ib, ROOT / "out/perky/simple-drum-assets")

    V, S, R = composer.VOICE_BASE, composer.SCRATCH_BASE, composer.RNG_BASE

    def entry(name, voice, engine):
        return (
            f"{name}:\n"
            f"        move    #${V:06x},r6\n"
            f"        move    #${S:06x},r5\n"
            f"        jsrl    {voice}\n"
            f"        rts\n")

    def quoted(name, voice, engine):
        return (
            f"{name}:\n"
            f"        move    #${V:06x},r6\n"
            f"        move    #${S:06x},r5\n"
            f"        jsrl    {voice}\n"
            f"        jsrl    m_rng_out\n"
            f"        rts\n")

    def dispatch(name, voice, engine):
        return (
            f"{name}:\n"
            f"        move    #$000300,r4\n"
            f"        jsrl    pk3d_source\n"
            f"        move    #$000000,r0\n"
            f"        rts\n")

    rng_out = (
        "m_rng_out:\n"
        f"        move    #${R:06x},r1\n"
        "        move    #$000300,r2\n"
        "        move    x:(r1)+,a\n        move    a1,x:(r2)+\n"
        "        move    x:(r1)+,a\n        move    a1,x:(r2)+\n"
        "        move    x:(r1)+,a\n        move    a1,x:(r2)+\n"
        "        move    x:(r1)+,a\n        move    a1,x:(r2)+\n"
        "        rts\n")

    # The Fold path enters through pk_simple_base; the Resonant voices do not.
    voices = {"fold": ("pk_simple_base\n        jsrl    pk_fold_voice", "pk_fold_voice"),
              "bass": (f"{composer.P}bass_voice", f"{composer.P}bass_voice"),
              "snare": (f"{composer.P}snare_voice", f"{composer.P}snare_voice")}
    probe = rng_out
    for label, engine, key in ENGINES:
        body = voices[key][0]
        probe += (f"meas_render_{key}:\n        move    #${V:06x},r6\n        move    #${S:06x},r5\n"
                  f"        jsrl    {body}\n        rts\n")
        probe += (f"meas_quoted_{key}:\n        move    #${V:06x},r6\n        move    #${S:06x},r5\n"
                  f"        jsrl    {body}\n        jsrl    m_rng_out\n        rts\n")
        probe += (f"meas_dispatch_{key}:\n        move    #$000300,r4\n        jsrl    pk3d_source\n"
                  f"        move    #$000000,r0\n        rts\n")

    src = composer.normalize(composer.compose()).replace("@CONT@", "$000400")
    binary, labels = join.assemble(composer, probe + "\n" + src, "cost")

    fold_state = fold.FoldDrum1.from_arm(
        (ROOT / "out/perky/engine-fixtures/engine-1-mode-1-corner-0/"
         "wrapper-window-before.bin").read_bytes()[0xC4:0xC4 + 0xF4]).words
    states = {"fold": fold_state + [0] * (composer.RNG_GAP_START - V - len(fold_state))}
    for key in ("bass", "snare"):
        voice, _rng = g.resonant_state(key, 0)
        w = list(voice.words)
        states[key] = w + [0] * (composer.RNG_GAP_START - V - len(w))

    print(f"{'engine':11s} {'render':>8s} {'quoted':>8s} {'dispatch':>9s} "
          f"{'overhead':>9s} {'ratio':>7s}")
    rows = []
    for label, engine, key in ENGINES:
        state = states[key]
        rec = [0] * 20
        rec[0] = 0x504B
        rec[2] = 0x5931
        rec[3] = 1
        rec[composer.ENGINE_ID_OFFSET] = engine
        rec[0x10] = 1
        data = (
            f"X {V:x} " + " ".join(f"{v:06x}" for v in state) + "\n"
            + f"X {S:x} " + " ".join(["000000"] * composer.SCRATCH_WORDS) + "\n"
            + "X 3964 " + " ".join(["ffffff"] * 17) + "\n"
            + f"X {composer.RNG_GAP_END:x} 000000 000000 000000 000000\n"
            + "P 400 00000c\n" + ytext
            # Seed the ENGINE LEDGER so the steady-state path is measured rather
            # than the re-seed: on an engine change the dispatcher ALSO clears the
            # shared voice block (108 words, ~3 cycles each), which is a real cost
            # but not the per-block one.
            + f"X {composer.ENGINE_LEDGER:x} {0x8000 | engine:06x}\n"
            + f"X 300 " + " ".join(f"{w:06x}" for w in rec) + "\n"
            + f"X 209 000300\nX 418 {composer.ADMITTED_SLOT:06x}\nX 20e 000000\n")
        got = {}
        for prefix in ("meas_render", "meas_quoted", "meas_dispatch"):
            tag = f"{prefix}_{key}"
            join.drive(composer, binary, labels, tag, data, tag)
            got[prefix] = int((join.OUT / f"join_{tag}.meter").read_text().split()[-1])
        check = got["meas_quoted"] - got["meas_render"]
        if not 5 <= check <= 60:
            raise SystemExit(
                f"measure-3algo-path-cost: the self-check FAILED for {label}: the "
                f"gate's 12-instruction dump measured {check:+d} cycles, which is "
                f"not tens of cycles -- the run is not measuring what it claims")
        rows.append((label, got["meas_render"], got["meas_quoted"], got["meas_dispatch"]))
        print(f"{label:11s} {got['meas_render']:8d} {got['meas_quoted']:8d} "
              f"{got['meas_dispatch']:9d} "
              f"{got['meas_dispatch'] - got['meas_quoted']:+9d} "
              f"{got['meas_dispatch'] / got['meas_render']:6.3f}x")
    print()
    print("the self-check passed for every engine: the gate's 12-instruction dump")
    print("measures tens of cycles, so the dispatch deltas are real.")
    print("All figures are MODELED cycles per 16-sample block; hardware is ~2x.")
    print("The Resonant states are synthetic STRESS states -- legitimate for a")
    print("delta over the same state, NOT production figures.")


if __name__ == "__main__":
    main()

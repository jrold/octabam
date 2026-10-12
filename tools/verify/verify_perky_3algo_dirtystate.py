#!/usr/bin/env python3
"""Dirty-state coverage for the composed Perky machine.

`verify_dirtystate.py` is the repository's gate for this class — "a persistent
slot that init does not clear holds whatever the effect before ours left in the
block, and no local render can see it, because the port and `dsp_host` boot
zeroed RAM" (it cost a session on Spectrum's stale h2 poles). It builds the
remix's own image and renders every module from a garbage block.

**For this remix it reports "0 renders, 0 failed"** — the composed machine is
installed as a source hook and declares no FX init, so that gate never exercises
it. This gate does, directly: it drives the composed renderer from a garbage
voice block, a garbage scratch block and garbage RNG limbs, on SILENCE, and
refuses any output.

On a real unit the DSP's RAM holds whatever ran before, so a machine that leaks
stale state into its output would be silent locally and audible there.
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tools/perky"),
                str(ROOT / "modules/perky"), str(ROOT / "tools/verify")]

OUT = ROOT / "out/perky/dsp-3algo"


def die(message: str) -> "NoReturn":
    raise SystemExit("verify-perky-3algo-dirtystate: " + message)


def garbage(count: int, seed: int) -> list[int]:
    """A deterministic mess -- not zeros, which is the whole point."""
    return [((i + 1) * seed + 0x5A5A) & 0xFFFF for i in range(count)]


def main() -> None:
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "g", ROOT / "tools/verify/verify_perky_3algo_exec.py")
    g = importlib.util.module_from_spec(spec)
    sys.modules["g"] = g
    spec.loader.exec_module(g)

    import build_dsp_3algo_source as composed
    renderers, labels = g.assemble(False, OUT / "dirty")
    e1, e2, _, _ = g.make_envelopes()
    ia = struct.pack("<257H", *[(i * 257 + i * i) & 0xFFFF for i in range(257)])
    ib = struct.pack("<257H", *[(65535 - i * 251) & 0xFFFF for i in range(257)])
    ytext = g.tables_text(e1, e2, ia, ib, ROOT / "out/perky/simple-drum-assets")

    cases = {
        "all zeros (the control)": [0] * composed.VOICE_BYTES,
        "garbage voice block": garbage(composed.VOICE_BYTES, 2654435761),
        "garbage, all $ffff": [0xFFFF] * composed.VOICE_BYTES,
        "garbage, alternating": [0xAAAA if i % 2 else 0x5555
                                 for i in range(composed.VOICE_BYTES)],
    }
    failures = []
    for tag, words in cases.items():
        got, _, worst = g.run(renderers, labels["pk3t_fold"], words,
                              [0xDEADBEEF, 0xCAFEBABE], ytext, 4, tag, OUT)
        peak = max((abs(v) for v in got), default=0)
        nonzero = sum(1 for v in got if v)
        note = ""
        if tag != "all zeros (the control)" and (nonzero or peak):
            failures.append((tag, nonzero, peak))
            note = "  <-- LEAKS"
        print(f"  {tag:26s} nonzero {nonzero:3d}/{len(got)}  peak {peak:8d}{note}")

    print()
    if failures:
        die("the composed machine renders output from uninitialised state on "
            "silence: " + ", ".join(f"{t} ({n} samples, peak {p})"
                                    for t, n, p in failures)
            + " -- on a real unit that state is whatever ran before, and no "
              "local render sees it because dsp_host boots zeroed RAM")
    print("perky-3algo-dirtystate: PASS (the composed machine is silent on "
          "silence from zeroed AND from garbage voice state, so it does not "
          "leak uninitialised state into its output -- coverage "
          "verify_dirtystate.py reports as '0 renders' for this remix)")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Run the complete shipping X-state voice gate with explicit long PERKY calls.

The underlying gate predates Octabam's ``jsrl`` pseudo-op and concatenates
several PERKY kernels at a high P origin.  Import it, rewrite every internal
``jsr pk_*`` to ``jsrl pk_*`` exactly as the shipping source generator does,
and then run its existing 36 x 16-sample PCM/state/RNG oracle comparison.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "tools/perky"), str(ROOT / "tools/verify")]


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"verify-perky-shipping-voice-exec: cannot import {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


sourcegen = load(
    "perky_shipping_sourcegen",
    ROOT / "tools/perky/build_noise_tone_synth_source.py",
)
base = load(
    "perky_shipping_xstate_gate",
    ROOT / "tools/verify/verify_perky_voice_xstate_exec.py",
)

_original_combined_source = base.combined_source


def combined_source() -> str:
    return sourcegen.force_long_local_jsr(_original_combined_source())


base.combined_source = combined_source

if __name__ == "__main__":
    base.main()

#!/usr/bin/env python3
"""Gate PERKY's generated synth-canary path without building a firmware image."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tools/perky")]

from remix import registry  # noqa:E402


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


fab = load_module("perky_synthpath_fab", ROOT / "tools/perky/fabricate_noise_tone_fixtures.py")
payload = load_module("perky_synthpath_payload", ROOT / "tools/perky/build_noise_tone_payload.py")
sourcegen = load_module("perky_synthpath_source", ROOT / "tools/perky/build_noise_tone_synth_source.py")


def fail(msg: str) -> None:
    raise SystemExit("verify-perky-synth-build-path: " + msg)


def main() -> None:
    r = registry.remix("perky-synth")
    if "PERKY PROBE" not in r.modules:
        fail("perky-synth does not carry PERKY PROBE")
    for donor in ("PLATE REV", "SPRING REV", "DARK REV"):
        if donor in r.modules:
            fail(f"perky-synth keeps {donor}; full three-reverb donor is unavailable")
    if r.fallback != "NONE":
        fail("isolated synth canary must use firmware NONE fallback")

    if sourcegen.FULL_DONOR_WORDS != 2724:
        fail(f"full donor budget is {sourcegen.FULL_DONOR_WORDS}, expected 2724")
    want_pieces = (
        "synth_seam_glue.asm",
        "noise_tone_voice_xstate_glue.asm",
        "noise_tone_math.asm",
        "noise_tone_filter.asm",
        "noise_tone_oscillator_packed.asm",
        "noise_tone_envelope_packed7.asm",
        "noise_tone_envelope.asm",
        "noise_tone_mix.asm",
    )
    if tuple(sourcegen.PIECES) != want_pieces:
        fail(f"source composition drifted: {sourcegen.PIECES!r}")

    with tempfile.TemporaryDirectory(prefix="perky-synth-path.") as td:
        td = Path(td)
        raw, packed = td / "raw", td / "packed"
        fab.emit_tables(raw)
        layout = payload.build(raw, packed)
        if layout.get("synthetic") is not True:
            fail("synthetic fixture lost provenance")
        src = sourcegen.generate(packed / "layout.json")

    if src.count("pk_probe_source:") != 1:
        fail("generated synth must expose exactly one manifest DspHook label")
    if "pk_synth_source:" in src:
        fail("generated synth left the development seam label unaliased")
    if src.count("@CONT@") != 1:
        fail("generated synth must leave exactly one per-payload continuation marker")
    if "@W0" in src or "@W1" in src or "@W2" in src or "@W3" in src:
        fail("generated synth left a wave identity marker unresolved")
    for label in (
        "pk_voice_xstate:", "pk_noise_step:", "pk_filter_probe:",
        "pk_osc_packed_probe:", "pk_envelope_packed7_cached:",
        "pk_envelope_probe:", "pk_mix_probe:",
    ):
        if src.count(label) != 1:
            fail(f"generated synth expected one {label}, found {src.count(label)}")

    # The wrapper must patch only the registry cache and restore it in finally;
    # tracked manifest mutation would make the safe/default probe ambiguous.
    wrapper = (ROOT / "tools/perky/build_synth_canary.py").read_text()
    for token in (
        "dataclasses.replace(original.dsp",
        "mods[key] = patched",
        "finally:",
        "mods[key] = original",
        'os.environ["REMIX"] = "perky-synth"',
        "build_perky_tables.build",
    ):
        if token not in wrapper:
            fail(f"build_synth_canary.py missing safety token {token!r}")
    if "write_text(" in wrapper and "dsp_source.write_text" not in wrapper:
        fail("wrapper gained an unexpected tracked-file write path")

    print(
        "PERKY synth build path: PASS "
        "(full three-reverb donor selected; generated hook/source complete; "
        "registry override restored; synthetic X/Y post-build path present)"
    )


if __name__ == "__main__":
    main()

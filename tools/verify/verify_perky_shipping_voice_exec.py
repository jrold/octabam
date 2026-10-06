#!/usr/bin/env python3
"""Execute the actual generated PERKY shipping synth against the voice oracle.

The older X-state gate is a useful harness, but its default ``combined_source``
concatenates the standalone primitive files directly.  Firmware does not ship
that text: ``build_noise_tone_synth_source.py`` deduplicates the common u32
helpers, lowers local conditional jumps to relative branches, and turns every
internal PERKY call into an explicit long JSR.

This wrapper therefore reuses only the proven harness/oracle/data machinery.
It builds the same synthetic payload used by the hardware canary, generates the
ACTUAL shipping synth source, prepends the harness entry stub, and runs the
existing 36 x 16-sample exact PCM/state/RNG comparison over that generated
source.  If this gate passes, the renderer text executed in the emulator is the
same renderer text the firmware builder later places in the donor region.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile

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
payload = load(
    "perky_shipping_payload",
    ROOT / "tools/perky/build_noise_tone_payload.py",
)
base = load(
    "perky_shipping_xstate_gate",
    ROOT / "tools/verify/verify_perky_voice_xstate_exec.py",
)


def build_shipping_source() -> str:
    with tempfile.TemporaryDirectory(prefix="perky-shipping-voice.") as td:
        td = Path(td)
        raw = td / "raw"
        packed = td / "packed"
        base.fab.emit_tables(raw)
        layout = payload.build(raw, packed)
        if layout.get("synthetic") is not True:
            raise SystemExit("verify-perky-shipping-voice-exec: fixture lost synthetic provenance")
        src = sourcegen.generate(packed / "layout.json")

    # The source seam is present in the generated firmware text but is not the
    # entry exercised by this voice-level harness. Give its stock continuation
    # a valid numeric target so the whole generated unit assembles unchanged.
    if src.count("@CONT@") != 1:
        raise SystemExit(
            f"verify-perky-shipping-voice-exec: generated source has "
            f"{src.count('@CONT@')} continuation markers"
        )
    src = src.replace("@CONT@", "$000426")

    if sourcegen._LOCAL_JUMP_RE.search(src):
        raise SystemExit(
            "verify-perky-shipping-voice-exec: generated source retained "
            "a local absolute conditional jump"
        )
    if sourcegen.force_long_local_jsr(src) != src:
        raise SystemExit(
            "verify-perky-shipping-voice-exec: generated source retained "
            "a plain internal PERKY jsr"
        )
    return src


def main() -> None:
    generated = build_shipping_source()

    # The harness probe itself predates high-P composition. Normalize just its
    # call into pk_voice_xstate; the generated firmware text below is already
    # fully normalized by sourcegen.generate().
    probe = sourcegen.relativize_local_conditionals(base.PROBE)
    probe = sourcegen.force_long_local_jsr(probe)

    def combined_source() -> str:
        return probe.rstrip() + "\n\n" + generated.rstrip() + "\n"

    base.combined_source = combined_source

    # Use the exact identities encoded into the synthetic shipping layout, not
    # the historical standalone gate's arbitrary 0x1111... test identities.
    ids = tuple(int(x) & 0xFFFFFFFF for x in base.fab.WAVE_ADDRESSES)
    if len(ids) != 4 or len(set(ids)) != 4:
        raise SystemExit(f"verify-perky-shipping-voice-exec: bad wave identities {ids!r}")
    base.IDS = ids

    base.main()


if __name__ == "__main__":
    main()

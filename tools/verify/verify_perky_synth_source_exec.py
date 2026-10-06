#!/usr/bin/env python3
"""Execute the shipping voice gate, then assemble/budget the generated synth."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "tools/perky")]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


fab = load_module("perky_synexec_fab", ROOT / "tools/perky/fabricate_noise_tone_fixtures.py")
payload = load_module("perky_synexec_payload", ROOT / "tools/perky/build_noise_tone_payload.py")
sourcegen = load_module("perky_synexec_source", ROOT / "tools/perky/build_noise_tone_synth_source.py")
XSTATE_ABI_GATE = ROOT / "tools/verify/verify_perky_xstate_asm_layout.py"
SHIPPING_GATE = ROOT / "tools/verify/verify_perky_shipping_voice_exec.py"


def main() -> None:
    # First pin the textual shipping ABI. This catches decimal compact-word
    # numbers accidentally written as hexadecimal DSP displacements before the
    # assembler or emulator can obscure the source of the failure.
    subprocess.run([sys.executable, str(XSTATE_ABI_GATE)], cwd=ROOT, check=True)

    # This is the hardware boundary: do not merely prove that the generated
    # source assembles. Execute the complete X-state renderer and require exact
    # PCM + all compact state + shared RNG parity against the Python oracle.
    subprocess.run([sys.executable, str(SHIPPING_GATE)], cwd=ROOT, check=True)

    with tempfile.TemporaryDirectory(prefix="perky-synth-source-exec.") as td:
        td = Path(td)
        raw, packed = td / "raw", td / "packed"
        fab.emit_tables(raw)
        payload.build(raw, packed)
        src = sourcegen.generate(packed / "layout.json")
        if sourcegen._LOCAL_JUMP_RE.search(src):
            raise AssertionError("generated synth retained a local absolute conditional jump")
        out = td / "perky_synth.asm"
        out.write_text(src)
        words = sourcegen.measure(src, out)

    spring = words <= sourcegen.SPRING_DONOR_WORDS
    print(
        "PERKY generated synth source: PASS "
        f"({words}/{sourcegen.FULL_DONOR_WORDS} P words in full donor, "
        f"FREE {sourcegen.FULL_DONOR_WORDS - words}; "
        f"SPRING-only {sourcegen.SPRING_DONOR_WORDS}: {'FITS' if spring else 'not yet'})"
    )


if __name__ == "__main__":
    main()

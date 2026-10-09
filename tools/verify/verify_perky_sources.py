#!/usr/bin/env python3
"""Static invariants for the PERKY source-machine scaffold.

This gate deliberately runs without Elektron or PĒRKONS firmware. It catches
layout drift before generated ColdFire/DSP code is allowed into an active
manifest.
"""
from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
HERE = ROOT / "modules/perky"


def require(text: str, pattern: str, label: str) -> None:
    if re.search(pattern, text, re.MULTILINE) is None:
        raise SystemExit(f"PERKY source gate: missing {label}: {pattern}")


def reject(text: str, pattern: str, label: str) -> None:
    if re.search(pattern, text, re.MULTILINE) is not None:
        raise SystemExit(f"PERKY source gate: forbidden {label}: {pattern}")


def main() -> None:
    control = (HERE / "control.c").read_text()
    machine = (HERE / "machine.s").read_text()
    probe = (HERE / "probe_glue.asm").read_text()
    port = (HERE / "PORT.md").read_text()

    # Only the three bytes already proven by Analog BD may be used as identity.
    require(machine, r"cmpi\.b\s+#'P'", "P signature")
    require(machine, r"cmpi\.b\s+#'K'", "K signature")
    require(machine, r"cmpi\.b\s+#1", "signature version")
    reject(machine, r"3\(%a1\)", "unproven fourth signature byte")

    # Engine family is persisted in a known source-parameter byte; MODE lives on
    # the main SRC page at slot 4 (TUNE/DECAY/P1/P2/MODE = the five visible
    # controls) so p-lock/LFO delivery uses the same first-page staging. It is
    # mirrored into the established PK/Y1 record slot 6 at render time.
    require(control, r"#define\s+MODEL_SLOT\s+11u", "model slot 11")
    require(control, r"#define\s+MODE_SLOT\s+4u", "main-page MODE slot 4")
    require(control, r"i\s*==\s*MODE_SLOT", "MODE descriptor slot")
    require(control, r"p\[6\]\s*=\s*p\[MODE_SLOT\]", "PK/Y1 MODE mirror to slot 6")
    require(control, r"0x00011111u", "five-control enable bitmap")
    require(machine, r"slot 6.*MODE", "MODE plumbing comment")

    # ColdFire record and DSP signature must agree on both 16-bit halves.
    require(control, r"record\[0\]\s*=\s*0x504b0000u", "PK record magic")
    require(control, r"record\[1\]\s*=\s*0x59310000u\s*\|\s*trig", "Y1 record magic")
    require(probe, r"#>\$00504b", "DSP PK magic")
    require(probe, r"#>\$005931", "DSP Y1 magic")

    # The canary must keep ordinary sources on stock and custom sources in the
    # stock AMP/FX continuation path.
    require(probe, r"pk_probe_stock:\s*\n\s*rts", "stock fallback")
    require(probe, r"jmp\s+@CONT@", "AMP/FX continuation")
    require(probe, r"x:>\$20c", "stock event offset")

    # Keep the documented first-engine oracle synchronized with the code.
    require(port, r"mutable state size: `0x120`", "Noise/Tone state size")
    require(port, r"noise/tone mix word: `0xf8`", "Noise/Tone mix offset")

    print("PERKY source/layout invariants: PASS")


if __name__ == "__main__":
    main()

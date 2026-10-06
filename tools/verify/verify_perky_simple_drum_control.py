#!/usr/bin/env python3
"""Qualify exact v1.2.1 Simple Drum control arithmetic without firmware blobs."""
from __future__ import annotations

import hashlib
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
PERKY = ROOT / "modules" / "perky"
sys.path.insert(0, str(PERKY))

import simple_drum_control as ctl  # noqa: E402

# SHA256s of the 128-value u16 result sequences captured from a fresh v1.2.1
# engine with physical controls 0..127.  Hashes retain a strong regression
# oracle without committing copied firmware-derived lookup tables.
PREPARED_SHA256 = "b90b3b9b4bd77eb683f83b43114f2b1ef2c0aa3d78cb3c45de89200f3d0b19f1"
DECAY_SHA256 = "c0d3a30b007591185e59db5736106fa14d3af3c87c5374a553544753b62c13e0"
ENV_SHA256 = "6b42105a889ee8fe5f809d266c7c387499e7ad3daf715a291e9351dc00d866b4"


def digest_u16(values: list[int]) -> str:
    blob = b"".join(struct.pack("<H", value & 0xFFFF) for value in values)
    return hashlib.sha256(blob).hexdigest()


def main() -> None:
    targets = [ctl.panel_to_target(v) for v in range(128)]
    if targets[:3] != [0, 32, 64] or targets[-2:] != [4032, 4095]:
        raise AssertionError("7-bit -> 12-bit panel target mapping drifted")

    prepared = [ctl.settle_from_zero(target, 17) for target in targets]
    if digest_u16(prepared) != PREPARED_SHA256:
        raise AssertionError("v1.2.1 control smoother no longer matches authentic sweep")
    if prepared[:3] != [0, 30, 62] or prepared[64] != 2046 or prepared[-1] != 4092:
        raise AssertionError("control smoother golden points drifted")

    decay = [ctl.amplitude_decay_rate(value) for value in prepared]
    if digest_u16(decay) != DECAY_SHA256:
        raise AssertionError("Simple Drum DECAY formula no longer matches authentic sweep")
    if (decay[0], decay[1], decay[2], decay[-1]) != (428, 389, 357, 8):
        raise AssertionError("Simple Drum DECAY golden points drifted")

    env = [ctl.pitch_envelope_decay_rate(value) for value in prepared]
    if digest_u16(env) != ENV_SHA256:
        raise AssertionError("Simple Drum ENV formula no longer matches authentic sweep")
    if (env[0], env[1], env[2], env[-1]) != (1040, 913, 808, 52):
        raise AssertionError("Simple Drum ENV golden points drifted")

    # Simple Drum's family-specific common-pitch offset cancels exactly, so the
    # prepared TUNE word is the renderer's 12-bit raw pitch.
    if any(ctl.raw_pitch(value) != value for value in prepared):
        raise AssertionError("Simple Drum TUNE/raw-pitch law drifted")

    # MIX is a direct prepared-word >> 1 in the native update path.
    if ctl.pitch_envelope_amount(0) != 0 or ctl.pitch_envelope_amount(4092) != 2046:
        raise AssertionError("Simple Drum MIX/pitch-envelope amount law drifted")

    # PerkyBits exposes physical panel order; native update consumes firmware
    # mode bytes 1,0,2 for M1,M2,M3 respectively.
    if ctl.PANEL_MODE_TO_FIRMWARE != (1, 0, 2):
        raise AssertionError("Simple Drum panel->firmware mode map drifted")
    waves = [ctl.wave_for_panel_mode(i) for i in range(3)]
    if waves != [0x080222A0, 0x080226A0, 0x080228A0]:
        raise AssertionError(f"Simple Drum physical-mode wave targets drifted: {waves!r}")

    print(
        "PERKY Simple Drum controls: PASS "
        "(128/128 authentic DECAY, 128/128 authentic ENV, exact smoother, "
        "TUNE/MIX laws, physical M1/M2/M3 wave map)"
    )


if __name__ == "__main__":
    main()

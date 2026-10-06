#!/usr/bin/env python3
"""Lock PERKY's five-control synthetic-canary contract.

This gate deliberately does NOT bless the mapping as PĒRKONS-equivalent.  It
only proves that the development full-machine path consumes the five published
Octatrack controls, writes them into owned compact-voice fields, uses three
real MODE wave pairs, and keeps the machine descriptor's MODE UI a proper
three-position select.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAP = (ROOT / "modules/perky/synthetic_control_map.asm").read_text()
SEAM = (ROOT / "modules/perky/synth_seam_glue.asm").read_text()
GEN = (ROOT / "tools/perky/build_noise_tone_synth_source.py").read_text()
CONTROL = (ROOT / "modules/perky/control.c").read_text()


def fail(msg: str) -> None:
    raise SystemExit("verify-perky-control-mapper: " + msg)


def need(text: str, token: str, where: str) -> None:
    if token not in text:
        fail(f"{where} missing {token!r}")


def mapped(p: int) -> tuple[int, int, int, int, int]:
    p &= 0x7F
    osc1 = 0x1000 + (p << 8)
    osc2 = 0x0C00 + (p << 7)
    decay = 0x0200 + ((0x7F - p) << 5)
    attack = 0x0800 + (p << 7)
    mix = p << 5
    return osc1, osc2, decay, attack, mix


def main() -> None:
    # Seam/generator integration: one routine, one call, tracked impulse probe
    # remains separate from this synthetic full-synth path.
    if MAP.count("pk_synth_apply_controls:") != 1:
        fail("synthetic mapper must expose exactly one entry label")
    if SEAM.count("jsr     pk_synth_apply_controls") != 1:
        fail("synth seam must call mapper exactly once per source block")
    need(GEN, '"synthetic_control_map.asm"', "synth source generator")
    need(GEN, 'src.count("pk_synth_apply_controls:") != 1', "synth source generator")
    need(GEN, "force_long_local_jsr", "synth source generator")
    need(GEN, "jsrl", "synth source generator")

    # Transport word -> published control. These are DSP words 8..19 created
    # from the twelve bytes pk_render() packs into record[4..9].
    for token, name in (
        ("move    x:(r4+$8),a", "TUNE"),
        ("move    x:(r4+$9),b", "DECAY"),
        ("move    x:(r4+$a),a", "ENV"),
        ("move    x:(r4+$b),a", "MIX"),
        ("move    x:(r4+$e),a", "MODE"),
    ):
        need(MAP, token, f"{name} transport")

    # Compact voice indices are decimal in the ABI, while DSP `$nn`
    # displacements are hexadecimal. Pin the corrected translations here.
    for token in (
        "x:(r6+$19)", "x:(r6+$1a)",  # words 25/26 osc1 increment
        "x:(r6+$21)", "x:(r6+$22)",  # words 33/34 osc2 increment
        "x:(r6+$0b)", "x:(r6+$0a)",  # words 11/10 decay/attack
        "x:(r6+$27)", "x:(r6+$28)",  # words 39/40 mix
    ):
        need(MAP, token, "compact-state mapper")

    # Endpoint model: every continuous control must span a useful, legal u16
    # range and DECAY must run in the intuitive direction (larger knob ->
    # smaller decrement -> longer synthetic tail).
    lo = mapped(0)
    mid = mapped(64)
    hi = mapped(127)
    if lo[0] != 0x1000 or hi[0] != 0x8F00 or not lo[0] < mid[0] < hi[0]:
        fail(f"TUNE osc1 mapping drifted: {lo[0]:04x}/{mid[0]:04x}/{hi[0]:04x}")
    if lo[1] != 0x0C00 or hi[1] != 0x4B80 or not lo[1] < mid[1] < hi[1]:
        fail(f"TUNE osc2 mapping drifted: {lo[1]:04x}/{mid[1]:04x}/{hi[1]:04x}")
    if lo[2] != 0x11E0 or hi[2] != 0x0200 or not lo[2] > mid[2] > hi[2]:
        fail(f"DECAY mapping drifted: {lo[2]:04x}/{mid[2]:04x}/{hi[2]:04x}")
    if lo[3] != 0x0800 or hi[3] != 0x4780 or not lo[3] < mid[3] < hi[3]:
        fail(f"ENV mapping drifted: {lo[3]:04x}/{mid[3]:04x}/{hi[3]:04x}")
    if lo[4] != 0x0000 or hi[4] != 0x0FE0 or mid[4] != 0x0800:
        fail(f"MIX mapping drifted: {lo[4]:04x}/{mid[4]:04x}/{hi[4]:04x}")
    if any(not 0 <= value <= 0xFFFF for row in (lo, mid, hi) for value in row):
        fail("synthetic control mapping escaped one 16-bit compact-state limb")

    # MODE uses three distinct wave pairs, setting both current and next so a
    # panel step is immediately audible rather than waiting for a phase wrap.
    mode_chunks = {
        0: ("@W0L@", "@W0H@", "@W1L@", "@W1H@"),
        1: ("@W1L@", "@W1H@", "@W2L@", "@W2H@"),
        2: ("@W2L@", "@W2H@", "@W3L@", "@W3H@"),
    }
    wave_fields_hex = ("1b", "1c", "1d", "1e", "23", "24", "25", "26")
    for mode, ids in mode_chunks.items():
        start = MAP.find(f"pksc_mode{mode}:")
        if start < 0:
            fail(f"MODE {mode} branch missing")
        end = MAP.find("\npksc_mode", start + 1)
        chunk = MAP[start:] if end < 0 else MAP[start:end]
        for identity in ids:
            if identity not in chunk:
                fail(f"MODE {mode} missing wave identity {identity}")
        for field in wave_fields_hex:
            if f"x:(r6+${field})" not in chunk:
                fail(f"MODE {mode} does not write compact wave field ${field}")

    # Panel contract: five enabled controls only; MODE is count 3 and uses a
    # stock stepped formatter + genuine 3-position widget.
    for token in (
        "#define MODE_FORMATTER 0x4003c718u",
        "#define MODE_WIDGET 0x40047424u",
        "put32(desc + 0xd2 + 4u * i, 3);",
        "put32(desc + 0x102 + 4u * i, i == 6u ? MODE_FORMATTER : 0);",
        "put32(desc + 0x132 + 4u * i, i == 6u ? MODE_WIDGET : 0);",
        "put32(desc + 0x1c2, 0x00000000u);",
        "put32(desc + 0x1c6, 0x01001111u);",
    ):
        need(CONTROL, token, "PERKY descriptor")

    print(
        "PERKY synthetic five-control mapper: PASS "
        "(TUNE/DECAY/ENV/MIX/MODE consumed; corrected compact-state offsets pinned; "
        "3 distinct MODE wave pairs; descriptor exposes exactly five controls)"
    )


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Gate the PĒRKONS voice silo: four voices, three algorithms each.

The drum has four voices and every voice owns three algorithms; the port keeps
that shape on Octatrack T1..T4 (T1=V1, T2=V2, T3=V3, T4=V4).  A track's ALGO
control ranges over its own family only, so no patch can put an algorithm on a
voice the hardware would not offer it on.

This gate pins the three things that make that true:

  1. the family table itself (which engine each family slot names, and how many
     slots of it are live);
  2. that the staked-out engines are a partition -- every implemented engine is
     reachable from exactly one voice, and nothing is reachable from two;
  3. that the shipping driver actually consults the table: the staged ALGO byte
     is mapped through it, and the SRC page publishes the per-voice length.

The runtime half of the proof is elsewhere: perky_cf_production_render_diff.cpp
drives pk_render for every (voice, engine) pair and compares the committed slot
bytes against a direct engine reference, and verify_perky_cf_userpath.py shows
the four families making audio together on the whole machine.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HEADER = ROOT / "modules/perky/cf_perky4.h"
CONTROL = ROOT / "modules/perky/control_cf_final.c"

# The hardware's own layout (modules/perky/hw4_profile.py ENGINE_NAMES):
#   V1 Fold Drum 1 / Wavetable V1 / Simple Drum
#   V2 Fold Drum 2 / Wavetable V2 / Complex Drum
#   V3 Resonant Drums / Slap / Karplus
#   V4 Noise Hat / Noise Tone / Acoustic Hats
# Only the implemented algorithms are listed, compacted to a contiguous knob
# range; the expected mapping is therefore the hardware order with the
# not-yet-ported engines removed.
EXPECTED = {
    0: ["FOLD1", "WAVETABLE", "SIMPLE_DRUM"],   # V1 hardware order
    1: ["FOLD2", "WAVETABLE", "COMPLEX_DRUM"],  # V2 hardware order
    2: ["RESONANT", "SLAP", "KARPLUS"],  # V3 complete
    3: ["NOISE_HAT", "NOISE_TONE", "ACOUSTIC_HATS"],  # V4 complete
}

TRACK_TO_VOICE = {0: 0, 1: 1, 2: 2, 3: 3}

# Wavetable Drum is the one algorithm the hardware's own silo offers on two
# voices (V1 and V2); every other engine belongs to exactly one voice.
SHARED_ENGINES = {"WAVETABLE"}


def fail(message: str) -> "NoReturn":
    raise SystemExit("verify-perky-cf-voice-silo: " + message)


def main() -> None:
    header = HEADER.read_text()
    control = CONTROL.read_text()

    table = re.search(
        r"pk4_family_engines\[PK4_VOICE_COUNT\]\[3\]\s*=\s*\{(.*?)\n\};",
        header, re.S)
    if not table:
        fail("cf_perky4.h: pk4_family_engines[PK4_VOICE_COUNT][3] not found")
    rows = re.findall(r"\{([^{}]*)\}", table.group(1))
    if len(rows) != 4:
        fail(f"cf_perky4.h: expected 4 family rows, found {len(rows)}")

    lengths = re.search(r"pk4_family_len\[PK4_VOICE_COUNT\]\s*=\s*\{([^}]*)\}", header)
    if not lengths:
        fail("cf_perky4.h: pk4_family_len[PK4_VOICE_COUNT] not found")
    lens = [int(v.strip().rstrip("u")) for v in lengths.group(1).split(",") if v.strip()]
    if len(lens) != 4:
        fail(f"cf_perky4.h: expected 4 family lengths, found {lens}")

    if lens != [len(v) for v in EXPECTED.values()]:
        fail(f"family lengths {lens} do not match the implemented set "
             f"{[len(v) for v in EXPECTED.values()]}")

    seen: dict[str, int] = {}
    for voice, row in enumerate(rows):
        names = [m for m in re.findall(r"PK4_ALGO_([A-Z_0-9]+)", row)]
        if len(names) != 3:
            fail(f"family {voice}: expected 3 slots, found {names}")
        want = EXPECTED[voice]
        if names[:len(want)] != want:
            fail(f"family {voice}: slots {names} do not start with {want}")
        # Everything past the live length is padding.  It must be a duplicate
        # of a live slot, so a clamped (out-of-range) local index can never
        # reach an algorithm this voice does not own.
        for pad in names[len(want):]:
            if pad not in want:
                fail(f"family {voice}: padding slot {pad} is not one of {want} "
                     "-- a clamp could select a foreign engine")
        for engine in names[:len(want)]:
            if engine in seen:
                if engine not in SHARED_ENGINES:
                    fail(f"engine {engine} is reachable from voice {seen[engine]} "
                         f"and voice {voice}")
                continue
            seen[engine] = voice

    if len(seen) != 11:
        fail(f"the silo covers {sorted(seen)} -- expected all eleven implemented engines")

    # The driver must enforce the silo in exactly one place and publish the
    # per-voice knob range.
    for needle in (
        "src[PK_FINAL_ALGO] = pk4_voice_engine((unsigned)voice, src[PK_FINAL_ALGO]);",
        "maximum = pk4_voice_len(voice);",
        "const unsigned voice = track < PK4_VOICE_COUNT ? track : 0u;",
        "return pk_final_page(track < 8u ? (unsigned)track : 0u);",
    ):
        if needle not in control:
            fail(f"control_cf_final.c is missing the silo wiring: {needle}")

    if "if (src[PK_FINAL_ALGO] >= PK_FINAL_ALGO_COUNT)" in control:
        fail("control_cf_final.c still clamps ALGO against the GLOBAL engine "
             "count instead of the voice's family length")

    # The track map is the whole point of the milestone: T1..T4, not T1/T2/T5/T6.
    for track, voice in TRACK_TO_VOICE.items():
        if f"case {track}u: return {voice};" not in control:
            fail(f"control_cf_final.c: pk_final_voice_index is missing "
                 f"case {track}u: return {voice};")
    for stray in ("case 4u: return 2;", "case 5u: return 3;"):
        if stray in control:
            fail(f"control_cf_final.c still maps a track to a voice with '{stray}'")

    print("PERKY CF voice silo: PASS "
          "(T1=V1 Fold1+Wavetable+SimpleDrum; T2=V2 Fold2+Wavetable+ComplexDrum; "
          "T3=V3 Resonant+Slap+Karplus; T4=V4 NoiseHat+NoiseTone+AcousticHats; staged ALGO is "
          "family-local and mapped through one table; SRC page publishes the "
          "per-voice length)")


if __name__ == "__main__":
    main()

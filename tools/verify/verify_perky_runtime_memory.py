#!/usr/bin/env python3
"""Pin PERKY Noise/Tone's current shipping runtime-memory budget.

This is intentionally separate from the table-content analyzer. The table
analyzer answers whether a particular pair of extracted envelope curves fits;
this gate pins the renderer-side allocations that do not depend on firmware
bytes.
"""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
PERKY = ROOT / "modules/perky"
sys.path.insert(0, str(PERKY))

import noise_tone_compact as compact  # noqa:E402
import noise_tone_envelope_cache as envcache  # noqa:E402

PRIVATE_X_WORDS = 616
PRIVATE_Y_WORDS = 2155
VOICES_PER_CORE = 4
RNG_WORDS = 4
EVENT_STAGING_WORDS = 1
SHARED_SCRATCH_WORDS = 64
SYNTHETIC_WAVE_Y = 683
SYNTHETIC_ENVELOPE_Y_EACH = 646


def main() -> None:
    state = compact.WORDS_PER_VOICE
    cache = envcache.CACHE_WORDS_PER_VOICE
    persistent_x = VOICES_PER_CORE * (state + cache) + RNG_WORDS
    x_words = persistent_x + EVENT_STAGING_WORDS + SHARED_SCRATCH_WORDS
    if state != 41:
        raise AssertionError(f"compact state drifted to {state} words/voice")
    if cache != 17:
        raise AssertionError(f"envelope cache drifted to {cache} words/voice")
    if persistent_x != 236:
        raise AssertionError(f"persistent X footprint drifted to {persistent_x} words/core")
    if x_words != 301:
        raise AssertionError(f"runtime X footprint incl seam/scratch drifted to {x_words} words/core")
    x_margin = PRIVATE_X_WORDS - x_words
    if x_margin != 315:
        raise AssertionError(f"runtime X margin drifted to {x_margin} words")

    synthetic_y = SYNTHETIC_WAVE_Y + 2 * SYNTHETIC_ENVELOPE_Y_EACH
    if synthetic_y != 1975:
        raise AssertionError(f"synthetic packed Y footprint drifted to {synthetic_y}")
    y_margin = PRIVATE_Y_WORDS - synthetic_y
    if y_margin != 180:
        raise AssertionError(f"synthetic packed Y margin drifted to {y_margin}")

    print(
        "PERKY runtime memory: PASS "
        f"(persistent X {persistent_x}; + event {EVENT_STAGING_WORDS} + "
        f"shared scratch {SHARED_SCRATCH_WORDS} = {x_words}/{PRIVATE_X_WORDS}, "
        f"margin {x_margin}; synthetic packed Y {synthetic_y}/{PRIVATE_Y_WORDS}, "
        f"margin {y_margin})"
    )


if __name__ == "__main__":
    main()

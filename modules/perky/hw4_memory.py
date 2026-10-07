"""Private DSP-X layout for the static four-voice HW4 audition profile.

The earlier PERKY4 profile reserved a 100-word renderer scratch block at X:$3900
and placed the 17-word Simple Drum pitch cache immediately after it at $3964.
HW4 needs Karplus' measured 128-word scratch ABI, so the cache and Fold2 trigger
snapshot move upward together.  This module is intentionally profile-specific;
it does not silently change the physically tested PERKY2/PERKY4 layouts.
"""

PRIVATE_X_BASE = 0x3800
PRIVATE_X_WORDS = 616
PRIVATE_X_END = PRIVATE_X_BASE + PRIVATE_X_WORDS  # exclusive

OVERLAY_BASE = 0x3800
OVERLAY_WORDS = 58
OVERLAY_SLOTS = 2                  # HW4 admits two local tracks per DSP core
OVERLAY_END = OVERLAY_BASE + 4 * OVERLAY_WORDS  # legacy markers still index 4 slots

RNG_BASE = 0x38E8
RNG_WORDS = 4
EVENT_X = 0x38EC
LEGACY_ADMISSION_X = 0x38ED        # no longer used for first-wins admission
MARKER_BASE = 0x38EE
MARKER_WORDS = 4

SCRATCH_BASE = 0x3900
SCRATCH_WORDS = 128
SCRATCH_END = SCRATCH_BASE + SCRATCH_WORDS

PITCH_CACHE_BASE = SCRATCH_END
PITCH_CACHE_WORDS = 17
PITCH_CACHE_END = PITCH_CACHE_BASE + PITCH_CACHE_WORDS

FOLD2_SHADOW_BASE = PITCH_CACHE_END
FOLD2_SHADOW_WORDS = 51
FOLD2_SHADOW_END = FOLD2_SHADOW_BASE + FOLD2_SHADOW_WORDS


def spans():
    return (
        ('overlays', OVERLAY_BASE, 4 * OVERLAY_WORDS),
        ('rng', RNG_BASE, RNG_WORDS),
        ('event', EVENT_X, 1),
        ('legacy-admission', LEGACY_ADMISSION_X, 1),
        ('markers', MARKER_BASE, MARKER_WORDS),
        ('scratch', SCRATCH_BASE, SCRATCH_WORDS),
        ('pitch-cache', PITCH_CACHE_BASE, PITCH_CACHE_WORDS),
        ('fold2-shadow', FOLD2_SHADOW_BASE, FOLD2_SHADOW_WORDS),
    )


def validate():
    items = spans()
    for name, base, words in items:
        assert words > 0, name
        assert PRIVATE_X_BASE <= base < PRIVATE_X_END, name
        assert base + words <= PRIVATE_X_END, (name, hex(base + words), hex(PRIVATE_X_END))
    for i, (an, ab, aw) in enumerate(items):
        for bn, bb, bw in items[i + 1:]:
            assert ab + aw <= bb or bb + bw <= ab, (an, bn)
    assert SCRATCH_WORDS >= 128
    assert PITCH_CACHE_BASE == 0x3980
    assert FOLD2_SHADOW_BASE == 0x3991
    assert FOLD2_SHADOW_END == 0x39C4


validate()

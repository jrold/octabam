"""Private DSP memory layout for the static four-voice HW4 audition profile.

The earlier PERKY4 profile reserved a 100-word renderer scratch block at X:$3900
and placed the 17-word Simple Drum pitch cache immediately after it at $3964.
HW4 needs Karplus' measured 128-word scratch ABI, so the cache and Fold2 trigger
snapshot move upward together.  Karplus also gets a 32-word frozen pre-trigger
snapshot in the remaining measured private-X window.

For the hardware audition, reclaimed local Y carries Karplus' two envelope
curves, 2K feedback ring, and three exact prepared-control lookup tables.  The
control tables occupy the formerly unused $1e00..$3e00 tail and end 255 words
below the stock boot-clear boundary at $3f00.  This is intentionally NOT a claim
for the final PERKY architecture: the dedicated perky-hw4 remix retires the
buffer-backed stock FX whose arena is borrowed here.
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

KARPLUS_SHADOW_BASE = FOLD2_SHADOW_END
KARPLUS_SHADOW_WORDS = 32
KARPLUS_SHADOW_END = KARPLUS_SHADOW_BASE + KARPLUS_SHADOW_WORDS
KARPLUS_TRIGGERED_WORD = 32        # first spare word in the 58-word track overlay

# First-audition local-Y placement.  Stock static uploads stop below $1000 and
# the stock init clear begins at $3f00, so boot-loaded data here survives.  The
# price is the FX1 instance arena; the perky-hw4 remix intentionally retires the
# buffer-backed effects for this test image.
HW4_Y_BASE = 0x1000
HW4_Y_BOOT_CLEAR = 0x3F00
KARPLUS_ENV1_BASE = 0x1000
KARPLUS_ENV_PACKED_WORDS = 684     # 1025 u16 values, 3 packed into 2 DSP words
KARPLUS_ENV2_BASE = KARPLUS_ENV1_BASE + KARPLUS_ENV_PACKED_WORDS
KARPLUS_RING_BASE = 0x1600         # aligned after both packed envelope tables
KARPLUS_RING_WORDS = 0x800
KARPLUS_RING_END = KARPLUS_RING_BASE + KARPLUS_RING_WORDS

# Exact live-control functions.  4096 u16 values pack three-in-two into 2731
# DSP words.  Three tables fit almost exactly in the remaining pre-clear arena:
# $1e00 + 3*2731 = $3e01, leaving $00ff words before $3f00.
KARPLUS_CONTROL_LUT_ENTRIES = 4096
KARPLUS_CONTROL_LUT_WORDS = 2731
KARPLUS_TUNE_DELAY_BASE = KARPLUS_RING_END
KARPLUS_DECAY_RATE_BASE = KARPLUS_TUNE_DELAY_BASE + KARPLUS_CONTROL_LUT_WORDS
KARPLUS_EDGE_COEFF_BASE = KARPLUS_DECAY_RATE_BASE + KARPLUS_CONTROL_LUT_WORDS
HW4_Y_END = KARPLUS_EDGE_COEFF_BASE + KARPLUS_CONTROL_LUT_WORDS


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
        ('karplus-shadow', KARPLUS_SHADOW_BASE, KARPLUS_SHADOW_WORDS),
    )


def y_spans():
    return (
        ('karplus-envelope1', KARPLUS_ENV1_BASE, KARPLUS_ENV_PACKED_WORDS),
        ('karplus-envelope2', KARPLUS_ENV2_BASE, KARPLUS_ENV_PACKED_WORDS),
        ('karplus-ring', KARPLUS_RING_BASE, KARPLUS_RING_WORDS),
        ('karplus-tune-delay', KARPLUS_TUNE_DELAY_BASE, KARPLUS_CONTROL_LUT_WORDS),
        ('karplus-decay-rate', KARPLUS_DECAY_RATE_BASE, KARPLUS_CONTROL_LUT_WORDS),
        ('karplus-edge-coeff', KARPLUS_EDGE_COEFF_BASE, KARPLUS_CONTROL_LUT_WORDS),
    )


def _validate_disjoint(items):
    for i, (an, ab, aw) in enumerate(items):
        for bn, bb, bw in items[i + 1:]:
            assert ab + aw <= bb or bb + bw <= ab, (an, bn)


def validate():
    items = spans()
    for name, base, words in items:
        assert words > 0, name
        assert PRIVATE_X_BASE <= base < PRIVATE_X_END, name
        assert base + words <= PRIVATE_X_END, (name, hex(base + words), hex(PRIVATE_X_END))
    _validate_disjoint(items)
    assert SCRATCH_WORDS >= 128
    assert PITCH_CACHE_BASE == 0x3980
    assert FOLD2_SHADOW_BASE == 0x3991
    assert FOLD2_SHADOW_END == 0x39C4
    assert KARPLUS_SHADOW_BASE == 0x39C4
    assert KARPLUS_SHADOW_END == 0x39E4

    yitems = y_spans()
    for name, base, words in yitems:
        assert words > 0, name
        assert HW4_Y_BASE <= base < HW4_Y_BOOT_CLEAR, name
        assert base + words <= HW4_Y_BOOT_CLEAR, (name, hex(base + words))
    _validate_disjoint(yitems)
    assert KARPLUS_ENV2_BASE + KARPLUS_ENV_PACKED_WORDS <= KARPLUS_RING_BASE
    assert KARPLUS_RING_END == 0x1E00
    assert KARPLUS_TUNE_DELAY_BASE == 0x1E00
    assert KARPLUS_DECAY_RATE_BASE == 0x28AB
    assert KARPLUS_EDGE_COEFF_BASE == 0x3356
    assert HW4_Y_END == 0x3E01
    assert HW4_Y_BOOT_CLEAR - HW4_Y_END == 0xFF


validate()

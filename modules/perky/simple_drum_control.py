"""Exact PĒRKONS v1.2.1 control preparation for the Simple Drum family.

This module contains only instruction-level arithmetic recovered from the
v1.2.1 update path.  It deliberately does not embed firmware-owned wave or
envelope table data.

Octatrack source controls are 7-bit (0..127).  The PĒRKONS panel/control path
uses 12-bit targets, then applies the firmware's 3/8 target + 5/8 history
smoother before converting those prepared words to renderer parameters.
"""
from __future__ import annotations

from dataclasses import dataclass

MASK16 = 0xFFFF
MASK32 = 0xFFFFFFFF
PANEL_MAX = 127
TARGET_MAX = 4095

# Simple Drum panel M1/M2/M3 -> firmware mode byte.  This is the explicit
# physical-panel mapping used by PerkyBits' v1.2.1 engine catalog.
PANEL_MODE_TO_FIRMWARE = (1, 0, 2)

# Firmware mode byte -> deferred oscillator target wave.  The current wave is
# swapped to this target by the oscillator when its phase wraps.
FIRMWARE_MODE_TO_WAVE = {
    0: 0x080226A0,
    1: 0x080222A0,
    2: 0x080228A0,
}

# The Simple Drum update path configures the common envelope helper with these
# per-envelope shape constants.  They are scalar configuration values, not
# copied curve data.
_AMP_DECAY_OFFSET = 50
_AMP_DECAY_SCALE = 5200
_PITCH_DECAY_OFFSET = 20
_PITCH_DECAY_SCALE = 400
_ENVELOPE_RATE_NUMERATOR = 0x000FFFFF


def panel_to_target(value: int) -> int:
    """Map an Octatrack 7-bit source value to the firmware's 12-bit target."""
    value = max(0, min(PANEL_MAX, int(value)))
    return TARGET_MAX if value == PANEL_MAX else value << 5


def smooth_control(old: int, target: int) -> int:
    """One exact v1.2.1 common-control update: (3*target + 5*old) >> 3."""
    old &= MASK32
    target &= MASK32
    return ((3 * target + 5 * old) & MASK32) >> 3


def settle_from_zero(target: int, updates: int = 17) -> int:
    """Helper matching the fresh-engine capture harness used for qualification."""
    value = 0
    for _ in range(int(updates)):
        value = smooth_control(value, target)
    return value


def _time_parameter(prepared: int) -> int:
    """Translate the smoothed DECAY word exactly as common update 0x08024714."""
    q = 0x7FFF + ((prepared & MASK16) << 2)
    mantissa = (q & 0x0FFF) + 0x1000
    exponent = (q >> 12) & 0x0F
    if exponent > 11:
        value = (mantissa << (exponent - 12)) & MASK16
    else:
        value = (mantissa >> (12 - exponent)) & MASK16

    # ARM path: subs #1; ubfx bits 1..15; subs #0x7f; uxth.
    value = (value - 1) & MASK32
    value = (value >> 1) & 0x7FFF
    return (value - 0x7F) & MASK16


def _envelope_decay_rate(control: int, offset: int, scale: int) -> int:
    """Exact +0x22 envelope increment produced by helper 0x08028784."""
    control &= MASK16
    denominator = 48 * (offset + 1)
    denominator += (48 * (scale - 1) * control) >> 12
    if denominator <= 0:
        raise ZeroDivisionError("invalid Simple Drum envelope denominator")
    return (_ENVELOPE_RATE_NUMERATOR // denominator) & MASK16


def amplitude_decay_rate(prepared_decay: int) -> int:
    """Renderer amplitude-envelope decay increment from smoothed DECAY."""
    return _envelope_decay_rate(
        _time_parameter(prepared_decay),
        _AMP_DECAY_OFFSET,
        _AMP_DECAY_SCALE,
    )


def pitch_envelope_decay_rate(prepared_env: int) -> int:
    """Renderer pitch-envelope decay increment from smoothed ENV."""
    return _envelope_decay_rate(
        prepared_env,
        _PITCH_DECAY_OFFSET,
        _PITCH_DECAY_SCALE,
    )


def raw_pitch(prepared_tune: int) -> int:
    """Simple Drum's 12-bit signed-pitch field for this family/slot."""
    return max(0, min(TARGET_MAX, int(prepared_tune)))


def pitch_envelope_amount(prepared_mix: int) -> int:
    """Simple Drum update stores MIX as the pitch-envelope amount >> 1."""
    return (int(prepared_mix) & MASK16) >> 1


def wave_for_panel_mode(panel_mode: int) -> int:
    """Return the authentic deferred wave address for physical M1/M2/M3."""
    panel_mode = max(0, min(2, int(panel_mode)))
    firmware_mode = PANEL_MODE_TO_FIRMWARE[panel_mode]
    return FIRMWARE_MODE_TO_WAVE[firmware_mode]


@dataclass(frozen=True)
class PreparedSimpleDrum:
    tune: int
    decay: int
    env: int
    mix: int
    raw_pitch: int
    amp_decay_rate: int
    pitch_decay_rate: int
    pitch_env_amount: int
    firmware_mode: int
    wave_address: int


def prepare(
    *,
    tune_target: int,
    decay_target: int,
    env_target: int,
    mix_target: int,
    panel_mode: int,
    previous: tuple[int, int, int, int] = (0, 0, 0, 0),
) -> PreparedSimpleDrum:
    """Apply one authentic control-update pass and derive renderer parameters."""
    targets = tuple(
        panel_to_target(v)
        for v in (tune_target, decay_target, env_target, mix_target)
    )
    smoothed = tuple(
        smooth_control(old, target)
        for old, target in zip(previous, targets)
    )
    mode = PANEL_MODE_TO_FIRMWARE[max(0, min(2, int(panel_mode)))]
    tune, decay, env, mix = smoothed
    return PreparedSimpleDrum(
        tune=tune,
        decay=decay,
        env=env,
        mix=mix,
        raw_pitch=raw_pitch(tune),
        amp_decay_rate=amplitude_decay_rate(decay),
        pitch_decay_rate=pitch_envelope_decay_rate(env),
        pitch_env_amount=pitch_envelope_amount(mix),
        firmware_mode=mode,
        wave_address=FIRMWARE_MODE_TO_WAVE[mode],
    )

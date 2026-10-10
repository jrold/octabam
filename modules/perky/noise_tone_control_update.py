"""Exact v1.2.1 Noise/Tone control/update arithmetic for the four-voice CF path.

This translates the original ARM routines:
  common update       0x08024714
  Waveform2 (M1)      0x08025870
  shared M2/M3        0x08025ab8
  envelope trigger    0x08024878 -> 0x08028774

No firmware-owned table bytes are embedded here.  Callers supply the exact
v1.2.1 pitch and chromatic tables extracted from their firmware image.
"""
from __future__ import annotations

import struct

import karplus_control_update as common
import simple_drum_control as control

MASK32 = 0xFFFFFFFF
PANEL_TO_FIRMWARE = (1, 0, 2)
SHARED_WAVE = {0: 0x080226A0, 2: 0x080228A0}
DEFAULT_WAVE = 0x080222A0
M1_WAVE = 0x080310E0


def u16(raw: bytes | bytearray, off: int) -> int:
    return struct.unpack_from('<H', raw, off)[0]


def u32(raw: bytes | bytearray, off: int) -> int:
    return struct.unpack_from('<I', raw, off)[0]


def put16(raw: bytearray, off: int, value: int) -> None:
    struct.pack_into('<H', raw, off, value & 0xFFFF)


def put32(raw: bytearray, off: int, value: int) -> None:
    struct.pack_into('<I', raw, off, value & MASK32)


def s16(value: int) -> int:
    value &= 0xFFFF
    return value - 0x10000 if value & 0x8000 else value


def s32(value: int) -> int:
    value &= MASK32
    return value - 0x100000000 if value & 0x80000000 else value


def _osc_increment(value: int) -> int:
    """Helper 0x0802847c: convert its u16 frequency input to phase increment."""
    shifted = s32((int(value) & 0xFFFF) << 20)
    product = shifted * s32(0x057619F1)
    high = s32((product >> 32) & MASK32)
    # ARM: high>>10 - sign(shifted)
    return (s32(high) >> 10) - (s32(shifted) >> 31)


def _filter_coefficient(value: int) -> int:
    # Helper 0x080288d0; identical arithmetic to the Karplus coefficient path.
    return common.karplus_coefficient(value)


def _env_rate(raw: bytearray, base: int, parameter: int, decay: bool) -> int:
    config = base + (0x1C if decay else 0x18)
    scale = u16(raw, config + 2)
    offset = u16(raw, config)
    product = (48 * ((scale - 1) & 0xFFFF) * (parameter & 0xFFFF)) & MASK32
    denominator = (48 * ((offset + 1) & 0xFFFF) + (product >> 12)) & MASK32
    return 0 if denominator == 0 else 0xFFFFF // denominator


def _configure_env(raw: bytearray, a: int, d: int) -> None:
    put16(raw, 0x94, _env_rate(raw, 0x74, a, False))
    put16(raw, 0x96, _env_rate(raw, 0x74, d, True))


def fresh_state(panel_mode: int, *, velocity: int = 255, note: int = 45) -> bytearray:
    """Renderer-complete initial state using only fields the native path touches."""
    panel_mode = max(0, min(2, int(panel_mode)))
    fw = PANEL_TO_FIRMWARE[panel_mode]
    raw = bytearray(0x120)
    # Object+8 = amplitude-envelope sustain threshold 0x0FF0, set once by the
    # original voice-default pass (0x080277a6) and never touched by init. Gates
    # obj[0x7B] in common_update. See docs/PK4_OBJ8_SUSTAIN.md.
    put16(raw, 8, 0x0FF0)
    raw[5] = fw
    raw[6] = max(1, min(255, int(velocity)))
    raw[7] = max(0, min(127, int(note)))

    # Common cVoice init 0x080246ac.
    put32(raw, 0x38, DEFAULT_WAVE)
    put32(raw, 0x3C, DEFAULT_WAVE)
    put32(raw, 0x60, 0x00020000)  # count=0, reload=2
    put16(raw, 0xA8, 0x0800)      # resonant filter damping
    raw[0x7A] = 1
    raw[0x7C] = 1
    put32(raw, 0x8C, 0x00020001)
    put32(raw, 0x90, 0x0FA00019)

    if fw == 1:  # panel M1 / Waveform2 init 0x08025834
        put16(raw, 0xC4, 1)
        put32(raw, 0x8C, 0x0FA00000)
        put32(raw, 0x90, 0x0FA00003)
        put32(raw, 0xE4, M1_WAVE)
        put32(raw, 0xE8, M1_WAVE)
    else:        # shared M2/M3 init 0x08025a84
        raw[0xC4] = 0
        put32(raw, 0xD0, DEFAULT_WAVE)
        put32(raw, 0xD4, DEFAULT_WAVE)
        raw[0x7C] = 0
        put32(raw, 0x90, 0x0FA00002)

    _configure_env(raw, 0x1000, 0x1000)
    return raw


def trigger(raw: bytearray, *, velocity: int = 255, note: int = 45) -> None:
    """Voice4 A2 trigger wrapper + common envelope trigger, before update()."""
    raw[6] = max(1, min(255, int(velocity)))
    if note:
        raw[7] = max(0, min(127, int(note)))
    raw[0x84] = 1  # envelope +0x10 trigger latch
    raw[0x74] = 1  # attack state
    if raw[0x7C] != 0:
        put32(raw, 0x80, 0)


def update(raw: bytearray, targets: tuple[int, int, int, int] | list[int],
           pitch: bytes, chromatic: bytes) -> tuple[int, int, int, int]:
    """One complete original Voice4 A2 update pass for the state's mode."""
    if len(raw) != 0x120:
        raise ValueError('Noise/Tone state must be 0x120 bytes')
    if len(targets) != 4:
        raise ValueError('four target words required')

    prepared = common.common_update(raw, targets, pitch, chromatic)
    fw = raw[5]
    if fw == 1:
        # 0x08025870: Waveform2 smooths TUNE a second time.
        tune = control.smooth_control(prepared[0], int(targets[0]))
        put32(raw, 0x1C, tune)
        index = max(0, min(
            4095,
            s16((tune & 0x0F80) - 0x0800 + common.note_offset(raw[7], chromatic)),
        ))
        put32(raw, 0xDC, common.pitch_at(pitch, index))
        p1 = u16(raw, 0xBE)
        put16(raw, 0x0A, u16(raw, 0xC0))
        put32(raw, 0xC8, (0x000CE364 - 199 * p1) & MASK32)
        return (tune, prepared[1], prepared[2], prepared[3])

    # 0x08025ab8: shared M2/M3 path.
    put32(raw, 0x3C, SHARED_WAVE.get(fw, DEFAULT_WAVE))
    p1 = u16(raw, 0xBE)
    put16(raw, 0xAA, _filter_coefficient(p1))

    tune_index = max(0, min(4095, s16(u16(raw, 0xBA))))
    base = (0xBB80 * common.pitch_at(pitch, tune_index)) >> 20
    scaled = ((base * ((u16(raw, 0xC0) + 0x0800) & 0xFFFF)) >> 12) & 0xFFFF
    put32(raw, 0xCC, _osc_increment(scaled) & MASK32)
    put32(raw, 0xF8, p1)
    return prepared


class ControlState:
    """Per-track authentic four-control smoothing cadence for Noise/Tone."""
    def __init__(self) -> None:
        self.targets = [0, 0, 0, 0]
        self.last_raw: tuple[int, int, int, int] | None = None
        self.panel_mode: int | None = None

    @staticmethod
    def _targets(raw: tuple[int, int, int, int]) -> list[int]:
        return [control.panel_to_target(v) for v in raw]

    def prepare(self, state: bytearray, raw_values: tuple[int, int, int, int],
                panel_mode: int, pitch: bytes, chromatic: bytes, *, trig: bool) -> None:
        raw_values = tuple(max(0, min(127, int(v))) for v in raw_values)
        panel_mode = max(0, min(2, int(panel_mode)))
        dirty = self.last_raw != raw_values or self.panel_mode != panel_mode
        if dirty:
            # Algorithm/mode setters each call update with the previous targets.
            update(state, self.targets, pitch, chromatic)
            update(state, self.targets, pitch, chromatic)
            state[5] = PANEL_TO_FIRMWARE[panel_mode]
            self.targets = self._targets(raw_values)
            for _ in range(16):
                update(state, self.targets, pitch, chromatic)
            self.last_raw = raw_values
            self.panel_mode = panel_mode
        if trig:
            trigger(state)
            update(state, self.targets, pitch, chromatic)

"""34-word DSP-state model for PĒRKONS v1.2.1 Simple Drum.

The renderer only needs one oscillator, two common envelope instances, the
prepared pitch/envelope controls, velocity and mute. The 4096-entry pitch
table is control-rate data: ``cached_base_frequency`` proves it can be reduced
to one prepared value per block while preserving the per-sample pitch envelope.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import simple_drum_ref as ref

MASK16 = 0xFFFF
MASK32 = 0xFFFFFFFF
WORDS_PER_VOICE = 34

VELOCITY = 0
MUTE = 1
OSC_PHASE = 2
OSC_INCREMENT = 4
OSC_CURRENT = 6
OSC_NEXT = 8
AMP_ENV = 10
PITCH_ENV = 21
RAW_PITCH = 32
PITCH_ENV_AMOUNT = 33
ENV_WORDS = 11

ENV_STATE = 0
ENV_SHAPE = 1
ENV_FLAG4 = 2
ENV_FLAG6 = 3
ENV_TRIGGER = 4
ENV_VALUE = 5
ENV_HOLD = 7
ENV_ATTACK = 9
ENV_DECAY = 10


def _u16(raw: bytes | bytearray, off: int) -> int:
    return raw[off] | (raw[off + 1] << 8)


def _u32(raw: bytes | bytearray, off: int) -> int:
    return _u16(raw, off) | (_u16(raw, off + 2) << 16)


def _put16(raw: bytearray, off: int, value: int) -> None:
    value &= MASK16
    raw[off] = value & 0xFF
    raw[off + 1] = (value >> 8) & 0xFF


def _put32(raw: bytearray, off: int, value: int) -> None:
    value &= MASK32
    _put16(raw, off, value)
    _put16(raw, off + 2, value >> 16)


def _s16(value: int) -> int:
    value &= MASK16
    return value - 0x10000 if value & 0x8000 else value


def _s32(value: int) -> int:
    value &= MASK32
    return value - 0x100000000 if value & 0x80000000 else value


def _u32bits(value: int) -> int:
    return value & MASK32


def _asr32(value: int, shift: int) -> int:
    return _s32(value) >> shift


def _mullo32(a: int, b: int) -> int:
    return _s32((_u32bits(a) * _u32bits(b)) & MASK32)


def _table_u16(table: bytes, index: int) -> int:
    off = index * 2
    return table[off] | (table[off + 1] << 8)


def _table_s16(table: bytes, index: int) -> int:
    return _s16(_table_u16(table, index))


@dataclass
class CompactSimpleDrum:
    words: list[int]

    def __post_init__(self) -> None:
        if len(self.words) != WORDS_PER_VOICE:
            raise ValueError(f"Simple Drum compact state must be {WORDS_PER_VOICE} words")
        self.words = [int(x) & MASK16 for x in self.words]

    @staticmethod
    def _set_list_u32(words: list[int], off: int, value: int) -> None:
        value &= MASK32
        words[off] = value & MASK16
        words[off + 1] = (value >> 16) & MASK16

    def u32(self, off: int) -> int:
        return self.words[off] | (self.words[off + 1] << 16)

    def set_u32(self, off: int, value: int) -> None:
        self._set_list_u32(self.words, off, value)

    @classmethod
    def from_arm(cls, raw: bytes | bytearray) -> "CompactSimpleDrum":
        if len(raw) != ref.STATE_BYTES:
            raise ValueError(f"state must be {ref.STATE_BYTES} bytes")
        w = [0] * WORDS_PER_VOICE
        w[VELOCITY] = raw[6]
        w[MUTE] = raw[0xB8]
        cls._set_list_u32(w, OSC_PHASE, _u32(raw, 0x30))
        cls._set_list_u32(w, OSC_INCREMENT, _u32(raw, 0x34))
        cls._set_list_u32(w, OSC_CURRENT, _u32(raw, 0x38))
        cls._set_list_u32(w, OSC_NEXT, _u32(raw, 0x3C))
        cls._copy_env_from_arm(w, AMP_ENV, raw, 0x74)
        cls._copy_env_from_arm(w, PITCH_ENV, raw, 0xC4)
        w[RAW_PITCH] = _u16(raw, 0xBA)
        w[PITCH_ENV_AMOUNT] = _u16(raw, 0xEC)
        return cls(w)

    @classmethod
    def _copy_env_from_arm(cls, w: list[int], dst: int,
                           raw: bytes | bytearray, src: int) -> None:
        w[dst + ENV_STATE] = raw[src]
        w[dst + ENV_SHAPE] = raw[src + 1]
        w[dst + ENV_FLAG4] = raw[src + 4]
        w[dst + ENV_FLAG6] = raw[src + 6]
        w[dst + ENV_TRIGGER] = raw[src + 7]
        cls._set_list_u32(w, dst + ENV_VALUE, _u32(raw, src + 0x0C))
        cls._set_list_u32(w, dst + ENV_HOLD, _u32(raw, src + 0x10))
        w[dst + ENV_ATTACK] = _u16(raw, src + 0x20)
        w[dst + ENV_DECAY] = _u16(raw, src + 0x22)

    def apply_to_arm(self, template: bytes | bytearray) -> bytes:
        if len(template) != ref.STATE_BYTES:
            raise ValueError(f"state must be {ref.STATE_BYTES} bytes")
        raw = bytearray(template)
        raw[6] = self.words[VELOCITY] & 0xFF
        raw[0xB8] = self.words[MUTE] & 0xFF
        _put32(raw, 0x30, self.u32(OSC_PHASE))
        _put32(raw, 0x34, self.u32(OSC_INCREMENT))
        _put32(raw, 0x38, self.u32(OSC_CURRENT))
        _put32(raw, 0x3C, self.u32(OSC_NEXT))
        self._copy_env_to_arm(raw, 0x74, AMP_ENV)
        self._copy_env_to_arm(raw, 0xC4, PITCH_ENV)
        _put16(raw, 0xBA, self.words[RAW_PITCH])
        _put16(raw, 0xEC, self.words[PITCH_ENV_AMOUNT])
        return bytes(raw)

    def _copy_env_to_arm(self, raw: bytearray, dst: int, src: int) -> None:
        raw[dst] = self.words[src + ENV_STATE] & 0xFF
        raw[dst + 1] = self.words[src + ENV_SHAPE] & 0xFF
        raw[dst + 4] = self.words[src + ENV_FLAG4] & 0xFF
        raw[dst + 6] = self.words[src + ENV_FLAG6] & 0xFF
        raw[dst + 7] = self.words[src + ENV_TRIGGER] & 0xFF
        _put32(raw, dst + 0x0C, self.u32(src + ENV_VALUE))
        _put32(raw, dst + 0x10, self.u32(src + ENV_HOLD))
        _put16(raw, dst + 0x20, self.words[src + ENV_ATTACK])
        _put16(raw, dst + 0x22, self.words[src + ENV_DECAY])


def _render_envelope(voice: CompactSimpleDrum, base: int,
                     envelope1: bytes | None,
                     envelope2: bytes | None) -> int:
    state = voice.words[base + ENV_STATE]
    value = _s32(voice.u32(base + ENV_VALUE))
    if state == 0:
        if voice.words[base + ENV_TRIGGER] or voice.words[base + ENV_FLAG4]:
            voice.words[base + ENV_STATE] = 1
    elif state == 1:
        value = _s32(_u32bits(value) + voice.words[base + ENV_ATTACK])
        voice.set_u32(base + ENV_VALUE, value)
        if voice.words[base + ENV_FLAG4]:
            if value > 0x000FFFFE:
                voice.words[base + ENV_STATE] = 4
                if value >= 0x00100000:
                    value = 0x000FFFFF
                    voice.set_u32(base + ENV_VALUE, value)
        elif value > 0x000FFFFE:
            voice.words[base + ENV_STATE] = 4 if voice.words[base + ENV_FLAG6] else 3
            if value >= 0x00100000:
                value = 0x000FFFFF
                voice.set_u32(base + ENV_VALUE, value)
    elif state == 2:
        pass
    elif state == 3:
        if not voice.words[base + ENV_TRIGGER] and (
            voice.words[base + ENV_FLAG4] or (voice.words[base + ENV_HOLD] & 0xFF) == 0
        ):
            voice.words[base + ENV_STATE] = 4
    elif state == 4:
        if voice.words[base + ENV_TRIGGER]:
            voice.words[base + ENV_STATE] = 1
        else:
            value = _s32(_u32bits(value) - voice.words[base + ENV_DECAY])
            voice.set_u32(base + ENV_VALUE, value)
            if value <= 0:
                value = 0
                voice.set_u32(base + ENV_VALUE, 0)
                voice.words[base + ENV_STATE] = 1 if voice.words[base + ENV_FLAG4] else 0

    shape = voice.words[base + ENV_SHAPE] & 0xFF
    if shape not in (1, 2):
        return (_u32bits(value) >> 4) & MASK16
    curve = envelope1 if shape == 1 else envelope2
    if curve is None:
        return 0
    raw = _u32bits(value)
    index = (raw >> 10) & 0x7FF
    nxt = (index + 1) & 0x7FF
    fraction = raw & 0x3FF
    a = _table_u16(curve, index)
    b = _table_u16(curve, nxt)
    return (a + _asr32(_mullo32(b - a, fraction), 10)) & MASK16


def cached_base_frequency(voice: CompactSimpleDrum, pitch_table: bytes) -> int:
    return ref.base_frequency(voice.words[RAW_PITCH], pitch_table)


def _set_oscillator_frequency(voice: CompactSimpleDrum, frequency: int) -> None:
    shifted = _s32((_u32bits(frequency) << 20) & MASK32)
    product = shifted * _s32(0x057619F1)
    high = _s32((product >> 32) & MASK32)
    result = _asr32(high, 10) - _asr32(shifted, 31)
    voice.set_u32(OSC_INCREMENT, result)


def _render_oscillator(voice: CompactSimpleDrum,
                       waves: Mapping[int, bytes]) -> int:
    phase = (voice.u32(OSC_PHASE) + voice.u32(OSC_INCREMENT)) & MASK32
    voice.set_u32(OSC_PHASE, phase)
    current = voice.u32(OSC_CURRENT)
    if _s32(phase) > 0x00100000:
        nxt = voice.u32(OSC_NEXT)
        phase = (phase - 0x00100000) & MASK32
        voice.set_u32(OSC_PHASE, phase)
        if nxt != current:
            current = nxt
            voice.set_u32(OSC_CURRENT, current)
    table = waves.get(current)
    if table is None:
        raise KeyError(f"missing Simple Drum wave table at 0x{current:08x}")
    index = (phase >> 12) & 0xFF
    nxt_index = (index + 1) & 0xFF
    fraction = phase & 0xFFF
    a = _table_s16(table, index)
    b = _table_s16(table, nxt_index)
    return _s16(a + _asr32(_mullo32(b - a, fraction), 12))


def render_block(voice: CompactSimpleDrum, sample_count: int,
                 waves: Mapping[int, bytes], pitch_table: bytes,
                 envelope1: bytes | None, envelope2: bytes | None,
                 *, prepared_base_frequency: int | None = None) -> list[int]:
    if prepared_base_frequency is None:
        prepared_base_frequency = cached_base_frequency(voice, pitch_table)
    base_frequency = prepared_base_frequency & MASK32
    out: list[int] = []
    for _ in range(sample_count):
        amplitude = _render_envelope(voice, AMP_ENV, envelope1, envelope2)
        pitch_envelope = _render_envelope(voice, PITCH_ENV, envelope1, envelope2)
        env_contribution = (
            pitch_envelope * voice.words[PITCH_ENV_AMOUNT]
        ) >> 10
        modulation = (voice.words[RAW_PITCH] * env_contribution) >> 16
        frequency = (base_frequency + modulation) & MASK32
        _set_oscillator_frequency(voice, frequency)
        oscillator = _render_oscillator(voice, waves)
        if voice.words[MUTE] & 0xFF:
            out.append(0)
            continue
        output = _asr32(_mullo32(amplitude, oscillator), 17)
        output = _asr32(_mullo32(output, voice.words[VELOCITY] & 0xFF), 8)
        out.append(max(-32768, min(32767, output)))
    return out


def abi_offsets() -> dict[str, int]:
    return {
        "velocity": VELOCITY,
        "mute": MUTE,
        "osc_phase": OSC_PHASE,
        "osc_increment": OSC_INCREMENT,
        "osc_current": OSC_CURRENT,
        "osc_next": OSC_NEXT,
        "amp_env": AMP_ENV,
        "pitch_env": PITCH_ENV,
        "raw_pitch": RAW_PITCH,
        "pitch_env_amount": PITCH_ENV_AMOUNT,
    }

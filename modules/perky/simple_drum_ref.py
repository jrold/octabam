"""Direct ARM-shaped reference model for PĒRKONS v1.2.1 Simple Drum.

This is a literal Python translation of PerkyBits' validated
``NativeV121SimpleDrum`` renderer. It intentionally keeps the original
0x120-byte state geometry so compact DSP representations can be checked
against a structurally independent oracle without storing firmware tables.
"""
from __future__ import annotations

from typing import Mapping

STATE_BYTES = 0x120
WAVE_BYTES = 256 * 2
PITCH_BYTES = 4096 * 2
ENVELOPE_BYTES = 2048 * 2
MASK16 = 0xFFFF
MASK32 = 0xFFFFFFFF


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


def _render_envelope(state: bytearray, base: int,
                     envelope1: bytes | None,
                     envelope2: bytes | None) -> int:
    envelope_state = state[base]
    value = _s32(_u32(state, base + 0x0C))

    if envelope_state == 0:
        if state[base + 7] != 0 or state[base + 4] != 0:
            state[base] = 1
    elif envelope_state == 1:
        value = _s32(_u32bits(value) + _u16(state, base + 0x20))
        _put32(state, base + 0x0C, value)
        if state[base + 4] != 0:
            if value > 0x000FFFFE:
                state[base] = 4
                if value >= 0x00100000:
                    value = 0x000FFFFF
                    _put32(state, base + 0x0C, value)
        elif value > 0x000FFFFE:
            state[base] = 4 if state[base + 6] != 0 else 3
            if value >= 0x00100000:
                value = 0x000FFFFF
                _put32(state, base + 0x0C, value)
    elif envelope_state == 2:
        pass
    elif envelope_state == 3:
        if state[base + 7] == 0 and (
            state[base + 4] != 0 or state[base + 0x10] == 0
        ):
            state[base] = 4
    elif envelope_state == 4:
        if state[base + 7] != 0:
            state[base] = 1
        else:
            value = _s32(_u32bits(value) - _u16(state, base + 0x22))
            _put32(state, base + 0x0C, value)
            if value <= 0:
                value = 0
                _put32(state, base + 0x0C, 0)
                state[base] = 1 if state[base + 4] != 0 else 0

    shape = state[base + 1]
    if shape not in (1, 2):
        return (_u32bits(value) >> 4) & MASK16
    curve = envelope1 if shape == 1 else envelope2
    if curve is None:
        return 0
    if len(curve) != ENVELOPE_BYTES:
        raise ValueError(f"envelope table must be {ENVELOPE_BYTES} bytes")
    raw = _u32bits(value)
    index = (raw >> 10) & 0x7FF
    nxt = (index + 1) & 0x7FF
    fraction = raw & 0x3FF
    a = _table_u16(curve, index)
    b = _table_u16(curve, nxt)
    return (a + _asr32(_mullo32(b - a, fraction), 10)) & MASK16


def pitch_lookup(raw_pitch: int, pitch_table: bytes) -> int:
    if len(pitch_table) != PITCH_BYTES:
        raise ValueError(f"pitch table must be {PITCH_BYTES} bytes")
    raw_pitch &= MASK16
    pitch = _s16(raw_pitch)
    negate = False
    if pitch < 0:
        magnitude = (-raw_pitch) & MASK16
        pitch = _s16(magnitude)
        if pitch >= 0x1000:
            negate = True

    value = 0
    if pitch < 0x1000:
        index = pitch & MASK16
        if index >= 4096:
            raise ValueError(f"pitch lookup index 0x{index:04x} outside 4096-entry table")
        value = _table_u16(pitch_table, index)
    else:
        p = pitch & MASK16
        shift = ((p - 0x1000) >> 9) & 0x7F
        adjust = shift * 127
        shift = (shift + 1) & 0xFF
        adjusted = _s16((p + (adjust << 9) - 0x200) & MASK16)
        index = adjusted & MASK16
        if index >= 4096:
            raise ValueError(f"pitch lookup index 0x{index:04x} outside 4096-entry table")
        value = (_table_u16(pitch_table, index) << shift) & MASK32

    if negate:
        value = (-value) & MASK32
    return _s32(value)


def base_frequency(raw_pitch: int, pitch_table: bytes) -> int:
    pitch = pitch_lookup(raw_pitch, pitch_table)
    return _u32bits(_mullo32(pitch, 0x0000BB80)) >> 20


def _set_oscillator_frequency(state: bytearray, base: int, frequency: int) -> None:
    shifted = _s32((_u32bits(frequency) << 20) & MASK32)
    product = shifted * _s32(0x057619F1)
    high = _s32((product >> 32) & MASK32)
    result = _asr32(high, 10) - _asr32(shifted, 31)
    _put32(state, base + 8, result)


def required_wave_addresses(state: bytes | bytearray) -> tuple[int, int]:
    return _u32(state, 0x2C + 0x0C), _u32(state, 0x2C + 0x10)


def _render_oscillator(state: bytearray, base: int,
                       waves: Mapping[int, bytes]) -> int:
    phase = (_u32(state, base + 4) + _u32(state, base + 8)) & MASK32
    _put32(state, base + 4, phase)
    current = _u32(state, base + 0x0C)
    if _s32(phase) > 0x00100000:
        nxt = _u32(state, base + 0x10)
        phase = (phase - 0x00100000) & MASK32
        _put32(state, base + 4, phase)
        if nxt != current:
            current = nxt
            _put32(state, base + 0x0C, current)

    table = waves.get(current)
    if table is None:
        raise KeyError(f"missing Simple Drum wave table at 0x{current:08x}")
    if len(table) != WAVE_BYTES:
        raise ValueError(f"wave table must be {WAVE_BYTES} bytes")
    index = (phase >> 12) & 0xFF
    nxt_index = (index + 1) & 0xFF
    fraction = phase & 0xFFF
    a = _table_s16(table, index)
    b = _table_s16(table, nxt_index)
    return _s16(a + _asr32(_mullo32(b - a, fraction), 12))


def render_block(state: bytearray, sample_count: int,
                 waves: Mapping[int, bytes], pitch_table: bytes,
                 envelope1: bytes | None, envelope2: bytes | None) -> tuple[list[int], bytes]:
    if len(state) != STATE_BYTES:
        raise ValueError(f"state must be {STATE_BYTES} bytes")
    out: list[int] = []
    for _ in range(sample_count):
        amplitude = _render_envelope(state, 0x74, envelope1, envelope2)
        pitch_envelope = _render_envelope(state, 0xC4, envelope1, envelope2)
        raw_pitch = _u16(state, 0xBA)
        base = base_frequency(raw_pitch, pitch_table)
        env_contribution = (pitch_envelope * _u16(state, 0xEC)) >> 10
        modulation = (raw_pitch * env_contribution) >> 16
        frequency = (base + modulation) & MASK32
        _set_oscillator_frequency(state, 0x2C, frequency)
        oscillator = _render_oscillator(state, 0x2C, waves)

        if state[0xB8] != 0:
            out.append(0)
            continue

        output = _asr32(_mullo32(amplitude, oscillator), 17)
        output = _asr32(_mullo32(output, state[6]), 8)
        output = max(-32768, min(32767, output))
        out.append(output)
    return out, bytes(state)

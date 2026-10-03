"""Host-side integer oracle for the v1.2.1 shared Noise / Tone renderer.

This is development/test code, not Octatrack DSP code.  It mirrors the native
PerkyBits integer model closely enough to generate deterministic vectors for a
DSP56300 translation while keeping firmware-owned state/tables out of this
repository.

Inputs are caller-supplied:
  * ``state``: 0x120 mutable bytes
  * ``waves``: mapping of firmware-style u32 addresses to 512-byte LE s16 tables
  * ``envelope1`` / ``envelope2``: optional 4096-byte LE u16 curves
  * ``rng``: two u32 words

No firmware blobs or extracted tables are embedded here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

STATE_BYTES = 0x120
WAVE_BYTES = 256 * 2
ENVELOPE_BYTES = 2048 * 2


def _u32(value: int) -> int:
    return value & 0xFFFFFFFF


def _s32(value: int) -> int:
    value &= 0xFFFFFFFF
    return value - 0x100000000 if value & 0x80000000 else value


def _s16(value: int) -> int:
    value &= 0xFFFF
    return value - 0x10000 if value & 0x8000 else value


def arshift32(value: int, shift: int) -> int:
    """ARM/reference-style signed 32-bit arithmetic right shift."""
    value = _s32(value)
    if shift == 0:
        return value
    return _s32(value >> shift)


def multiply_low32(a: int, b: int) -> int:
    """Low 32 bits of the reference's unsigned-bit-pattern multiply."""
    return _s32((_u32(a) * _u32(b)) & 0xFFFFFFFF)


def _read_u16(data: bytes | bytearray, offset: int) -> int:
    return data[offset] | (data[offset + 1] << 8)


def _read_u32(data: bytes | bytearray, offset: int) -> int:
    return (
        data[offset]
        | (data[offset + 1] << 8)
        | (data[offset + 2] << 16)
        | (data[offset + 3] << 24)
    )


def _write_u16(data: bytearray, offset: int, value: int) -> None:
    value &= 0xFFFF
    data[offset] = value & 0xFF
    data[offset + 1] = value >> 8


def _write_u32(data: bytearray, offset: int, value: int) -> None:
    value &= 0xFFFFFFFF
    data[offset] = value & 0xFF
    data[offset + 1] = (value >> 8) & 0xFF
    data[offset + 2] = (value >> 16) & 0xFF
    data[offset + 3] = value >> 24


def _table_u16(table: bytes, index: int) -> int:
    return _read_u16(table, index * 2)


def _table_s16(table: bytes, index: int) -> int:
    return _s16(_table_u16(table, index))


@dataclass
class RngState:
    low: int
    high: int

    def normalize(self) -> None:
        self.low = _u32(self.low)
        self.high = _u32(self.high)


def next_random(rng: RngState) -> int:
    """Advance the firmware-compatible two-word generator; return 31 bits."""
    a = 0x5851F42D
    b = 0x4C957F2D

    old_low = _u32(rng.low)
    old_high = _u32(rng.high)

    accumulator = _u32(old_low * a)
    accumulator = _u32(accumulator + _u32(old_high * b))

    product = old_low * b
    product_low = product & 0xFFFFFFFF
    product_high = (product >> 32) & 0xFFFFFFFF
    new_low = _u32(product_low + 1)
    carry = 1 if new_low < product_low else 0
    new_high = _u32(accumulator + product_high + carry)

    rng.low = new_low
    rng.high = new_high
    return new_high & 0x7FFFFFFF


def render_envelope(
    state: bytearray,
    base: int,
    envelope1: bytes | None,
    envelope2: bytes | None,
) -> int:
    envelope_state = state[base]
    value = _s32(_read_u32(state, base + 0x0C))

    if envelope_state == 0:
        if state[base + 7] != 0 or state[base + 4] != 0:
            state[base] = 1

    elif envelope_state == 1:
        value = _s32(_u32(value) + _read_u16(state, base + 0x20))
        _write_u32(state, base + 0x0C, value)

        if state[base + 4] != 0:
            if value > 0x000FFFFE:
                state[base] = 4
                if value >= 0x00100000:
                    value = 0x000FFFFF
                    _write_u32(state, base + 0x0C, value)
        elif value > 0x000FFFFE:
            state[base] = 3 if state[base + 6] == 0 else 4
            if value >= 0x00100000:
                value = 0x000FFFFF
                _write_u32(state, base + 0x0C, value)

    elif envelope_state == 3:
        if state[base + 7] == 0 and (
            state[base + 4] != 0 or state[base + 0x10] == 0
        ):
            state[base] = 4

    elif envelope_state == 4:
        if state[base + 7] != 0:
            state[base] = 1
        else:
            value = _s32(_u32(value) - _read_u16(state, base + 0x22))
            _write_u32(state, base + 0x0C, value)
            if value <= 0:
                value = 0
                _write_u32(state, base + 0x0C, 0)
                state[base] = 1 if state[base + 4] != 0 else 0

    shape = state[base + 1]
    if shape not in (1, 2):
        return (_u32(value) >> 4) & 0xFFFF

    curve = envelope1 if shape == 1 else envelope2
    if curve is None:
        return 0
    if len(curve) != ENVELOPE_BYTES:
        raise ValueError(f"envelope table must be {ENVELOPE_BYTES} bytes")

    raw = _u32(value)
    index = (raw >> 10) & 0x7FF
    nxt = (index + 1) & 0x7FF
    fraction = raw & 0x3FF
    first = _table_u16(curve, index)
    second = _table_u16(curve, nxt)
    return (first + arshift32(multiply_low32(second - first, fraction), 10)) & 0xFFFF


def render_noise(state: bytearray, base: int, rng: RngState) -> int:
    count = _read_u16(state, base)
    if count != 0:
        _write_u16(state, base, count - 1)
        return _s16(_read_u16(state, base + 0x10))

    _write_u16(state, base, _read_u16(state, base + 2))
    result = _s16(next_random(rng))
    _write_u16(state, base + 0x10, result)
    return result


def advance_filter(state: bytearray, base: int, input_sample: int) -> None:
    coefficient = _read_u16(state, base + 0x0E)
    velocity = _s32(_read_u32(state, base + 0x18))

    product = multiply_low32(velocity, coefficient)
    if product < 0:
        product = _s32(_u32(product) + 0xFFFF)

    first = _s32(_read_u32(state, base + 0x10))
    first = _s32(_u32(first) + _u32(arshift32(product, 16)))
    first = max(-32767, min(32767, first))
    _write_u32(state, base + 0x10, first)

    second = _s32(_u32(input_sample) - _u32(first))
    damping = multiply_low32(velocity, _read_u16(state, base + 0x0C))
    second = _s32(_u32(second) - _u32(arshift32(damping, 10)))
    second = max(-32767, min(32767, second))
    _write_u32(state, base + 0x14, second)

    feedback = multiply_low32(second, coefficient)
    if feedback < 0:
        feedback = _s32(_u32(feedback) + 0xFFFF)

    velocity = _s32(_u32(velocity) + _u32(arshift32(feedback, 16)))
    velocity = max(-32767, min(32767, velocity))
    _write_u32(state, base + 0x18, velocity)


def render_oscillator(
    state: bytearray,
    base: int,
    waves: Mapping[int, bytes],
) -> int:
    phase = _u32(_read_u32(state, base + 4) + _read_u32(state, base + 8))
    _write_u32(state, base + 4, phase)
    current = _read_u32(state, base + 0x0C)

    if _s32(phase) > 0x00100000:
        nxt_addr = _read_u32(state, base + 0x10)
        phase = _u32(phase - 0x00100000)
        _write_u32(state, base + 4, phase)
        if nxt_addr != current:
            current = nxt_addr
            _write_u32(state, base + 0x0C, current)

    table = waves.get(current)
    if table is None:
        raise KeyError(f"missing Noise/Tone wave table at 0x{current:08x}")
    if len(table) != WAVE_BYTES:
        raise ValueError(f"wave table must be {WAVE_BYTES} bytes")

    index = (phase >> 12) & 0xFF
    nxt = (index + 1) & 0xFF
    fraction = phase & 0xFFF
    first = _table_s16(table, index)
    second = _table_s16(table, nxt)
    result = first + arshift32(multiply_low32(second - first, fraction), 12)
    return _s16(result)


def required_wave_addresses(state: bytes | bytearray) -> tuple[int, int, int, int]:
    if len(state) != STATE_BYTES:
        raise ValueError(f"state must be {STATE_BYTES} bytes")
    return (
        _read_u32(state, 0x2C + 0x0C),
        _read_u32(state, 0x2C + 0x10),
        _read_u32(state, 0xC4 + 0x0C),
        _read_u32(state, 0xC4 + 0x10),
    )


def render_block(
    state: bytearray,
    sample_count: int,
    waves: Mapping[int, bytes],
    rng: RngState,
    envelope1: bytes | None = None,
    envelope2: bytes | None = None,
) -> list[int]:
    """Render signed 16-bit samples and mutate state/RNG exactly as the oracle."""
    if len(state) != STATE_BYTES:
        raise ValueError(f"state must be {STATE_BYTES} bytes")
    if sample_count < 0:
        raise ValueError("sample_count must be non-negative")

    rng.normalize()
    output: list[int] = []
    for _ in range(sample_count):
        amplitude = render_envelope(state, 0x74, envelope1, envelope2)
        noise = render_noise(state, 0x60, rng)

        advance_filter(state, 0x9C, noise)
        advance_filter(state, 0x9C, noise)

        mix = _read_u32(state, 0xF8)
        accumulator = arshift32(multiply_low32(mix, noise), 13)

        oscillator1 = render_oscillator(state, 0x2C, waves)
        oscillator2 = render_oscillator(state, 0xC4, waves)
        oscillator_sum = arshift32(_s32(oscillator1 + oscillator2), 4)

        tonal = multiply_low32(_s32(0x00000FFF - mix), oscillator_sum)
        accumulator = _s32(
            _u32(accumulator)
            + _u32(arshift32(tonal, 9))
        )

        sample = arshift32(multiply_low32(accumulator, amplitude), 16)
        sample = arshift32(multiply_low32(sample, state[6]), 8)
        sample = max(-32768, min(32767, sample))
        output.append(sample)

    return output

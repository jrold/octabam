"""DSP56300-oriented word model for the PERKY Noise/Tone renderer.

The reference in :mod:`noise_tone_ref` intentionally mirrors the original
32-bit ARM implementation.  This file is the bridge to the 24-bit DSP56300:
it performs every 32-bit operation as two explicit 16-bit limbs and stores the
0x120-byte engine state as one byte per DSP data-memory word.

That representation is deliberately boring:

* one mutable firmware byte -> one X/Y/P data word containing 0..255;
* one waveform sample -> one signed 16-bit value in a 24-bit data word;
* u32 values -> four byte-words in little-endian order;
* 32x32 multiplication -> four 16-bit partial products;
* arithmetic right shift -> explicit sign-filled limb shifts.

The point is not to be fast in Python.  The point is that every primitive below
has a direct DSP56300 spelling and can be compared bit-for-bit with the ARM
oracle before any assembly is trusted.  No PĒRKONS firmware data or table blob
is included here; callers supply state and tables exactly as the oracle does.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from noise_tone_ref import ENVELOPE_BYTES, STATE_BYTES, WAVE_BYTES

MASK16 = 0xFFFF
MASK32 = 0xFFFFFFFF


def _s16(v: int) -> int:
    v &= MASK16
    return v - 0x10000 if v & 0x8000 else v


def _s32_int(v: int) -> int:
    v &= MASK32
    return v - 0x100000000 if v & 0x80000000 else v


@dataclass(frozen=True)
class U32:
    """A 32-bit bit pattern as the two 16-bit limbs the DSP port will use."""

    lo: int
    hi: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "lo", self.lo & MASK16)
        object.__setattr__(self, "hi", self.hi & MASK16)

    @classmethod
    def from_int(cls, value: int) -> "U32":
        value &= MASK32
        return cls(value & MASK16, value >> 16)

    def unsigned(self) -> int:
        return self.lo | (self.hi << 16)

    def signed(self) -> int:
        return _s32_int(self.unsigned())

    def negative(self) -> bool:
        return bool(self.hi & 0x8000)


def add32(a: U32, b: U32) -> U32:
    low = a.lo + b.lo
    carry = low >> 16
    return U32(low, a.hi + b.hi + carry)


def add16(a: U32, value: int) -> U32:
    return add32(a, U32(value, 0))


def sub32(a: U32, b: U32) -> U32:
    low = a.lo - b.lo
    borrow = 1 if low < 0 else 0
    return U32(low, a.hi - b.hi - borrow)


def sub16(a: U32, value: int) -> U32:
    return sub32(a, U32(value, 0))


def and32(a: U32, value: int) -> U32:
    return U32(a.lo & value, a.hi & (value >> 16))


def arshift32_words(a: U32, shift: int) -> U32:
    """Signed 32-bit arithmetic shift using only 16-bit limb operations."""
    if not 0 <= shift <= 31:
        raise ValueError("shift must be 0..31")
    if shift == 0:
        return a
    sign = 0xFFFF if a.negative() else 0
    signed_hi = _s16(a.hi)
    if shift < 16:
        carry_mask = (1 << shift) - 1
        lo = (a.lo >> shift) | ((a.hi & carry_mask) << (16 - shift))
        hi = signed_hi >> shift
        return U32(lo, hi)
    lo = signed_hi >> (shift - 16)
    return U32(lo, sign)


def mul_low32_words(a: U32, b: U32) -> U32:
    """Low 32 bits of a 32x32 multiply, decomposed into 16x16 products."""
    p0 = a.lo * b.lo
    middle = a.lo * b.hi + a.hi * b.lo + (p0 >> 16)
    return U32(p0, middle)


def mul_full64_words(a: U32, b: U32) -> tuple[U32, U32]:
    """Unsigned 32x32 -> (low32, high32) via four 16x16 partial products."""
    p0 = a.lo * b.lo
    p1 = a.lo * b.hi
    p2 = a.hi * b.lo
    p3 = a.hi * b.hi

    r0 = p0 & MASK16
    t1 = (p0 >> 16) + p1 + p2
    r1 = t1 & MASK16
    t2 = (t1 >> 16) + p3
    r2 = t2 & MASK16
    r3 = (t2 >> 16) & MASK16
    return U32(r0, r1), U32(r2, r3)


def signed_gt(a: U32, value: int) -> bool:
    b = U32.from_int(value)
    ah, bh = _s16(a.hi), _s16(b.hi)
    return ah > bh or (ah == bh and a.lo > b.lo)


def signed_le_zero(a: U32) -> bool:
    return a.negative() or (a.hi == 0 and a.lo == 0)


def clamp_s32_to_s16ish(a: U32, lo: int, hi: int) -> U32:
    """Clamp the signed value to the small ranges used by the filter."""
    s = a.signed()
    if s < lo:
        return U32.from_int(lo)
    if s > hi:
        return U32.from_int(hi)
    return a


class WordState:
    """0x120 firmware bytes represented as 0x120 DSP data words."""

    def __init__(self, raw: bytes | bytearray):
        if len(raw) != STATE_BYTES:
            raise ValueError(f"state must be {STATE_BYTES} bytes")
        self.w = [int(x) for x in raw]

    def byte(self, off: int) -> int:
        return self.w[off] & 0xFF

    def set_byte(self, off: int, value: int) -> None:
        self.w[off] = value & 0xFF

    def u16(self, off: int) -> int:
        return self.byte(off) | (self.byte(off + 1) << 8)

    def set_u16(self, off: int, value: int) -> None:
        value &= MASK16
        self.set_byte(off, value)
        self.set_byte(off + 1, value >> 8)

    def u32(self, off: int) -> U32:
        return U32(self.u16(off), self.u16(off + 2))

    def set_u32(self, off: int, value: U32 | int) -> None:
        value = value if isinstance(value, U32) else U32.from_int(value)
        self.set_u16(off, value.lo)
        self.set_u16(off + 2, value.hi)

    def bytes(self) -> bytes:
        return bytes(x & 0xFF for x in self.w)


@dataclass
class WordRng:
    low: U32
    high: U32

    @classmethod
    def from_ints(cls, low: int, high: int) -> "WordRng":
        return cls(U32.from_int(low), U32.from_int(high))


def next_random(rng: WordRng) -> U32:
    """Exact firmware two-word RNG using only 16-bit-limb multiplies/adds."""
    a = U32.from_int(0x5851F42D)
    b = U32.from_int(0x4C957F2D)

    accumulator = add32(mul_low32_words(rng.low, a),
                        mul_low32_words(rng.high, b))
    product_low, product_high = mul_full64_words(rng.low, b)
    new_low = add16(product_low, 1)
    carry = 1 if product_low.lo == 0xFFFF and product_low.hi == 0xFFFF else 0
    new_high = add32(add32(accumulator, product_high), U32(carry, 0))

    rng.low = new_low
    rng.high = new_high
    return U32(new_high.lo, new_high.hi & 0x7FFF)


def _table_u16(table: bytes, index: int) -> int:
    off = index * 2
    return table[off] | (table[off + 1] << 8)


def _table_s16(table: bytes, index: int) -> int:
    return _s16(_table_u16(table, index))


def render_envelope(
    state: WordState,
    base: int,
    envelope1: bytes | None,
    envelope2: bytes | None,
) -> int:
    envelope_state = state.byte(base)
    value = state.u32(base + 0x0C)

    if envelope_state == 0:
        if state.byte(base + 7) != 0 or state.byte(base + 4) != 0:
            state.set_byte(base, 1)

    elif envelope_state == 1:
        value = add16(value, state.u16(base + 0x20))
        state.set_u32(base + 0x0C, value)

        if state.byte(base + 4) != 0:
            if signed_gt(value, 0x000FFFFE):
                state.set_byte(base, 4)
                if not signed_gt(U32.from_int(0x00100000), value.unsigned()):
                    value = U32.from_int(0x000FFFFF)
                    state.set_u32(base + 0x0C, value)
        elif signed_gt(value, 0x000FFFFE):
            state.set_byte(base, 3 if state.byte(base + 6) == 0 else 4)
            if not signed_gt(U32.from_int(0x00100000), value.unsigned()):
                value = U32.from_int(0x000FFFFF)
                state.set_u32(base + 0x0C, value)

    elif envelope_state == 3:
        if state.byte(base + 7) == 0 and (
            state.byte(base + 4) != 0 or state.u32(base + 0x10).unsigned() == 0
        ):
            state.set_byte(base, 4)

    elif envelope_state == 4:
        if state.byte(base + 7) != 0:
            state.set_byte(base, 1)
        else:
            value = sub16(value, state.u16(base + 0x22))
            state.set_u32(base + 0x0C, value)
            if signed_le_zero(value):
                value = U32(0, 0)
                state.set_u32(base + 0x0C, value)
                state.set_byte(base, 1 if state.byte(base + 4) != 0 else 0)

    shape = state.byte(base + 1)
    if shape not in (1, 2):
        return (value.unsigned() >> 4) & MASK16

    curve = envelope1 if shape == 1 else envelope2
    if curve is None:
        return 0
    if len(curve) != ENVELOPE_BYTES:
        raise ValueError(f"envelope table must be {ENVELOPE_BYTES} bytes")

    raw = value.unsigned()
    index = (raw >> 10) & 0x7FF
    nxt = (index + 1) & 0x7FF
    fraction = raw & 0x3FF
    first = _table_u16(curve, index)
    second = _table_u16(curve, nxt)
    delta = U32.from_int(second - first)
    interp = arshift32_words(mul_low32_words(delta, U32(fraction, 0)), 10).signed()
    return (first + interp) & MASK16


def render_noise(state: WordState, base: int, rng: WordRng) -> int:
    count = state.u16(base)
    if count != 0:
        state.set_u16(base, count - 1)
        return _s16(state.u16(base + 0x10))

    state.set_u16(base, state.u16(base + 2))
    result = _s16(next_random(rng).lo)
    state.set_u16(base + 0x10, result)
    return result


def advance_filter(state: WordState, base: int, input_sample: int) -> None:
    coefficient = state.u16(base + 0x0E)
    velocity = state.u32(base + 0x18)

    product = mul_low32_words(velocity, U32(coefficient, 0))
    if product.negative():
        product = add16(product, 0xFFFF)

    first = add32(state.u32(base + 0x10), arshift32_words(product, 16))
    first = clamp_s32_to_s16ish(first, -32767, 32767)
    state.set_u32(base + 0x10, first)

    second = sub32(U32.from_int(input_sample), first)
    damping = mul_low32_words(velocity, U32(state.u16(base + 0x0C), 0))
    second = sub32(second, arshift32_words(damping, 10))
    second = clamp_s32_to_s16ish(second, -32767, 32767)
    state.set_u32(base + 0x14, second)

    feedback = mul_low32_words(second, U32(coefficient, 0))
    if feedback.negative():
        feedback = add16(feedback, 0xFFFF)

    velocity = add32(velocity, arshift32_words(feedback, 16))
    velocity = clamp_s32_to_s16ish(velocity, -32767, 32767)
    state.set_u32(base + 0x18, velocity)


def render_oscillator(state: WordState, base: int, waves: Mapping[int, bytes]) -> int:
    phase = add32(state.u32(base + 4), state.u32(base + 8))
    state.set_u32(base + 4, phase)
    current = state.u32(base + 0x0C)

    if signed_gt(phase, 0x00100000):
        nxt_addr = state.u32(base + 0x10)
        phase = sub32(phase, U32.from_int(0x00100000))
        state.set_u32(base + 4, phase)
        if nxt_addr != current:
            current = nxt_addr
            state.set_u32(base + 0x0C, current)

    table = waves.get(current.unsigned())
    if table is None:
        raise KeyError(f"missing Noise/Tone wave table at 0x{current.unsigned():08x}")
    if len(table) != WAVE_BYTES:
        raise ValueError(f"wave table must be {WAVE_BYTES} bytes")

    raw_phase = phase.unsigned()
    index = (raw_phase >> 12) & 0xFF
    nxt = (index + 1) & 0xFF
    fraction = raw_phase & 0xFFF
    first = _table_s16(table, index)
    second = _table_s16(table, nxt)
    delta = U32.from_int(second - first)
    interp = arshift32_words(mul_low32_words(delta, U32(fraction, 0)), 12).signed()
    return _s16(first + interp)


def render_block(
    raw_state: bytearray,
    sample_count: int,
    waves: Mapping[int, bytes],
    rng: WordRng,
    envelope1: bytes | None = None,
    envelope2: bytes | None = None,
) -> tuple[list[int], bytes]:
    """Render through the DSP representation; return samples and final bytes."""
    if sample_count < 0:
        raise ValueError("sample_count must be non-negative")
    state = WordState(raw_state)
    output: list[int] = []

    for _ in range(sample_count):
        amplitude = render_envelope(state, 0x74, envelope1, envelope2)
        noise = render_noise(state, 0x60, rng)

        advance_filter(state, 0x9C, noise)
        advance_filter(state, 0x9C, noise)

        mix = state.u32(0xF8)
        accumulator = arshift32_words(
            mul_low32_words(mix, U32.from_int(noise)), 13
        )

        oscillator1 = render_oscillator(state, 0x2C, waves)
        oscillator2 = render_oscillator(state, 0xC4, waves)
        oscillator_sum = arshift32_words(
            U32.from_int(oscillator1 + oscillator2), 4
        )

        tonal_mix = sub32(U32.from_int(0x00000FFF), mix)
        tonal = mul_low32_words(tonal_mix, oscillator_sum)
        accumulator = add32(accumulator, arshift32_words(tonal, 9))

        sample = arshift32_words(
            mul_low32_words(accumulator, U32(amplitude, 0)), 16
        )
        sample = arshift32_words(
            mul_low32_words(sample, U32(state.byte(6), 0)), 8
        ).signed()
        sample = max(-32768, min(32767, sample))
        output.append(sample)

    return output, state.bytes()

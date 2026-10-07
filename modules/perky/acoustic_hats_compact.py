"""Compact exact host model for PĒRKONS v1.2.1 Acoustic Hats.

The original renderer object is only 0x10c bytes, but the closed/open/ride
samples are external firmware assets.  Keep those samples external: the live
renderer state is 35 16-bit words plus the firmware-global held sample.
"""
from __future__ import annotations

from dataclasses import dataclass
import struct

import resonator_compact as c

WORDS = 35
VELOCITY = 0
MUTE = 1
AMP_ENV = 2
INDEX = AMP_ENV + c.ENV_WORDS       # u32 sample index
FRACTION = INDEX + 2                # u32 interpolation phase remainder
INCREMENT = FRACTION + 2            # u32 phase increment
SHIFT = INCREMENT + 2               # byte in ARM, word here
MASK = SHIFT + 1                    # u32 phase mask
HOLD_RELOAD = MASK + 2              # u32 sample-and-hold reload
HOLD = HOLD_RELOAD + 2               # u32 remaining hold
SAMPLE_ADDRESS = HOLD + 2            # u32 external asset identity
SAMPLE_LENGTH = SAMPLE_ADDRESS + 2   # u32 signed16 samples
FILTER_INT = SAMPLE_LENGTH + 2       # u32/s32 integer history
FILTER_FLOAT = FILTER_INT + 2        # IEEE754 single bits
FILTER_DIRTY = FILTER_FLOAT + 2      # byte flag
assert FILTER_DIRTY + 1 == WORDS


def _f32(value: float) -> float:
    return struct.unpack('<f', struct.pack('<f', float(value)))[0]


def _float_from_bits(bits: int) -> float:
    return struct.unpack('<f', struct.pack('<I', bits & c.MASK32))[0]


def _float_bits(value: float) -> int:
    return struct.unpack('<I', struct.pack('<f', _f32(value)))[0]


DECAY = _float_from_bits(0x3F7AE148)  # 0.980000019073486328125f


def _sample(sample: bytes, index: int) -> int:
    off = int(index) * 2
    if off < 0 or off + 1 >= len(sample):
        return 0
    return c.s16(sample[off] | (sample[off + 1] << 8))


def _sat16(value: int) -> int:
    return max(-32768, min(32767, int(value)))


@dataclass
class AcousticHats:
    words: list[int]

    def __post_init__(self) -> None:
        if len(self.words) != WORDS:
            raise ValueError(f'Acoustic Hats state must be {WORDS} words')
        self.words = [int(v) & c.MASK16 for v in self.words]

    @classmethod
    def from_arm(cls, raw: bytes | bytearray) -> 'AcousticHats':
        if len(raw) != 0x10C:
            raise ValueError('Acoustic Hats ARM state must be 0x10c bytes')
        w = [0] * WORDS
        w[VELOCITY] = raw[6]
        w[MUTE] = raw[0xB8]
        c.copy_env_from_arm(w, AMP_ENV, raw, 0x74)
        for dst, off in (
            (INDEX, 0xC4),
            (FRACTION, 0xC8),
            (INCREMENT, 0xCC),
            (MASK, 0xD4),
            (HOLD_RELOAD, 0xD8),
            (HOLD, 0xDC),
            (SAMPLE_ADDRESS, 0xF8),
            (SAMPLE_LENGTH, 0xFC),
            (FILTER_INT, 0x100),
            (FILTER_FLOAT, 0x104),
        ):
            c.set_u32(w, dst, c.u32(raw, off))
        w[SHIFT] = raw[0xD0]
        w[FILTER_DIRTY] = raw[0x108]
        return cls(w)

    def apply_to_arm(self, template: bytes | bytearray) -> bytes:
        if len(template) != 0x10C:
            raise ValueError('Acoustic Hats template must be 0x10c bytes')
        raw = bytearray(template)
        w = self.words
        raw[6] = w[VELOCITY] & 0xFF
        raw[0xB8] = w[MUTE] & 0xFF
        c.copy_env_to_arm(w, AMP_ENV, raw, 0x74)
        for src, off in (
            (INDEX, 0xC4),
            (FRACTION, 0xC8),
            (INCREMENT, 0xCC),
            (MASK, 0xD4),
            (HOLD_RELOAD, 0xD8),
            (HOLD, 0xDC),
            (SAMPLE_ADDRESS, 0xF8),
            (SAMPLE_LENGTH, 0xFC),
            (FILTER_INT, 0x100),
            (FILTER_FLOAT, 0x104),
        ):
            c.put32(raw, off, c.get_u32(w, src))
        raw[0xD0] = w[SHIFT] & 0xFF
        raw[0x108] = w[FILTER_DIRTY] & 0xFF
        return bytes(raw)

    def render(self, n: int, sample: bytes,
               envelope1: bytes | None, envelope2: bytes | None,
               global_sample: list[int]) -> list[int]:
        """Render ``n`` mono samples.

        ``sample`` is the selected closed/open/ride signed16 asset beginning at
        this engine state's SAMPLE_ADDRESS. ``global_sample`` is a one-element
        mutable list mirroring firmware global 0x20007598.
        """
        if len(global_sample) != 1:
            raise ValueError('global_sample must be a one-element mutable list')
        w = self.words
        length = c.get_u32(w, SAMPLE_LENGTH)
        if length * 2 > len(sample):
            raise ValueError('sample asset is shorter than state sample length')

        out: list[int] = []
        for _ in range(n):
            amplitude = c.render_envelope(w, AMP_ENV, envelope1, envelope2)
            index = c.get_u32(w, INDEX)
            if length == 0 or length <= index:
                out.append(0)
                continue

            next_index = (index + 1) & c.MASK32
            nxt = _sample(sample, next_index) if length > next_index else 0
            fraction = c.get_u32(w, FRACTION)
            mask = c.get_u32(w, MASK)
            shift = w[SHIFT] & 0xFF
            hold = c.get_u32(w, HOLD)

            if hold != 0:
                hold = (hold - 1) & c.MASK32
                interpolated = c.s32(global_sample[0])
            else:
                current = _sample(sample, index)
                weighted_next = c.mullo(c.s32(fraction), nxt)
                complement = c.s32((mask - fraction) & c.MASK32)
                weighted_current = c.mullo(complement, current)
                interpolated = c.asr(
                    c.add(weighted_next, weighted_current), shift + 1
                )
                global_sample[0] = interpolated
                hold = c.get_u32(w, HOLD_RELOAD)

            envelope_scaled = c.asr(c.mullo(interpolated, amplitude), 15)
            c.set_u32(w, HOLD, hold)

            advanced = (
                c.get_u32(w, FRACTION) + c.get_u32(w, INCREMENT)
            ) & c.MASK32
            advance = advanced >> shift
            c.set_u32(w, INDEX, (index + advance) & c.MASK32)
            c.set_u32(w, FRACTION, advanced & mask)

            if w[FILTER_DIRTY] & 0xFF:
                previous = _f32(float(c.s32(c.get_u32(w, FILTER_INT))))
                w[FILTER_DIRTY] = 0
            else:
                previous = _float_from_bits(c.get_u32(w, FILTER_FLOAT))

            # Preserve the M7's separate single-precision VCVT/VMUL/VADD
            # operations. The summed branch intentionally uses the *previous*
            # value, not decayed; that is what the v1.2.1 renderer does.
            input_f = _f32(float(envelope_scaled))
            decayed = _f32(previous * DECAY)
            summed = _f32(input_f + previous)
            c.set_u32(w, FILTER_FLOAT, _float_bits(decayed))
            filtered = int(summed)  # C++ float -> int truncates toward zero
            c.set_u32(w, FILTER_INT, filtered)

            if w[MUTE] & 0xFF:
                out.append(0)
                continue
            value = c.asr(c.mullo(filtered, w[VELOCITY] & 0xFF), 8)
            out.append(_sat16(value))

        return out

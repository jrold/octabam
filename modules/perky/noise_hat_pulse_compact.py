"""Exact compact host model for PĒRKONS v1.2.1 Noise Hat Pulse Stack.

The ARM object has an important alias: the u16 second-filter input at +0x136
is the high half of the local u32 LCG state at +0x134.  It is therefore not an
independent state field.  Keeping that alias explicit gives a 59-word compact
state and makes an LCG update change the second-filter input on the same sample,
just as the native renderer does.
"""
from __future__ import annotations

from dataclasses import dataclass

import resonator_compact as c

FILTER_WORDS = 8
F_DAMP = 0
F_COEFF = 1
F_FIRST = 2
F_SECOND = 4
F_VELOCITY = 6

PULSE_STACK_WORDS = 59
PS_VELOCITY = 0
PS_ENV = 1
PS_FILTER_A = PS_ENV + c.ENV_WORDS              # 12 .. 19
PS_FILTER_B = PS_FILTER_A + FILTER_WORDS        # 20 .. 27
PS_PHASES = PS_FILTER_B + FILTER_WORDS          # 28 .. 39 (6 x u32)
PS_INCREMENTS = PS_PHASES + 12                  # 40 .. 51 (6 x u32)
PS_RANDOM_PHASE = PS_INCREMENTS + 12            # 52 .. 53
PS_RANDOM_INCREMENT = PS_RANDOM_PHASE + 2       # 54 .. 55
PS_RANDOM = PS_RANDOM_INCREMENT + 2             # 56 .. 57
PS_SECOND_INPUT = PS_RANDOM + 1                 # 57, alias of RNG high u16
PS_MIX = PS_RANDOM + 2                          # 58
assert PS_MIX + 1 == PULSE_STACK_WORDS

PS_PHASE_OFFSETS = (0x100, 0x0FC, 0x104, 0x108, 0x10C, 0x110)
PS_INCREMENT_OFFSETS = (0x11C, 0x118, 0x120, 0x124, 0x128, 0x12C)


def _sat_filter(value: int) -> int:
    return max(-32767, min(32767, value))


def _sat16(value: int) -> int:
    return max(-32768, min(32767, value))


def _filter_from_arm(words: list[int], dst: int,
                     raw: bytes | bytearray, src: int) -> None:
    words[dst + F_DAMP] = c.u16(raw, src + 0x0C)
    words[dst + F_COEFF] = c.u16(raw, src + 0x0E)
    c.set_u32(words, dst + F_FIRST, c.u32(raw, src + 0x10))
    c.set_u32(words, dst + F_SECOND, c.u32(raw, src + 0x14))
    c.set_u32(words, dst + F_VELOCITY, c.u32(raw, src + 0x18))


def _filter_to_arm(words: list[int], src: int,
                   raw: bytearray, dst: int) -> None:
    c.put16(raw, dst + 0x0C, words[src + F_DAMP])
    c.put16(raw, dst + 0x0E, words[src + F_COEFF])
    c.put32(raw, dst + 0x10, c.get_u32(words, src + F_FIRST))
    c.put32(raw, dst + 0x14, c.get_u32(words, src + F_SECOND))
    c.put32(raw, dst + 0x18, c.get_u32(words, src + F_VELOCITY))


def _advance_filter(words: list[int], base: int, input_value: int) -> None:
    coefficient = words[base + F_COEFF]
    velocity = c.s32(c.get_u32(words, base + F_VELOCITY))

    product = c.mullo(velocity, coefficient)
    if product < 0:
        product = c.s32(c.u32bits(product) + 0xFFFF)

    first = c.add(
        c.s32(c.get_u32(words, base + F_FIRST)),
        c.asr(product, 16),
    )
    first = _sat_filter(first)
    c.set_u32(words, base + F_FIRST, first)

    second = c.sub(input_value, first)
    second = c.sub(
        second,
        c.asr(c.mullo(velocity, words[base + F_DAMP]), 10),
    )
    second = _sat_filter(second)
    c.set_u32(words, base + F_SECOND, second)

    feedback = c.mullo(second, coefficient)
    if feedback < 0:
        feedback = c.s32(c.u32bits(feedback) + 0xFFFF)

    velocity = c.add(velocity, c.asr(feedback, 16))
    velocity = _sat_filter(velocity)
    c.set_u32(words, base + F_VELOCITY, velocity)


@dataclass
class NoiseHatPulseStack:
    """Firmware mode 2 Pulse Stack renderer with exact ARM aliasing."""

    words: list[int]

    def __post_init__(self) -> None:
        if len(self.words) != PULSE_STACK_WORDS:
            raise ValueError(
                f'Noise Hat Pulse Stack state must be '
                f'{PULSE_STACK_WORDS} words'
            )
        self.words = [int(v) & c.MASK16 for v in self.words]

    @classmethod
    def from_arm(cls, raw: bytes | bytearray) -> 'NoiseHatPulseStack':
        if len(raw) != 0x160:
            raise ValueError('Noise Hat Pulse Stack ARM state must be 0x160 bytes')
        w = [0] * PULSE_STACK_WORDS
        w[PS_VELOCITY] = raw[6]
        c.copy_env_from_arm(w, PS_ENV, raw, 0x74)
        _filter_from_arm(w, PS_FILTER_A, raw, 0xC4)
        _filter_from_arm(w, PS_FILTER_B, raw, 0xE0)

        for i, off in enumerate(PS_PHASE_OFFSETS):
            c.set_u32(w, PS_PHASES + 2 * i, c.u32(raw, off))
        for i, off in enumerate(PS_INCREMENT_OFFSETS):
            c.set_u32(w, PS_INCREMENTS + 2 * i, c.u32(raw, off))
        c.set_u32(w, PS_RANDOM_PHASE, c.u32(raw, 0x114))
        c.set_u32(w, PS_RANDOM_INCREMENT, c.u32(raw, 0x130))
        c.set_u32(w, PS_RANDOM, c.u32(raw, 0x134))
        # +0x136 is already represented by PS_RANDOM+1.
        if w[PS_SECOND_INPUT] != c.u16(raw, 0x136):
            raise AssertionError('Pulse Stack RNG/input alias is inconsistent')
        w[PS_MIX] = c.u16(raw, 0x138)
        return cls(w)

    def apply_to_arm(self, template: bytes | bytearray) -> bytes:
        if len(template) != 0x160:
            raise ValueError('Noise Hat Pulse Stack template must be 0x160 bytes')
        raw = bytearray(template)
        w = self.words
        raw[6] = w[PS_VELOCITY] & 0xFF
        c.copy_env_to_arm(w, PS_ENV, raw, 0x74)
        _filter_to_arm(w, PS_FILTER_A, raw, 0xC4)
        _filter_to_arm(w, PS_FILTER_B, raw, 0xE0)

        for i, off in enumerate(PS_PHASE_OFFSETS):
            c.put32(raw, off, c.get_u32(w, PS_PHASES + 2 * i))
        for i, off in enumerate(PS_INCREMENT_OFFSETS):
            c.put32(raw, off, c.get_u32(w, PS_INCREMENTS + 2 * i))
        c.put32(raw, 0x114, c.get_u32(w, PS_RANDOM_PHASE))
        c.put32(raw, 0x130, c.get_u32(w, PS_RANDOM_INCREMENT))
        c.put32(raw, 0x134, c.get_u32(w, PS_RANDOM))
        # Writing the RNG also writes +0x136 because it is the same storage.
        c.put16(raw, 0x138, w[PS_MIX])
        return bytes(raw)

    def render(self, n: int, envelope1: bytes | None,
               envelope2: bytes | None) -> list[int]:
        w = self.words
        out: list[int] = []

        for _ in range(n):
            old_phase = c.get_u32(w, PS_RANDOM_PHASE)
            random_phase = (
                old_phase + c.get_u32(w, PS_RANDOM_INCREMENT)
            ) & c.MASK32
            c.set_u32(w, PS_RANDOM_PHASE, random_phase)
            if random_phase < old_phase:
                random_value = (
                    c.get_u32(w, PS_RANDOM) * 0x0019660D
                    + 0x3C6EF35F
                ) & c.MASK32
                c.set_u32(w, PS_RANDOM, random_value)

            sign_count = 0
            for i in range(6):
                phase_off = PS_PHASES + 2 * i
                increment_off = PS_INCREMENTS + 2 * i
                phase = (
                    c.get_u32(w, phase_off)
                    + c.get_u32(w, increment_off)
                ) & c.MASK32
                c.set_u32(w, phase_off, phase)
                sign_count += phase >> 31

            pulse_stack = c.mullo(sign_count - 3, 0x1555)
            _advance_filter(w, PS_FILTER_A, pulse_stack)

            # Exact ARM alias: high16(local RNG) is the second-filter input.
            second_input = w[PS_SECOND_INPUT] - 0x8000
            previous = c.s32(c.get_u32(w, PS_FILTER_A + F_VELOCITY))
            _advance_filter(w, PS_FILTER_B, second_input)
            target = c.s32(c.get_u32(w, PS_FILTER_B + F_SECOND))

            mix = c.s16(w[PS_MIX])
            delta = c.sub(target, previous)
            interpolation = c.asr(c.mullo(mix, delta), 15)
            filtered = c.add(previous, interpolation)

            amplitude = c.render_envelope(
                w, PS_ENV, envelope1, envelope2
            )
            value = c.asr(c.mullo(filtered, amplitude), 16)
            value = c.asr(c.mullo(value, w[PS_VELOCITY] & 0xFF), 8)
            out.append(_sat16(value))

        return out

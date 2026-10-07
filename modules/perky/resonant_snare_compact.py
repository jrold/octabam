"""Compact exact v1.2.1 Resonant Snare renderer.

The 0x1d4-byte ARM object reduces to 101 16-bit words: one common envelope,
noise sample/hold, three resonators, four multiplicative decay ramps and two
mix coefficients.  Rendering mirrors NativeV121ResonantSnare.cpp exactly.
"""
from __future__ import annotations

from dataclasses import dataclass

import resonator_compact as c

WORDS = 101
VELOCITY = 0
AMP_ENV = 1
NOISE = AMP_ENV + c.ENV_WORDS
RES1 = NOISE + 3
RES2 = RES1 + c.RESONATOR_WORDS
RES3 = RES2 + c.RESONATOR_WORDS
DECAY_A = RES3 + c.RESONATOR_WORDS
DECAY_B = DECAY_A + c.DECAY_WORDS
DECAY_C = DECAY_B + c.DECAY_WORDS
DECAY_D = DECAY_C + c.DECAY_WORDS
MIX_SECOND = DECAY_D + c.DECAY_WORDS  # ARM 0x168, u32
MIX_FIRST = MIX_SECOND + 2             # ARM 0x164, u32
assert MIX_FIRST + 2 == WORDS

RES1_MAP = dict(
    dirty=0xF8, pitch_a=0xFA, pitch_b=0xFC,
    coeff_b=0x104, coeff_a=0x108, mod=0x100,
    bypass=0x10C, position=0x110, velocity=0x114,
)
RES2_MAP = dict(
    dirty=0x11C, pitch_a=0x11E, pitch_b=0x120,
    coeff_b=0x128, coeff_a=0x12C, mod=0x124,
    bypass=0x130, position=0x134, velocity=0x138,
)
RES3_MAP = dict(
    dirty=0x140, pitch_a=0x142, pitch_b=0x144,
    coeff_b=0x14C, coeff_a=0x150, mod=0x148,
    bypass=0x154, position=0x158, velocity=0x15C,
)


def _decay_map(base: int):
    return dict(mul_off=base, count_off=base + 4, value_off=base + 8,
                sign_off=base + 12, min_off=base + 16)


@dataclass
class ResonantSnare:
    words: list[int]

    def __post_init__(self):
        if len(self.words) != WORDS:
            raise ValueError(f"Resonant Snare compact state must be {WORDS} words")
        self.words = [int(v) & c.MASK16 for v in self.words]

    @classmethod
    def from_arm(cls, raw: bytes | bytearray) -> "ResonantSnare":
        if len(raw) != 0x1D4:
            raise ValueError("Resonant Snare state must be 0x1d4 bytes")
        w = [0] * WORDS
        w[VELOCITY] = raw[6]
        c.copy_env_from_arm(w, AMP_ENV, raw, 0x74)
        c.copy_noise_from_arm(w, NOISE, raw)
        c.copy_resonator_from_arm(w, RES1, raw, **RES1_MAP)
        c.copy_resonator_from_arm(w, RES2, raw, **RES2_MAP)
        c.copy_resonator_from_arm(w, RES3, raw, **RES3_MAP)
        c.copy_decay_from_arm(w, DECAY_A, raw, **_decay_map(0x174))
        c.copy_decay_from_arm(w, DECAY_B, raw, **_decay_map(0x18C))
        c.copy_decay_from_arm(w, DECAY_C, raw, **_decay_map(0x1A4))
        c.copy_decay_from_arm(w, DECAY_D, raw, **_decay_map(0x1BC))
        c.set_u32(w, MIX_SECOND, c.u32(raw, 0x168))
        c.set_u32(w, MIX_FIRST, c.u32(raw, 0x164))
        return cls(w)

    def apply_to_arm(self, template: bytes | bytearray) -> bytes:
        if len(template) != 0x1D4:
            raise ValueError("Resonant Snare template must be 0x1d4 bytes")
        raw = bytearray(template)
        raw[6] = self.words[VELOCITY] & 0xFF
        c.copy_env_to_arm(self.words, AMP_ENV, raw, 0x74)
        c.copy_noise_to_arm(self.words, NOISE, raw)
        c.copy_resonator_to_arm(self.words, RES1, raw, **RES1_MAP)
        c.copy_resonator_to_arm(self.words, RES2, raw, **RES2_MAP)
        c.copy_resonator_to_arm(self.words, RES3, raw, **RES3_MAP)
        c.copy_decay_to_arm(self.words, DECAY_A, raw, **_decay_map(0x174))
        c.copy_decay_to_arm(self.words, DECAY_B, raw, **_decay_map(0x18C))
        c.copy_decay_to_arm(self.words, DECAY_C, raw, **_decay_map(0x1A4))
        c.copy_decay_to_arm(self.words, DECAY_D, raw, **_decay_map(0x1BC))
        c.put32(raw, 0x168, c.get_u32(self.words, MIX_SECOND))
        c.put32(raw, 0x164, c.get_u32(self.words, MIX_FIRST))
        return bytes(raw)

    def render(self, sample_count: int, envelope1: bytes | None,
               envelope2: bytes | None, interpolation_a: bytes,
               interpolation_b: bytes, rng: list[int]) -> list[int]:
        if len(rng) != 2:
            raise ValueError("rng must be [low32, high32]")
        w = self.words
        out: list[int] = []
        for _ in range(sample_count):
            c.render_envelope(w, AMP_ENV, envelope1, envelope2)

            a = c.decay_level(w, DECAY_A)
            b = c.decay_level(w, DECAY_B, add_constant=True, constant=0x0A3D)
            first_drive = c.add(c.s32(a), c.s32(b))
            _, velocity1 = c.resonator(
                w, RES1, first_drive, interpolation_a, interpolation_b
            )

            cv = c.decay_level(w, DECAY_C, add_constant=True, constant=0x3333)
            first_mix = c.add(velocity1, c.asr(first_drive, 4))
            _, velocity2 = c.resonator(
                w, RES2, c.s32(cv), interpolation_a, interpolation_b
            )
            second_mix = c.add(velocity2, c.asr(c.s32(cv), 4))

            d = c.decay_level(w, DECAY_D)
            random_value = c.render_noise(w, NOISE, rng)
            _, velocity3 = c.resonator(
                w, RES3, random_value, interpolation_a, interpolation_b
            )

            term1 = c.asr(c.mullo(
                second_mix, c.s32(c.get_u32(w, MIX_SECOND))
            ), 15)
            term2 = c.asr(c.mullo(
                c.s32(c.get_u32(w, MIX_FIRST)), first_mix
            ), 15)
            term3 = c.asr(c.mullo(velocity3, c.s32(d)), 15)
            mixed = c.add(c.add(term1, term2), term3)
            out.append(c.velocity_scale(w[VELOCITY], c.add(mixed, mixed)))
        return out

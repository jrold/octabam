"""Compact exact v1.2.1 Resonant Bass renderer.

The 0x178-byte ARM object is reduced to 88 DSP words: one shared envelope,
noise sample/hold, two resonators and four multiplicative decay ramps.  All
per-sample arithmetic mirrors NativeV121ResonantBass.cpp modulo 2^32.
"""
from __future__ import annotations

from dataclasses import dataclass

import resonator_compact as c

WORDS = 88
VELOCITY = 0
AMP_ENV = 1                   # 11
NOISE = AMP_ENV + c.ENV_WORDS # 12..14
TONE_RES = NOISE + 3          # 15..28
PITCH = TONE_RES + c.RESONATOR_WORDS  # 29
RESONATOR_STATE = PITCH + 1   # 30..31 u32
RESONATOR_COEFF = RESONATOR_STATE + 2 # 32..33 u32
DECAY_A = RESONATOR_COEFF + 2 # 34..43
DECAY_B = DECAY_A + c.DECAY_WORDS     # 44..53
DECAY_C = DECAY_B + c.DECAY_WORDS     # 54..63
DECAY_LEVEL = DECAY_C + c.DECAY_WORDS # 64..73
NOISE_RES = DECAY_LEVEL + c.DECAY_WORDS # 74..87
assert NOISE_RES + c.RESONATOR_WORDS == WORDS

TONE_MAP = dict(
    dirty=0xC4, pitch_a=0xC6, pitch_b=0xC8,
    coeff_b=0xD0, coeff_a=0xD4, mod=0xCC,
    bypass=0xD8, position=0xDC, velocity=0xE0,
)
NOISE_MAP = dict(
    dirty=0x158, pitch_a=0x15A, pitch_b=0x15C,
    coeff_b=0x164, coeff_a=0x168, mod=0x160,
    bypass=0x16C, position=0x170, velocity=0x174,
)


def _decay_map(base: int):
    return dict(mul_off=base, count_off=base + 4, value_off=base + 8,
                sign_off=base + 12, min_off=base + 16)


@dataclass
class ResonantBass:
    words: list[int]

    def __post_init__(self):
        if len(self.words) != WORDS:
            raise ValueError(f"Resonant Bass compact state must be {WORDS} words")
        self.words = [int(v) & c.MASK16 for v in self.words]

    @classmethod
    def from_arm(cls, raw: bytes | bytearray) -> "ResonantBass":
        if len(raw) != 0x178:
            raise ValueError("Resonant Bass state must be 0x178 bytes")
        w = [0] * WORDS
        w[VELOCITY] = raw[6]
        c.copy_env_from_arm(w, AMP_ENV, raw, 0x74)
        c.copy_noise_from_arm(w, NOISE, raw)
        c.copy_resonator_from_arm(w, TONE_RES, raw, **TONE_MAP)
        w[PITCH] = c.u16(raw, 0xF0)
        c.set_u32(w, RESONATOR_STATE, c.u32(raw, 0xE8))
        c.set_u32(w, RESONATOR_COEFF, c.u32(raw, 0xEC))
        c.copy_decay_from_arm(w, DECAY_A, raw, **_decay_map(0xF8))
        c.copy_decay_from_arm(w, DECAY_B, raw, **_decay_map(0x110))
        c.copy_decay_from_arm(w, DECAY_C, raw, **_decay_map(0x128))
        c.copy_decay_from_arm(w, DECAY_LEVEL, raw, **_decay_map(0x144))
        c.copy_resonator_from_arm(w, NOISE_RES, raw, **NOISE_MAP)
        return cls(w)

    def apply_to_arm(self, template: bytes | bytearray) -> bytes:
        if len(template) != 0x178:
            raise ValueError("Resonant Bass template must be 0x178 bytes")
        raw = bytearray(template)
        raw[6] = self.words[VELOCITY] & 0xFF
        c.copy_env_to_arm(self.words, AMP_ENV, raw, 0x74)
        c.copy_noise_to_arm(self.words, NOISE, raw)
        c.copy_resonator_to_arm(self.words, TONE_RES, raw, **TONE_MAP)
        c.put16(raw, 0xF0, self.words[PITCH])
        c.put32(raw, 0xE8, c.get_u32(self.words, RESONATOR_STATE))
        c.put32(raw, 0xEC, c.get_u32(self.words, RESONATOR_COEFF))
        c.copy_decay_to_arm(self.words, DECAY_A, raw, **_decay_map(0xF8))
        c.copy_decay_to_arm(self.words, DECAY_B, raw, **_decay_map(0x110))
        c.copy_decay_to_arm(self.words, DECAY_C, raw, **_decay_map(0x128))
        c.copy_decay_to_arm(self.words, DECAY_LEVEL, raw, **_decay_map(0x144))
        c.copy_resonator_to_arm(self.words, NOISE_RES, raw, **NOISE_MAP)
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

            # mod A: unsigned multiply, >>12, signed floor; no sign inversion.
            mod_a = ((c.get_u32(w, DECAY_A + c.DECAY_MUL)
                      * c.get_u32(w, DECAY_A + c.DECAY_VALUE)) & c.MASK32) >> 12
            minimum = c.s32(c.get_u32(w, DECAY_A + c.DECAY_MIN))
            if c.s32(mod_a) < minimum:
                mod_a = c.u32bits(minimum)
            c.set_u32(w, DECAY_A + c.DECAY_VALUE, mod_a)
            count_a = c.s32(c.get_u32(w, DECAY_A + c.DECAY_COUNT))
            if count_a > 0:
                count_a = c.sub(count_a, 1)
                c.set_u32(w, DECAY_A + c.DECAY_COUNT, count_a)
                if count_a == 0:
                    mod_a = c.u32bits(c.add(
                        c.s32(mod_a),
                        c.abs_arm(c.s32(c.get_u32(w, DECAY_A + c.DECAY_SIGN)))
                    ))
                    c.set_u32(w, DECAY_A + c.DECAY_VALUE, mod_a)

            # mod B: sign of the counter flips A; sign field flips B.
            count_b = c.s32(c.get_u32(w, DECAY_B + c.DECAY_COUNT))
            mod_b = ((c.get_u32(w, DECAY_B + c.DECAY_MUL)
                      * c.get_u32(w, DECAY_B + c.DECAY_VALUE)) & c.MASK32) >> 12
            minimum = c.s32(c.get_u32(w, DECAY_B + c.DECAY_MIN))
            if c.s32(mod_b) < minimum:
                mod_b = c.u32bits(minimum)
            if count_b < 0:
                mod_a = c.u32bits(c.neg(c.s32(mod_a)))
            active_b = count_b != 0
            sign_b = c.s32(c.get_u32(w, DECAY_B + c.DECAY_SIGN))
            c.set_u32(w, DECAY_B + c.DECAY_VALUE, mod_b)
            mod_a = c.u32bits(c.add(c.s32(mod_a), (1 << 14) if active_b else 0))
            if count_b > 0:
                count_b = c.sub(count_b, 1)
                c.set_u32(w, DECAY_B + c.DECAY_COUNT, count_b)
                if count_b == 0:
                    mod_b = c.u32bits(c.add(c.s32(mod_b), c.abs_arm(sign_b)))
                    c.set_u32(w, DECAY_B + c.DECAY_VALUE, mod_b)
            if sign_b < 0:
                mod_b = c.u32bits(c.neg(c.s32(mod_b)))
            drive = c.add(c.s32(mod_a), c.s32(mod_b))

            # C is a pitch-offset timer; its numeric value is maintained but
            # only the counter state affects the pitch selected this sample.
            mod_c = ((c.get_u32(w, DECAY_C + c.DECAY_MUL)
                      * c.get_u32(w, DECAY_C + c.DECAY_VALUE)) & c.MASK32) >> 12
            minimum = c.s32(c.get_u32(w, DECAY_C + c.DECAY_MIN))
            if c.s32(mod_c) < minimum:
                mod_c = c.u32bits(minimum)
            count_c = c.s32(c.get_u32(w, DECAY_C + c.DECAY_COUNT))
            c.set_u32(w, DECAY_C + c.DECAY_VALUE, mod_c)
            skip_pitch_offset = count_c == 0
            if count_c > 0:
                count_c = c.sub(count_c, 1)
                c.set_u32(w, DECAY_C + c.DECAY_COUNT, count_c)
                if count_c == 0:
                    mod_c = c.u32bits(c.add(
                        c.s32(mod_c),
                        c.abs_arm(c.s32(c.get_u32(w, DECAY_C + c.DECAY_SIGN)))
                    ))
                    c.set_u32(w, DECAY_C + c.DECAY_VALUE, mod_c)
                    skip_pitch_offset = True

            pitch = w[PITCH]
            if not skip_pitch_offset:
                pitch = (pitch + 0x880) & c.MASK16
            signed_pitch = c.s16(pitch)
            drive_quarter = c.asr(drive, 4)

            if (w[TONE_RES + c.RES_DIRTY]
                    or c.s16(w[TONE_RES + c.RES_PITCH_A]) != signed_pitch):
                w[TONE_RES + c.RES_PITCH_A] = pitch
                w[TONE_RES + c.RES_DIRTY] = 1
            _, tone_velocity = c.resonator(
                w, TONE_RES, drive, interpolation_a, interpolation_b
            )

            resonator = c.s32(c.get_u32(w, RESONATOR_STATE))
            resonator_input = c.add(tone_velocity, drive_quarter)
            resonator_delta = c.sub(resonator_input, resonator)

            level = ((c.get_u32(w, DECAY_LEVEL + c.DECAY_MUL)
                      * c.get_u32(w, DECAY_LEVEL + c.DECAY_VALUE)) & c.MASK32) >> 12
            minimum = c.s32(c.get_u32(w, DECAY_LEVEL + c.DECAY_MIN))
            if c.s32(level) < minimum:
                level = c.u32bits(minimum)
            c.set_u32(w, DECAY_LEVEL + c.DECAY_VALUE, level)

            resonator = c.add(
                resonator,
                c.asr(c.mullo(c.s32(c.get_u32(w, RESONATOR_COEFF)),
                              resonator_delta), 15),
            )
            c.set_u32(w, RESONATOR_STATE, resonator)

            level_count = c.s32(c.get_u32(w, DECAY_LEVEL + c.DECAY_COUNT))
            if level_count > 0:
                level_count = c.sub(level_count, 1)
                c.set_u32(w, DECAY_LEVEL + c.DECAY_COUNT, level_count)
                if level_count == 0:
                    level = c.u32bits(c.add(
                        c.s32(level),
                        c.abs_arm(c.s32(c.get_u32(w, DECAY_LEVEL + c.DECAY_SIGN)))
                    ))
                    c.set_u32(w, DECAY_LEVEL + c.DECAY_VALUE, level)
            if c.s32(c.get_u32(w, DECAY_LEVEL + c.DECAY_SIGN)) < 0:
                level = c.u32bits(c.neg(c.s32(level)))

            noise = c.render_noise(w, NOISE, rng)
            _, noise_velocity = c.resonator(
                w, NOISE_RES, noise, interpolation_a, interpolation_b
            )
            product = c.mullo(noise_velocity, c.s32(level))
            mixed = c.add(resonator, c.asr(product, 16))
            tripled = c.add(mixed, c.add(mixed, mixed))
            out.append(c.velocity_scale(w[VELOCITY], tripled))
        return out

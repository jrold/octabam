"""Compact exact render model for PĒRKONS v1.2.1 Fold Drum 2.

Fold Drum 2 shares Fold Drum 1's envelopes, pitch law, fold stage, transient
generator and RNG, but keeps two simple oscillators and crossfades between them.
The firmware stores two object pointers at +0x128/+0x12c that select which
oscillator is primary; PRIMARY stores that choice without retaining an absolute
ARM object address.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import simple_drum_compact as common

MASK16 = 0xFFFF
WORDS = 51

VELOCITY = 0
MUTE = 1
OSC_A = 2          # fixed ARM oscillator at object +0x2c (phase at +0x30)
AMP_ENV = 10
PITCH_ENV = 21
RAW_PITCH = 32
PITCH_AMOUNT = 33
OSC_B = 34         # fixed ARM oscillator at object +0xf4 (phase at +0xf8)
MODE = 42
COUNTER = 43
FOLD = 44
NOISE_COUNT = 45
NOISE_RATE = 46
NOISE_SAMPLE = 47
FADE_SAVED = 48    # ARM +0x130
FADE = 49          # ARM +0x132
PRIMARY = 50       # 0 => oscillator A is p1, 1 => oscillator B is p1


def _copy_osc_from_arm(words: list[int], dst: int,
                       raw: bytes | bytearray, phase_off: int) -> None:
    for i in range(4):
        common.CompactSimpleDrum._set_list_u32(
            words, dst + 2 * i, common._u32(raw, phase_off + 4 * i)
        )


def _copy_osc_to_arm(words: list[int], src: int,
                     raw: bytearray, phase_off: int) -> None:
    for i in range(4):
        value = words[src + 2 * i] | (words[src + 2 * i + 1] << 16)
        common._put32(raw, phase_off + 4 * i, value)


class _OscView:
    """Expose one 8-word Fold2 oscillator to the qualified Simple helpers."""

    def __init__(self, voice: "FoldDrum2", base: int):
        self.voice = voice
        self.base = base

    @property
    def words(self) -> list[int]:
        return self.voice.words

    def u32(self, off: int) -> int:
        i = self.base + off - common.OSC_PHASE
        return self.voice.words[i] | (self.voice.words[i + 1] << 16)

    def set_u32(self, off: int, value: int) -> None:
        i = self.base + off - common.OSC_PHASE
        self.voice.words[i] = value & MASK16
        self.voice.words[i + 1] = (value >> 16) & MASK16


@dataclass
class FoldDrum2:
    words: list[int]

    def __post_init__(self) -> None:
        if len(self.words) != WORDS:
            raise ValueError(f"Fold Drum 2 compact state must be {WORDS} words")
        self.words = [int(x) & MASK16 for x in self.words]
        self.words[PRIMARY] &= 1

    @classmethod
    def from_arm(cls, raw: bytes | bytearray) -> "FoldDrum2":
        if len(raw) != 0x134:
            raise ValueError("Fold Drum 2 state must be 0x134 bytes")

        # The first oscillator/envelopes/control layout is common with the
        # qualified Simple/Fold1 state through +0x11f.
        base = common.CompactSimpleDrum.from_arm(bytes(raw[:0x120]))
        words = list(base.words)
        words[PITCH_AMOUNT] = common._u16(raw, 0xEE)

        words.extend([0] * (WORDS - len(words)))
        _copy_osc_from_arm(words, OSC_B, raw, 0xF8)

        words[MODE] = raw[5]
        words[COUNTER] = common._u16(raw, 0xEC)
        words[FOLD] = common._u16(raw, 0xF0)
        words[NOISE_COUNT] = common._u16(raw, 0x60)
        words[NOISE_RATE] = common._u16(raw, 0x62)
        words[NOISE_SAMPLE] = common._u16(raw, 0x70)
        words[FADE_SAVED] = common._u16(raw, 0x130)
        words[FADE] = common._u16(raw, 0x132)

        p1 = common._u32(raw, 0x128)
        p2 = common._u32(raw, 0x12C)
        if p1 == p2 or abs(int(p1) - int(p2)) != 0xC8:
            raise ValueError(
                f"Fold Drum 2 oscillator pointers are not +0x2c/+0xf4: "
                f"0x{p1:08x}, 0x{p2:08x}"
            )
        words[PRIMARY] = 0 if p1 < p2 else 1
        return cls(words)

    def apply_to_arm(self, template: bytes | bytearray) -> bytes:
        if len(template) != 0x134:
            raise ValueError("Fold Drum 2 template must be 0x134 bytes")

        raw = bytearray(template)
        first = common.CompactSimpleDrum(self.words[:34])
        raw[:0x120] = first.apply_to_arm(raw[:0x120])
        common._put16(raw, 0xEE, self.words[PITCH_AMOUNT])
        _copy_osc_to_arm(self.words, OSC_B, raw, 0xF8)

        raw[5] = self.words[MODE] & 0xFF
        common._put16(raw, 0xEC, self.words[COUNTER])
        common._put16(raw, 0xF0, self.words[FOLD])
        common._put16(raw, 0x60, self.words[NOISE_COUNT])
        common._put16(raw, 0x62, self.words[NOISE_RATE])
        common._put16(raw, 0x70, self.words[NOISE_SAMPLE])
        common._put16(raw, 0x130, self.words[FADE_SAVED])
        common._put16(raw, 0x132, self.words[FADE])

        p1 = common._u32(raw, 0x128)
        p2 = common._u32(raw, 0x12C)
        if p1 == p2 or abs(int(p1) - int(p2)) != 0xC8:
            raise ValueError("Fold Drum 2 template has unsupported oscillator pointers")
        low, high = min(p1, p2), max(p1, p2)
        if self.words[PRIMARY]:
            common._put32(raw, 0x128, high)
            common._put32(raw, 0x12C, low)
        else:
            common._put32(raw, 0x128, low)
            common._put32(raw, 0x12C, high)
        return bytes(raw)

    def _primary_views(self) -> tuple[_OscView, _OscView]:
        a = _OscView(self, OSC_A)
        b = _OscView(self, OSC_B)
        return (b, a) if self.words[PRIMARY] else (a, b)

    def _add_transient(self, folded: int, rng: list[int]) -> int:
        counter = self.words[COUNTER]
        if counter > 0x210:
            return folded

        mode = self.words[MODE] & 0xFF
        if mode == 0:
            folded = common._s32(common._u32bits(folded) + 0x3FFF)
        elif mode == 2:
            if self.words[NOISE_COUNT]:
                self.words[NOISE_COUNT] = (self.words[NOISE_COUNT] - 1) & MASK16
            else:
                self.words[NOISE_COUNT] = self.words[NOISE_RATE]
                low, high = rng[0] & 0xFFFFFFFF, rng[1] & 0xFFFFFFFF
                product = low * 0x4C957F2D
                product_low = product & 0xFFFFFFFF
                new_low = (product_low + 1) & 0xFFFFFFFF
                carry = int(new_low < product_low)
                new_high = (
                    low * 0x5851F42D
                    + high * 0x4C957F2D
                    + (product >> 32)
                    + carry
                ) & 0xFFFFFFFF
                rng[:] = [new_low, new_high]
                self.words[NOISE_SAMPLE] = new_high & MASK16

            noise = common._s16(self.words[NOISE_SAMPLE])
            if counter <= 0x110:
                if counter <= 0x8F:
                    # ARM keeps only the sign-extended 26-bit field here.
                    field = common._u32bits(common._mullo32(noise, 11)) >> 4
                    field &= 0x03FFFFFF
                    if field & 0x02000000:
                        field |= 0xFC000000
                    transient = common._s32(field)
                else:
                    remaining = 0x110 - counter
                    transient = common._asr32(
                        common._mullo32(noise, remaining), 8
                    )
                    transient = common._asr32(
                        common._mullo32(44, transient), 6
                    )
                folded = common._s32(
                    common._u32bits(folded) + common._u32bits(transient)
                )

        self.words[COUNTER] = (counter + 1) & MASK16
        return folded

    def render(self, sample_count: int, waves: Mapping[int, bytes],
               pitch_table: bytes, envelope1: bytes | None,
               envelope2: bytes | None, rng: list[int],
               *, prepared_base_frequency: int | None = None) -> list[int]:
        if len(rng) != 2:
            raise ValueError("rng must be [low32, high32]")

        # Envelopes and prepared pitch live in the common first 34 words.
        common_voice = common.CompactSimpleDrum(self.words[:34])
        if prepared_base_frequency is None:
            prepared_base_frequency = common.cached_base_frequency(
                common_voice, pitch_table
            )
        base = prepared_base_frequency & 0xFFFFFFFF

        out: list[int] = []
        for _ in range(sample_count):
            amp = common._render_envelope(
                common_voice, common.AMP_ENV, envelope1, envelope2
            )
            pitch_env = common._render_envelope(
                common_voice, common.PITCH_ENV, envelope1, envelope2
            )

            low13 = pitch_env & 0x1FFF
            high = pitch_env >> 13
            factor = ((low13 + 0x2000) >> (13 - high)) - 1
            frequency = (
                base + ((common_voice.words[common.PITCH_ENV_AMOUNT] * factor) >> 9)
            ) & 0xFFFFFFFF

            # Copy envelope/control mutations back before oscillator helpers.
            self.words[:34] = common_voice.words
            first, second = self._primary_views()
            common._set_oscillator_frequency(first, frequency)

            fade = self.words[FADE]
            faded_amp = (amp - fade) & MASK16 if fade < amp else amp
            # Native uses: if (fade < amplitude) amplitude -= fade.
            if not (fade < amp):
                faded_amp = amp

            first_osc = common._render_oscillator(first, waves)
            second_osc = common._render_oscillator(second, waves)

            first_product = common._mullo32(faded_amp, first_osc)
            fade_again = self.words[FADE]
            self.words[FADE_SAVED] = faded_amp
            second_product = common._mullo32(fade_again, second_osc)

            fade_counter = max(fade_again, 0x88) - 0x88
            summed = common._s32(
                common._u32bits(common._asr32(second_product, 16))
                + common._u32bits(common._asr32(first_product, 16))
            )
            original = common._asr32(summed, 1)
            self.words[FADE] = fade_counter & MASK16

            amount = common._s16(self.words[FOLD]) + 0x100
            driven = common._asr32(common._mullo32(original, amount), 8)
            phase = (common._u32bits(driven) + 0x8000) & 0x1FFFF
            folded = (
                int(phase) - 0x8000
                if phase < 0x10000
                else 0x18000 - int(phase)
            )
            folded = self._add_transient(folded, rng)

            if self.words[MUTE] & 0xFF:
                out.append(0)
                continue

            mixed = common._asr32(
                common._s32(
                    common._u32bits(folded) + common._u32bits(original)
                ),
                1,
            )
            sample = common._asr32(
                common._mullo32(mixed, self.words[VELOCITY] & 0xFF), 8
            )
            out.append(max(-32768, min(32767, sample)))

        # oscillator writes already hit self.words; preserve envelope/control
        # mutations from the common helper without overwriting oscillator A.
        self.words[AMP_ENV:PITCH_ENV + common.ENV_WORDS] = (
            common_voice.words[AMP_ENV:PITCH_ENV + common.ENV_WORDS]
        )
        self.words[RAW_PITCH] = common_voice.words[RAW_PITCH]
        self.words[PITCH_AMOUNT] = common_voice.words[common.PITCH_ENV_AMOUNT]
        return out

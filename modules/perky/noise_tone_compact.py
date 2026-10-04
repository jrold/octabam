"""Compact DSP-native model for the PERKY Noise/Tone voice.

The older ``noise_tone_word_model`` intentionally mirrors all 0x120 firmware
bytes as DSP words.  That is ideal for proving arithmetic, but it wastes data
memory.  This file defines the shipping ABI candidate: only the 41 words the
validated renderer actually reads or mutates.

The representation is deliberately boring and assembler-friendly:

* one byte/u16 field -> one DSP data word (low 16 bits used);
* every u32 -> two 16-bit limbs, low then high;
* four voices are contiguous; the global RNG is separate/shared;
* table identities remain 32-bit until the final image builder maps them to
  packed local table offsets.

``from_arm`` and ``apply_to_arm`` are qualification adapters only.  They let a
compact voice run beside the 0x120-byte ARM-shaped oracle and prove that every
sample plus every renderer-owned mutable field is identical.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from noise_tone_ref import STATE_BYTES, ENVELOPE_BYTES, WAVE_BYTES
from noise_tone_word_model import (
    MASK16,
    U32,
    WordRng,
    add16,
    add32,
    arshift32_words,
    clamp_s32_to_s16ish,
    mul_low32_words,
    signed_gt,
    signed_le_zero,
    sub16,
    sub32,
)

MASK32 = 0xFFFFFFFF
WORDS_PER_VOICE = 41

# Stable compact-word ABI.  Keep this flat: the eventual DSP56300 assembly
# wants immediate offsets, and the verifier pins the exact list.
VEL = 0
ENV_STATE = 1
ENV_SHAPE = 2
ENV_FLAG4 = 3
ENV_FLAG6 = 4
ENV_TRIGGER = 5
ENV_VALUE = 6          # +6/+7 u32
ENV_HOLD = 8           # +8/+9 u32
ENV_ATTACK = 10
ENV_DECAY = 11
NOISE_COUNT = 12
NOISE_RELOAD = 13
NOISE_HELD = 14
FILTER_DAMPING = 15
FILTER_COEFF = 16
FILTER_FIRST = 17      # +17/+18 u32
FILTER_SECOND = 19     # +19/+20 u32
FILTER_VELOCITY = 21   # +21/+22 u32
OSC1_PHASE = 23        # +23/+24 u32
OSC1_INCREMENT = 25    # +25/+26 u32
OSC1_CURRENT = 27      # +27/+28 u32
OSC1_NEXT = 29         # +29/+30 u32
OSC2_PHASE = 31        # +31/+32 u32
OSC2_INCREMENT = 33    # +33/+34 u32
OSC2_CURRENT = 35      # +35/+36 u32
OSC2_NEXT = 37         # +37/+38 u32
MIX = 39               # +39/+40 u32

U32_FIELDS = (
    ENV_VALUE, ENV_HOLD,
    FILTER_FIRST, FILTER_SECOND, FILTER_VELOCITY,
    OSC1_PHASE, OSC1_INCREMENT, OSC1_CURRENT, OSC1_NEXT,
    OSC2_PHASE, OSC2_INCREMENT, OSC2_CURRENT, OSC2_NEXT,
    MIX,
)


def _u16(raw: bytes | bytearray, off: int) -> int:
    return raw[off] | (raw[off + 1] << 8)


def _u32(raw: bytes | bytearray, off: int) -> int:
    return _u16(raw, off) | (_u16(raw, off + 2) << 16)


def _put16(raw: bytearray, off: int, value: int) -> None:
    value &= MASK16
    raw[off] = value & 0xFF
    raw[off + 1] = value >> 8


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


def _table_u16(table: bytes, index: int) -> int:
    off = index * 2
    return table[off] | (table[off + 1] << 8)


def _table_s16(table: bytes, index: int) -> int:
    return _s16(_table_u16(table, index))


@dataclass
class CompactVoice:
    words: list[int]

    def __post_init__(self) -> None:
        if len(self.words) != WORDS_PER_VOICE:
            raise ValueError(f"compact voice must be {WORDS_PER_VOICE} words")
        self.words = [int(x) & MASK16 for x in self.words]

    @classmethod
    def from_arm(cls, raw: bytes | bytearray) -> "CompactVoice":
        if len(raw) != STATE_BYTES:
            raise ValueError(f"ARM-shaped state must be 0x{STATE_BYTES:x} bytes")
        w = [0] * WORDS_PER_VOICE
        w[VEL] = raw[6]

        e = 0x74
        w[ENV_STATE] = raw[e]
        w[ENV_SHAPE] = raw[e + 1]
        w[ENV_FLAG4] = raw[e + 4]
        w[ENV_FLAG6] = raw[e + 6]
        w[ENV_TRIGGER] = raw[e + 7]
        cls._set_list_u32(w, ENV_VALUE, _u32(raw, e + 0x0C))
        cls._set_list_u32(w, ENV_HOLD, _u32(raw, e + 0x10))
        w[ENV_ATTACK] = _u16(raw, e + 0x20)
        w[ENV_DECAY] = _u16(raw, e + 0x22)

        n = 0x60
        w[NOISE_COUNT] = _u16(raw, n)
        w[NOISE_RELOAD] = _u16(raw, n + 2)
        w[NOISE_HELD] = _u16(raw, n + 0x10)

        f = 0x9C
        w[FILTER_DAMPING] = _u16(raw, f + 0x0C)
        w[FILTER_COEFF] = _u16(raw, f + 0x0E)
        cls._set_list_u32(w, FILTER_FIRST, _u32(raw, f + 0x10))
        cls._set_list_u32(w, FILTER_SECOND, _u32(raw, f + 0x14))
        cls._set_list_u32(w, FILTER_VELOCITY, _u32(raw, f + 0x18))

        for base, phase, inc, current, nxt in (
            (0x2C, OSC1_PHASE, OSC1_INCREMENT, OSC1_CURRENT, OSC1_NEXT),
            (0xC4, OSC2_PHASE, OSC2_INCREMENT, OSC2_CURRENT, OSC2_NEXT),
        ):
            cls._set_list_u32(w, phase, _u32(raw, base + 4))
            cls._set_list_u32(w, inc, _u32(raw, base + 8))
            cls._set_list_u32(w, current, _u32(raw, base + 0x0C))
            cls._set_list_u32(w, nxt, _u32(raw, base + 0x10))

        cls._set_list_u32(w, MIX, _u32(raw, 0xF8))
        return cls(w)

    @staticmethod
    def _set_list_u32(words: list[int], off: int, value: int) -> None:
        value &= MASK32
        words[off] = value & MASK16
        words[off + 1] = (value >> 16) & MASK16

    def u32(self, off: int) -> U32:
        return U32(self.words[off], self.words[off + 1])

    def set_u32(self, off: int, value: U32 | int) -> None:
        value = value if isinstance(value, U32) else U32.from_int(value)
        self.words[off] = value.lo
        self.words[off + 1] = value.hi

    def apply_to_arm(self, template: bytes | bytearray) -> bytes:
        """Overlay every renderer-owned field onto an ARM-shaped state copy."""
        if len(template) != STATE_BYTES:
            raise ValueError(f"ARM-shaped state must be 0x{STATE_BYTES:x} bytes")
        raw = bytearray(template)
        raw[6] = self.words[VEL] & 0xFF

        e = 0x74
        raw[e] = self.words[ENV_STATE] & 0xFF
        raw[e + 1] = self.words[ENV_SHAPE] & 0xFF
        raw[e + 4] = self.words[ENV_FLAG4] & 0xFF
        raw[e + 6] = self.words[ENV_FLAG6] & 0xFF
        raw[e + 7] = self.words[ENV_TRIGGER] & 0xFF
        _put32(raw, e + 0x0C, self.u32(ENV_VALUE).unsigned())
        _put32(raw, e + 0x10, self.u32(ENV_HOLD).unsigned())
        _put16(raw, e + 0x20, self.words[ENV_ATTACK])
        _put16(raw, e + 0x22, self.words[ENV_DECAY])

        n = 0x60
        _put16(raw, n, self.words[NOISE_COUNT])
        _put16(raw, n + 2, self.words[NOISE_RELOAD])
        _put16(raw, n + 0x10, self.words[NOISE_HELD])

        f = 0x9C
        _put16(raw, f + 0x0C, self.words[FILTER_DAMPING])
        _put16(raw, f + 0x0E, self.words[FILTER_COEFF])
        _put32(raw, f + 0x10, self.u32(FILTER_FIRST).unsigned())
        _put32(raw, f + 0x14, self.u32(FILTER_SECOND).unsigned())
        _put32(raw, f + 0x18, self.u32(FILTER_VELOCITY).unsigned())

        for base, phase, inc, current, nxt in (
            (0x2C, OSC1_PHASE, OSC1_INCREMENT, OSC1_CURRENT, OSC1_NEXT),
            (0xC4, OSC2_PHASE, OSC2_INCREMENT, OSC2_CURRENT, OSC2_NEXT),
        ):
            _put32(raw, base + 4, self.u32(phase).unsigned())
            _put32(raw, base + 8, self.u32(inc).unsigned())
            _put32(raw, base + 0x0C, self.u32(current).unsigned())
            _put32(raw, base + 0x10, self.u32(nxt).unsigned())

        _put32(raw, 0xF8, self.u32(MIX).unsigned())
        return bytes(raw)


def render_envelope(voice: CompactVoice, envelope1: bytes | None,
                    envelope2: bytes | None) -> int:
    state = voice.words[ENV_STATE] & 0xFF
    value = voice.u32(ENV_VALUE)

    if state == 0:
        if voice.words[ENV_TRIGGER] or voice.words[ENV_FLAG4]:
            voice.words[ENV_STATE] = 1
    elif state == 1:
        value = add16(value, voice.words[ENV_ATTACK])
        voice.set_u32(ENV_VALUE, value)
        if voice.words[ENV_FLAG4]:
            if signed_gt(value, 0x000FFFFE):
                voice.words[ENV_STATE] = 4
                if not signed_gt(U32.from_int(0x00100000), value.unsigned()):
                    value = U32.from_int(0x000FFFFF)
                    voice.set_u32(ENV_VALUE, value)
        elif signed_gt(value, 0x000FFFFE):
            voice.words[ENV_STATE] = 3 if voice.words[ENV_FLAG6] == 0 else 4
            if not signed_gt(U32.from_int(0x00100000), value.unsigned()):
                value = U32.from_int(0x000FFFFF)
                voice.set_u32(ENV_VALUE, value)
    elif state == 3:
        if not voice.words[ENV_TRIGGER] and (
            voice.words[ENV_FLAG4] or voice.u32(ENV_HOLD).unsigned() == 0
        ):
            voice.words[ENV_STATE] = 4
    elif state == 4:
        if voice.words[ENV_TRIGGER]:
            voice.words[ENV_STATE] = 1
        else:
            value = sub16(value, voice.words[ENV_DECAY])
            voice.set_u32(ENV_VALUE, value)
            if signed_le_zero(value):
                value = U32(0, 0)
                voice.set_u32(ENV_VALUE, value)
                voice.words[ENV_STATE] = 1 if voice.words[ENV_FLAG4] else 0

    shape = voice.words[ENV_SHAPE] & 0xFF
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


def render_noise(voice: CompactVoice, rng: WordRng) -> int:
    count = voice.words[NOISE_COUNT]
    if count:
        voice.words[NOISE_COUNT] = (count - 1) & MASK16
        return _s16(voice.words[NOISE_HELD])

    voice.words[NOISE_COUNT] = voice.words[NOISE_RELOAD]
    # Keep the exact RNG spelling in one place: import lazily to avoid giving
    # the compact ABI a second independently-maintained PRNG implementation.
    from noise_tone_word_model import next_random
    result = _s16(next_random(rng).lo)
    voice.words[NOISE_HELD] = result & MASK16
    return result


def advance_filter(voice: CompactVoice, input_sample: int) -> None:
    coefficient = voice.words[FILTER_COEFF]
    velocity = voice.u32(FILTER_VELOCITY)

    product = mul_low32_words(velocity, U32(coefficient, 0))
    if product.negative():
        product = add16(product, 0xFFFF)
    first = add32(voice.u32(FILTER_FIRST), arshift32_words(product, 16))
    first = clamp_s32_to_s16ish(first, -32767, 32767)
    voice.set_u32(FILTER_FIRST, first)

    second = sub32(U32.from_int(input_sample), first)
    damping = mul_low32_words(velocity, U32(voice.words[FILTER_DAMPING], 0))
    second = sub32(second, arshift32_words(damping, 10))
    second = clamp_s32_to_s16ish(second, -32767, 32767)
    voice.set_u32(FILTER_SECOND, second)

    feedback = mul_low32_words(second, U32(coefficient, 0))
    if feedback.negative():
        feedback = add16(feedback, 0xFFFF)
    velocity = add32(velocity, arshift32_words(feedback, 16))
    velocity = clamp_s32_to_s16ish(velocity, -32767, 32767)
    voice.set_u32(FILTER_VELOCITY, velocity)


def render_oscillator(voice: CompactVoice, phase_off: int,
                      increment_off: int, current_off: int, next_off: int,
                      waves: Mapping[int, bytes]) -> int:
    phase = add32(voice.u32(phase_off), voice.u32(increment_off))
    voice.set_u32(phase_off, phase)
    current = voice.u32(current_off)

    if signed_gt(phase, 0x00100000):
        nxt = voice.u32(next_off)
        phase = sub32(phase, U32.from_int(0x00100000))
        voice.set_u32(phase_off, phase)
        if nxt != current:
            current = nxt
            voice.set_u32(current_off, current)

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


def render_block(voice: CompactVoice, sample_count: int,
                 waves: Mapping[int, bytes], rng: WordRng,
                 envelope1: bytes | None, envelope2: bytes | None) -> list[int]:
    out: list[int] = []
    for _ in range(sample_count):
        amplitude = render_envelope(voice, envelope1, envelope2)
        noise = render_noise(voice, rng)
        advance_filter(voice, noise)
        advance_filter(voice, noise)

        mix = voice.u32(MIX)
        accumulator = arshift32_words(
            mul_low32_words(mix, U32.from_int(noise)), 13
        ).signed()

        osc1 = render_oscillator(
            voice, OSC1_PHASE, OSC1_INCREMENT, OSC1_CURRENT, OSC1_NEXT, waves
        )
        osc2 = render_oscillator(
            voice, OSC2_PHASE, OSC2_INCREMENT, OSC2_CURRENT, OSC2_NEXT, waves
        )
        oscillator_sum = arshift32_words(U32.from_int(osc1 + osc2), 4).signed()
        tonal = mul_low32_words(
            U32.from_int(0x00000FFF - mix.unsigned()),
            U32.from_int(oscillator_sum),
        )
        accumulator = _s32(
            (accumulator + arshift32_words(tonal, 9).signed()) & MASK32
        )

        output = arshift32_words(
            mul_low32_words(U32.from_int(accumulator), U32(amplitude, 0)), 16
        ).signed()
        output = arshift32_words(
            mul_low32_words(U32.from_int(output), U32(voice.words[VEL], 0)), 8
        ).signed()
        output = max(-32768, min(32767, output))
        out.append(output)
    return out


def abi_offsets() -> dict[str, int]:
    return {
        "velocity": VEL,
        "env_state": ENV_STATE,
        "env_shape": ENV_SHAPE,
        "env_flag4": ENV_FLAG4,
        "env_flag6": ENV_FLAG6,
        "env_trigger": ENV_TRIGGER,
        "env_value": ENV_VALUE,
        "env_hold": ENV_HOLD,
        "env_attack": ENV_ATTACK,
        "env_decay": ENV_DECAY,
        "noise_count": NOISE_COUNT,
        "noise_reload": NOISE_RELOAD,
        "noise_held": NOISE_HELD,
        "filter_damping": FILTER_DAMPING,
        "filter_coeff": FILTER_COEFF,
        "filter_first": FILTER_FIRST,
        "filter_second": FILTER_SECOND,
        "filter_velocity": FILTER_VELOCITY,
        "osc1_phase": OSC1_PHASE,
        "osc1_increment": OSC1_INCREMENT,
        "osc1_current": OSC1_CURRENT,
        "osc1_next": OSC1_NEXT,
        "osc2_phase": OSC2_PHASE,
        "osc2_increment": OSC2_INCREMENT,
        "osc2_current": OSC2_CURRENT,
        "osc2_next": OSC2_NEXT,
        "mix": MIX,
    }

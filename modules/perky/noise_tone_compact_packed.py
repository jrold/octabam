"""Complete compact PERKY Noise/Tone renderer using shipping packed tables.

This is the bridge between the already-proven 41-word compact renderer and the
DSP image representation:

* oscillator reads use ``PackedWaves`` (three u16 samples / two 24-bit words);
* shaped envelope reads use ``PackedEnvelope`` plus one 17-word-equivalent
  cache per voice;
* state/RNG arithmetic is otherwise the same word-exact implementation as
  ``noise_tone_compact``.

The gate requires this renderer to produce identical PCM, compact state and RNG
to the raw-table compact renderer. No approximation is introduced by packing.
"""
from __future__ import annotations

from dataclasses import dataclass

import noise_tone_compact as c
from noise_tone_envelope_cache import EnvelopeCache, envelope_at_cached
from noise_tone_tables import PackedEnvelope, PackedWaves, WAVE_SAMPLES, wave_at
from noise_tone_word_model import (
    MASK16,
    U32,
    WordRng,
    add16,
    add32,
    arshift32_words,
    clamp_s32_to_s16ish,
    mul_low32_words,
    next_random,
    signed_gt,
    signed_le_zero,
    sub16,
    sub32,
)

MASK32 = 0xFFFFFFFF


@dataclass
class PackedTables:
    waves: PackedWaves
    envelope1: PackedEnvelope
    envelope2: PackedEnvelope

    def ordinal(self, address: int) -> int:
        try:
            return self.waves.addresses.index(address & MASK32)
        except ValueError as exc:
            raise KeyError(f"unknown packed wave identity 0x{address&MASK32:08x}") from exc


def _s16(value: int) -> int:
    value &= MASK16
    return value - 0x10000 if value & 0x8000 else value


def _s32(value: int) -> int:
    value &= MASK32
    return value - 0x100000000 if value & 0x80000000 else value


def render_envelope(voice: c.CompactVoice, tables: PackedTables,
                    cache1: EnvelopeCache, cache2: EnvelopeCache) -> int:
    state = voice.words[c.ENV_STATE] & 0xFF
    value = voice.u32(c.ENV_VALUE)

    if state == 0:
        if voice.words[c.ENV_TRIGGER] or voice.words[c.ENV_FLAG4]:
            voice.words[c.ENV_STATE] = 1
    elif state == 1:
        value = add16(value, voice.words[c.ENV_ATTACK])
        voice.set_u32(c.ENV_VALUE, value)
        if voice.words[c.ENV_FLAG4]:
            if signed_gt(value, 0x000FFFFE):
                voice.words[c.ENV_STATE] = 4
                if not signed_gt(U32.from_int(0x00100000), value.unsigned()):
                    value = U32.from_int(0x000FFFFF)
                    voice.set_u32(c.ENV_VALUE, value)
        elif signed_gt(value, 0x000FFFFE):
            voice.words[c.ENV_STATE] = 3 if voice.words[c.ENV_FLAG6] == 0 else 4
            if not signed_gt(U32.from_int(0x00100000), value.unsigned()):
                value = U32.from_int(0x000FFFFF)
                voice.set_u32(c.ENV_VALUE, value)
    elif state == 3:
        if not voice.words[c.ENV_TRIGGER] and (
            voice.words[c.ENV_FLAG4] or voice.u32(c.ENV_HOLD).unsigned() == 0
        ):
            voice.words[c.ENV_STATE] = 4
    elif state == 4:
        if voice.words[c.ENV_TRIGGER]:
            voice.words[c.ENV_STATE] = 1
        else:
            value = sub16(value, voice.words[c.ENV_DECAY])
            voice.set_u32(c.ENV_VALUE, value)
            if signed_le_zero(value):
                value = U32(0, 0)
                voice.set_u32(c.ENV_VALUE, value)
                voice.words[c.ENV_STATE] = 1 if voice.words[c.ENV_FLAG4] else 0

    shape = voice.words[c.ENV_SHAPE] & 0xFF
    if shape not in (1, 2):
        return (value.unsigned() >> 4) & MASK16

    raw = value.unsigned()
    index = (raw >> 10) & 0x7FF
    nxt = (index + 1) & 0x7FF
    fraction = raw & 0x3FF
    table = tables.envelope1 if shape == 1 else tables.envelope2
    cache = cache1 if shape == 1 else cache2
    first = envelope_at_cached(table, index, cache)
    second = envelope_at_cached(table, nxt, cache)
    delta = U32.from_int(second - first)
    interp = arshift32_words(mul_low32_words(delta, U32(fraction, 0)), 10).signed()
    return (first + interp) & MASK16


def render_noise(voice: c.CompactVoice, rng: WordRng) -> int:
    count = voice.words[c.NOISE_COUNT]
    if count:
        voice.words[c.NOISE_COUNT] = (count - 1) & MASK16
        return _s16(voice.words[c.NOISE_HELD])
    voice.words[c.NOISE_COUNT] = voice.words[c.NOISE_RELOAD]
    result = _s16(next_random(rng).lo)
    voice.words[c.NOISE_HELD] = result & MASK16
    return result


def advance_filter(voice: c.CompactVoice, input_sample: int) -> None:
    coefficient = voice.words[c.FILTER_COEFF]
    velocity = voice.u32(c.FILTER_VELOCITY)
    product = mul_low32_words(velocity, U32(coefficient, 0))
    if product.negative():
        product = add16(product, 0xFFFF)
    first = add32(voice.u32(c.FILTER_FIRST), arshift32_words(product, 16))
    first = clamp_s32_to_s16ish(first, -32767, 32767)
    voice.set_u32(c.FILTER_FIRST, first)

    second = sub32(U32.from_int(input_sample), first)
    damping = mul_low32_words(velocity, U32(voice.words[c.FILTER_DAMPING], 0))
    second = sub32(second, arshift32_words(damping, 10))
    second = clamp_s32_to_s16ish(second, -32767, 32767)
    voice.set_u32(c.FILTER_SECOND, second)

    feedback = mul_low32_words(second, U32(coefficient, 0))
    if feedback.negative():
        feedback = add16(feedback, 0xFFFF)
    velocity = add32(velocity, arshift32_words(feedback, 16))
    velocity = clamp_s32_to_s16ish(velocity, -32767, 32767)
    voice.set_u32(c.FILTER_VELOCITY, velocity)


def _wave_sample(tables: PackedTables, address: int, index: int) -> int:
    return _s16(wave_at(tables.waves, address, index))


def render_oscillator(voice: c.CompactVoice, phase_off: int,
                      increment_off: int, current_off: int, next_off: int,
                      tables: PackedTables) -> int:
    phase = add32(voice.u32(phase_off), voice.u32(increment_off))
    voice.set_u32(phase_off, phase)
    current = voice.u32(current_off)

    if signed_gt(phase, 0x00100000):
        nxt_addr = voice.u32(next_off)
        phase = sub32(phase, U32.from_int(0x00100000))
        voice.set_u32(phase_off, phase)
        if nxt_addr != current:
            current = nxt_addr
            voice.set_u32(current_off, current)

    address = current.unsigned()
    # Resolve now so an invalid address fails before either sample read.
    tables.ordinal(address)
    raw_phase = phase.unsigned()
    index = (raw_phase >> 12) & 0xFF
    nxt = (index + 1) & 0xFF
    fraction = raw_phase & 0xFFF
    first = _wave_sample(tables, address, index)
    second = _wave_sample(tables, address, nxt)
    delta = U32.from_int(second - first)
    interp = arshift32_words(mul_low32_words(delta, U32(fraction, 0)), 12).signed()
    return _s16(first + interp)


def render_block(voice: c.CompactVoice, sample_count: int, tables: PackedTables,
                 rng: WordRng, cache1: EnvelopeCache | None = None,
                 cache2: EnvelopeCache | None = None) -> list[int]:
    cache1 = cache1 or EnvelopeCache()
    cache2 = cache2 or EnvelopeCache()
    out: list[int] = []

    for _ in range(sample_count):
        amplitude = render_envelope(voice, tables, cache1, cache2)
        noise = render_noise(voice, rng)
        advance_filter(voice, noise)
        advance_filter(voice, noise)

        mix = voice.u32(c.MIX)
        accumulator = arshift32_words(
            mul_low32_words(mix, U32.from_int(noise)), 13
        )

        osc1 = render_oscillator(
            voice, c.OSC1_PHASE, c.OSC1_INCREMENT,
            c.OSC1_CURRENT, c.OSC1_NEXT, tables,
        )
        osc2 = render_oscillator(
            voice, c.OSC2_PHASE, c.OSC2_INCREMENT,
            c.OSC2_CURRENT, c.OSC2_NEXT, tables,
        )
        oscillator_sum = arshift32_words(U32.from_int(osc1 + osc2), 4)
        tonal_gain = sub32(U32.from_int(0x00000FFF), mix)
        tonal = mul_low32_words(tonal_gain, oscillator_sum)
        accumulator = add32(accumulator, arshift32_words(tonal, 9))

        output = arshift32_words(
            mul_low32_words(accumulator, U32(amplitude, 0)), 16
        )
        output = arshift32_words(
            mul_low32_words(output, U32(voice.words[c.VEL], 0)), 8
        ).signed()
        out.append(max(-32768, min(32767, output)))

    return out

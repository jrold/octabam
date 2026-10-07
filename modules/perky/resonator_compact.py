"""Shared exact integer primitives for v1.2.1 resonant PĒRKONS engines."""
from __future__ import annotations

MASK16 = 0xFFFF
MASK32 = 0xFFFFFFFF
ENV_WORDS = 11
DECAY_WORDS = 10
RESONATOR_WORDS = 14

ENV_STATE = 0
ENV_SHAPE = 1
ENV_FLAG4 = 2
ENV_FLAG6 = 3
ENV_TRIGGER = 4
ENV_VALUE = 5
ENV_HOLD = 7
ENV_ATTACK = 9
ENV_DECAY = 10

DECAY_MUL = 0
DECAY_COUNT = 2
DECAY_VALUE = 4
DECAY_SIGN = 6
DECAY_MIN = 8

RES_DIRTY = 0
RES_PITCH_A = 1
RES_PITCH_B = 2
RES_COEFF_B = 3
RES_COEFF_A = 5
RES_MOD = 7
RES_BYPASS = 9
RES_POSITION = 10
RES_VELOCITY = 12


def u16(raw: bytes | bytearray, off: int) -> int:
    return raw[off] | (raw[off + 1] << 8)


def u32(raw: bytes | bytearray, off: int) -> int:
    return u16(raw, off) | (u16(raw, off + 2) << 16)


def put16(raw: bytearray, off: int, value: int) -> None:
    value &= MASK16
    raw[off] = value & 0xFF
    raw[off + 1] = value >> 8


def put32(raw: bytearray, off: int, value: int) -> None:
    value &= MASK32
    put16(raw, off, value)
    put16(raw, off + 2, value >> 16)


def s16(value: int) -> int:
    value &= MASK16
    return value - 0x10000 if value & 0x8000 else value


def s32(value: int) -> int:
    value &= MASK32
    return value - 0x100000000 if value & 0x80000000 else value


def u32bits(value: int) -> int:
    return value & MASK32


def add(a: int, b: int) -> int:
    return s32(u32bits(a) + u32bits(b))


def sub(a: int, b: int) -> int:
    return s32(u32bits(a) - u32bits(b))


def neg(value: int) -> int:
    return s32(-u32bits(value))


def abs_arm(value: int) -> int:
    return neg(value) if value < 0 else value


def asr(value: int, shift: int) -> int:
    return s32(value) >> shift


def mullo(a: int, b: int) -> int:
    return s32((u32bits(a) * u32bits(b)) & MASK32)


def get_u32(words: list[int], off: int) -> int:
    return words[off] | (words[off + 1] << 16)


def set_u32(words: list[int], off: int, value: int) -> None:
    value &= MASK32
    words[off] = value & MASK16
    words[off + 1] = value >> 16


def table_u16(table: bytes, index: int) -> int:
    off = 2 * index
    return table[off] | (table[off + 1] << 8)


def copy_env_from_arm(words: list[int], dst: int,
                      raw: bytes | bytearray, src: int) -> None:
    words[dst + ENV_STATE] = raw[src]
    words[dst + ENV_SHAPE] = raw[src + 1]
    words[dst + ENV_FLAG4] = raw[src + 4]
    words[dst + ENV_FLAG6] = raw[src + 6]
    words[dst + ENV_TRIGGER] = raw[src + 7]
    set_u32(words, dst + ENV_VALUE, u32(raw, src + 0x0C))
    set_u32(words, dst + ENV_HOLD, u32(raw, src + 0x10))
    words[dst + ENV_ATTACK] = u16(raw, src + 0x20)
    words[dst + ENV_DECAY] = u16(raw, src + 0x22)


def copy_env_to_arm(words: list[int], src: int,
                    raw: bytearray, dst: int) -> None:
    raw[dst] = words[src + ENV_STATE] & 0xFF
    raw[dst + 1] = words[src + ENV_SHAPE] & 0xFF
    raw[dst + 4] = words[src + ENV_FLAG4] & 0xFF
    raw[dst + 6] = words[src + ENV_FLAG6] & 0xFF
    raw[dst + 7] = words[src + ENV_TRIGGER] & 0xFF
    put32(raw, dst + 0x0C, get_u32(words, src + ENV_VALUE))
    put32(raw, dst + 0x10, get_u32(words, src + ENV_HOLD))
    put16(raw, dst + 0x20, words[src + ENV_ATTACK])
    put16(raw, dst + 0x22, words[src + ENV_DECAY])


def render_envelope(words: list[int], base: int,
                    envelope1: bytes | None,
                    envelope2: bytes | None) -> int:
    state = words[base + ENV_STATE]
    value = s32(get_u32(words, base + ENV_VALUE))
    if state == 0:
        if words[base + ENV_TRIGGER] or words[base + ENV_FLAG4]:
            words[base + ENV_STATE] = 1
    elif state == 1:
        value = add(value, words[base + ENV_ATTACK])
        set_u32(words, base + ENV_VALUE, value)
        if words[base + ENV_FLAG4]:
            if value > 0x000FFFFE:
                words[base + ENV_STATE] = 4
                if value >= 0x00100000:
                    value = 0x000FFFFF
                    set_u32(words, base + ENV_VALUE, value)
        elif value > 0x000FFFFE:
            words[base + ENV_STATE] = 4 if words[base + ENV_FLAG6] else 3
            if value >= 0x00100000:
                value = 0x000FFFFF
                set_u32(words, base + ENV_VALUE, value)
    elif state == 3:
        if not words[base + ENV_TRIGGER] and (
            words[base + ENV_FLAG4] or (words[base + ENV_HOLD] & 0xFF) == 0
        ):
            words[base + ENV_STATE] = 4
    elif state == 4:
        if words[base + ENV_TRIGGER]:
            words[base + ENV_STATE] = 1
        else:
            value = sub(value, words[base + ENV_DECAY])
            set_u32(words, base + ENV_VALUE, value)
            if value <= 0:
                value = 0
                set_u32(words, base + ENV_VALUE, 0)
                words[base + ENV_STATE] = 1 if words[base + ENV_FLAG4] else 0

    shape = words[base + ENV_SHAPE] & 0xFF
    if shape not in (1, 2):
        return (u32bits(value) >> 4) & MASK16
    curve = envelope1 if shape == 1 else envelope2
    if curve is None:
        return 0
    raw = u32bits(value)
    index = (raw >> 10) & 0x7FF
    nxt = (index + 1) & 0x7FF
    fraction = raw & 0x3FF
    a = table_u16(curve, index)
    b = table_u16(curve, nxt)
    return (a + asr(mullo(b - a, fraction), 10)) & MASK16


def interpolate(table: bytes, phase: int) -> int:
    phase &= MASK32
    index = phase >> 24
    fraction = (phase >> 8) & MASK16
    a = table_u16(table, index)
    b = table_u16(table, index + 1)
    product = (fraction * u32bits(b - a)) & MASK32
    return (a + (product >> 16)) & MASK16


def next_random(rng: list[int]) -> int:
    old_low, old_high = rng[0] & MASK32, rng[1] & MASK32
    accumulator = (old_low * 0x5851F42D) & MASK32
    accumulator = (accumulator + old_high * 0x4C957F2D) & MASK32
    product = old_low * 0x4C957F2D
    product_low = product & MASK32
    new_low = (product_low + 1) & MASK32
    carry = int(new_low < product_low)
    new_high = (accumulator + (product >> 32) + carry) & MASK32
    rng[:] = [new_low, new_high]
    return new_high & 0x7FFFFFFF


def render_noise(words: list[int], base: int, rng: list[int]) -> int:
    count = words[base]
    if count:
        words[base] = (count - 1) & MASK16
        return s16(words[base + 2])
    words[base] = words[base + 1]
    result = s16(next_random(rng))
    words[base + 2] = result & MASK16
    return result


def copy_noise_from_arm(words: list[int], dst: int,
                        raw: bytes | bytearray, src: int = 0x60) -> None:
    words[dst] = u16(raw, src)
    words[dst + 1] = u16(raw, src + 2)
    words[dst + 2] = u16(raw, src + 0x10)


def copy_noise_to_arm(words: list[int], src: int,
                      raw: bytearray, dst: int = 0x60) -> None:
    put16(raw, dst, words[src])
    put16(raw, dst + 2, words[src + 1])
    put16(raw, dst + 0x10, words[src + 2])


def copy_decay_from_arm(words: list[int], dst: int,
                        raw: bytes | bytearray,
                        mul_off: int, count_off: int, value_off: int,
                        sign_off: int, min_off: int) -> None:
    for d, off in ((DECAY_MUL, mul_off), (DECAY_COUNT, count_off),
                   (DECAY_VALUE, value_off), (DECAY_SIGN, sign_off),
                   (DECAY_MIN, min_off)):
        set_u32(words, dst + d, u32(raw, off))


def copy_decay_to_arm(words: list[int], src: int, raw: bytearray,
                      mul_off: int, count_off: int, value_off: int,
                      sign_off: int, min_off: int) -> None:
    for d, off in ((DECAY_MUL, mul_off), (DECAY_COUNT, count_off),
                   (DECAY_VALUE, value_off), (DECAY_SIGN, sign_off),
                   (DECAY_MIN, min_off)):
        put32(raw, off, get_u32(words, src + d))


def decay_level(words: list[int], base: int,
                *, add_constant: bool = False, constant: int = 0) -> int:
    product = (get_u32(words, base + DECAY_MUL)
               * get_u32(words, base + DECAY_VALUE)) & MASK32
    value = product >> 12
    minimum = s32(get_u32(words, base + DECAY_MIN))
    if s32(value) < minimum:
        value = u32bits(minimum)
    count = s32(get_u32(words, base + DECAY_COUNT))
    sign = s32(get_u32(words, base + DECAY_SIGN))
    set_u32(words, base + DECAY_VALUE, value)
    use_constant = add_constant and count != 0
    if count > 0:
        count = sub(count, 1)
        set_u32(words, base + DECAY_COUNT, count)
        if count == 0:
            value = u32bits(add(s32(value), abs_arm(sign)))
            set_u32(words, base + DECAY_VALUE, value)
            use_constant = False
    if sign < 0:
        value = u32bits(neg(s32(value)))
    if use_constant:
        value = u32bits(add(s32(value), constant))
    return value


def copy_resonator_from_arm(words: list[int], dst: int,
                            raw: bytes | bytearray, *, dirty: int,
                            pitch_a: int, pitch_b: int, coeff_b: int,
                            coeff_a: int, mod: int, bypass: int,
                            position: int, velocity: int) -> None:
    words[dst + RES_DIRTY] = raw[dirty]
    words[dst + RES_PITCH_A] = u16(raw, pitch_a)
    words[dst + RES_PITCH_B] = u16(raw, pitch_b)
    set_u32(words, dst + RES_COEFF_B, u32(raw, coeff_b))
    set_u32(words, dst + RES_COEFF_A, u32(raw, coeff_a))
    set_u32(words, dst + RES_MOD, u32(raw, mod))
    words[dst + RES_BYPASS] = raw[bypass]
    set_u32(words, dst + RES_POSITION, u32(raw, position))
    set_u32(words, dst + RES_VELOCITY, u32(raw, velocity))


def copy_resonator_to_arm(words: list[int], src: int, raw: bytearray,
                          *, dirty: int, pitch_a: int, pitch_b: int,
                          coeff_b: int, coeff_a: int, mod: int, bypass: int,
                          position: int, velocity: int) -> None:
    raw[dirty] = words[src + RES_DIRTY] & 0xFF
    put16(raw, pitch_a, words[src + RES_PITCH_A])
    put16(raw, pitch_b, words[src + RES_PITCH_B])
    put32(raw, coeff_b, get_u32(words, src + RES_COEFF_B))
    put32(raw, coeff_a, get_u32(words, src + RES_COEFF_A))
    put32(raw, mod, get_u32(words, src + RES_MOD))
    raw[bypass] = words[src + RES_BYPASS] & 0xFF
    put32(raw, position, get_u32(words, src + RES_POSITION))
    put32(raw, velocity, get_u32(words, src + RES_VELOCITY))


def clamp32767(value: int) -> int:
    if value < -32767:
        return -32767
    if value >= 32767:
        return 32767
    return value


def resonator(words: list[int], base: int, input_value: int,
              interp_a: bytes, interp_b: bytes) -> tuple[int, int]:
    if words[base + RES_DIRTY]:
        pa = s16(words[base + RES_PITCH_A])
        pb = s16(words[base + RES_PITCH_B])
        set_u32(words, base + RES_COEFF_B,
                interpolate(interp_a, u32bits(pa << 17)))
        set_u32(words, base + RES_COEFF_A,
                interpolate(interp_b, u32bits(pb << 17)))
        words[base + RES_DIRTY] = 0

    coeff_a = s32(get_u32(words, base + RES_COEFF_A))
    position = s32(get_u32(words, base + RES_POSITION))
    modulation = s32(get_u32(words, base + RES_MOD))
    coeff_b = s32(get_u32(words, base + RES_COEFF_B))
    if modulation:
        scale = 0x80
        if position > 0x1000:
            coeff_a = add(coeff_a, asr(sub(position, 0x800), 3))
            scale = asr(position, 4)
        coeff_b = add(coeff_b, asr(mullo(scale, modulation), 9))

    velocity = s32(get_u32(words, base + RES_VELOCITY))
    filtered = input_value
    if not words[base + RES_BYPASS]:
        filtered = sub(input_value, asr(mullo(velocity, coeff_a), 15))
    position = add(position, asr(mullo(velocity, coeff_b), 15))
    position = clamp32767(position)
    set_u32(words, base + RES_POSITION, position)
    filtered = sub(filtered, position)
    velocity = add(velocity, asr(mullo(coeff_b, filtered), 15))
    velocity = clamp32767(velocity)
    set_u32(words, base + RES_VELOCITY, velocity)
    return position, velocity


def velocity_scale(velocity: int, value: int) -> int:
    out = asr(mullo(value, velocity & 0xFF), 8)
    return max(-32768, min(32767, out))

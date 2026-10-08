#include "cf_noise_tone.h"

#include <limits.h>

static uint16_t rd16(const uint8_t *p)
{
    return (uint16_t)p[0] | (uint16_t)((uint16_t)p[1] << 8);
}

static uint32_t rd32(const uint8_t *p)
{
    return (uint32_t)p[0]
        | ((uint32_t)p[1] << 8)
        | ((uint32_t)p[2] << 16)
        | ((uint32_t)p[3] << 24);
}

static void wr16(uint8_t *p, uint16_t v)
{
    p[0] = (uint8_t)v;
    p[1] = (uint8_t)(v >> 8);
}

static void wr32(uint8_t *p, uint32_t v)
{
    p[0] = (uint8_t)v;
    p[1] = (uint8_t)(v >> 8);
    p[2] = (uint8_t)(v >> 16);
    p[3] = (uint8_t)(v >> 24);
}

/* Twos-complement bit reinterpretation without implementation-defined casts. */
static int32_t s32(uint32_t u)
{
    if ((u & 0x80000000u) == 0)
        return (int32_t)u;
    return -1 - (int32_t)(~u);
}

static uint32_t u32(int32_t s)
{
    if (s >= 0)
        return (uint32_t)s;
    return ~(uint32_t)(-1 - s);
}

static int16_t s16(uint16_t u)
{
    if ((u & 0x8000u) == 0)
        return (int16_t)u;
    return (int16_t)(-1 - (int16_t)(uint16_t)(~u));
}

static int32_t asr32(int32_t v, unsigned shift)
{
    uint32_t bits;
    if (shift == 0)
        return v;
    bits = u32(v) >> shift;
    if (v < 0)
        bits |= (~(uint32_t)0) << (32u - shift);
    return s32(bits);
}

static int32_t mul_lo32(int32_t a, int32_t b)
{
    uint64_t product = (uint64_t)u32(a) * (uint64_t)u32(b);
    return s32((uint32_t)product);
}

static int32_t add_wrap(int32_t a, int32_t b)
{
    return s32(u32(a) + u32(b));
}

static int32_t sub_wrap(int32_t a, int32_t b)
{
    return s32(u32(a) - u32(b));
}

static int16_t clamp16(int32_t v)
{
    if (v > INT16_MAX)
        return INT16_MAX;
    if (v < INT16_MIN)
        return INT16_MIN;
    return (int16_t)v;
}

static uint16_t nt_render_linear_env(uint8_t *state, size_t base)
{
    uint8_t env_state = state[base];
    int32_t value = s32(rd32(state + base + 0x0c));

    switch (env_state) {
    case 0:
        if (state[base + 7] != 0 || state[base + 4] != 0)
            state[base] = 1;
        break;
    case 1:
        value = add_wrap(value, (int32_t)rd16(state + base + 0x20));
        wr32(state + base + 0x0c, u32(value));
        if (state[base + 4] != 0) {
            if (value > 0x000ffffe) {
                state[base] = 4;
                if (value >= 0x00100000) {
                    value = 0x000fffff;
                    wr32(state + base + 0x0c, u32(value));
                }
            }
        } else if (value > 0x000ffffe) {
            state[base] = state[base + 6] == 0 ? 3 : 4;
            if (value >= 0x00100000) {
                value = 0x000fffff;
                wr32(state + base + 0x0c, u32(value));
            }
        }
        break;
    case 2:
        break;
    case 3:
        if (state[base + 7] == 0
            && (state[base + 4] != 0 || state[base + 0x10] == 0))
            state[base] = 4;
        break;
    case 4:
        if (state[base + 7] != 0) {
            state[base] = 1;
        } else {
            value = sub_wrap(value, (int32_t)rd16(state + base + 0x22));
            wr32(state + base + 0x0c, u32(value));
            if (value <= 0) {
                value = 0;
                wr32(state + base + 0x0c, 0);
                state[base] = state[base + 4] != 0 ? 1 : 0;
            }
        }
        break;
    default:
        break;
    }
    return (uint16_t)((u32(value) >> 4) & 0xffffu);
}

static int16_t nt_read_m1_wave(const uint8_t *table, uint32_t index)
{
    return s16(rd16(table + ((size_t)(index & 0x7ffu) * 2u)));
}

static int nt_m1_osc(uint8_t *state,
                     const uint8_t *wave_a, uint32_t wave_a_address,
                     const uint8_t *wave_b, uint32_t wave_b_address,
                     int16_t *result)
{
    const size_t base = 0xd4;
    uint32_t phase = rd32(state + base + 4);
    const uint32_t increment = rd32(state + base + 8);
    uint32_t current = rd32(state + base + 0x10);
    const uint8_t *table;
    uint32_t lookup_phase, phase_offset, index, next_index;
    int32_t fraction, first, second, delta, interpolated;

    phase += increment;
    wr32(state + base + 4, phase);
    if (s32(phase) > 0x00100000) {
        const uint32_t next = rd32(state + base + 0x14);
        phase -= 0x00100000u;
        wr32(state + base + 4, phase);
        if (next != current) {
            current = next;
            wr32(state + base + 0x10, current);
        }
    }

    if (current == wave_a_address)
        table = wave_a;
    else if (current == wave_b_address)
        table = wave_b;
    else
        return 0;

    lookup_phase = phase;
    phase_offset = rd32(state + base + 0x0c);
    if (phase_offset != 0) {
        lookup_phase += phase_offset;
        if (s32(lookup_phase) > 0x00100000)
            lookup_phase -= 0x00100000u;
    }

    index = (lookup_phase >> 9) & 0x7ffu;
    next_index = (index + 1u) & 0x7ffu;
    fraction = (int32_t)(lookup_phase & 0x1ffu);
    first = (int32_t)nt_read_m1_wave(table, index);
    second = (int32_t)nt_read_m1_wave(table, next_index);
    delta = second - first;
    interpolated = first + asr32(mul_lo32(delta, fraction), 9);
    *result = s16((uint16_t)interpolated);
    return 1;
}

int pk_cf_nt_m1_render(uint8_t state[PK_CF_NT_STATE_BYTES],
                       int16_t *destination,
                       uint32_t sample_count,
                       const uint8_t *wave_a,
                       uint32_t wave_a_address,
                       const uint8_t *wave_b,
                       uint32_t wave_b_address)
{
    uint32_t i;
    if (!state || !destination || !wave_a || !wave_b || state[0x75] != 0)
        return 0;

    for (i = 0; i < sample_count; ++i) {
        const uint16_t envelope = nt_render_linear_env(state, 0x74);
        const uint32_t phase = rd32(state + 0xd8);
        const uint32_t reduction = rd32(state + 0xc8);
        int16_t oscillator = 0;
        int32_t scaled, output;

        if (phase > reduction)
            wr32(state + 0xd8, phase - reduction);

        if (!nt_m1_osc(state, wave_a, wave_a_address,
                       wave_b, wave_b_address, &oscillator))
            return 0;

        if (state[0xb8] != 0) {
            destination[i] = 0;
            continue;
        }

        scaled = asr32(mul_lo32((int32_t)oscillator, (int32_t)envelope), 17);
        output = asr32(mul_lo32(scaled, (int32_t)state[6]), 8);
        destination[i] = clamp16(output);
    }
    return 1;
}

static uint16_t nt_table_u16(const uint8_t *table, size_t index)
{
    return rd16(table + index * 2u);
}

static int16_t nt_table_s16(const uint8_t *table, size_t index)
{
    return s16(nt_table_u16(table, index));
}

static const uint8_t *nt_find_wave(const pk_cf_nt_shared_tables *tables,
                                   uint32_t address)
{
    unsigned i;
    for (i = 0; i < 4; ++i)
        if (tables->waves[i].table && tables->waves[i].address == address)
            return tables->waves[i].table;
    return 0;
}

static uint16_t nt_shared_env(uint8_t *state, size_t base,
                              const pk_cf_nt_shared_tables *tables)
{
    uint8_t env_state = state[base];
    int32_t value = s32(rd32(state + base + 0x0c));
    uint8_t shape;
    const uint8_t *curve;
    uint32_t raw;
    size_t index, next;
    int32_t fraction, a, b;

    switch (env_state) {
    case 0:
        if (state[base + 7] != 0 || state[base + 4] != 0)
            state[base] = 1;
        break;
    case 1:
        value = s32(u32(value) + (uint32_t)rd16(state + base + 0x20));
        wr32(state + base + 0x0c, u32(value));
        if (state[base + 4] != 0) {
            if (value > 0x000ffffe) {
                state[base] = 4;
                if (value >= 0x00100000) {
                    value = 0x000fffff;
                    wr32(state + base + 0x0c, u32(value));
                }
            }
        } else if (value > 0x000ffffe) {
            state[base] = state[base + 6] == 0 ? 3 : 4;
            if (value >= 0x00100000) {
                value = 0x000fffff;
                wr32(state + base + 0x0c, u32(value));
            }
        }
        break;
    case 2:
        break;
    case 3:
        if (state[base + 7] == 0
            && (state[base + 4] != 0 || state[base + 0x10] == 0))
            state[base] = 4;
        break;
    case 4:
        if (state[base + 7] != 0) {
            state[base] = 1;
        } else {
            value = s32(u32(value) - (uint32_t)rd16(state + base + 0x22));
            wr32(state + base + 0x0c, u32(value));
            if (value <= 0) {
                value = 0;
                wr32(state + base + 0x0c, 0);
                state[base] = state[base + 4] != 0 ? 1 : 0;
            }
        }
        break;
    default:
        break;
    }

    shape = state[base + 1];
    if (shape != 1 && shape != 2)
        return (uint16_t)((u32(value) >> 4) & 0xffffu);
    curve = shape == 1 ? tables->envelope1 : tables->envelope2;
    if (!curve)
        return 0;

    raw = u32(value);
    index = (size_t)((raw >> 10) & 0x7ffu);
    next = (index + 1u) & 0x7ffu;
    fraction = (int32_t)(raw & 0x3ffu);
    a = (int32_t)nt_table_u16(curve, index);
    b = (int32_t)nt_table_u16(curve, next);
    return (uint16_t)(a + asr32(mul_lo32(b - a, fraction), 10));
}

static uint32_t nt_random(pk_cf_nt_rng *rng)
{
    const uint32_t a = 0x5851f42du;
    const uint32_t b = 0x4c957f2du;
    const uint32_t old_low = rng->low;
    const uint32_t old_high = rng->high;
    uint32_t accumulator = (uint32_t)((uint64_t)old_low * a);
    const uint64_t product = (uint64_t)old_low * b;
    const uint32_t product_low = (uint32_t)product;
    const uint32_t product_high = (uint32_t)(product >> 32);
    const uint32_t new_low = product_low + 1u;
    const uint32_t carry = new_low < product_low ? 1u : 0u;
    uint32_t new_high;

    accumulator += (uint32_t)((uint64_t)old_high * b);
    new_high = accumulator + product_high + carry;
    rng->low = new_low;
    rng->high = new_high;
    return new_high & 0x7fffffffu;
}

static int16_t nt_noise(uint8_t *state, size_t base, pk_cf_nt_rng *rng)
{
    const uint16_t count = rd16(state + base);
    int16_t result;
    if (count != 0) {
        wr16(state + base, (uint16_t)(count - 1u));
        return s16(rd16(state + base + 0x10));
    }
    wr16(state + base, rd16(state + base + 2));
    result = s16((uint16_t)nt_random(rng));
    wr16(state + base + 0x10, (uint16_t)result);
    return result;
}

static void nt_filter(uint8_t *state, size_t base, int32_t input)
{
    const uint16_t coefficient = rd16(state + base + 0x0e);
    int32_t velocity = s32(rd32(state + base + 0x18));
    int32_t product = mul_lo32(velocity, (int32_t)coefficient);
    int32_t first, second, damping, feedback;

    if (product < 0)
        product = s32(u32(product) + 0xffffu);
    first = s32(rd32(state + base + 0x10));
    first = s32(u32(first) + u32(asr32(product, 16)));
    if (first > 32767) first = 32767;
    else if (first < -32767) first = -32767;
    wr32(state + base + 0x10, u32(first));

    second = s32(u32(input) - u32(first));
    damping = mul_lo32(velocity, (int32_t)rd16(state + base + 0x0c));
    second = s32(u32(second) - u32(asr32(damping, 10)));
    if (second > 32767) second = 32767;
    else if (second < -32767) second = -32767;
    wr32(state + base + 0x14, u32(second));

    feedback = mul_lo32(second, (int32_t)coefficient);
    if (feedback < 0)
        feedback = s32(u32(feedback) + 0xffffu);
    velocity = s32(u32(velocity) + u32(asr32(feedback, 16)));
    if (velocity > 32767) velocity = 32767;
    else if (velocity < -32767) velocity = -32767;
    wr32(state + base + 0x18, u32(velocity));
}

static int nt_shared_osc(uint8_t *state, size_t base,
                         const pk_cf_nt_shared_tables *tables,
                         int16_t *result)
{
    uint32_t phase = rd32(state + base + 4) + rd32(state + base + 8);
    uint32_t current;
    const uint8_t *table;
    uint32_t index, next_index;
    int32_t fraction, first, second;

    wr32(state + base + 4, phase);
    current = rd32(state + base + 0x0c);
    if (s32(phase) > 0x00100000) {
        const uint32_t next = rd32(state + base + 0x10);
        phase -= 0x00100000u;
        wr32(state + base + 4, phase);
        if (next != current) {
            current = next;
            wr32(state + base + 0x0c, current);
        }
    }

    table = nt_find_wave(tables, current);
    if (!table)
        return 0;
    index = (phase >> 12) & 0xffu;
    next_index = (index + 1u) & 0xffu;
    fraction = (int32_t)(phase & 0xfffu);
    first = (int32_t)nt_table_s16(table, index);
    second = (int32_t)nt_table_s16(table, next_index);
    *result = s16((uint16_t)(first + asr32(mul_lo32(second - first, fraction), 12)));
    return 1;
}

int pk_cf_nt_shared_render(uint8_t state[PK_CF_NT_STATE_BYTES],
                           int16_t *destination,
                           uint32_t sample_count,
                           const pk_cf_nt_shared_tables *tables,
                           pk_cf_nt_rng *rng)
{
    uint32_t i;
    if (!state || !destination || !tables || !rng)
        return 0;

    for (i = 0; i < sample_count; ++i) {
        const uint16_t amplitude = nt_shared_env(state, 0x74, tables);
        const int32_t noise = (int32_t)nt_noise(state, 0x60, rng);
        const uint32_t mix_u = rd32(state + 0xf8);
        const int32_t mix = s32(mix_u);
        int32_t accumulator, oscillator_sum, tonal, output;
        int16_t oscillator1 = 0, oscillator2 = 0;

        nt_filter(state, 0x9c, noise);
        nt_filter(state, 0x9c, noise);
        accumulator = asr32(mul_lo32(mix, noise), 13);

        if (!nt_shared_osc(state, 0x2c, tables, &oscillator1)
            || !nt_shared_osc(state, 0xc4, tables, &oscillator2))
            return 0;

        oscillator_sum = asr32(s32((uint32_t)((int32_t)oscillator1
                                             + (int32_t)oscillator2)), 4);
        tonal = mul_lo32(s32(0x00000fffu - mix_u), oscillator_sum);
        accumulator = s32(u32(accumulator) + u32(asr32(tonal, 9)));
        output = asr32(mul_lo32(accumulator, (int32_t)amplitude), 16);
        output = asr32(mul_lo32(output, (int32_t)state[6]), 8);
        destination[i] = clamp16(output);
    }
    return 1;
}

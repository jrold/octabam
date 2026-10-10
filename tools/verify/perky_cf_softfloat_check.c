/* Host check for modules/perky/cf_softfloat.h: every soft op must produce the
 * same bits as the platform's own IEEE-754 single arithmetic. */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "cf_softfloat.h"

static uint64_t state = 0x243F6A8885A308D3ull;
static uint32_t rnd(void)
{
    state ^= state << 13;
    state ^= state >> 7;
    state ^= state << 17;
    return (uint32_t)(state >> 16);
}
static uint32_t f2b(float f) { uint32_t u; memcpy(&u, &f, 4); return u; }
static float b2f(uint32_t u) { float f; memcpy(&f, &u, 4); return f; }

static int failures = 0;
static unsigned checked = 0;

static void check_mul(uint32_t a, uint32_t b)
{
    const uint32_t got = pk_cf_f32_mul(a, b);
    const uint32_t want = f2b(b2f(a) * b2f(b));
    ++checked;
    if (got != want && failures < 12)
        printf("MUL a=%08x b=%08x got=%08x want=%08x\n", a, b, got, want);
    failures += (got != want);
}
static void check_add(uint32_t a, uint32_t b)
{
    const uint32_t got = pk_cf_f32_add(a, b);
    const uint32_t want = f2b(b2f(a) + b2f(b));
    ++checked;
    if (got != want && failures < 12)
        printf("ADD a=%08x b=%08x got=%08x want=%08x\n", a, b, got, want);
    failures += (got != want);
}
static void check_i2f(int32_t v)
{
    const uint32_t got = pk_cf_i32_to_f32(v);
    const uint32_t want = f2b((float)v);
    ++checked;
    if (got != want && failures < 12)
        printf("I2F v=%d got=%08x want=%08x\n", v, got, want);
    failures += (got != want);
}
static void check_f2i(uint32_t a)
{
    const int32_t got = pk_cf_f32_to_i32_trunc(a);
    const int32_t want = (int32_t)b2f(a);
    ++checked;
    if (got != want && failures < 12)
        printf("F2I a=%08x got=%d want=%d\n", a, got, want);
    failures += (got != want);
}

/* A finite, ordinary-magnitude single: exponent in [-30, 30]. */
static uint32_t ordinary(void)
{
    const uint32_t sign = (rnd() & 1u) ? 0x80000000u : 0u;
    const uint32_t e = 97u + (rnd() % 61u);          /* 2^-30 .. 2^30 */
    return sign | (e << 23) | (rnd() & 0x7fffffu);
}

int main(void)
{
    const uint32_t decay = 0x3F7AE148u;
    uint32_t i, j;
    /* i32 -> f32 over the whole range, exhaustively where it is cheap */
    for (i = 0; i < 0x800000u; i += 977u)
        check_i2f((int32_t)i - 0x400000);
    for (i = 0x7fff0000u; i != 0u; i += 0x10001u) {
        check_i2f((int32_t)i);
        check_i2f(-(int32_t)i);
    }
    check_i2f(0);
    check_i2f(1);  check_i2f(-1);
    check_i2f(0x7ffffff);  check_i2f(-0x7ffffff);
    check_i2f(-0x8000000); check_i2f(0x7ffffff);
    check_i2f(0x8000000);
    check_i2f(0x7fffffff);
    check_i2f((int32_t)0x80000000);
    /* small integers exactly (they are what the audio path produces) */
    for (i = 0; i < 200000u; ++i) {
        check_i2f((int32_t)i);
        check_i2f(-(int32_t)i);
        check_f2i(pk_cf_i32_to_f32((int32_t)i));
        check_f2i(pk_cf_i32_to_f32(-(int32_t)i));
    }
    /* the filter's exact operands */
    for (i = 0; i < 20000u; ++i) {
        const uint32_t p = pk_cf_i32_to_f32((int32_t)(rnd() % 4000000u) - 2000000);
        check_mul(p, decay);
        check_add(pk_cf_i32_to_f32((int32_t)(rnd() % 4000000u) - 2000000), p);
    }
    /* randoms, mul and add */
    for (i = 0; i < 4000000u; ++i) {
        const uint32_t a = ordinary(), b = ordinary();
        check_mul(a, b);
        check_add(a, b);
        check_mul(a, decay);
        check_add(a, decay);
    }
    /* exact cancellation and near-cancellation */
    for (i = 0; i < 200000u; ++i) {
        const uint32_t a = ordinary();
        const uint32_t b = a ^ 0x80000000u;
        check_add(a, b);
        j = 1u + (rnd() % 64u);
        check_add(a, (a ^ 0x80000000u));
        check_add(a, (a & 0xff800000u) | ((a + j) & 0x007fffffu));
    }
    printf("softfloat: %u operations checked, %d mismatches\n", checked, failures);
    return failures ? 1 : 0;
}

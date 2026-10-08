#ifndef OCTABAM_PERKY_CF_MATH_H
#define OCTABAM_PERKY_CF_MATH_H

#include <stdint.h>

/* Freestanding 32x32 helpers.  Keep the ColdFire runtime self-contained: these
 * avoid C uint64_t operations that may lower to libgcc calls on m68k-elf-gcc.
 * Results are exact modulo/two's-complement bit arithmetic. */
static inline uint32_t pk_cf_mul_hi_u32(uint32_t a, uint32_t b)
{
    const uint32_t a0 = a & 0xffffu;
    const uint32_t a1 = a >> 16;
    const uint32_t b0 = b & 0xffffu;
    const uint32_t b1 = b >> 16;
    const uint32_t p0 = a0 * b0;
    const uint32_t p1 = a0 * b1;
    const uint32_t p2 = a1 * b0;
    const uint32_t p3 = a1 * b1;
    const uint32_t middle = (p0 >> 16) + (p1 & 0xffffu) + (p2 & 0xffffu);
    return p3 + (p1 >> 16) + (p2 >> 16) + (middle >> 16);
}

static inline uint32_t pk_cf_mul_lo_u32(uint32_t a, uint32_t b)
{
    return a * b;
}

static inline int32_t pk_cf_mul_hi_s32(int32_t a, int32_t b)
{
    const uint32_t ua = (uint32_t)a;
    const uint32_t ub = (uint32_t)b;
    uint32_t hi = pk_cf_mul_hi_u32(ua, ub);
    if (a < 0)
        hi -= ub;
    if (b < 0)
        hi -= ua;
    return (int32_t)hi;
}

#endif

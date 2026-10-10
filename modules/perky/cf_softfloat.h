#ifndef OCTABAM_PERKY_CF_SOFTFLOAT_H
#define OCTABAM_PERKY_CF_SOFTFLOAT_H

#include <stdint.h>
#include "cf_math.h"

/* Exact binary32 (IEEE-754 single) building blocks for the one engine whose
 * renderer is float: Acoustic Hats' one-pole filter does
 *     decayed = previous * DECAY;   summed = input + previous;
 * and stores the single's bits in its object.
 *
 * The ColdFire build is freestanding -msoft-float with no libgcc helpers
 * linked, so the arithmetic is written here in 32-bit integers with
 * round-to-nearest-ties-to-even, exactly the operations the ARM's VFP would
 * perform.  Everything is plain 32-bit: a 64-bit multiply would emit
 * __muldi3, which the link cannot resolve.
 *
 * Validated against the host's own float by
 * tools/verify/verify_perky_cf_softfloat.py (exhaustive over small integers
 * and the captured filter values, plus millions of random pairs).
 */

static inline int32_t pk_cf_clz32(uint32_t x)
{
    int32_t n = 0;
    if (x == 0u)
        return 32;
    while (!(x & 0x80000000u)) {
        x <<= 1;
        ++n;
    }
    return n;
}

/* Assemble a finite single from an unbiased exponent, a 24-bit mantissa
 * (implicit bit set) and the two rounding bits below it.  e is clipped the
 * same way a hardware op would: 128+ overflows to infinity, -126 and below
 * flushes to a subnormal or zero.  The renderer only ever lands in the normal
 * range; the tails exist so the routine is total. */
static inline uint32_t pk_cf_f32_pack(uint32_t sign, int32_t e,
                                      uint32_t mant, uint32_t guard,
                                      uint32_t sticky)
{
    if (guard && (sticky || (mant & 1u)))
        ++mant;
    if (mant & 0x1000000u) {
        mant >>= 1;
        ++e;
    }
    if (e >= 128)
        return sign | 0x7f800000u;
    if (e >= -126)
        return sign | ((uint32_t)(e + 127) << 23) | (mant & 0x7fffffu);
    /* Subnormal: shift the mantissa down with one more round-to-nearest. */
    {
        const uint32_t sh = (uint32_t)(-126 - e) + 1u;
        if (sh > 24u)
            return sign;
        sticky = sticky || ((mant & ((1u << sh) - 1u)) != 0u);
        mant >>= sh;
        if ((mant & 1u) && sticky)
            ++mant;
        if (mant & 0x800000u)
            return sign | ((uint32_t)(e + 127 + (int32_t)sh) << 23);
        return sign | mant;
    }
}

static inline uint32_t pk_cf_f32_mul(uint32_t a, uint32_t b)
{
    const uint32_t sign = (a ^ b) & 0x80000000u;
    int32_t ea = (int32_t)((a >> 23) & 0xffu);
    int32_t eb = (int32_t)((b >> 23) & 0xffu);
    uint32_t ma = a & 0x7fffffu, mb = b & 0x7fffffu;
    uint32_t hi, lo, mant, guard, sticky;
    int32_t e;
    if ((ea == 0 && ma == 0u) || (eb == 0 && mb == 0u))
        return sign;                       /* a real zero times a finite value */
    if (ea == 0xff || eb == 0xff)
        return sign | 0x7f800000u;         /* inf/nan: never reached here */
    if (ea == 0) {
        e = -126;
        while (!(ma & 0x800000u)) { ma <<= 1; --e; }
    } else {
        e = ea - 127;
        ma |= 0x800000u;
    }
    if (eb == 0) {
        int32_t f = -126;
        while (!(mb & 0x800000u)) { mb <<= 1; --f; }
        e += f;
    } else {
        e += eb - 127;
        mb |= 0x800000u;
    }
    /* The 48-bit product P = hi<<32 | lo; its leading bit is 46 or 47. */
    hi = pk_cf_mul_hi_u32(ma, mb);
    lo = pk_cf_mul_lo_u32(ma, mb);
    if (hi & 0x8000u) {
        mant = (hi << 8) | (lo >> 24);
        guard = (lo >> 23) & 1u;
        sticky = (lo & 0x7fffffu) != 0u;
        ++e;
    } else {
        mant = (hi << 9) | (lo >> 23);
        guard = (lo >> 22) & 1u;
        sticky = (lo & 0x3fffffu) != 0u;
    }
    return pk_cf_f32_pack(sign, e, mant, guard, sticky);
}

static inline uint32_t pk_cf_i32_to_f32(int32_t v);

static inline uint32_t pk_cf_f32_add(uint32_t a, uint32_t b)
{
    uint32_t sa = a & 0x80000000u;
    uint32_t sb = b & 0x80000000u;
    int32_t ea = (int32_t)((a >> 23) & 0xffu);
    int32_t eb = (int32_t)((b >> 23) & 0xffu);
    uint32_t ma = a & 0x7fffffu, mb = b & 0x7fffffu;
    int32_t e, f, d, h, eps;
    uint32_t MA, MB, big, small, V, sign, guard, rest, g, s;
    if (ea == 0 && ma == 0u)
        return b;
    if (eb == 0 && mb == 0u)
        return a;
    if (ea == 0xff || eb == 0xff)
        return sa | 0x7f800000u;
    if (ea == 0) {
        e = -126;
        MA = ma;
        while (!(MA & 0x800000u)) { MA <<= 1; --e; }
    } else {
        e = ea - 127;
        MA = ma | 0x800000u;
    }
    if (eb == 0) {
        f = -126;
        MB = mb;
        while (!(MB & 0x800000u)) { MB <<= 1; --f; }
    } else {
        f = eb - 127;
        MB = mb | 0x800000u;
    }
    if (e < f) {                                   /* keep the larger exponent in a */
        const int32_t t = e;
        const uint32_t u = MA, v = sa;
        e = f;
        f = t;
        MA = MB;
        MB = u;
        sa = sb;
        sb = v;
    }
    sign = sa;
    d = e - f;
    /* Align both mantissas in a 27-bit field (leading bit 26, three bits below
     * the 24-bit result).  big = MA<<3 is exact; small = MB * 2^(3-d) exactly
     * for d <= 3, and otherwise an integer part plus a sub-unit remainder. */
    big = MA << 3;
    if (d <= 3) {
        small = MB << (3 - d);
        eps = 0;
    } else if (d < 35) {
        const uint32_t k = (uint32_t)(d - 3);
        small = MB >> k;
        eps = ((MB & ((1u << k) - 1u)) != 0u) ? 1 : 0;
    } else {
        small = 0u;
        eps = 1;
    }
    if (sign == sb) {
        V = big + small;
    } else if (big > small) {
        V = big - small;
        eps = -eps;
    } else if (big < small) {
        V = small - big;
        sign = sb;
    } else if (eps == 0) {
        return 0u;                                 /* exact cancellation */
    } else {
        /* MA == MB >> d exactly: the true difference is the bits the field
         * could not hold, and it is exactly representable. */
        const uint32_t R = MB & ((1u << (uint32_t)d) - 1u);
        const uint32_t r32 = pk_cf_i32_to_f32((int32_t)R);
        return (sb == 0u) ? (r32 + ((uint32_t)(f - 23) << 23))
                          : ((r32 + ((uint32_t)(f - 23) << 23)) | 0x80000000u);
    }
    if (V == 0u)
        return sign;
    h = 31 - pk_cf_clz32(V);
    if (h < 23)
        return pk_cf_f32_pack(sign, e + h - 26, V << (23 - h), 0u, 0u);
    guard = (h >= 24) ? ((V >> (h - 24)) & 1u) : 0u;
    rest = (h >= 25) ? (V & ((1u << (h - 24)) - 1u)) : 0u;
    if (eps == 0) {
        g = guard;
        s = (rest != 0u);
    } else if (eps > 0) {
        g = guard;
        s = 1u;
    } else if (rest != 0u) {
        g = guard;
        s = 1u;
    } else {
        g = 0u;                                    /* just below the boundary */
        s = 1u;
    }
    return pk_cf_f32_pack(sign, e + h - 26, V >> (h - 23), g, s);
}

static inline uint32_t pk_cf_i32_to_f32(int32_t v)
{
    uint32_t sign, m, mant, guard, sticky;
    int32_t h;
    if (v == 0)
        return 0u;
    sign = (v < 0) ? 0x80000000u : 0u;
    m = (uint32_t)v;
    if (v < 0)
        m = 0u - m;
    h = 31 - pk_cf_clz32(m);
    if (h <= 23) {
        mant = m << (23 - h);
        guard = 0u;
        sticky = 0u;
    } else {
        mant = m >> (h - 23);
        guard = (m >> (h - 24)) & 1u;
        sticky = (m & ((1u << (h - 24)) - 1u)) != 0u;
    }
    return pk_cf_f32_pack(sign, h, mant, guard, sticky);
}

static inline int32_t pk_cf_f32_to_i32_trunc(uint32_t a)
{
    const int32_t e = (int32_t)((a >> 23) & 0xffu) - 127;
    const uint32_t m = (a & 0x7fffffu) | 0x800000u;
    uint32_t mag;
    if (e < 0)
        return 0;
    if (e > 30)
        return (a & 0x80000000u) ? (int32_t)0x80000000 : (int32_t)0x7fffffff;
    mag = (e <= 23) ? (m >> (23 - e)) : (m << (e - 23));
    return (a & 0x80000000u) ? (int32_t)(0u - mag) : (int32_t)mag;
}

#endif

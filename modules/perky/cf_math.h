#ifndef OCTABAM_PERKY_CF_MATH_H
#define OCTABAM_PERKY_CF_MATH_H

#include <stdint.h>
#include <stddef.h>

/* ---- word/long state access ------------------------------------------------
 * Every engine object is the byte image of an ARM firmware object, stored
 * little-endian; the ColdFire is big-endian, so a plain word/long load is
 * byte-reversed.  The byte-wise r16/r32/w16/w32 helpers the engines used cost
 * 4-11 instructions each (mvz.b / lsl / or ladders), and the synthesised
 * objects are read and written tens of times per sample, so they dominated
 * the frame.  These do the access plus the byte swap in 2-4 instructions.
 *
 * Safety: every state array in cf_perky4.h is a multiple of four bytes long
 * and every field offset the engines touch is even, so no access lands on an
 * odd address (which a real ColdFire faults on).  The inline asm keeps the
 * constant displacement visible in the generated assembly, so
 * tools/verify/verify_perky_cf_odd_access.py still audits every one of them.
 *
 * The host builds (x86, little-endian) take the portable branch and produce
 * exactly the same values, which is what the fixtures were captured from. */
#if defined(__mcoldfire__)
/* BYTEREV is a ColdFire V4e instruction (0x02c0) that reverses a data
 * register's four bytes in one cycle-class op, and leaves the condition codes
 * alone. The stock MAIN OS image already executes one at 0x4004098e, so the
 * part has it; the emulator implements the same semantics (tools/emu/ot_emu/
 * v4e.cpp). One load plus one byterev replaces an 11-instruction mvz.b/lsl/or
 * ladder. */
static inline uint32_t pk_cf_ld32(const uint8_t *p, size_t o)
{
    uint32_t v;
    __asm__("move.l %1,%0\n\tbyterev %0"
            : "=d"(v) : "m"(*(const uint32_t *)(const void *)(p + o)));
    return v;
}
static inline void pk_cf_st32(uint8_t *p, size_t o, uint32_t v)
{
    __asm__("byterev %0\n\tmove.l %0,%1"
            : "+d"(v), "=m"(*(uint32_t *)(void *)(p + o)));
}
/* A 32-bit load reversed gives the little-endian long; its LOW word is the
 * little-endian 16-bit field, so a word read is the same pair. The two extra
 * bytes are read from inside the same object (or asset table) and discarded. */
static inline uint16_t pk_cf_ld16(const uint8_t *p, size_t o)
{
    uint32_t v;
    __asm__("move.l %1,%0\n\tbyterev %0"
            : "=d"(v) : "m"(*(const uint32_t *)(const void *)(p + o)));
    return (uint16_t)v;
}
static inline void pk_cf_st16(uint8_t *p, size_t o, uint16_t v)
{
    p[o] = (uint8_t)v;
    p[o + 1] = (uint8_t)(v >> 8);
}
#else
static inline uint16_t pk_cf_ld16(const uint8_t *p, size_t o)
{
    return (uint16_t)((uint16_t)p[o] | (uint16_t)((uint16_t)p[o + 1] << 8));
}
static inline uint32_t pk_cf_ld32(const uint8_t *p, size_t o)
{
    return (uint32_t)p[o] | ((uint32_t)p[o + 1] << 8)
         | ((uint32_t)p[o + 2] << 16) | ((uint32_t)p[o + 3] << 24);
}
static inline void pk_cf_st16(uint8_t *p, size_t o, uint16_t v)
{
    p[o] = (uint8_t)v;
    p[o + 1] = (uint8_t)(v >> 8);
}
static inline void pk_cf_st32(uint8_t *p, size_t o, uint32_t v)
{
    p[o] = (uint8_t)v;
    p[o + 1] = (uint8_t)(v >> 8);
    p[o + 2] = (uint8_t)(v >> 16);
    p[o + 3] = (uint8_t)(v >> 24);
}
#endif

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

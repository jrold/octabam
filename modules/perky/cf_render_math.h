#ifndef OCTABAM_PERKY_CF_RENDER_MATH_H
#define OCTABAM_PERKY_CF_RENDER_MATH_H
#include "cf_math.h"

/* Exact high products for the two positive constants used by CF rendering.
 * Fractional EMAC without rounding yields product >> 31; shifting once more
 * gives the signed high word. Both constants are positive and below INT_MAX,
 * so that intermediate always fits signed 32 bits, including INT_MIN input.
 * Save raw accumulator bits in integer mode, including its extension, and
 * restore MACSR exactly. Every public renderer brackets all helper use. */
#if defined(__mcoldfire__)
typedef struct { uint32_t status,low,extension; } pk_cf_render_math_context;
static inline pk_cf_render_math_context pk_cf_render_math_begin(void){
    pk_cf_render_math_context c;
    __asm__ volatile(
        "move.l %%macsr,%0\n\t"
        "move.l #0,%%macsr\n\t"
        "move.l %%acc0,%1\n\t"
        "move.l %%accext01,%2\n\t"
        "move.l #0,%%acc0\n\t"
        "move.l #0x20,%%macsr"
        : "=&d"(c.status),"=&d"(c.low),"=&d"(c.extension) :: "cc","memory");
    return c;
}
static inline void pk_cf_render_math_end(pk_cf_render_math_context c){
    __asm__ volatile(
        "move.l #0,%%macsr\n\t"
        "move.l %0,%%acc0\n\t"
        "move.l %1,%%accext01\n\t"
        "move.l %2,%%macsr"
        :: "d"(c.low),"d"(c.extension),"d"(c.status) : "cc","memory");
}
/* Read a spilled context directly. Passing a volatile struct by value makes
 * GCC copy all twelve bytes before restoring it (and can emit memcpy at Os).
 * Keep the value entry above for renderers whose allocation is better there. */
static inline void pk_cf_render_math_end_saved(const volatile pk_cf_render_math_context *c){
    __asm__ volatile(
        "move.l #0,%%macsr\n\t"
        "move.l %0,%%acc0\n\t"
        "move.l %1,%%accext01\n\t"
        "move.l %2,%%macsr"
        :: "d"(c->low),"d"(c->extension),"d"(c->status) : "cc","memory");
}
static inline int32_t pk_cf_render_frequency_hi(int32_t a){
    int32_t out;const int32_t b=0x057619f1;
    __asm__ volatile("mac.l %1,%2,%%acc0\n\tmovclr.l %%acc0,%0"
        : "=d"(out) : "d"(a),"d"(b) : "cc");
    return out>>1;
}
static inline uint32_t pk_cf_render_rng_hi(uint32_t a){
    int32_t out;const uint32_t b=0x4c957f2du;
    __asm__ volatile("mac.l %1,%2,%%acc0\n\tmovclr.l %%acc0,%0"
        : "=d"(out) : "d"(a),"d"(b) : "cc");
    return (uint32_t)(out>>1)+((int32_t)a<0?b:0u);
}
#else
typedef struct { uint32_t unused; } pk_cf_render_math_context;
static inline pk_cf_render_math_context pk_cf_render_math_begin(void){pk_cf_render_math_context c={0};return c;}
static inline void pk_cf_render_math_end(pk_cf_render_math_context c){(void)c;}
static inline void pk_cf_render_math_end_saved(const volatile pk_cf_render_math_context *c){(void)c;}
static inline int32_t pk_cf_render_frequency_hi(int32_t a){return pk_cf_mul_hi_s32(a,0x057619f1);}
static inline uint32_t pk_cf_render_rng_hi(uint32_t a){return pk_cf_mul_hi_u32(a,0x4c957f2du);}
#endif
#endif

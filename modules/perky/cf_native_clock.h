#ifndef OCTABAM_PERKY_CF_NATIVE_CLOCK_H
#define OCTABAM_PERKY_CF_NATIVE_CLOCK_H
#include <stdint.h>

/* Experimental 48 kHz source -> 44.1 kHz OT adapter. The caller owns native
 * synthesis, independent state and trigger/algorithm resets. Output is signed
 * 24-bit source PCM with the same exact x32 gain as the qualified DSP path.
 * Division rounds toward minus infinity, matching source_clock.Clock.
 */
typedef struct { uint32_t phase, have; int32_t carry; } pk_cf_native_clock;
static inline void pk_cf_native_reset(pk_cf_native_clock *c)
{ c->phase=0; c->have=0; c->carry=0; }
static inline uint32_t pk_cf_native_needed(const pk_cf_native_clock *c,uint32_t n)
{
    uint32_t sum=c->phase+13u*n,extra=sum/147u,phase=sum-147u*extra;
    return n+extra+(phase>=13u)-c->have;
}
static inline void pk_cf_native_convert(pk_cf_native_clock *c,const int16_t *data,
                                        uint32_t n,int32_t *out)
{
    uint32_t i,index=0,phase=c->phase;
    for(i=0;i<n;i++) {
        int32_t a=data[index],b=phase?data[index+1]:a;
        int32_t product=(b-a)*32*(int32_t)phase;
        int32_t correction=product<0?-(int32_t)(((uint32_t)-product+146u)/147u):product/147;
        out[i]=a*32+correction;
        phase+=13u;index++;
        if(phase>=147u){phase-=147u;index++;}
    }
    c->phase=phase;c->have=phase>=13u;
    c->carry=c->have?data[index]:0;
}
#endif

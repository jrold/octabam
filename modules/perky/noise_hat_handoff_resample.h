#ifndef PERKY_NOISE_HAT_HANDOFF_RESAMPLE_H
#define PERKY_NOISE_HAT_HANDOFF_RESAMPLE_H
#include "cf_native_clock.h"
#include NHB_CLOCK_TABLE
/* n = (high<<16)+low. Table stores quotient and remainder of high<<16.
 * The remaining t is <=65681. For that range, (t*57066)>>23 is exactly
 * floor(t/147), including every multiple; both multiplication and sum fit u32.
 * The guard retains general u32 behavior outside the int16 audio bound.
 */
static inline uint32_t pk_nhb_div147(uint32_t n)
{
    if(n>306179666u)return n/147u;
    uint32_t packed=nhb_div147_high[n>>16];
    uint32_t t=(n&65535u)+(packed&255u);
    return (packed>>8)+((t*57066u)>>23);
}
static inline uint32_t pk_nhb_native_needed(const pk_cf_native_clock*c,uint32_t n)
{
    if(n>16u||c->phase>=147u)return pk_cf_native_needed(c,n);
    uint32_t sum=c->phase+13u*n,extra=sum>=294u?2u:sum>=147u;
    uint32_t phase=sum-147u*extra;
    return n+extra+(phase>=13u)-c->have;
}
static inline void pk_nhb_native_convert(pk_cf_native_clock*c,const int16_t*data,
                                         uint32_t n,int32_t*out)
{
    uint32_t i,index=0,phase=c->phase;
    for(i=0;i<n;i++){
        int32_t a=data[index],b=phase?data[index+1]:a;
        int32_t product=(b-a)*32*(int32_t)phase;
        int32_t correction=product<0?-(int32_t)pk_nhb_div147((uint32_t)-product+146u):
                                       (int32_t)pk_nhb_div147((uint32_t)product);
        out[i]=a*32+correction;
        phase+=13u;index++;
        if(phase>=147u){phase-=147u;index++;}
    }
    c->phase=phase;c->have=phase>=13u;c->carry=c->have?data[index]:0;
}
/* Probe-local substitution: the shared native clock and author renderer remain
 * unchanged and are the independent source-audio oracle. */
#define pk_cf_native_needed pk_nhb_native_needed
#ifdef __mcoldfire__
void pk_nhb_native_convert_fast(pk_cf_native_clock*,const int16_t*,uint32_t,int32_t*);
#define pk_cf_native_convert pk_nhb_native_convert_fast
#else
#define pk_cf_native_convert pk_nhb_native_convert
#endif
#endif

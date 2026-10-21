#ifndef OCTABAM_NOISE_HAT_HANDOFF_CLOCK_H
#define OCTABAM_NOISE_HAT_HANDOFF_CLOCK_H
#include "cf_native_clock.h"
/* The background shadow needs only the converter's final phase/carry. No
 * interpolated output is consumed there. This is the closed form of the
 * existing converter's index/phase loop, with exactly the same native FIFO.
 */
static inline void pk_nhb_advance_clock(pk_cf_native_clock*c,const int16_t*pcm,unsigned n)
{
    unsigned sum=c->phase+13u*n,extra=sum/147u;
    c->phase=sum-147u*extra;c->have=c->phase>=13u;
    c->carry=c->have?pcm[n+extra]:0;
}
#endif

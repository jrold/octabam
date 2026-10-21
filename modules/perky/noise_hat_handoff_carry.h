#ifndef OCTABAM_NOISE_HAT_HANDOFF_CARRY_H
#define OCTABAM_NOISE_HAT_HANDOFF_CARRY_H
#include <stdint.h>
/* Only the resampler's retained sample needs a delayed output in the inner
 * shadow. These are the existing five fixed stages, with the exact signed
 * shifts, saturation and final int16 wrap of nh_delay_step. Inputs were
 * captured from the very taps sent to A, so no mutable ring is read here.
 */
static inline int16_t pk_nhb_delay_carry(int16_t input,int mix,const uint16_t*taps)
{
    static const int gains[5]={1,1,3,5,7};int stage=input;
    for(unsigned k=0;k<5;k++){
        stage=(stage*(gains[k]-16)+gains[k]*(int16_t)taps[k])>>4;
        if(stage>32767)stage=32767;else if(stage< -32767)stage= -32767;
    }
    return (int16_t)((input*(4095-mix)+mix*((stage*5)>>1))>>12);
}
#endif

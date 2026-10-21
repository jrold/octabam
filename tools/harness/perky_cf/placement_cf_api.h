#ifndef OCTABAM_PLACEMENT_CF_API_H
#define OCTABAM_PLACEMENT_CF_API_H
#include <stdint.h>
extern uint32_t placement_inputs[4][10],placement_mask,placement_status;
extern uint32_t placement_packets[4][40],placement_calls[4],placement_native_samples[4];
extern int32_t placement_output[4][16];
void placement_bind(const uint8_t *const p[16]);
void placement_init(void);
int placement_prepare(unsigned tr,const uint32_t *input,int trig);
int placement_segment(unsigned tr,uint32_t start,uint32_t end,unsigned trace_half);
void placement_pack(unsigned tr,unsigned split);
#endif

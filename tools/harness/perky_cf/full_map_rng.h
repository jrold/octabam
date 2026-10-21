/* Exact white-noise/hold progression, without the filter or delay work.
 * The DSP and CF alternatives share the original per-voice RNG. Keeping
 * these few fields current avoids a state round-trip on ALGO changes. */
#include "cf_render_math.h"
__attribute__((noinline)) void fm_hat_noise(unsigned mode,unsigned n)
{
 if(mode!=1||!n)return;
 pk4_track*t=&placement_engine.tracks[3];uint8_t*s=t->nh;
 unsigned count=pk_cf_ld16(s,0x378),value=pk_cf_ld16(s,0x388);
 unsigned reload=pk_cf_ld16(s,0x37a),hold=placement_engine.nh_hold[0];
 unsigned hold_value=placement_engine.nh_hold[1],hold_reload=pk_cf_ld16(s,0x3dc);
 pk_cf_render_math_context context=pk_cf_render_math_begin();
 for(unsigned i=0;i<n;i++){
  if(hold){hold--;continue;}
  if(count)count--;
  else{
   uint32_t lo=t->rng_low,hi=t->rng_high,product=lo*0x4c957f2du;
   uint32_t next=product+1u;
   t->rng_high=lo*0x5851f42du+hi*0x4c957f2du+pk_cf_render_rng_hi(lo)+(next<product);
   t->rng_low=next;value=(uint16_t)(t->rng_high&0x7fffffffu);count=reload;
  }
  hold_value=value;hold=hold_reload;
 }
 pk_cf_render_math_end(context);
 pk_cf_st16(s,0x378,(uint16_t)count);pk_cf_st16(s,0x388,(uint16_t)value);
 placement_engine.nh_hold[0]=(uint16_t)hold;placement_engine.nh_hold[1]=(uint16_t)hold_value;
}

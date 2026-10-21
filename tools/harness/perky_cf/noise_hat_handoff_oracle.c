#include <string.h>
/* Independent persistent original-author stream. Target state is read ONCE
 * before the first frame; later controls, native state and clocks evolve here.
 * No handoff snapshots, target post-state or DSP patch lists enter this model.
 */
#include "noise_hat_controls_oracle.c"
#include "cf_native_clock.h"
extern void pk_nha_codec(uint8_t*,unsigned,uint16_t*,int);
static uint8_t stream_raw[PK_CF_NH_WRAPPER_BYTES];
static pk4_control stream_control;
static pk4_assets stream_assets;
static pk_cf_nh_rng stream_rng;
static uint16_t stream_hold[2];
static pk_cf_native_clock stream_clock;
static unsigned stream_mode;
void nhb_original_init(const uint8_t*raw,const uint32_t*targets,const uint8_t*tail,
 const uint32_t*side,const uint32_t*clock,unsigned mode,const uint8_t*pitch,
 const uint8_t*chromatic,const uint8_t*env1,const uint8_t*env2)
{
    memcpy(stream_raw,raw,sizeof(stream_raw));
    for(unsigned i=0;i<4;i++){stream_control.targets[i]=targets[i];stream_control.last_raw[i]=tail[i];}
    stream_control.last_mode=tail[4];stream_control.valid=tail[5];
    stream_assets.pitch=pitch;stream_assets.chromatic=chromatic;
    stream_assets.envelope1=env1;stream_assets.envelope2=env2;
    stream_rng.low=side[0];stream_rng.high=side[1];stream_hold[0]=side[2];stream_hold[1]=side[3];
    stream_clock.phase=clock[0];stream_clock.have=clock[1];stream_clock.carry=(int32_t)clock[2];stream_mode=mode;
}
static void stream_segment(unsigned n,int32_t*out)
{
    if(!n)return;
    int16_t data[20];unsigned have=stream_clock.have,need=pk_cf_native_needed(&stream_clock,n);
    if(have)data[0]=(int16_t)stream_clock.carry;
    pk_cf_nh_tables tables={stream_assets.envelope1,stream_assets.envelope2};
    if(!pk_cf_nh_render(stream_raw+(nh_mode(stream_mode)==2?NH_PULSE:0),data+have,need,
                        nh_mode(stream_mode),&tables,&stream_rng,stream_hold))__builtin_trap();
    pk_cf_native_convert(&stream_clock,data,n,out);
}
void nhb_original_prefix(unsigned split,int32_t*out)
{stream_segment(split,out);}
void nhb_original_event(const uint8_t raw[4],unsigned mode,unsigned vel,unsigned note,int trig,
 unsigned split,int32_t*out,uint16_t*state,uint16_t*side,uint32_t*clock,uint16_t*ring)
{
    if(trig)pk_cf_native_reset(&stream_clock);
    prepare_nh(&stream_control,stream_raw,raw,mode,vel,note,trig,&stream_assets);
    stream_mode=mode;stream_segment(16-split,out+split);
    pk_nha_codec(stream_raw,0,state,0);pk_nha_codec(stream_raw,1,state,0);pk_nha_codec(stream_raw+NH_PULSE,2,state+121,0);
    side[0]=stream_hold[0];side[1]=stream_hold[1];side[2]=stream_rng.low;side[3]=stream_rng.low>>16;
    side[4]=stream_rng.high;side[5]=stream_rng.high>>16;
    clock[0]=stream_clock.phase;clock[1]=stream_clock.have;clock[2]=(uint32_t)stream_clock.carry;
    for(unsigned i=0;i<4805;i++)ring[i]=pk_cf_ld16(stream_raw,0x3f8+2*i);
    clock[3]=pk_cf_ld16(stream_raw,0x2982);
}

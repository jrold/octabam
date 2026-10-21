/* Whole-machine observer reference. Original renderer/control implementation,
 * original initializers and independent persistent state; no target snapshots.
 */
#include <string.h>
#include "placement_cf_engine.c"
extern void pk_nha_codec(uint8_t*,unsigned,uint16_t*,int);
static pk4_engine fm_pristine;
static uint8_t fm_ah_initial[PK_CF_AH_STATE_BYTES];
static unsigned fm_generation[4],fm_first[4],fm_writes[60],fm_count;
void fm_ref_init(const uint8_t*const*assets)
{
 placement_bind(assets);placement_init();fm_pristine=placement_engine;
 memcpy(fm_ah_initial,placement_ah_state,sizeof(fm_ah_initial));
 for(unsigned i=0;i<4;i++){fm_generation[i]=0;fm_first[i]=1;}
 fm_count=0;
}
void fm_ref_start(void){fm_count=0;}
int fm_ref_segment(unsigned tr,unsigned start,unsigned end)
{
 unsigned before=pk_cf_ld16(placement_engine.tracks[3].nh,0x2982);
 unsigned algo=placement_engine.tracks[3].active_algo;
 int ok=placement_segment(tr,start,end,start?1:0);
 if(tr==3&&algo==PK4_ALGO_NOISE_HAT){
  unsigned after=pk_cf_ld16(placement_engine.tracks[3].nh,0x2982);
  while(before!=after){if(++before==4805)before=0;if(fm_count>=20)return 0;
   fm_writes[3*fm_count]=fm_generation[3];fm_writes[3*fm_count+1]=before;
   fm_writes[3*fm_count+2]=pk_cf_ld16(placement_engine.tracks[3].nh,0x3f8+2*before);fm_count++;
  }
 }
 return ok;
}
int fm_ref_prepare(unsigned tr,const uint32_t*input,unsigned generation)
{
 pk4_track*t=&placement_engine.tracks[tr];const pk4_track*p=&fm_pristine.tracks[tr];unsigned algo=input[0];
 if(fm_generation[tr]!=generation){
  if(!fm_first[tr])t->initialized_mask=0;
  fm_first[tr]=0;fm_generation[tr]=generation;t->rng_low=1;t->rng_high=0;
  pk_cf_native_reset(&placement_clocks[tr]);
  if(tr==3)placement_engine.nh_hold[0]=placement_engine.nh_hold[1]=0;
 }
 unsigned bit=1u<<algo;
 if(!(t->initialized_mask&bit)){
#define FM_COPY(field,control) memcpy(t->field,p->field,sizeof(t->field));t->control=p->control
  switch(algo){
  case PK4_ALGO_FOLD1:FM_COPY(fold1,fold1_ctl);break;
  case PK4_ALGO_FOLD2:FM_COPY(fold2,fold2_ctl);break;
  case PK4_ALGO_WAVETABLE:FM_COPY(wt,wt_ctl);break;
  case PK4_ALGO_SIMPLE_DRUM:FM_COPY(sd,sd_ctl);break;
  case PK4_ALGO_COMPLEX_DRUM:FM_COPY(cd,cd_ctl);break;
  case PK4_ALGO_SLAP:FM_COPY(slap,slap_ctl);break;
  case PK4_ALGO_KARPLUS:FM_COPY(karplus,karplus_ctl);break;
  case PK4_ALGO_NOISE_HAT:FM_COPY(nh,nh_ctl);break;
  case PK4_ALGO_NOISE_TONE:FM_COPY(nt_m1,nt_m1_ctl);FM_COPY(nt_shared,nt_shared_ctl);break;
  case PK4_ALGO_RESONANT:FM_COPY(res_snare,res_snare_ctl);FM_COPY(res_bass,res_bass_ctl);FM_COPY(res_nt,res_nt_ctl);break;
  case 10:memcpy(placement_ah_state,fm_ah_initial,sizeof(fm_ah_initial));memset(&placement_ah_control,0,sizeof(placement_ah_control));placement_ah_hold=0;break;
  default:return 0;
  }
#undef FM_COPY
  t->initialized_mask|=bit;
 }
 return placement_prepare(tr,input,input[9]!=0);
}
void fm_ref_pcm(unsigned tr,int32_t*out){memcpy(out,placement_output[tr],64);}
unsigned fm_ref_hat(uint16_t*state,uint16_t*side,unsigned*writes)
{
 pk4_track*t=&placement_engine.tracks[3];uint8_t*s=t->nh;
 pk_nha_codec(s,0,state,0);pk_nha_codec(s,1,state,0);pk_nha_codec(s+NH_PULSE,2,state+121,0);
 side[0]=placement_engine.nh_hold[0];side[1]=placement_engine.nh_hold[1];
 side[2]=t->rng_low;side[3]=t->rng_low>>16;side[4]=t->rng_high;side[5]=t->rng_high>>16;
 memcpy(writes,fm_writes,3*fm_count*sizeof(unsigned));return fm_count;
}
void fm_ref_clock(unsigned tr,unsigned*out){out[0]=placement_clocks[tr].phase;out[1]=placement_clocks[tr].have;out[2]=placement_clocks[tr].carry;}

unsigned fm_ref_hat_valid(void){return !!(placement_engine.tracks[3].initialized_mask&(1u<<PK4_ALGO_NOISE_HAT));}

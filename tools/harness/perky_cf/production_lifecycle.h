/* Candidate integration, deliberately separate from the qualified F7 path.
 * Uses the production Bank/Part generation and staged six-control ABI.
 * Audio owns resets. Inactive algorithm objects are reset on first use in
 * the new generation, never by the UI task. The reference image stays F7.
 */
static pk4_engine placement_pristine;
uint32_t pk_prod_generation,pk_prod_voice_generation[4],pk_prod_resets[4];
uint32_t pk_prod_algorithms[4],pk_prod_modes[4];
uint32_t pk_prod_last_reset[4];
static unsigned pk_prod_first[4];
extern void pk_prod_copy(void*,const void*,unsigned);
#define prod_copy pk_prod_copy
#include "production_sparse.h"
void placement_production_init(void)
{prod_copy(&placement_pristine,&placement_engine,sizeof(placement_pristine));
 for(unsigned i=0;i<4;i++){
  pk_prod_first[i]=1;
  prod_sparse_build(&pk_prod_sparse_slap[i],placement_pristine.tracks[i].slap,sizeof(placement_pristine.tracks[i].slap));
  prod_sparse_build(&pk_prod_sparse_hat[i],placement_pristine.tracks[i].nh,sizeof(placement_pristine.tracks[i].nh));
 }}
void placement_production_observe(unsigned generation)
{pk_prod_generation=generation;}
/* Observable actual production event boundary, before the control prepare.
 * The independent witness resets from its own original initializer here;
 * it never copies the target's post-reset bytes into its reference stream.
 */
__attribute__((noinline)) void placement_production_event(unsigned tr,unsigned algo)
{
 pk4_track*t=&placement_engine.tracks[tr];const pk4_track*p=&placement_pristine.tracks[tr];
 pk_prod_last_reset[tr]=0;
 if(pk_prod_voice_generation[tr]!=pk_prod_generation){
  pk_prod_last_reset[tr]=1;
  if(!pk_prod_first[tr])t->initialized_mask=0;
  pk_prod_first[tr]=0;t->rng_low=1;t->rng_high=0;
  pk_cf_native_reset(&placement_clocks[tr]);
  if(tr==3)placement_engine.nh_hold[0]=placement_engine.nh_hold[1]=0;
  pk_prod_voice_generation[tr]=pk_prod_generation;pk_prod_resets[tr]++;
 }
 unsigned bit=1u<<algo;
 if(t->initialized_mask&bit)return;
#define PROD(field,ctl) prod_copy(t->field,p->field,sizeof(t->field));prod_copy(&t->ctl,&p->ctl,sizeof(t->ctl))
 if(algo==PK4_ALGO_WAVETABLE){PROD(wt,wt_ctl);}
 else if(algo==PK4_ALGO_SLAP){pk_prod_sparse_restore(t->slap,p->slap,sizeof(t->slap),&pk_prod_sparse_slap[tr]);prod_copy(&t->slap_ctl,&p->slap_ctl,sizeof(t->slap_ctl));}
 else if(algo==PK4_ALGO_NOISE_HAT){pk_prod_sparse_restore(t->nh,p->nh,sizeof(t->nh),&pk_prod_sparse_hat[tr]);prod_copy(&t->nh_ctl,&p->nh_ctl,sizeof(t->nh_ctl));}
 else if(algo==PK4_ALGO_FOLD1){PROD(fold1,fold1_ctl);}
 else if(algo==PK4_ALGO_FOLD2){PROD(fold2,fold2_ctl);}
 else if(algo==PK4_ALGO_KARPLUS){PROD(karplus,karplus_ctl);}
 else if(algo==PK4_ALGO_RESONANT){PROD(res_snare,res_snare_ctl);PROD(res_bass,res_bass_ctl);PROD(res_nt,res_nt_ctl);}
 else if(algo==PK4_ALGO_NOISE_TONE){PROD(nt_m1,nt_m1_ctl);PROD(nt_shared,nt_shared_ctl);}
 else if(algo==PK4_ALGO_SIMPLE_DRUM){PROD(sd,sd_ctl);}
 else if(algo==PK4_ALGO_COMPLEX_DRUM){PROD(cd,cd_ctl);}
#undef PROD
 t->initialized_mask|=bit;
 /* The previous algorithm remains active for the already-rendered prefix.
  * placement_prepare changes it only after this event-boundary reset. */
}

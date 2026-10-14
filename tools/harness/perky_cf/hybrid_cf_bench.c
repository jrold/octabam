#include "cf_perky4.c"
/* Diagnostic only: two logical instances, same production helper bodies. */
typedef struct { uint8_t wt[2][PK_CF_WT_STATE_BYTES]; uint8_t snare[PK_CF_RES_SNARE_STATE_BYTES]; uint8_t bass[PK_CF_RES_SNARE_STATE_BYTES]; uint8_t nt[PK_CF_NT_STATE_BYTES]; pk4_control control[3]; uint32_t rng_low,rng_high; } bench_voice;
bench_voice voices[2];
pk4_assets assets;
uint32_t profile[2], modes[2], knobs[2][4], triggers[2];
int16_t output[2][16];
volatile uint32_t status;
uint32_t ready_cookie=0x504b434f;
void bench_init(void){unsigned i,j;uint8_t *p=(uint8_t*)voices;for(j=0;j<sizeof(voices);j++)p[j]=0;for(i=0;i<2;i++){wt_init(voices[i].wt[0],255,45);wt_init(voices[i].wt[1],255,45);res_init_snare(voices[i].snare,255,63);res_init_bass(voices[i].bass,255,63);res_init_nt(voices[i].nt,255,63,&assets);voices[i].rng_low=1;}ready_cookie=0x504b5244;status=1;}
void bench_prepare(void){unsigned i;for(i=0;i<2;i++){bench_voice*v=&voices[i];uint8_t raw[4]={(uint8_t)knobs[i][0],(uint8_t)knobs[i][1],(uint8_t)knobs[i][2],(uint8_t)knobs[i][3]};unsigned p=profile[i];if(p<2)prepare_wt(&v->control[p],v->wt[p],raw,modes[i],255,45,triggers[i],&assets);else prepare_res_family(&v->control[2],v->snare,v->bass,v->nt,raw,(uint8_t)modes[i],255,45,triggers[i],&assets);}status=1;}
void bench_render(void){unsigned i,j;status=1;for(i=0;i<2;i++){bench_voice*v=&voices[i];int ok;unsigned p=profile[i];if(p<2){pk_cf_wt_tables t={assets.pitch,assets.envelope1,assets.envelope2,assets.wt_base,assets.wt_bank};ok=pk_cf_wt_render(v->wt[p],output[i],16,&t);}else if(modes[i]<2){pk_cf_res_tables t={assets.envelope1,assets.envelope2,assets.res_interp_a,assets.res_interp_b};pk_cf_res_rng rng={v->rng_low,v->rng_high};ok=modes[i]==0?pk_cf_res_snare_render(v->snare,output[i],16,&t,&rng):pk_cf_res_bass_render(v->bass,output[i],16,&t,&rng);v->rng_low=rng.low;v->rng_high=rng.high;}else{pk_cf_nt_shared_tables t;pk_cf_nt_rng rng={v->rng_low,v->rng_high};t.envelope1=assets.envelope1;t.envelope2=assets.envelope2;for(j=0;j<4;j++){t.waves[j].address=assets.waves[j].address;t.waves[j].table=assets.waves[j].table;}ok=pk_cf_nt_shared_render(v->nt,output[i],16,&t,&rng);v->rng_low=rng.low;v->rng_high=rng.high;}if(!ok)status=0;}}

#include "hybrid_cf_bench_layout.h"

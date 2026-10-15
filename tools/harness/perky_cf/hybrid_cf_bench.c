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

/* Independent original arithmetic for exhaustive control-table development.
 * Kept out of shipping firmware; the lightweight benchmark retains this entry. */
uint32_t control_math_checks,control_math_failures;
static uint16_t original_env_rate(const uint8_t*s,uint16_t prepared){
    uint32_t off=(uint32_t)s[0x90]|((uint32_t)s[0x91]<<8);
    uint32_t scale=(uint32_t)s[0x92]|((uint32_t)s[0x93]<<8);
    uint32_t product=48u*((scale-1u)&0xffffu)*(uint32_t)prepared;
    uint32_t den=48u*((off+1u)&0xffffu)+(product>>12);
    return den?(uint16_t)(0xfffffu/den):0;
}
int bench_control_math_probe(void){
    static const uint32_t configs[]={0x0fa00005u,0x0fa00002u,0x1c700032u,0u,0xffffffffu,0x00020001u};
    uint8_t state[0x98];uint32_t i,j;
    for(i=0;i<sizeof(state);i++)state[i]=0;
    control_math_checks=control_math_failures=0;
    for(j=0;j<6;j++){
        w32(state,0x90,configs[j]);
        for(i=0;i<(j<3?65536u:4096u);i++){
            if(common_decay_rate(state,(uint16_t)i)!=original_env_rate(state,time_parameter((uint16_t)i)))++control_math_failures;
            ++control_math_checks;
        }
    }
    for(i=0;i<256;i++){
        uint32_t n=i+3u,oct=n/12u,step=n%12u;
        uint16_t raw=(uint16_t)assets.chromatic[2u*step]|(uint16_t)((uint16_t)assets.chromatic[2u*step+1u]<<8);
        int32_t expected=(int16_t)(uint16_t)((uint32_t)raw+(oct<<9));
        if(note_offset((uint8_t)i,&assets)!=expected)++control_math_failures;
        ++control_math_checks;
    }
    /* Original unsigned recurrence, independent of generated thresholds.
     * Exhaust every feasible signed delta at four translations, then random
     * bounded and full-width corrupt states for all counts 0..17. */
    for(j=14u;j<=16u;j++){
        int32_t delta;
        for(delta=-4095;delta<=4095;delta++){
            uint32_t targets[4],expected[4],k,pass;
            uint32_t magnitude=(uint32_t)(delta<0?-delta:delta),slack=4095u-magnitude;
            for(k=0;k<4;k++){
                uint32_t shift=k==0?0u:k==1?slack:k==2?slack/2u:3u*slack/4u;
                uint32_t old=shift+(delta>0?(uint32_t)delta:0u);
                targets[k]=shift+(delta<0?(uint32_t)-delta:0u);
                w32(state,0x1cu+4u*k,old);expected[k]=old;
                for(pass=0;pass<j;pass++)expected[k]=(3u*targets[k]+5u*expected[k])>>3;
            }
            common_smooth_many(state,targets,j);
            for(k=0;k<4;k++){
                if(r32(state,0x1cu+4u*k)!=expected[k])++control_math_failures;
                ++control_math_checks;
            }
        }
    }
    {uint32_t seed=0x193a762fu;
     for(i=0;i<32768u;i++){
        uint32_t targets[4],expected[4],k,pass,count=i%18u;
        for(k=0;k<4;k++){
            seed=1664525u*seed+1013904223u;expected[k]=(i&1u)?seed:seed&4095u;
            w32(state,0x1cu+4u*k,expected[k]);
            seed=1664525u*seed+1013904223u;targets[k]=(i&1u)?seed:seed&4095u;
            for(pass=0;pass<count;pass++)expected[k]=(3u*targets[k]+5u*expected[k])>>3;
        }
        common_smooth_many(state,targets,count);
        for(k=0;k<4;k++){
            if(r32(state,0x1cu+4u*k)!=expected[k])++control_math_failures;
            ++control_math_checks;
        }
     }}
    return control_math_failures==0;
}

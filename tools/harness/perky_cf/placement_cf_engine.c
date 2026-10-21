/* Opt-in feasibility harness. Existing native renderers and control laws are
 * reused unchanged; firmware assets enter only through the binding API.
 * Public inputs use generic engine IDs, 10 = restored Acoustic Hats.
 */
#define pk4_encode_stock_segment placement_unused_stock_encoder
#include "cf_perky4.c"
#undef pk4_encode_stock_segment
#include "cf_acoustic_hats.h"
#include "cf_native_clock.h"
#include <stddef.h>

pk4_engine placement_engine;
pk4_assets placement_assets;
pk_cf_ah_tables placement_ah_tables;
uint8_t placement_ah_state[PK_CF_AH_STATE_BYTES];
pk4_control placement_ah_control;
int32_t placement_ah_hold;
uint32_t placement_ah_initialized;
pk_cf_native_clock placement_clocks[4];
/* algo, mode, decay, tune, p1, p2, velocity, note, boundary offset, trig */
uint32_t placement_inputs[4][10];
uint32_t placement_mask=15u;
uint32_t placement_status,placement_calls[4],placement_native_samples[4];
int32_t placement_output[4][16];
uint32_t placement_packets[4][40];
/* Per segment: old phase, carried sample count, generated count, requested
 * OT count, then complete native data (carry included), all canonical ints. */
int32_t placement_trace[4][2][24];
uint32_t placement_trace_enabled;

void placement_bind(const uint8_t *const p[16])
{
    unsigned i;placement_assets.pitch=p[0];placement_assets.chromatic=p[1];
    placement_assets.envelope1=p[2];placement_assets.envelope2=p[3];
    for(i=0;i<4;i++){placement_assets.waves[i].address=0x080222a0u+512u*i;placement_assets.waves[i].table=p[4+i];}
    placement_assets.m1_wave=p[8];placement_assets.m1_wave_address=0x080310e0u;
    placement_assets.res_interp_a=p[9];placement_assets.res_interp_b=p[10];
    placement_assets.wt_base=p[11];placement_assets.wt_bank=p[12];
    placement_ah_tables.envelope1=p[2];placement_ah_tables.envelope2=p[3];
    for(i=0;i<3;i++){
        placement_ah_tables.samples[i].address=(uint32_t[]){PK_CF_AH_CLOSED_ADDR,PK_CF_AH_OPEN_ADDR,PK_CF_AH_RIDE_ADDR}[i];
        placement_ah_tables.samples[i].bytes=(uint32_t[]){PK_CF_AH_CLOSED_BYTES,PK_CF_AH_OPEN_BYTES,PK_CF_AH_RIDE_BYTES}[i];
        placement_ah_tables.samples[i].data=p[13+i];
    }
}

void placement_init(void)
{
    unsigned tr,algo,i;
    pk4_init(&placement_engine,&placement_assets);
    for(tr=0;tr<4;tr++) {
        for(algo=0;algo<PK4_ALGO_COUNT;algo++)pk4_algo_init(&placement_engine,tr,algo,0,255,45);
        pk_cf_native_reset(&placement_clocks[tr]);
        placement_calls[tr]=placement_native_samples[tr]=0;
        for(i=0;i<16;i++)placement_output[tr][i]=0;
    }
    pk_cf_ah_init(placement_ah_state,0);
    for(i=0;i<sizeof(placement_ah_control);i++)((uint8_t*)&placement_ah_control)[i]=0;
    placement_ah_hold=0;placement_ah_initialized=0;placement_status=1;
}

int placement_prepare(unsigned tr,const uint32_t *input,int trig)
{
    uint8_t algo=(uint8_t)input[0],mode=(uint8_t)input[1];
    uint8_t raw[4]={(uint8_t)input[3],(uint8_t)input[2],(uint8_t)input[4],(uint8_t)input[5]};
    if(algo>10||mode>2||tr>3)return 0;
    if(trig||placement_engine.tracks[tr].active_algo!=algo)pk_cf_native_reset(&placement_clocks[tr]);
    if(algo==10) {
        unsigned i;
        if(tr!=3)return 0;
        if(control_dirty(&placement_ah_control,raw,mode)) {
            common_smooth_only(placement_ah_state,placement_ah_control.targets);
            common_smooth_only(placement_ah_state,placement_ah_control.targets);
            control_commit(&placement_ah_control,raw,mode);
            for(i=0;i<(trig?15u:14u);i++)common_smooth_only(placement_ah_state,placement_ah_control.targets);
            if(!trig){common_smooth_only(placement_ah_state,placement_ah_control.targets);pk_cf_ah_update(placement_ah_state,mode,placement_assets.pitch,placement_assets.chromatic);}
        }
        if(trig){pk_cf_ah_trigger(placement_ah_state,(uint8_t)input[6],(uint8_t)input[7]);common_smooth_only(placement_ah_state,placement_ah_control.targets);pk_cf_ah_update(placement_ah_state,mode,placement_assets.pitch,placement_assets.chromatic);}
        placement_engine.tracks[tr].active_algo=algo;placement_engine.tracks[tr].active_mode=mode;
        placement_ah_initialized=1;return 1;
    }
    return pk4_prepare_event(&placement_engine,tr,(uint8_t)input[2],(uint8_t)input[3],
        (uint8_t)input[4],(uint8_t)input[5],mode,algo,(uint8_t)input[6],(uint8_t)input[7],trig);
}

int placement_segment(unsigned tr,uint32_t start,uint32_t end,unsigned trace_half)
{
    if(end<start||end>16||tr>3)return 0;
    pk_cf_native_clock *c=&placement_clocks[tr];int16_t data[20];
    uint32_t n=end-start,need,i,have=c->have;
    if(!n){if(placement_trace_enabled)for(i=0;i<24;i++)placement_trace[tr][trace_half][i]=0;return 1;}
    need=pk_cf_native_needed(c,n);
    if(need+have>20)return 0;
    if(have)data[0]=(int16_t)c->carry;
    if(placement_engine.tracks[tr].active_algo==10) {
        if(!pk_cf_ah_render(placement_ah_state,data+have,need,&placement_ah_tables,&placement_ah_hold))return 0;
    }else if(!pk4_render(&placement_engine,tr,data+have,need))return 0;
    if(placement_trace_enabled) {
        placement_trace[tr][trace_half][0]=(int32_t)c->phase;
        placement_trace[tr][trace_half][1]=(int32_t)have;
        placement_trace[tr][trace_half][2]=(int32_t)need;
        placement_trace[tr][trace_half][3]=(int32_t)n;
        for(i=0;i<20;i++)placement_trace[tr][trace_half][4+i]=i<need+have?data[i]:0;
    }
    pk_cf_native_convert(c,data,n,placement_output[tr]+start);
    placement_native_samples[tr]+=need;return 1;
}

void placement_pack(unsigned tr,unsigned split)
{
    uint32_t *d=placement_packets[tr];unsigned i;
    d[0]=(split<<8)|split;d[1]=0;d[2]=0x04000000;d[3]=0;
    for(i=0;i<split;i++){uint32_t q=(uint32_t)placement_output[tr][i]<<8;d[4+2*i]=q;d[5+2*i]=q;}
    d+=4+2*split;
    d[0]=((16u-split)<<8)|(16u-split);d[1]=0;d[2]=0x04000000;d[3]=0;
    for(i=split;i<16;i++){uint32_t q=(uint32_t)placement_output[tr][i]<<8;d[4+2*(i-split)]=q;d[5+2*(i-split)]=q;}
}

void placement_frame(void)
{
    unsigned tr;
    placement_status=1;
    for(tr=0;tr<4;tr++)if(placement_mask&(1u<<tr)) {
        unsigned split=placement_inputs[tr][8];
        if(split>15u||!placement_segment(tr,0,split,0)||
           !placement_prepare(tr,placement_inputs[tr],placement_inputs[tr][9]!=0)||
           !placement_segment(tr,split,16,1)){placement_status=0;return;}
        placement_pack(tr,split);placement_calls[tr]++;
    }
}

/* Canonical state witness. Raw ARM objects are bytes; native scalar/control
 * fields are explicitly serialized LE to compare compiler ABIs faithfully. */
static void pc_byte(uint8_t **d,const uint8_t *s,unsigned n){while(n--)*(*d)++=*s++;}
static void pc_u32(uint8_t **d,uint32_t v){unsigned i;for(i=0;i<4;i++)*(*d)++=(uint8_t)(v>>(8*i));}
static void pc_control(uint8_t **d,const pk4_control *c){unsigned i;for(i=0;i<4;i++)pc_u32(d,c->targets[i]);pc_byte(d,c->last_raw,4);*(*d)++=c->last_mode;*(*d)++=c->valid;}
unsigned placement_snapshot(uint8_t *out)
{
    uint8_t *d=out;unsigned tr,i;
    for(tr=0;tr<4;tr++) {
        pk4_track *t=&placement_engine.tracks[tr];
        pc_byte(&d,(const uint8_t*)t,offsetof(pk4_track,wt)+sizeof(t->wt));
        const pk4_control *controls[]={&t->fold1_ctl,&t->fold2_ctl,&t->karplus_ctl,&t->nt_m1_ctl,&t->nt_shared_ctl,
            &t->res_snare_ctl,&t->res_bass_ctl,&t->res_nt_ctl,&t->nh_ctl,&t->sd_ctl,&t->cd_ctl,&t->slap_ctl,&t->wt_ctl};
        for(i=0;i<13;i++)pc_control(&d,controls[i]);
        pc_u32(&d,t->rng_low);pc_u32(&d,t->rng_high);pc_u32(&d,t->initialized_mask);
        pc_u32(&d,t->active_algo);pc_u32(&d,t->active_mode);
        pc_u32(&d,placement_clocks[tr].phase);pc_u32(&d,placement_clocks[tr].have);pc_u32(&d,(uint32_t)placement_clocks[tr].carry);
    }
    for(i=0;i<2;i++)pc_u32(&d,placement_engine.nh_hold[i]);
    pc_byte(&d,placement_ah_state,sizeof(placement_ah_state));pc_control(&d,&placement_ah_control);pc_u32(&d,(uint32_t)placement_ah_hold);
    return (unsigned)(d-out);
}

const uint32_t placement_layout[]={sizeof(pk4_track),offsetof(pk4_track,wt)+PK_CF_WT_STATE_BYTES,
    offsetof(pk4_track,fold1_ctl),sizeof(pk4_control),offsetof(pk4_control,last_raw),
    offsetof(pk4_control,last_mode),offsetof(pk4_control,valid),offsetof(pk4_track,rng_low),
    offsetof(pk4_track,rng_high),offsetof(pk4_track,initialized_mask),
    offsetof(pk4_track,active_algo),offsetof(pk4_track,active_mode),offsetof(pk4_engine,nh_hold),sizeof(pk_cf_native_clock)};

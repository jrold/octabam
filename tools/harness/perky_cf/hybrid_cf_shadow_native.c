/* Native shadow of the exact same narrow adapter and production helpers used
 * in the target benchmark. This is a compiler/architecture differential; the
 * separate original-firmware gates remain the synthesis authority. */
#include "hybrid_cf_bench.c"
#include "hybrid_cf_shadow.h"

void hybrid_shadow_bind(const uint8_t *const p[13])
{
    unsigned i;
    assets.pitch=p[0]; assets.chromatic=p[1];
    assets.envelope1=p[2]; assets.envelope2=p[3];
    for(i=0;i<4;i++) {
        assets.waves[i].address=0x080222a0u+512u*i;
        assets.waves[i].table=p[4+i];
    }
    assets.m1_wave=p[8]; assets.m1_wave_address=0x080310e0u;
    assets.res_interp_a=p[9]; assets.res_interp_b=p[10];
    assets.wt_base=p[11]; assets.wt_bank=p[12];
}

void hybrid_shadow_step(unsigned action, const uint32_t inputs[14])
{
    unsigned i,j;
    for(i=0;i<2;i++) {
        profile[i]=inputs[i]; modes[i]=inputs[2+i];
        for(j=0;j<4;j++)knobs[i][j]=inputs[4+4*i+j];
        triggers[i]=inputs[12+i];
    }
    if(action==HYB_INIT)bench_init();
    else if(action==HYB_PREPARE)bench_prepare();
    else if(action==HYB_RENDER)bench_render();
}

/* Canonical bytes retain every state byte and control/RNG/PCM value. Only
 * compiler-inserted aggregate padding is excluded. Fixed-width numeric fields
 * are serialized LE on both hosts; synthesis objects already use ARM bytes. */
static void shadow_u32(uint8_t **out,uint32_t value)
{
    unsigned i;for(i=0;i<4;i++)*(*out)++=(uint8_t)(value>>(8*i));
}
static void shadow_bytes(uint8_t **out,const uint8_t *source,unsigned bytes)
{
    unsigned i;for(i=0;i<bytes;i++)*(*out)++=source[i];
}
unsigned hybrid_shadow_snapshot(uint8_t *destination,unsigned capacity)
{
    const unsigned controls=sizeof(voices[0].control)/sizeof(pk4_control);
    const unsigned needed=2u*(sizeof(voices[0].wt)+sizeof(voices[0].snare)
        +sizeof(voices[0].bass)+sizeof(voices[0].nt)+22u*controls+8u)+64u+4u;
    uint8_t *out=destination;
    unsigned i,j,k;
    if(!destination||capacity<needed)return needed;
    for(i=0;i<2;i++) {
        bench_voice *v=&voices[i];
        shadow_bytes(&out,(const uint8_t *)v->wt,sizeof(v->wt));
        shadow_bytes(&out,v->snare,sizeof(v->snare));
        shadow_bytes(&out,v->bass,sizeof(v->bass));
        shadow_bytes(&out,v->nt,sizeof(v->nt));
        for(j=0;j<controls;j++) {
            const pk4_control *c=&v->control[j];
            for(k=0;k<4;k++)shadow_u32(&out,c->targets[k]);
            shadow_bytes(&out,c->last_raw,4);
            *out++=c->last_mode;*out++=c->valid;
        }
        shadow_u32(&out,v->rng_low);shadow_u32(&out,v->rng_high);
    }
    for(i=0;i<2;i++)for(j=0;j<16;j++) {
        const uint16_t value=(uint16_t)output[i][j];
        *out++=(uint8_t)value;*out++=(uint8_t)(value>>8);
    }
    shadow_u32(&out,status);
    return (unsigned)(out-destination);
}

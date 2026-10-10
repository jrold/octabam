/* ColdFire renderer + control path for the PĒRKONS v1.2.1 Acoustic Hats
 * family (V4 algorithm 3).
 *
 * Operates directly on the original 0x10C-byte ARM object at the offsets the
 * firmware uses, mirroring modules/perky/acoustic_hats_compact.py -- exact
 * against the firmware's captured PCM, object and firmware-global held sample
 * for all nine engine-12 captures.
 *
 * The one-pole filter is the only float arithmetic in the port:
 *     decayed = previous * 0.98f;   summed = input + previous;
 * with the single's bits kept in the object.  cf_softfloat.h computes those
 * exactly in integers; the build is freestanding -msoft-float with no libgcc
 * float helpers, and a 64-bit multiply would pull in __muldi3.
 */
#include "cf_acoustic_hats.h"
#include "cf_math.h"
#include "cf_softfloat.h"
#include <limits.h>

/* 0.980000019073486328125f, the captured decay constant. */
#define PK_CF_AH_DECAY_BITS 0x3f7ae148u

#include "cf_acoustic_hats_rate.inc"

static uint16_t r16(const uint8_t*s,size_t o){return pk_cf_ld16(s,o);}
static uint32_t r32(const uint8_t*s,size_t o){return pk_cf_ld32(s,o);}
static void w16(uint8_t*s,size_t o,uint16_t v){pk_cf_st16(s,o,v);}
static void w32(uint8_t*s,size_t o,uint32_t v){pk_cf_st32(s,o,v);}
static int16_t s16(uint16_t u){return (u&0x8000u)?(int16_t)(-1-(int16_t)(uint16_t)~u):(int16_t)u;}
static int32_t s32(uint32_t u){return (u&0x80000000u)?-1-(int32_t)~u:(int32_t)u;}
static uint32_t u32(int32_t s){return s>=0?(uint32_t)s:~(uint32_t)(-1-s);}
static int32_t asr(int32_t v,unsigned n){uint32_t b;if(!n)return v;b=u32(v)>>n;if(v<0)b|=(~0u)<<(32u-n);return s32(b);}
static int32_t mullo(int32_t a,int32_t b){return s32(pk_cf_mul_lo_u32(u32(a),u32(b)));}
static uint16_t tab16(const uint8_t*t,size_t i){return pk_cf_ld16(t,2u*i);}
/* --- shared common envelope, identical to cf_fold's ----------------------- */
static uint16_t env(uint8_t*s,size_t b,const pk_cf_ah_tables*t){
    uint8_t st=s[b];int32_t v=s32(r32(s,b+0xc));
    switch(st){
    case 0:if(s[b+7]||s[b+4])s[b]=1;break;
    case 1:v=s32(u32(v)+(uint32_t)r16(s,b+0x20));w32(s,b+0xc,u32(v));if(s[b+4]){if(v>0xffffe){s[b]=4;if(v>=0x100000){v=0xfffff;w32(s,b+0xc,u32(v));}}}else if(v>0xffffe){s[b]=s[b+6]?4:3;if(v>=0x100000){v=0xfffff;w32(s,b+0xc,u32(v));}}break;
    case 2:break;
    case 3:if(!s[b+7]&&(s[b+4]||!s[b+0x10]))s[b]=4;break;
    case 4:if(s[b+7])s[b]=1;else{v=s32(u32(v)-(uint32_t)r16(s,b+0x22));w32(s,b+0xc,u32(v));if(v<=0){v=0;w32(s,b+0xc,0);s[b]=s[b+4]?1:0;}}break;
    default:break;}
    if(s[b+1]!=1&&s[b+1]!=2)return (uint16_t)((u32(v)>>4)&0xffffu);
    {const uint8_t*c=s[b+1]==1?t->envelope1:t->envelope2;uint32_t raw,idx,nx;int32_t f,a,z;
     if(!c)return 0;
     raw=u32(v);idx=(raw>>10)&0x7ffu;nx=(idx+1)&0x7ffu;f=(int32_t)(raw&0x3ffu);
     a=(int32_t)tab16(c,idx);z=(int32_t)tab16(c,nx);
     return (uint16_t)(a+asr(mullo(z-a,f),10));}
}

static int32_t pitch(uint16_t raw,const uint8_t*t){
    int32_t p=(int32_t)s16(raw);int neg=0;uint32_t v=0;
    if(p<0){uint16_t m=(uint16_t)(0u-raw);p=(int32_t)s16(m);if(p>=0x1000)neg=1;}
    if(p<0x1000){
        v=tab16(t,(uint16_t)p);
    } else {
        uint16_t q=(uint16_t)p;uint32_t sh=((q-0x1000u)>>9)&0x7fu,ad=sh*127u;int16_t ix;
        sh=(sh+1u)&0xffu;ix=s16((uint16_t)((uint32_t)q+(ad<<9)-0x200u));
        v=(uint32_t)tab16(t,(uint16_t)ix)<<sh;
    }
    if(neg)
        v=0u-v;
    return s32(v);
}

static uint16_t time_parameter(uint16_t prepared){
    uint32_t q=0x7fffu+((uint32_t)prepared<<2),mant=(q&0xfffu)+0x1000u,exp=(q>>12)&0xfu,v;
    if(exp>11u)v=(mant<<(exp-12u))&0xffffu;else v=(mant>>(12u-exp))&0xffffu;
    v=(v-1u)&0xffffffffu;v=(v>>1)&0x7fffu;return (uint16_t)((v-0x7fu)&0xffffu);
}
/* The family's envelope-rate helper: 0xFFFFF / (48*(off+1) + (48*(scale-1) *
 * time_parameter)>>12), with this family's own (off, scale) -- (12, 841) for
 * the amplitude decay and (1, 841) for the attack, exact over all 128 sweep
 * points of both controls. */
static uint16_t ah_rate(uint32_t base,uint16_t param){
    const uint32_t den=(uint32_t)base+((40320u*(uint32_t)param)>>12);
    return den?(uint16_t)(0xfffffu/den):0;
}

void pk_cf_ah_init(uint8_t*s,uint8_t panel_mode){
    unsigned i;for(i=0;i<PK_CF_AH_STATE_BYTES;++i)s[i]=0;
    w16(s,6,0x3fffu);w16(s,8,0x0ff0u);
    w32(s,0x00,0x08032694u);
    w32(s,0x0c,0x200006c4u);w32(s,0x10,0x200006c8u);
    w32(s,0x14,0x200006ccu);w32(s,0x18,0x200006d0u);
    w32(s,0x38,0x080222a0u);w32(s,0x3c,0x080222a0u);
    w32(s,0x58,0x0802819du);
    w16(s,0x62,2u);
    s[0x7a]=1u;s[0x7c]=1u;
    w32(s,0x8c,0x00000001u);
    w16(s,0x90,12u);
    w16(s,0xa8,0x0800u);
    s[0xd0]=12u;
    w32(s,0xd4,0x0fffu);
    /* the three hat descriptors, and the one PANEL MODE selects */
    w32(s,0xe0,PK_CF_AH_CLOSED_ADDR);w32(s,0xe4,PK_CF_AH_CLOSED_BYTES);
    w32(s,0xe8,PK_CF_AH_OPEN_ADDR);  w32(s,0xec,PK_CF_AH_OPEN_BYTES);
    w32(s,0xf0,PK_CF_AH_RIDE_ADDR);  w32(s,0xf4,PK_CF_AH_RIDE_BYTES);
    if(panel_mode==1u){w32(s,0xf8,PK_CF_AH_OPEN_ADDR);w32(s,0xfc,PK_CF_AH_OPEN_BYTES);}
    else if(panel_mode==2u){w32(s,0xf8,PK_CF_AH_RIDE_ADDR);w32(s,0xfc,PK_CF_AH_RIDE_BYTES);}
    else {w32(s,0xf8,PK_CF_AH_CLOSED_ADDR);w32(s,0xfc,PK_CF_AH_CLOSED_BYTES);}
}

void pk_cf_ah_update(uint8_t*s,uint8_t panel_mode,const uint8_t*pitch_table,const uint8_t*chromatic){
    const uint16_t prep_tune=(uint16_t)r32(s,0x1c);
    const uint16_t prep_decay=(uint16_t)r32(s,0x20);
    const uint16_t prep_p1=(uint16_t)r32(s,0x24);
    const uint16_t prep_p2=(uint16_t)r32(s,0x28);
    const uint32_t n=(uint32_t)s[7]+3u;
    const int32_t offset=(int32_t)s16((uint16_t)(tab16(chromatic,n%12u)+(uint32_t)((n/12u)<<9)));
    const int32_t pi=s16((uint16_t)(prep_tune-0x800u+(uint16_t)offset));
    const uint32_t ix=(uint32_t)(pi<0?0:(pi>4095?4095:pi));
    w16(s,0xba,(uint16_t)ix);
    w16(s,0xbc,prep_decay);w16(s,0xbe,prep_p1);w16(s,0xc0,prep_p2);
    w16(s,0x0a,prep_p2);
    w32(s,0x34,pitch_table?(uint32_t)pitch((uint16_t)ix,pitch_table):0u);
    s[0x7b]=(uint8_t)(r16(s,8)<=prep_decay);
    w16(s,0x94,ah_rate(96u,time_parameter(prep_p2)));
    w16(s,0x96,ah_rate(624u,time_parameter(prep_decay)));
    w32(s,0xcc,ah_rate_table[ix]);
    w32(s,0xd8,(uint32_t)(prep_p1>>6));
    if(panel_mode==1u){w32(s,0xf8,PK_CF_AH_OPEN_ADDR);w32(s,0xfc,PK_CF_AH_OPEN_BYTES);}
    else if(panel_mode==2u){w32(s,0xf8,PK_CF_AH_RIDE_ADDR);w32(s,0xfc,PK_CF_AH_RIDE_BYTES);}
    else {w32(s,0xf8,PK_CF_AH_CLOSED_ADDR);w32(s,0xfc,PK_CF_AH_CLOSED_BYTES);}
}

void pk_cf_ah_trigger(uint8_t*s,uint8_t velocity,uint8_t note){
    s[6]=velocity?velocity:1u;
    if(note)s[7]=note;
    s[0x84]=1u;s[0x74]=1u;
    if(s[0x7c])w32(s,0x80,0u);
    s[0x108]=1u;                    /* the filter re-seeds from the integer history */
}

/* The external asset read: out of range reads 0, it does not end the block. */
static int32_t ah_sample(const uint8_t*b,uint32_t bytes,uint32_t index){
    const uint32_t off=index<<1;
    if(off+1u>=bytes)return 0;
    return s16((uint16_t)((uint16_t)b[off]|(uint16_t)((uint16_t)b[off+1u]<<8)));
}

int pk_cf_ah_render(uint8_t*s,int16_t*d,uint32_t n,const pk_cf_ah_tables*t,int32_t*hold){
    uint32_t i,length,bytes=0;
    const uint8_t*sample=0;
    uint32_t index,fraction,rate,mask,shift,hold_left;
    uint32_t filter_bits,previous_bits;
    uint8_t filter_seed,velocity,mute;
    if(!s||!d||!t||!hold)return 0;
    {
        const uint32_t address=r32(s,0xf8);
        unsigned k;
        for(k=0;k<3u;k++)
            if(t->samples[k].data&&t->samples[k].address==address)
                sample=t->samples[k].data,bytes=t->samples[k].bytes;
    }
    if(!sample)return 0;
    length=r32(s,0xfc);
    /* These renderer fields cannot be modified from inside a block.  Keep
     * them native in registers rather than endian-loading/storing them for
     * every one of the 16 samples. */
    index=r32(s,0xc4);fraction=r32(s,0xc8);rate=r32(s,0xcc);
    mask=r32(s,0xd4);shift=(uint32_t)s[0xd0];hold_left=r32(s,0xdc);
    filter_bits=r32(s,0x100);previous_bits=r32(s,0x104);filter_seed=s[0x108];
    velocity=s[6];mute=s[0xb8];
    for(i=0;i<n;i++){
        const uint16_t amplitude=env(s,0x74,t);
        uint32_t advanced;
        int32_t interpolated,envelope_scaled,filtered;
        if(length==0u||length<=index){d[i]=0;continue;}
        {
            const uint32_t next_index=index+1u;
            const int32_t nxt=(length>next_index)?ah_sample(sample,bytes,next_index):0;
            if(hold_left!=0u){
                hold_left=(hold_left-1u)&0xffffffffu;
                interpolated=s32((uint32_t)*hold);
            } else {
                const int32_t current=ah_sample(sample,bytes,index);
                const int32_t weighted_next=mullo(s32(fraction),nxt);
                const int32_t complement=s32((mask-fraction)&0xffffffffu);
                interpolated=asr(s32(u32(weighted_next)+u32(mullo(complement,current))),shift+1u);
                *hold=interpolated;
                hold_left=r32(s,0xd8);
            }
            envelope_scaled=asr(mullo(interpolated,(int32_t)amplitude),15);
        }
        advanced=(fraction+rate)&0xffffffffu;
        index=(index+(advanced>>shift))&0xffffffffu;
        fraction=advanced&mask;
        {
            uint32_t previous;
            if(filter_seed){previous=pk_cf_i32_to_f32(s32(filter_bits));filter_seed=0u;}
            else previous=previous_bits;
            {
                const uint32_t input_bits=pk_cf_i32_to_f32(envelope_scaled);
                previous_bits=pk_cf_f32_mul(previous,PK_CF_AH_DECAY_BITS);
                filtered=pk_cf_f32_to_i32_trunc(pk_cf_f32_add(input_bits,previous));
                filter_bits=(uint32_t)filtered;
            }
        }
        if(mute){d[i]=0;continue;}
        {
            int32_t value=asr(mullo(filtered,(int32_t)(velocity&0xffu)),8);
            if(value>INT16_MAX)value=INT16_MAX;else if(value<INT16_MIN)value=INT16_MIN;
            d[i]=(int16_t)value;
        }
    }
    w32(s,0xc4,index);w32(s,0xc8,fraction);w32(s,0xdc,hold_left);
    w32(s,0x100,filter_bits);w32(s,0x104,previous_bits);s[0x108]=filter_seed;
    return 1;
}
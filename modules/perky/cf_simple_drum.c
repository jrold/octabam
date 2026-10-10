/* ColdFire renderer for the PĒRKONS v1.2.1 Simple Drum family (V1 algorithm 3).
 *
 * Operates directly on the original ARM object (0x120 bytes) at the same
 * offsets the firmware uses, the way cf_fold / cf_karplus / cf_noise_tone do.
 * Every operation mirrors modules/perky/simple_drum_compact.py, which
 * reproduces the real firmware's own captured PCM, final state and active
 * retrigger exactly for engine 3 across all three modes and all three control
 * corners (out/perky/engine-fixtures/engine-3-*).
 *
 * Panel mapping: M1/M2/M3 select the firmware modes 1/0/2, i.e. the deferred
 * wave targets 0x080222A0 / 0x080226A0 / 0x080228A0.
 */
#include "cf_simple_drum.h"
#include "cf_math.h"
#include <limits.h>

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
static int16_t tabs16(const uint8_t*t,size_t i){return s16(tab16(t,i));}
static const uint8_t* wave(const pk_cf_fold_tables*t,uint32_t a){unsigned i;for(i=0;i<4;i++)if(t->waves[i].table&&t->waves[i].address==a)return t->waves[i].table;return 0;}

/* --- the shared common envelope, identical to cf_fold's ------------------- */
static uint16_t env(uint8_t*s,size_t b,const pk_cf_fold_tables*t){
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

/* The full native pitch lookup (the >= 0x1000 magnitude-shift path is kept so
 * a raw pitch outside the prepared 12-bit window still behaves). */
static int32_t pitch(uint16_t raw,const uint8_t*t){
    int32_t p=(int32_t)s16(raw);int neg=0;uint32_t v=0;
    if(p<0){uint16_t m=(uint16_t)(0u-raw);p=(int32_t)s16(m);if(p>=0x1000)neg=1;}
    if(p<0x1000)v=tab16(t,(uint16_t)p);
    else{uint16_t q=(uint16_t)p;uint32_t sh=((q-0x1000u)>>9)&0x7fu,ad=sh*127u;int16_t ix;
         sh=(sh+1u)&0xffu;ix=s16((uint16_t)((uint32_t)q+(ad<<9)-0x200u));
         v=(uint32_t)tab16(t,(uint16_t)ix)<<sh;}
    if(neg)v=0u-v;
    return s32(v);
}

static uint32_t frequency_step(uint32_t f){
    int32_t shifted=s32(f<<20);
    int32_t hi=pk_cf_mul_hi_s32(shifted,s32(0x057619f1u));
    int32_t result=asr(hi,10)-asr(shifted,31);
    return u32(result);
}
static void setfreq(uint8_t*s,size_t b,uint32_t f){w32(s,b+8,frequency_step(f));}

typedef struct {
    const uint8_t *table;
    uint32_t table_address;
    uint32_t phase;
    uint32_t step;
    uint32_t current;
    uint32_t next;
} sd_osc_state;

static void osc_load(sd_osc_state*o,const uint8_t*s,size_t b){
    o->table=0;o->table_address=0xffffffffu;
    o->phase=r32(s,b+4);o->step=r32(s,b+8);o->current=r32(s,b+0xc);o->next=r32(s,b+0x10);
}
static void osc_store(const sd_osc_state*o,uint8_t*s,size_t b){
    w32(s,b+4,o->phase);w32(s,b+8,o->step);w32(s,b+0xc,o->current);
}
static int osc_step(sd_osc_state*o,const pk_cf_fold_tables*t,int16_t*out){
    uint32_t i,j;int32_t f,a,z;
    o->phase+=o->step;
    if(s32(o->phase)>0x100000){o->phase-=0x100000u;if(o->next!=o->current)o->current=o->next;}
    if(o->current!=o->table_address){o->table=wave(t,o->current);o->table_address=o->current;}
    if(!o->table)return 0;
    i=(o->phase>>12)&0xffu;j=(i+1)&0xffu;f=(int32_t)(o->phase&0xfffu);
    a=(int32_t)tabs16(o->table,i);z=(int32_t)tabs16(o->table,j);
    *out=s16((uint16_t)(a+asr(mullo(z-a,f),12)));
    return 1;
}

/* The pitch term is loop-invariant at 16 samples per block: raw_pitch (0xba)
 * and the wave view only change in the update pass, never inside a block. */
static uint32_t base_frequency(uint8_t*s,const uint8_t*t){
    int32_t p=pitch(r16(s,0xba),t);
    return(uint32_t)mullo(p,0xbb80)>>20;
}

/* --- control path --------------------------------------------------------
 * All arithmetic is the firmware's own, recovered in
 * modules/perky/simple_drum_control.py and pinned against a 128-point
 * authentic sweep by tools/verify/verify_perky_simple_drum_control.py. */
static uint16_t sd_time_parameter(uint16_t prepared){
    uint32_t q=0x7fffu+((uint32_t)prepared<<2),mant=(q&0xfffu)+0x1000u,exp=(q>>12)&0xfu,v;
    if(exp>11u)v=(mant<<(exp-12u))&0xffffu;else v=(mant>>(12u-exp))&0xffffu;
    v=(v-1u)&0xffffffffu;v=(v>>1)&0x7fffu;return (uint16_t)((v-0x7fu)&0xffffu);
}
static uint16_t sd_env_rate(uint16_t control,uint32_t offset,uint32_t scale){
    uint32_t den=48u*(offset+1u)+((48u*(scale-1u)*(uint32_t)control)>>12);
    return den?(uint16_t)(0xfffffu/den):0u;
}
static uint32_t sd_wave_address(uint8_t panel_mode){
    if(panel_mode==0u)return PK_CF_SD_WAVE_M1;
    return panel_mode==1u?PK_CF_SD_WAVE_M2:PK_CF_SD_WAVE_M3;
}

void pk_cf_sd_init(uint8_t*s,uint8_t panel_mode,uint8_t velocity,uint8_t note){
    size_t i;for(i=0;i<PK_CF_SD_STATE_BYTES;++i)s[i]=0;
    w16(s,8,0x0ff0u);                       /* common sustain threshold */
    s[6]=velocity?velocity:1u;              /* VELOCITY */
    s[7]=note;                              /* NOTE */
    w32(s,0x58,PK_CF_SD_OSC_RENDER);        /* guard + oscillator entry */
    w32(s,0x5c,sd_wave_address(panel_mode));/* the object's own wave view */
    w32(s,0x38,PK_CF_SD_OSC_BASE_WAVE);     /* current wave until the first wrap */
    w32(s,0x3c,sd_wave_address(panel_mode));/* deferred target wave */
    /* amplitude envelope: shape 0 (linear), flag6 set, reset armed, constant attack */
    s[0x74]=0;s[0x75]=0;s[0x78]=0;s[0x7a]=1;s[0x7b]=0;s[0x7c]=1;
    w16(s,0x94,PK_CF_SD_AMP_ATTACK);
    /* pitch envelope: shape 1 (envelope1 curve), flag6 set, reset armed, constant attack */
    s[0xc4]=0;s[0xc5]=1;s[0xc8]=0;s[0xca]=1;s[0xcb]=0;s[0xcc]=1;
    w16(s,0xe4,PK_CF_SD_PITCH_ATTACK);
    w16(s,0x84,1u);w16(s,0xd4,1u);          /* envelope hold words */
}

void pk_cf_sd_update(uint8_t*s,uint8_t panel_mode,const uint8_t*pitch_table){
    uint16_t tune=(uint16_t)r32(s,0x1c),decay=(uint16_t)r32(s,0x20);
    uint16_t envc=(uint16_t)r32(s,0x24),mix=(uint16_t)r32(s,0x28);
    w16(s,0xba,tune);                       /* raw pitch is the prepared TUNE word */
    w16(s,0x96,sd_env_rate((uint16_t)sd_time_parameter(decay),50u,5200u));
    w16(s,0xe6,sd_env_rate(envc,20u,400u));
    w16(s,0xec,(uint16_t)(mix>>1));
    w32(s,0x3c,sd_wave_address(panel_mode));
    /* The firmware's post-trigger snapshot already carries the oscillator
     * increment recomputed from the fresh raw pitch with both envelopes at
     * zero, so do the same.  The renderer overwrites it per sample either way;
     * this keeps the object byte-identical to the captured one. */
    if(pitch_table)setfreq(s,0x2c,base_frequency(s,pitch_table));
}

void pk_cf_sd_trigger(uint8_t*s,uint8_t velocity,uint8_t note){
    s[6]=velocity?velocity:1u;
    if(note)s[7]=note;
    /* envelope_trigger on both envelopes, in the shared form the other engines
     * use: arm the state machine and clear the value when the envelope owns a
     * reset slot. */
    s[0x74]=1u;s[0x84]=1u;
    s[0xc4]=1u;s[0xd4]=1u;
    w32(s,0x80,0u);
    w32(s,0xd0,0u);
}

int pk_cf_sd_render(uint8_t*s,int16_t*d,uint32_t n,const pk_cf_fold_tables*t){
    uint32_t i;
    sd_osc_state osc;
    uint32_t fb;
    uint16_t amount,raw;
    uint8_t mute,velocity;
    if(!s||!d||!t||!t->pitch)return 0;
    if(r32(s,0x58)!=PK_CF_SD_OSC_RENDER)return 0;
    fb=base_frequency(s,t->pitch);
    amount=r16(s,0xec);raw=r16(s,0xba);mute=s[0xb8];velocity=s[6];
    osc_load(&osc,s,0x2c);
    for(i=0;i<n;i++){
        uint16_t a=env(s,0x74,t),pe=env(s,0xc4,t);
        int16_t o=0;int32_t out;
        uint32_t contrib=((uint32_t)pe*(uint32_t)amount)>>10;
        uint32_t mod=((uint32_t)raw*contrib)>>16;
        osc.step=frequency_step(fb+mod);
        if(!osc_step(&osc,t,&o)){osc_store(&osc,s,0x2c);return 0;}
        if(mute){d[i]=0;continue;}
        out=asr(mullo((int32_t)a,(int32_t)o),17);
        out=asr(mullo(out,(int32_t)velocity),8);
        if(out>INT16_MAX)out=INT16_MAX;else if(out<INT16_MIN)out=INT16_MIN;
        d[i]=(int16_t)out;
    }
    osc_store(&osc,s,0x2c);
    return 1;
}

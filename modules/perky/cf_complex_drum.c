/* ColdFire renderer for the PĒRKONS v1.2.1 Complex Drum family (V2 algorithm 3).
 *
 * Operates directly on the original 0x140-byte ARM object at the offsets the
 * firmware uses.  Mirrors modules/perky/complex_drum_compact.py, which
 * reproduces the real firmware's captured PCM exactly (object located at
 * wrapper + 0x1F8 by rendering every window of the capture through the model).
 *
 * Main and modulation oscillators sit at object 0x2C and 0xC4 (the firmware's
 * own oscillator geometry), the common envelopes at 0x74 and 0xF8.
 */
#include "cf_complex_drum.h"
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

/* --- shared common envelope, identical to cf_fold's ----------------------- */
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

static void setfreq(uint8_t*s,size_t b,uint32_t f){
    int32_t shifted=s32(f<<20);
    int32_t hi=pk_cf_mul_hi_s32(shifted,s32(0x057619f1u));
    int32_t result=asr(hi,10)-asr(shifted,31);
    w32(s,b+8,u32(result));
}

static int osc(uint8_t*s,size_t b,const pk_cf_fold_tables*t,int16_t*out){
    uint32_t ph=r32(s,b+4)+r32(s,b+8),cur;const uint8_t*tb;uint32_t i,j;int32_t f,a,z;
    w32(s,b+4,ph);
    cur=r32(s,b+0xc);
    if(s32(ph)>0x100000){
        uint32_t nx=r32(s,b+0x10);
        ph-=0x100000;w32(s,b+4,ph);
        if(nx!=cur){cur=nx;w32(s,b+0xc,cur);}
    }
    tb=wave(t,cur);if(!tb)return 0;
    i=(ph>>12)&0xffu;j=(i+1)&0xffu;f=(int32_t)(ph&0xfffu);
    a=(int32_t)tabs16(tb,i);z=(int32_t)tabs16(tb,j);
    *out=s16((uint16_t)(a+asr(mullo(z-a,f),12)));
    return 1;
}

/* --- control path ---------------------------------------------------------
 * Laws recovered by sweeping the real firmware and solving the exact
 * (offset, scale, shift) that satisfies every captured point; exact over
 * 3584 points spanning 1627 distinct prepared values per control. */
static uint16_t cd_time_parameter(uint16_t prepared){
    uint32_t q=0x7fffu+((uint32_t)prepared<<2),mant=(q&0xfffu)+0x1000u,exp=(q>>12)&0xfu,v;
    if(exp>11u)v=(mant<<(exp-12u))&0xffffu;else v=(mant>>(12u-exp))&0xffffu;
    v=(v-1u)&0xffffffffu;v=(v>>1)&0x7fffu;return (uint16_t)((v-0x7fu)&0xffffu);
}
static uint16_t cd_amp_rate(uint16_t prepared_decay){
    uint32_t den=48u*51u+((48u*7279u*(uint32_t)cd_time_parameter(prepared_decay))>>12);
    return den?(uint16_t)(0xfffffu/den):0u;
}
static uint16_t cd_pitch_rate(uint16_t prepared_p1){
    uint32_t den=(43244160u-9552u*(uint32_t)prepared_p1)>>12;
    return den?(uint16_t)(0xfffffu/den):0u;
}
static uint32_t cd_main_wave(uint8_t panel_mode){
    if(panel_mode==0u)return PK_CF_CD_WAVE_M1;
    return panel_mode==1u?PK_CF_CD_WAVE_M2:PK_CF_CD_WAVE_M3;
}

void pk_cf_cd_init(uint8_t*s,uint8_t panel_mode,uint8_t velocity,uint8_t note){
    size_t i;for(i=0;i<PK_CF_CD_STATE_BYTES;++i)s[i]=0;
    w16(s,8,0x0ff0u);
    s[6]=velocity?velocity:1u;
    s[7]=note;
    w32(s,0x58,PK_CF_CD_OSC_RENDER);
    w32(s,0x5c,cd_main_wave(panel_mode));
    w32(s,0x38,PK_CF_CD_MAIN_BASE_WAVE);      /* main oscillator current */
    w32(s,0x3c,cd_main_wave(panel_mode));     /* main oscillator target */
    w32(s,0xd0,PK_CF_CD_MOD_WAVE);            /* modulation current */
    w32(s,0xd4,PK_CF_CD_MOD_WAVE);            /* modulation target (fixed) */
    s[0x74]=0;s[0x75]=0;s[0x78]=0;s[0x7a]=1;s[0x7b]=0;s[0x7c]=1;
    w16(s,0x94,PK_CF_CD_AMP_ATTACK);
    s[0xf8]=0;s[0xf9]=1;s[0xfc]=0;s[0xfe]=1;s[0xff]=0;s[0x100]=1;
    w16(s,0x118,PK_CF_CD_PITCH_ATTACK);
    w16(s,0x84,1u);w16(s,0x108,1u);
}

void pk_cf_cd_update(uint8_t*s,uint8_t panel_mode,const uint8_t*pitch_table){
    uint16_t tune=(uint16_t)r32(s,0x1c),decay=(uint16_t)r32(s,0x20);
    uint16_t p1=(uint16_t)r32(s,0x24),p2=(uint16_t)r32(s,0x28);
    uint32_t biased=(uint32_t)tune+PK_CF_CD_TUNE_BIAS;
    w16(s,0xba,(uint16_t)(biased>4095u?4095u:biased));
    w16(s,0x96,cd_amp_rate(decay));
    w16(s,0x11a,cd_pitch_rate(p1));
    w16(s,0x120,p2);
    w32(s,0x3c,cd_main_wave(panel_mode));
    if(pitch_table)setfreq(s,0x2c,(uint32_t)mullo(pitch(r16(s,0xba),pitch_table),0xbb80u)>>20);
}

void pk_cf_cd_trigger(uint8_t*s,uint8_t velocity,uint8_t note){
    s[6]=velocity?velocity:1u;
    if(note)s[7]=note;
    s[0x74]=1u;s[0x84]=1u;
    s[0xf8]=1u;s[0x108]=1u;
    w32(s,0x80,0u);
    w32(s,0x104,0u);
}

int pk_cf_cd_render(uint8_t*s,int16_t*d,uint32_t n,const pk_cf_fold_tables*t){
    uint32_t i;
    if(!s||!d||!t||!t->pitch)return 0;
    if(r32(s,0x58)!=PK_CF_CD_OSC_RENDER)return 0;
    {
        const uint32_t base=(uint32_t)mullo(pitch(r16(s,0xba),t->pitch),0xbb80u)>>20;
        const uint16_t amount=r16(s,0x120);
        for(i=0;i<n;i++){
            uint16_t a=env(s,0x74,t),pe=env(s,0xf8,t);
            int16_t o=0,mo=0;
            uint32_t lo,hi,factor,freq;
            int32_t out;
            if(!osc(s,0xc4,t,&mo))return 0;
            lo=(uint32_t)pe&0x1fffu;hi=(uint32_t)pe>>13;
            factor=((lo+0x2000u)>>(13u-hi))-1u;
            freq=base+((uint32_t)amount*factor>>10)+u32(asr((int32_t)s16((uint16_t)mo),6));
            setfreq(s,0x2c,freq);
            if(!osc(s,0x2c,t,&o))return 0;
            if(s[0xb8]){d[i]=0;continue;}
            out=asr(mullo((int32_t)o,(int32_t)a),16);
            out=asr(mullo(out,(int32_t)s[6]),8);
            if(out>INT16_MAX)out=INT16_MAX;else if(out<INT16_MIN)out=INT16_MIN;
            d[i]=(int16_t)out;
        }
    }
    return 1;
}

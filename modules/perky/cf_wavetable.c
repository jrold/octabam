/* ColdFire renderer for the PĒRKONS v1.2.1 Wavetable Drum family (V1/V2 a2).
 *
 * Operates directly on the original 0x150-byte ARM object at the offsets the
 * firmware uses, mirroring modules/perky/wavetable_drum_compact.py -- exact
 * against the firmware's captured PCM and full object for all nine engine-2
 * and all nine engine-5 captures (first block + continuation).
 *
 * Two oscillators: a primary fixed on the shared 0x080222A0 table and a
 * secondary that walks the 48-table bank, crossfaded by the object's own mix
 * word.  The common envelope pair sits at 0x74 and 0xC4, the amplitude rate at
 * 0x96, the raw pitch at 0xBA and the pitch-envelope amount at 0xEC.
 */
#include "cf_wavetable.h"
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
/* Same little-endian word as the byte pair, through the typed helper: every
 * table in this engine is a multiple of four bytes and 2*i is even, so the
 * load is a single move.l + byterev rather than two byte loads, a shift and
 * an or.  The two bytes past the field are inside the same table (or the
 * next one in the bank) and are discarded. */
static uint16_t tab16(const uint8_t*t,size_t i){return pk_cf_ld16(t,2u*i);}
static int16_t tabs16(const uint8_t*t,size_t i){return s16(tab16(t,i));}

const uint8_t *pk_cf_wt_wave(const pk_cf_wt_tables *t, uint32_t address)
{
    if (!t)
        return 0;
    if (address == PK_CF_WT_BASE_WAVE)
        return t->base_wave;
    if (address >= PK_CF_WT_BANK_BASE) {
        const uint32_t delta = address - PK_CF_WT_BANK_BASE;
        if ((delta % PK_CF_WT_BANK_STRIDE) == 0u && (delta / PK_CF_WT_BANK_STRIDE) < PK_CF_WT_BANK_COUNT)
            return t->bank + (delta / PK_CF_WT_BANK_STRIDE) * PK_CF_WT_TABLE_BYTES;
    }
    return 0;
}

/* --- shared common envelope, identical to cf_fold's ----------------------- */
static uint16_t env(uint8_t*s,size_t b,const pk_cf_wt_tables*t){
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

static void wt_set_frequency(uint8_t*s,uint32_t f){
    int32_t shifted=s32(f<<20);
    int32_t hi=pk_cf_mul_hi_s32(shifted,s32(0x057619f1u));
    int32_t result=asr(hi,10)-asr(shifted,31);
    w32(s,0xf8,u32(result));
}

int pk_cf_wt_render(uint8_t*s,int16_t*d,uint32_t n,const pk_cf_wt_tables*t){
    uint32_t i;
    uint32_t base;
    /* Resolved wave views, kept across samples: the primary and secondary
     * addresses only move at the object's own wave/phase transitions, so
     * resolving all four every sample was four constant-folded address
     * comparisons and a bank index for nothing. */
    uint32_t a_cur=0xffffffffu,a_nc=0xffffffffu,a_sec=0xffffffffu,a_ns=0xffffffffu;
    const uint8_t*wc=0,*wn=0,*sc=0,*sn=0;
    if(!s||!d||!t||!t->pitch||!t->base_wave||!t->bank)return 0;
    base=(uint32_t)mullo(pitch(r16(s,0xba),t->pitch),0xbb80u)>>20;
    for(i=0;i<n;i++){
        const uint16_t amp=env(s,0x74,t);
        const uint16_t pe=env(s,0xc4,t);
        const uint32_t lo=(uint32_t)pe&0x1fffu,sh=13u-(uint32_t)(pe>>13);
        const int32_t factor=(int32_t)(((lo+0x2000u)>>sh)-1u);
        uint32_t frequency=base+(((uint32_t)r16(s,0xec)*(uint32_t)factor)>>9);
        uint32_t phase,index,following,fraction,cur,sec,nc,ns;
        if(s[0x128]==1u)frequency>>=1;
        wt_set_frequency(s,frequency);
        phase=r32(s,0xf4)+r32(s,0xf8);
        if(s32(phase)>0x100000){
            phase-=0x100000u;
            w16(s,0x112,r16(s,0x114));
            if(r32(s,0x100)!=r32(s,0x104)){
                w32(s,0x100,r32(s,0x104));
                w32(s,0x108,r32(s,0x10c));
            }
        }
        w32(s,0xf4,phase);
        index=(phase>>9)&0x7ffu;following=(index+1)&0x7ffu;fraction=phase&0x1ffu;
        cur=r32(s,0x100);sec=r32(s,0x108);nc=cur;ns=sec;
        if(index>following&&r32(s,0x104)!=cur){nc=r32(s,0x104);ns=r32(s,0x10c);}
        if(cur!=a_cur){wc=pk_cf_wt_wave(t,cur);a_cur=cur;}
        if(nc!=a_nc){wn=pk_cf_wt_wave(t,nc);a_nc=nc;}
        if(sec!=a_sec){sc=pk_cf_wt_wave(t,sec);a_sec=sec;}
        if(ns!=a_ns){sn=pk_cf_wt_wave(t,ns);a_ns=ns;}
        if(!wc||!wn||!sc||!sn)return 0;
        {
            const int32_t a1=(int32_t)tabs16(wc,index),a2=(int32_t)tabs16(wn,following);
            const int32_t b1=(int32_t)tabs16(sc,index),b2=(int32_t)tabs16(sn,following);
            const int32_t first=s16((uint16_t)(a1+asr(mullo(a2-a1,(int32_t)fraction),9)));
            const int32_t second=s16((uint16_t)(b1+asr(mullo(b2-b1,(int32_t)fraction),9)));
            /* 32-bit two's-complement blend, exactly the host model's
             * (first*(255-MIX) + second*MIX) & 0xFFFFFFFF; uint32 multiply
             * wraps so a MIX word past 255 stays bit-exact without a 64-bit
             * helper the freestanding ColdFire runtime does not link. */
            const uint32_t mix=r16(s,0x112);
            const uint32_t mixed=(uint32_t)first*(uint32_t)(255-(int32_t)mix)
                                 +(uint32_t)second*mix;
            const int32_t osc=s16((uint16_t)(mixed>>8));
            int32_t sample=asr(mullo(osc,(int32_t)amp),16);
            sample=asr(mullo(sample,(int32_t)(s[6]&0xffu)),8);
            if(s[0xb8])sample=0;
            else if(sample>INT16_MAX)sample=INT16_MAX;
            else if(sample<INT16_MIN)sample=INT16_MIN;
            d[i]=(int16_t)sample;
        }
    }
    return 1;
}

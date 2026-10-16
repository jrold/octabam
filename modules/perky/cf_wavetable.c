#if defined(__mcoldfire__)
#pragma GCC optimize ("no-unroll-loops")
#endif
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
#include "cf_render_math.h"
#include <limits.h>

static uint16_t r16(const uint8_t*s,size_t o){return pk_cf_ld16(s,o);}
static uint32_t r32(const uint8_t*s,size_t o){return pk_cf_ld32(s,o);}
static void w16(uint8_t*s,size_t o,uint16_t v){pk_cf_st16(s,o,v);}
static void w32(uint8_t*s,size_t o,uint32_t v){pk_cf_st32(s,o,v);}
static int16_t s16(uint16_t u){return (int16_t)u;}
static int32_t s32(uint32_t u){return (int32_t)u;}
static uint32_t u32(int32_t s){return (uint32_t)s;}
static int32_t asr(int32_t v,unsigned n){return v>>n;}
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

/* --- shared common envelope, identical to cf_fold's, block-cached --------- */
typedef struct { uint8_t st; int32_t v; } wt_env;
typedef struct { uint8_t curve,f4,f6,f7,f10; uint16_t rate_up,rate_dn; const uint8_t*e1,*e2;
                 uint32_t cached_index,cached_pair; } wt_env_cfg;
static void wt_env_load(wt_env_cfg*c,wt_env*e,const uint8_t*s,size_t b,const pk_cf_wt_tables*t){
    e->st=s[b];
    e->v=s32(r32(s,b+0xc));
    c->f4=s[b+4];c->f6=s[b+6];c->f7=s[b+7];c->f10=s[b+0x10];
    c->curve=s[b+1];
    c->rate_up=r16(s,b+0x20);c->rate_dn=r16(s,b+0x22);
    c->e1=t->envelope1;c->e2=t->envelope2;c->cached_index=UINT32_MAX;c->cached_pair=0;
}
static void wt_env_store(uint8_t*s,size_t b,const wt_env*e){s[b]=e->st;w32(s,b+0xc,u32(e->v));}
static uint16_t wt_env_step(wt_env_cfg*c,wt_env*e){
    switch(e->st){
    case 0:if(c->f7||c->f4)e->st=1;break;
    case 1:e->v=s32(u32(e->v)+(uint32_t)c->rate_up);if(c->f4){if(e->v>0xffffe){e->st=4;if(e->v>=0x100000)e->v=0xfffff;}}else if(e->v>0xffffe){e->st=c->f6?4:3;if(e->v>=0x100000)e->v=0xfffff;}break;
    case 2:break;
    case 3:if(!c->f7&&(c->f4||!c->f10))e->st=4;break;
    case 4:if(c->f7)e->st=1;else{e->v=s32(u32(e->v)-(uint32_t)c->rate_dn);if(e->v<=0){e->v=0;e->st=c->f4?1:0;}}break;
    default:break;}
    if(c->curve!=1&&c->curve!=2)return (uint16_t)((u32(e->v)>>4)&0xffffu);
    {const uint8_t*ct=c->curve==1?c->e1:c->e2;uint32_t raw,idx,nx;int32_t f,a,z;
     if(!ct)return 0;
     raw=u32(e->v);idx=(raw>>10)&0x7ffu;nx=(idx+1)&0x7ffu;f=(int32_t)(raw&0x3ffu);
     /* Adjacent samples commonly reuse the same interpolation interval.
      * Cache only its immutable table pair, not the evolving envelope value. */
     if(c->cached_index!=idx){
         c->cached_pair=nx?pk_cf_ld32(ct,2u*idx):
             (uint32_t)tab16(ct,idx)|((uint32_t)tab16(ct,nx)<<16);
         c->cached_index=idx;
     }
     a=(int32_t)(c->cached_pair&0xffffu);z=(int32_t)(c->cached_pair>>16);
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

/* Same arithmetic as the original state-writing helper, but return the
 * increment so a render block can keep phase/increment in registers. */
static uint32_t wt_frequency_step(uint32_t f){
    int32_t shifted=s32(f<<20);
    int32_t hi=pk_cf_render_frequency_hi(shifted);
    int32_t result=asr(hi,10)-asr(shifted,31);
    return u32(result);
}

/* Pitch conversion is independent of oscillator phase and wave selection.
 * Keep its temporaries out of the oscillator's live register set. The buffer
 * starts as u16 envelope values widened to u32 and is overwritten in place. */
static void __attribute__((noinline))
wt_frequency_block(uint32_t *steps,uint32_t n,uint32_t base,
                   uint32_t pe_amount,uint32_t half_rate){
    uint32_t i;
    if(!pe_amount){
        const uint32_t increment=wt_frequency_step(base>>half_rate);
        for(i=0;i<n;i++)steps[i]=increment;
        return;
    }
    /* The original conversion discards all but the low twelve frequency
     * bits. Quantized pitch envelopes often repeat that key for many samples;
     * reuse only an exactly equal key, never approximate the envelope. */
    uint32_t previous=UINT32_MAX,increment=0;
    for(i=0;i<n;i++){
        const uint32_t pe=steps[i];
        const uint32_t lo=pe&0x1fffu,sh=13u-(pe>>13);
        const uint32_t factor=((lo+0x2000u)>>sh)-1u;
        const uint32_t frequency=base+((pe_amount*factor)>>9);
        const uint32_t key=(frequency>>half_rate)&0xfffu;
        if(key!=previous){increment=wt_frequency_step(key);previous=key;}
        steps[i]=increment;
    }
}

/* Avoid duplicating the oscillator for combinations of mute, envelope and
 * wave-boundary tests. Keep one compact loop instead of trading instruction
 * cache for unswitched copies. Clang does not support GCC optimize pragmas. */
#if defined(__GNUC__) && !defined(__clang__)
#pragma GCC push_options
#pragma GCC optimize ("no-unswitch-loops")
#endif
static int wt_render_chunk(uint8_t*s,int16_t*d,uint32_t n,const pk_cf_wt_tables*t){
    uint32_t i;
    uint32_t base;
    /* Current wave views change only at the object's phase transition. */
    const uint8_t *wc,*sc;
    /* Block invariants and block-local state.  The firmware-visible object is
     * observed at render-call boundaries, so avoid endian load/store traffic
     * for fields that are only consumed by this loop and commit them once. */
    uint32_t pe_amount,half_rate,phase,step,cur,sec,target_cur,target_sec;
    uint16_t mix,target_mix;
    uint8_t velocity,mute;
    wt_env_cfg ea_cfg,ep_cfg;
    wt_env ea,ep,initial_ea,initial_ep;
    uint16_t amplitudes[16];uint32_t steps[16];
    if(!s||!d||!t||!t->pitch||!t->base_wave||!t->bank)return 0;
    pe_amount=r16(s,0xec);half_rate=(s[0x128]==1u)?1u:0u;
    phase=r32(s,0xf4);step=r32(s,0xf8);
    cur=r32(s,0x100);target_cur=r32(s,0x104);
    sec=r32(s,0x108);target_sec=r32(s,0x10c);
    mix=r16(s,0x112);target_mix=r16(s,0x114);
    velocity=s[6];mute=s[0xb8];
    wt_env_load(&ea_cfg,&ea,s,0x74,t);
    wt_env_load(&ep_cfg,&ep,s,0xc4,t);
    base=(uint32_t)mullo(pitch(r16(s,0xba),t->pitch),0xbb80u)>>20;
    initial_ea=ea;initial_ep=ep;
    for(i=0;i<n;i++)amplitudes[i]=wt_env_step(&ea_cfg,&ea);
    for(i=0;i<n;i++)steps[i]=wt_env_step(&ep_cfg,&ep);
    wt_frequency_block(steps,n,base,pe_amount,half_rate);
    wc=pk_cf_wt_wave(t,cur);sc=pk_cf_wt_wave(t,sec);
    for(i=0;i<n;i++){
        const uint8_t *wn,*sn;
        const uint16_t amp=amplitudes[i];
        uint32_t index,following,fraction;
        step=steps[i];
        phase+=step;
        if(s32(phase)>0x100000){
            phase-=0x100000u;
            mix=target_mix;
            if(cur!=target_cur){cur=target_cur;sec=target_sec;
                wc=pk_cf_wt_wave(t,cur);sc=pk_cf_wt_wave(t,sec);}

        }
        index=(phase>>9)&0x7ffu;following=(index+1)&0x7ffu;fraction=phase&0x1ffu;
        wn=wc;sn=sc;
        if(index>following&&target_cur!=cur){
            wn=pk_cf_wt_wave(t,target_cur);sn=pk_cf_wt_wave(t,target_sec);
        }
        if(!wc||!wn||!sc||!sn){
            /* Preserve the original partial-state commit on malformed wave
             * addresses: only envelopes through the failed sample survive. */
            uint32_t j;ea=initial_ea;ep=initial_ep;
            for(j=0;j<=i;j++){
                (void)wt_env_step(&ea_cfg,&ea);(void)wt_env_step(&ep_cfg,&ep);
            }
            w32(s,0xf4,phase);w32(s,0xf8,step);
            w32(s,0x100,cur);w32(s,0x108,sec);w16(s,0x112,mix);
            wt_env_store(s,0x74,&ea);wt_env_store(s,0xc4,&ep);
            return 0;
        }
        /* Silence changes no oscillator/envelope state. Validate addresses
         * first so even a muted malformed object retains its failure point. */
        if(mute||!velocity||!amp){d[i]=0;continue;}
        {
            int32_t a1,a2,b1,b2;
            if(following){
                const uint32_t a=pk_cf_ld32(wc,2u*index);
                const uint32_t b=pk_cf_ld32(sc,2u*index);
                a1=s16((uint16_t)a);a2=s16((uint16_t)(a>>16));
                b1=s16((uint16_t)b);b2=s16((uint16_t)(b>>16));
            }else{
                a1=tabs16(wc,index);a2=tabs16(wn,following);
                b1=tabs16(sc,index);b2=tabs16(sn,following);
            }
            const int32_t first=s16((uint16_t)(a1+asr(mullo(a2-a1,(int32_t)fraction),9)));
            const int32_t second=s16((uint16_t)(b1+asr(mullo(b2-b1,(int32_t)fraction),9)));
            /* 32-bit two's-complement blend, exactly the host model's
             * (first*(255-MIX) + second*MIX) & 0xFFFFFFFF; uint32 multiply
             * wraps so a MIX word past 255 stays bit-exact without a 64-bit
             * helper the freestanding ColdFire runtime does not link. */
            /* Distribute the blend modulo 2^32. This needs only one
             * variable multiply, including for malformed MIX > 255. */
            const uint32_t mixed=((uint32_t)first<<8)-(uint32_t)first
                                 +(uint32_t)(second-first)*(uint32_t)mix;
            const int32_t osc=s16((uint16_t)(mixed>>8));
            int32_t sample=asr(mullo(osc,(int32_t)amp),16);
            sample=asr(mullo(sample,(int32_t)(velocity&0xffu)),8);
            if(mute)sample=0;
            else if(sample>INT16_MAX)sample=INT16_MAX;
            else if(sample<INT16_MIN)sample=INT16_MIN;
            d[i]=(int16_t)sample;
        }
    }
    w32(s,0xf4,phase);w32(s,0xf8,step);
    w32(s,0x100,cur);w32(s,0x108,sec);w16(s,0x112,mix);
    wt_env_store(s,0x74,&ea);wt_env_store(s,0xc4,&ep);
    return 1;
}
#if defined(__GNUC__) && !defined(__clang__)
#pragma GCC pop_options
#endif
/* Short independent envelope passes reduce register pressure in the oscillator
 * loop. All samples are still generated in this call, without added latency.
 * Chunks preserve the public renderer's arbitrary block-length contract. */
int pk_cf_wt_render(uint8_t*s,int16_t*d,uint32_t n,const pk_cf_wt_tables*t){
    if(!s||!d||!t||!t->pitch||!t->base_wave||!t->bank)return 0;
    if(!n)return 1;
    int ok=1;pk_cf_render_math_context context=pk_cf_render_math_begin();
    do{
        uint32_t count=n>16u?16u:n;
        if(!wt_render_chunk(s,d,count,t)){ok=0;break;}
        d+=count;n-=count;
    }while(n);
    pk_cf_render_math_end(context);
    return ok;
}

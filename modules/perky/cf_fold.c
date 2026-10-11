#include "cf_fold.h"
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

static uint16_t env(uint8_t*s,size_t b,const pk_cf_fold_tables*t){
    uint8_t st=s[b];int32_t v=s32(r32(s,b+0xc));
    switch(st){
    case 0:if(s[b+7]||s[b+4])s[b]=1;break;
    case 1:v=s32(u32(v)+(uint32_t)r16(s,b+0x20));w32(s,b+0xc,u32(v));if(s[b+4]){if(v>0xffffe){s[b]=4;if(v>=0x100000){v=0xfffff;w32(s,b+0xc,u32(v));}}}else if(v>0xffffe){s[b]=s[b+6]?4:3;if(v>=0x100000){v=0xfffff;w32(s,b+0xc,u32(v));}}break;
    case 2:break;
    case 3:if(!s[b+7]&&(s[b+4]||!s[b+0x10]))s[b]=4;break;
    case 4:if(s[b+7])s[b]=1;else{v=s32(u32(v)-(uint32_t)r16(s,b+0x22));w32(s,b+0xc,u32(v));if(v<=0){v=0;w32(s,b+0xc,0);s[b]=s[b+4]?1:0;}}break;
    default:break;
    }
    if(s[b+1]!=1&&s[b+1]!=2)return (uint16_t)((u32(v)>>4)&0xffffu);
    {
        const uint8_t*c=s[b+1]==1?t->envelope1:t->envelope2;uint32_t raw,idx,nx;int32_t f,a,z;
        if(!c)return 0;
        raw=u32(v);idx=(raw>>10)&0x7ffu;nx=(idx+1)&0x7ffu;f=(int32_t)(raw&0x3ffu);
        a=(int32_t)tab16(c,idx);z=(int32_t)tab16(c,nx);
        return (uint16_t)(a+asr(mullo(z-a,f),10));
    }
}

static int32_t pitch(uint16_t raw,const uint8_t*t){
    int32_t p=(int32_t)s16(raw);int neg=0;uint32_t v=0;
    if(p<0){uint16_t m=(uint16_t)(0u-raw);p=(int32_t)s16(m);if(p>=0x1000)neg=1;}
    if(p<0x1000)v=tab16(t,(uint16_t)p);
    else{uint16_t q=(uint16_t)p;uint32_t sh=((q-0x1000u)>>9)&0x7fu,ad=sh*127u;int16_t ix;sh=(sh+1u)&0xffu;ix=s16((uint16_t)((uint32_t)q+(ad<<9)-0x200u));v=(uint32_t)tab16(t,(uint16_t)ix)<<sh;}
    if(neg)v=0u-v;
    return s32(v);
}

/* Return the oscillator increment instead of writing it into the ARM-layout
 * object every sample.  Renderers keep the hot oscillator fields native for
 * the 16-sample block and publish them at the call boundary. */
static uint32_t frequency_step(uint32_t f){
    int32_t shifted=s32(f<<20);
    int32_t hi=pk_cf_mul_hi_s32(shifted,s32(0x057619f1u));
    int32_t result=asr(hi,10)-asr(shifted,31);
    return u32(result);
}

typedef struct {
    const uint8_t *table;
    uint32_t table_address;
    uint32_t phase;
    uint32_t step;
    uint32_t current;
    uint32_t next;
} fold_osc_state;

static void osc_load(fold_osc_state*o,const uint8_t*s,size_t b){
    o->table=0;
    o->table_address=0xffffffffu;
    o->phase=r32(s,b+4);
    o->step=r32(s,b+8);
    o->current=r32(s,b+0xc);
    o->next=r32(s,b+0x10);
}
static void osc_store(const fold_osc_state*o,uint8_t*s,size_t b){
    w32(s,b+4,o->phase);
    w32(s,b+8,o->step);
    w32(s,b+0xc,o->current);
}
static int osc_step(fold_osc_state*o,const pk_cf_fold_tables*t,int16_t*out){
    uint32_t i,j;int32_t f,a,z;
    o->phase+=o->step;
    if(s32(o->phase)>0x100000){
        o->phase-=0x100000u;
        if(o->next!=o->current)o->current=o->next;
    }
    if(o->current!=o->table_address){
        o->table=wave(t,o->current);
        o->table_address=o->current;
    }
    if(!o->table)return 0;
    i=(o->phase>>12)&0xffu;j=(i+1)&0xffu;f=(int32_t)(o->phase&0xfffu);
    a=(int32_t)tabs16(o->table,i);z=(int32_t)tabs16(o->table,j);
    *out=s16((uint16_t)(a+asr(mullo(z-a,f),12)));
    return 1;
}

static uint32_t rnd(pk_cf_fold_rng*r){
    const uint32_t a=0x5851f42d,b=0x4c957f2d;uint32_t ol=r->low,oh=r->high,acc=pk_cf_mul_lo_u32(ol,a),pl=pk_cf_mul_lo_u32(ol,b),ph=pk_cf_mul_hi_u32(ol,b),nl,carry,nh;
    acc+=pk_cf_mul_lo_u32(oh,b);nl=pl+1u;carry=nl<pl;nh=acc+ph+carry;r->low=nl;r->high=nh;return nh&0x7fffffffu;
}
static int16_t noise(uint8_t*s,size_t b,pk_cf_fold_rng*r){uint16_t c=r16(s,b);int16_t x;if(c){w16(s,b,(uint16_t)(c-1));return s16(r16(s,b+0x10));}w16(s,b,r16(s,b+2));x=s16((uint16_t)rnd(r));w16(s,b+0x10,(uint16_t)x);return x;}
static int32_t tri(int32_t in){uint32_t p=(u32(in)+0x8000u)&0x1ffffu;return p<0x10000u?(int32_t)p-0x8000:0x18000-(int32_t)p;}
static void transient(uint8_t*s,int32_t*f,pk_cf_fold_rng*r){uint16_t c=r16(s,0xec);if(c>0x210)return;if(s[5]==0)*f=s32(u32(*f)+0x3fffu);else if(s[5]==2){int32_t n=(int32_t)noise(s,0x60,r);if(c<=0x110){if(c<=0x8f){int32_t m=mullo(n,11);uint32_t field=(u32(m)>>4)&0x03ffffffu;if(field&0x02000000u)field|=0xfc000000u;*f=s32(u32(*f)+field);}else{int32_t rem=(int32_t)(0x110u-c),x=asr(mullo(n,rem),8);x=asr(mullo(44,x),6);*f=s32(u32(*f)+u32(x));}}}w16(s,0xec,(uint16_t)(c+1));}
static int16_t vel8(uint8_t velocity,int32_t in){int32_t o=asr(mullo(in,(int32_t)velocity),8);if(o>INT16_MAX)o=INT16_MAX;else if(o<INT16_MIN)o=INT16_MIN;return (int16_t)o;}

/* THE PITCH TERM IS LOOP-INVARIANT (frame-cost work, 9 Oct 2026). `freq` was
 * one function and the sample loop called it once per sample -- but its first
 * half depends on s[0xba] ALONE, which only common_update writes and that runs
 * before the block, never inside it. So the `pitch()` table read and the
 * `mullo(p,0xbb80)` after it were recomputed identically 16 times a block, per
 * oscillator (both of fold2's included). Split: the base is taken once per
 * block, the pitch envelope's own term stays per sample. Numerically identical
 * -- the qualification suite compares PCM, not cycles. */
static uint32_t freq_base(uint8_t*s,const uint8_t*t){int32_t p=pitch(r16(s,0xba),t);return(uint32_t)mullo(p,0xbb80)>>20;}
static uint32_t freq_env(const uint8_t*s,uint16_t pe){uint32_t lo=pe&0x1fffu,hi=pe>>13,factor=(uint16_t)(((lo+0x2000u)>>(13u-hi))-1u);return((uint32_t)r16(s,0xee)*factor)>>9;}
static int support1(const uint8_t*s){return r32(s,0x58)==PK_CF_FOLD_SIMPLE_OSC_RENDER;}
static int support2(const uint8_t*s,uint32_t o){uint32_t p1=r32(s,0x128),p2=r32(s,0x12c),a=o+0x2c,b=o+0xf4;if(!((p1==a&&p2==b)||(p1==b&&p2==a)))return 0;return r32(s,0x58)==PK_CF_FOLD_SIMPLE_OSC_RENDER&&r32(s,0x120)==PK_CF_FOLD_SIMPLE_OSC_RENDER;}

int pk_cf_fold1_render(uint8_t*s,int16_t*d,uint32_t n,const pk_cf_fold_tables*t,pk_cf_fold_rng*r){
    uint32_t i;
    fold_osc_state osc;
    uint32_t fb;
    int32_t amount;
    uint8_t mute,velocity;
    if(!s||!d||!t||!r||!t->pitch||!support1(s))return 0;
    fb=freq_base(s,t->pitch);
    amount=(int32_t)s16(r16(s,0xf0))+0x100;
    mute=s[0xb8];velocity=s[6];
    osc_load(&osc,s,0x2c);
    for(i=0;i<n;i++){
        uint16_t a=env(s,0x74,t),pe=env(s,0xc4,t);int16_t o=0;int32_t driven,folded,mixed,shaped;
        osc.step=frequency_step(fb+freq_env(s,pe));
        if(!osc_step(&osc,t,&o)){osc_store(&osc,s,0x2c);return 0;}
        driven=asr(mullo(o,amount),8);folded=tri(driven);transient(s,&folded,r);
        if(mute){d[i]=0;continue;}
        mixed=asr(s32(u32(folded)+u32((int32_t)o)),1);shaped=asr(mullo((int32_t)a,mixed),16);d[i]=vel8(velocity,shaped);
    }
    osc_store(&osc,s,0x2c);
    return 1;
}

int pk_cf_fold2_render(uint8_t*s,uint32_t obj,int16_t*d,uint32_t n,const pk_cf_fold_tables*t,pk_cf_fold_rng*r){
    uint32_t i;
    fold_osc_state o1s,o2s;
    uint32_t fb;
    int32_t amount;
    uint8_t mute,velocity;
    size_t p1,p2;
    uint16_t fade,last_a;
    if(!s||!d||!t||!r||!t->pitch||!support2(s,obj))return 0;
    fb=freq_base(s,t->pitch);
    amount=(int32_t)s16(r16(s,0xf0))+0x100;
    mute=s[0xb8];velocity=s[6];
    p1=(size_t)(r32(s,0x128)-obj);p2=(size_t)(r32(s,0x12c)-obj);
    fade=r16(s,0x132);last_a=r16(s,0x130);
    osc_load(&o1s,s,p1);osc_load(&o2s,s,p2);
    for(i=0;i<n;i++){
        uint16_t a=env(s,0x74,t),pe=env(s,0xc4,t),fc;
        int16_t o1=0,o2=0;
        int32_t fp,sp,sum,orig,driven,folded,mixed;
        const uint32_t fx=fb+freq_env(s,pe);
        o1s.step=frequency_step(fx);
        if(fade<a)a=(uint16_t)(a-fade);
        if(!osc_step(&o1s,t,&o1)){
            osc_store(&o1s,s,p1);osc_store(&o2s,s,p2);w16(s,0x130,last_a);w16(s,0x132,fade);return 0;
        }
        if(!osc_step(&o2s,t,&o2)){
            osc_store(&o1s,s,p1);osc_store(&o2s,s,p2);w16(s,0x130,last_a);w16(s,0x132,fade);return 0;
        }
        fp=mullo((int32_t)a,(int32_t)o1);
        sp=mullo((int32_t)fade,(int32_t)o2);
        fc=fade<0x88u?0x88u:fade;
        sum=s32(u32(asr(sp,16))+u32(asr(fp,16)));
        fc=(uint16_t)(fc-0x88u);
        orig=asr(sum,1);
        last_a=a;fade=fc;
        driven=asr(mullo(orig,amount),8);folded=tri(driven);transient(s,&folded,r);
        if(mute){d[i]=0;continue;}
        mixed=asr(s32(u32(folded)+u32(orig)),1);d[i]=vel8(velocity,mixed);
    }
    osc_store(&o1s,s,p1);osc_store(&o2s,s,p2);w16(s,0x130,last_a);w16(s,0x132,fade);
    return 1;
}

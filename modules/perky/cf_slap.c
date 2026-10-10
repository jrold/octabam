/* ColdFire renderer for the PĒRKONS v1.2.1 Slap family (V3 algorithm 2).
 *
 * Operates directly on the original 0x2670-byte ARM object at the offsets the
 * firmware uses, mirroring modules/perky/slap_compact.py (exact against the
 * firmware's captured PCM, object and RNG for M1/M2/M3 x 3 corners x
 * continuation/retrigger).
 */
#include "cf_slap.h"
#include "cf_math.h"
#include <limits.h>

static uint16_t r16(const uint8_t*s,size_t o){return (uint16_t)s[o]|(uint16_t)((uint16_t)s[o+1]<<8);}
static uint32_t r32(const uint8_t*s,size_t o){return (uint32_t)s[o]|((uint32_t)s[o+1]<<8)|((uint32_t)s[o+2]<<16)|((uint32_t)s[o+3]<<24);}
static void w16(uint8_t*s,size_t o,uint16_t v){s[o]=(uint8_t)v;s[o+1]=(uint8_t)(v>>8);}
static void w32(uint8_t*s,size_t o,uint32_t v){s[o]=(uint8_t)v;s[o+1]=(uint8_t)(v>>8);s[o+2]=(uint8_t)(v>>16);s[o+3]=(uint8_t)(v>>24);}
static int16_t s16(uint16_t u){return (u&0x8000u)?(int16_t)(-1-(int16_t)(uint16_t)~u):(int16_t)u;}
static int32_t s32(uint32_t u){return (u&0x80000000u)?-1-(int32_t)~u:(int32_t)u;}
static uint32_t u32(int32_t s){return s>=0?(uint32_t)s:~(uint32_t)(-1-s);}
static int32_t asr(int32_t v,unsigned n){uint32_t b;if(!n)return v;b=u32(v)>>n;if(v<0)b|=(~0u)<<(32u-n);return s32(b);}
static int32_t mullo(int32_t a,int32_t b){return s32(pk_cf_mul_lo_u32(u32(a),u32(b)));}
static int32_t add(int32_t a,int32_t b){return s32(u32(a)+u32(b));}
static int32_t sub(int32_t a,int32_t b){return s32(u32(a)-u32(b));}
static int32_t clamp32767(int32_t v){if(v<-32767)return -32767;if(v>=32767)return 32767;return v;}
static uint16_t tab16(const uint8_t*t,size_t i){return (uint16_t)t[2*i]|(uint16_t)((uint16_t)t[2*i+1]<<8);}

/* --- shared common envelope (amp env at object 0x74) ---------------------- */
static uint16_t slap_env(uint8_t*s,size_t b,const pk_cf_fold_tables*t){
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

/* --- shared 32-bit PRNG, identical to cf_fold's --------------------------- */
static uint32_t slap_rnd(pk_cf_fold_rng*r){const uint32_t a=0x5851f42d,b=0x4c957f2d;uint32_t ol=r->low,oh=r->high,acc=pk_cf_mul_lo_u32(ol,a),pl=pk_cf_mul_lo_u32(ol,b),ph=pk_cf_mul_hi_u32(ol,b),nl,carry,nh;acc+=pk_cf_mul_lo_u32(oh,b);nl=pl+1u;carry=nl<pl;nh=acc+ph+carry;r->low=nl;r->high=nh;return nh&0x7fffffffu;}

/* Noise source: a countdown of held samples then a fresh PRNG draw. */
static int16_t slap_noise(uint8_t*s,pk_cf_fold_rng*r){
    uint16_t c=r16(s,0x60);
    if(c){w16(s,0x60,(uint16_t)(c-1u));return s16(r16(s,0x70));}
    w16(s,0x60,r16(s,0x62));
    {int16_t x=s16((uint16_t)slap_rnd(r));w16(s,0x70,(uint16_t)x);return x;}
}

/* One filter stage advance (the firmware's helper, run twice per sample). */
static void slap_filter(uint8_t*s,int32_t in){
    int32_t coeff=(int32_t)r16(s,0xaa);
    int32_t velocity=s32(r32(s,0xb4));
    int32_t product=mullo(velocity,coeff),first,second,fb;
    if(product<0)product=s32(u32(product)+0xffffu);
    first=clamp32767(add(s32(r32(s,0xac)),asr(product,16)));
    w32(s,0xac,u32(first));
    second=clamp32767(sub(sub(in,first),asr(mullo(velocity,(int32_t)r16(s,0xa8)),10)));
    w32(s,0xb0,u32(second));
    fb=mullo(second,coeff);
    if(fb<0)fb=s32(u32(fb)+0xffffu);
    velocity=clamp32767(add(velocity,asr(fb,16)));
    w32(s,0xb4,u32(velocity));
}

/* Five-tap feedback delay ring into the object's own 0x12C5-word ring. */
static int32_t slap_delay(uint8_t*s,int32_t in){
    uint32_t index=r16(s,0x266a),next=index+1u,tap;
    int32_t stage=in;
    if(next>PK_CF_SLAP_RING_LEN-1u)next=0u;
    for(tap=0;tap<5u;tap++){
        uint32_t delay=(uint32_t)r16(s,0xcc+2u*tap);
        int32_t gain=s32((uint32_t)r16(s,0xd6+2u*tap));
        uint32_t ri=index>=delay?(index-delay):(PK_CF_SLAP_RING_LEN+index-delay);
        int32_t acc=mullo(stage,gain-0x10);
        acc=add(acc,mullo(gain,(int32_t)s16(r16(s,PK_CF_SLAP_RING_OFF+2u*ri))));
        stage=clamp32767(asr(acc,4));
    }
    w16(s,PK_CF_SLAP_RING_OFF+2u*next,(uint16_t)stage);
    w16(s,0x266a,(uint16_t)next);
    {int32_t mix=s16(r16(s,0x266c)),wet=asr(mullo(stage,5),1);
     int32_t out=mullo(in,0x0fff-mix);
     out=add(out,mullo(mix,wet));
     return asr(out,12);}
}

/* Native re-trigger: arm the envelope and clear its value when the object owns
 * a reset slot (object+0x7C). */
static void slap_retrigger(uint8_t*s){
    uint32_t hold=r32(s,0x84);
    w32(s,0x84,(hold&0xffffff00u)|1u);
    s[0x74]=1u;
    if(s[0x7c])w32(s,0x80,0u);
}

static int16_t slap_velocity(uint8_t vel,int32_t value){
    int32_t out=asr(mullo(value,(int32_t)(vel&0xffu)),8);
    if(out>INT16_MAX)out=INT16_MAX;else if(out<INT16_MIN)out=INT16_MIN;
    return (int16_t)out;
}

/* --- control path ---------------------------------------------------------
 * Seven closed-form laws plus the filter-coefficient curve, which is captured
 * data over the complete 12-bit domain (modules/perky/slap_coeff_table.py). */
#include "cf_slap_coeff.inc"

static uint16_t slap_time_parameter(uint16_t prepared){
    uint32_t q=0x7fffu+((uint32_t)prepared<<2),mant=(q&0xfffu)+0x1000u,exp=(q>>12)&0xfu,v;
    if(exp>11u)v=(mant<<(exp-12u))&0xffffu;else v=(mant>>(12u-exp))&0xffffu;
    v=(v-1u)&0xffffffffu;v=(v>>1)&0x7fffu;return (uint16_t)((v-0x7fu)&0xffffu);
}
/* Amplitude-envelope decay rate: the standard helper with offset 18 and scale
 * 750, exact over all 3584 captured points. */
static uint16_t slap_amp_rate(uint16_t prepared_decay){
    uint32_t den=48u*19u+((48u*749u*(uint32_t)slap_time_parameter(prepared_decay))>>12);
    return den?(uint16_t)(0xfffffu/den):0u;
}

void pk_cf_slap_init(uint8_t*s,uint8_t panel_mode,uint8_t velocity,uint8_t note){
    size_t i;for(i=0;i<PK_CF_SLAP_STATE_BYTES;++i)s[i]=0;
    w16(s,8,0x0ff0u);
    s[6]=velocity?velocity:1u;
    s[7]=note;
    /* noise source: reload 2, empty hold */
    w16(s,0x60,0u);w16(s,0x62,2u);w16(s,0x70,0u);
    /* amplitude envelope: linear shape, flag6 set, reset armed */
    s[0x74]=0;s[0x75]=0;s[0x78]=0;s[0x7a]=1;s[0x7b]=0;s[0x7c]=1;
    w16(s,0x84,1u);
    w16(s,0x94,PK_CF_SLAP_AMP_ATTACK);
    /* delay counters and taps, straight from the captured init state; MODE
     * only moves the counter's target */
    w16(s,0xc2,0u);w16(s,0xc4,0u);w16(s,0xc6,5u);
    w16(s,0xca,(uint16_t)(PK_CF_SLAP_MODE_STRIDE*(uint16_t)(panel_mode+1u)));
    for(i=0;i<5u;++i){w16(s,0xcc+2u*i,(uint16_t)SLAP_TAP_DELAY[i]);w16(s,0xd6+2u*i,(uint16_t)SLAP_TAP_GAIN[i]);}
    w16(s,0x266a,0u);w16(s,0x266c,0u);
}

void pk_cf_slap_update(uint8_t*s,uint8_t panel_mode,const uint8_t*pitch_table){
    uint16_t tune=(uint16_t)r32(s,0x1c),decay=(uint16_t)r32(s,0x20);
    uint16_t p1=(uint16_t)r32(s,0x24),p2=(uint16_t)r32(s,0x28);
    uint32_t biased=(uint32_t)tune+PK_CF_SLAP_TUNE_BIAS;
    (void)pitch_table;
    w16(s,0xba,(uint16_t)(biased>4095u?4095u:biased));
    w16(s,0xaa,(uint16_t)SLAP_COEFF[tune&0x0fffu]);
    w16(s,0x96,slap_amp_rate(decay));
    w16(s,0xbe,p1);
    w16(s,0x266c,(uint16_t)(p1>>1));
    w16(s,0xc0,p2);
    w16(s,0xa8,(uint16_t)(2048u-((uint32_t)p2>>1)));
    w16(s,0xca,(uint16_t)(PK_CF_SLAP_MODE_STRIDE*(uint16_t)(panel_mode+1u)));
    /* sustain gate: the common obj+8 <= decay rule, read by the envelope */
    s[0x7b]=(uint8_t)(r16(s,8)<=decay);
}

void pk_cf_slap_trigger(uint8_t*s,uint8_t velocity,uint8_t note){
    s[6]=velocity?velocity:1u;
    if(note)s[7]=note;
    slap_retrigger(s);
}

int pk_cf_slap_render(uint8_t*s,int16_t*d,uint32_t n,const pk_cf_fold_tables*t,pk_cf_fold_rng*rng){
    uint32_t i;
    if(!s||!d||!t||!t->envelope1||!rng)return 0;
    for(i=0;i<n;i++){
        int16_t nv=slap_noise(s,rng);
        uint32_t first=r16(s,0xc2);
        uint16_t a;
        int32_t scaled;
        slap_filter(s,(int32_t)nv);
        slap_filter(s,(int32_t)nv);
        if((uint32_t)r16(s,0xca)>first){
            w16(s,0xc2,(uint16_t)((first+1u)&0xffffu));
        }else{
            uint32_t second=r16(s,0xc4);
            if((uint32_t)r16(s,0xc6)>second){
                w16(s,0xc4,(uint16_t)((second+1u)&0xffffu));
                w16(s,0xc2,0u);
                slap_retrigger(s);
            }
        }
        a=slap_env(s,0x74,t);
        scaled=asr(mullo(s32(r32(s,0xac)),(int32_t)a),16);
        d[i]=slap_velocity(s[6],slap_delay(s,scaled));
    }
    return 1;
}

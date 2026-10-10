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

static uint16_t r16(const uint8_t*s,size_t o){return pk_cf_ld16(s,o);}
static uint32_t r32(const uint8_t*s,size_t o){return pk_cf_ld32(s,o);}
static void w16(uint8_t*s,size_t o,uint16_t v){pk_cf_st16(s,o,v);}
static void w32(uint8_t*s,size_t o,uint32_t v){pk_cf_st32(s,o,v);}
static int16_t s16(uint16_t u){return (u&0x8000u)?(int16_t)(-1-(int16_t)(uint16_t)~u):(int16_t)u;}
static int32_t s32(uint32_t u){return (u&0x80000000u)?-1-(int32_t)~u:(int32_t)u;}
static uint32_t u32(int32_t s){return s>=0?(uint32_t)s:~(uint32_t)(-1-s);}
static int32_t asr(int32_t v,unsigned n){uint32_t b;if(!n)return v;b=u32(v)>>n;if(v<0)b|=(~0u)<<(32u-n);return s32(b);}
static int32_t mullo(int32_t a,int32_t b){return s32(pk_cf_mul_lo_u32(u32(a),u32(b)));}
static int32_t add(int32_t a,int32_t b){return s32(u32(a)+u32(b));}
static int32_t sub(int32_t a,int32_t b){return s32(u32(a)-u32(b));}
static int32_t clamp32767(int32_t v){if(v<-32767)return -32767;if(v>=32767)return 32767;return v;}
static uint16_t tab16(const uint8_t*t,size_t i){return pk_cf_ld16(t,2u*i);}

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

typedef struct {
    uint16_t count,reload;
    int16_t held;
} slap_noise_state;
static int16_t slap_noise_step(slap_noise_state*n,pk_cf_fold_rng*r){
    if(n->count){n->count=(uint16_t)(n->count-1u);return n->held;}
    n->count=n->reload;n->held=s16((uint16_t)slap_rnd(r));return n->held;
}

typedef struct {
    int32_t coeff,damp;
    int32_t first,second,velocity;
} slap_filter_state;
/* One filter stage advance (the firmware's helper, run twice per sample),
 * with the history kept native across the block. */
static void slap_filter_step(slap_filter_state*f,int32_t in){
    int32_t product=mullo(f->velocity,f->coeff),fb;
    if(product<0)product=s32(u32(product)+0xffffu);
    f->first=clamp32767(add(f->first,asr(product,16)));
    f->second=clamp32767(sub(sub(in,f->first),asr(mullo(f->velocity,f->damp),10)));
    fb=mullo(f->second,f->coeff);
    if(fb<0)fb=s32(u32(fb)+0xffffu);
    f->velocity=clamp32767(add(f->velocity,asr(fb,16)));
}

typedef struct {
    uint16_t index,mix;
    uint16_t delay[5],gain[5];
} slap_delay_state;
/* Five-tap feedback delay ring.  The ring itself still receives each sample
 * immediately; only invariant tap metadata and the running index stay native. */
static int32_t slap_delay_step(uint8_t*s,slap_delay_state*q,int32_t in){
    uint32_t next=(uint32_t)q->index+1u,tap;
    int32_t stage=in;
    if(next>PK_CF_SLAP_RING_LEN-1u)next=0u;
    for(tap=0;tap<5u;tap++){
        uint32_t delay=(uint32_t)q->delay[tap];
        int32_t gain=(int32_t)q->gain[tap];
        uint32_t ri=(uint32_t)q->index>=delay?((uint32_t)q->index-delay):(PK_CF_SLAP_RING_LEN+(uint32_t)q->index-delay);
        int32_t acc=mullo(stage,gain-0x10);
        acc=add(acc,mullo(gain,(int32_t)s16(r16(s,PK_CF_SLAP_RING_OFF+2u*ri))));
        stage=clamp32767(asr(acc,4));
    }
    w16(s,PK_CF_SLAP_RING_OFF+2u*next,(uint16_t)stage);
    q->index=(uint16_t)next;
    {int32_t mix=s16(q->mix),wet=asr(mullo(stage,5),1);
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
    uint32_t i,k;
    slap_noise_state ns;
    slap_filter_state fs;
    slap_delay_state ds;
    uint16_t first_count,second_count,second_limit,target;
    uint8_t velocity;
    if(!s||!d||!t||!t->envelope1||!rng)return 0;

    ns.count=r16(s,0x60);ns.reload=r16(s,0x62);ns.held=s16(r16(s,0x70));
    fs.coeff=(int32_t)r16(s,0xaa);fs.damp=(int32_t)r16(s,0xa8);
    fs.first=s32(r32(s,0xac));fs.second=s32(r32(s,0xb0));fs.velocity=s32(r32(s,0xb4));
    ds.index=r16(s,0x266a);ds.mix=r16(s,0x266c);
    for(k=0;k<5u;k++){ds.delay[k]=r16(s,0xcc+2u*k);ds.gain[k]=r16(s,0xd6+2u*k);}
    first_count=r16(s,0xc2);second_count=r16(s,0xc4);second_limit=r16(s,0xc6);target=r16(s,0xca);
    velocity=s[6];

    for(i=0;i<n;i++){
        int16_t nv=slap_noise_step(&ns,rng);
        uint16_t a;
        int32_t scaled;
        slap_filter_step(&fs,(int32_t)nv);
        slap_filter_step(&fs,(int32_t)nv);
        if((uint32_t)target>(uint32_t)first_count){
            first_count=(uint16_t)(first_count+1u);
        }else if((uint32_t)second_limit>(uint32_t)second_count){
            second_count=(uint16_t)(second_count+1u);
            first_count=0u;
            slap_retrigger(s);
        }
        a=slap_env(s,0x74,t);
        scaled=asr(mullo(fs.first,(int32_t)a),16);
        d[i]=slap_velocity(velocity,slap_delay_step(s,&ds,scaled));
    }

    w16(s,0x60,ns.count);w16(s,0x70,(uint16_t)ns.held);
    w32(s,0xac,u32(fs.first));w32(s,0xb0,u32(fs.second));w32(s,0xb4,u32(fs.velocity));
    w16(s,0xc2,first_count);w16(s,0xc4,second_count);
    w16(s,0x266a,ds.index);
    return 1;
}

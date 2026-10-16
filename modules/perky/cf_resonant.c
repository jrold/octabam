#if defined(__mcoldfire__)
#pragma GCC optimize ("no-unroll-loops", "no-split-loops")
#endif
/* Loop splitting duplicates these short recurrence passes. The footprint
 * campaign measures smaller code and lower snare/bass target cost with it
 * disabled; keep the same options on primitives and callers. */
/* ColdFire renderer for the PĒRKONS v1.2.1 Resonant Drums family.
 *
 * Operates directly on the original ARM object (0x178 bytes for the bassdrum
 * path, 0x1d4 for the snare path) at the same offsets the firmware uses, the
 * way cf_fold/cf_karplus/cf_noise_tone do.  Every operation mirrors
 * modules/perky/resonator_compact.py, resonant_bass_compact.py and
 * resonant_snare_compact.py, which are exact against NativeV121ResonantBass /
 * NativeV121ResonantSnare and against the real firmware's own PCM captured
 * under Unicorn (out/perky/engine-fixtures/engine-7-*).
 *
 * Panel mapping (engine 7):  M1 -> snare object,  M2 -> bass object,
 * M3 -> the shared Noise/Tone renderer that is already shipped.
 *
 * ⚠️ BLOCK-CACHED RENDER (frame-cost work, 10 Oct 2026).  The renderers used
 * to call a per-sample helper for every object field: the snare alone touched
 * the object ~50 times a sample -- four decays x five fields, three resonators
 * x nine, envelope, noise -- and most of that traffic was invariants (each
 * decay's mul/min/sign, each resonator's coefficient/modulation/bypass, the
 * output mixes).  A 16-sample render now loads the working state once, runs
 * the recurrence in locals and commits once, the way cf_noise_hat already did.
 * Independent block passes preserve the sample order within each recurrence.
 * The object bytes, PCM and RNG are compared with the frozen implementation,
 * including split lengths, malformed state and envelope transitions. */
#include "cf_resonant.h"
#include "cf_render_math.h"
#include <limits.h>

/* Helpers and loops share the top-level GCC options; local optimize scopes
 * can outline primitive operations (see trap-cf-inline-options). */

static uint16_t r16(const uint8_t*p,size_t o){return pk_cf_ld16(p,o);}
static uint32_t r32(const uint8_t*p,size_t o){return pk_cf_ld32(p,o);}
static void w16(uint8_t*p,size_t o,uint16_t v){pk_cf_st16(p,o,v);}
static void w32(uint8_t*p,size_t o,uint32_t v){pk_cf_st32(p,o,v);}
static int16_t s16(uint16_t u){return (int16_t)u;}
static int32_t s32(uint32_t u){return (int32_t)u;}
static uint32_t u32(int32_t s){return (uint32_t)s;}
static int32_t asr(int32_t v,unsigned n){return v>>n;}
static int32_t mullo(int32_t a,int32_t b){return s32(pk_cf_mul_lo_u32(u32(a),u32(b)));}
static int32_t add(int32_t a,int32_t b){return s32(u32(a)+u32(b));}
static int32_t sub(int32_t a,int32_t b){return s32(u32(a)-u32(b));}
static int32_t neg(int32_t v){return s32(0u-u32(v));}
static int32_t abs_arm(int32_t v){return v<0?neg(v):v;}
static int32_t clamp32767(int32_t v){
    if(v<-32767)return -32767;
    if(v>=32767)return 32767;
    return v;
}
static uint16_t tab16(const uint8_t*t,size_t i){return r16(t,i*2u);}

/* Map-specific loads/stores must inline: otherwise the target sees a dynamic
 * map pointer and pays both the call and map-offset loads on every block.
 * Inlining exposes the fixed even displacements to the ColdFire access helpers
 * and lets pitch loads remain inside the dirty-coefficient path. */

/* --- block working state -------------------------------------------------- */
typedef struct { int32_t v; uint16_t rate_up,rate_dn; uint8_t st,curve,f4,f6,f7,f10;
                 const uint8_t*env1,*env2; } res_env_l;
typedef struct { uint32_t mul,value; int32_t min,count,sign; } res_dec_l;
typedef struct { uint32_t coeff_a,coeff_b,position,velocity,modulation;
                 int32_t pitch_a,pitch_b; uint8_t bypass,dirty; } res_core_l;
typedef struct { uint16_t counter,reload; int16_t held; } res_noise_l;

/* --- shared envelope (base 0x74), identical to the other CF engines ------- */
static inline void __attribute__((always_inline)) res_env_load(res_env_l*m,const uint8_t*s,size_t b,const pk_cf_res_tables*t){
    m->st=s[b];
    m->v=s32(r32(s,b+0xc));
    m->f4=s[b+4];m->f6=s[b+6];m->f7=s[b+7];m->f10=s[b+0x10];
    m->curve=s[b+1];
    m->rate_up=r16(s,b+0x20);m->rate_dn=r16(s,b+0x22);
    m->env1=t->envelope1;m->env2=t->envelope2;
}
static inline void __attribute__((always_inline)) res_env_store(uint8_t*s,size_t b,const res_env_l*m){
    s[b]=(uint8_t)m->st;
    w32(s,b+0xc,u32(m->v));
}
static inline uint16_t __attribute__((always_inline)) res_env_step(res_env_l*m){
    switch(m->st){
    case 0: if(m->f7||m->f4)m->st=1; break;
    case 1: m->v=s32(u32(m->v)+(uint32_t)m->rate_up);
            if(m->f4){if(m->v>0xffffe){m->st=4;if(m->v>=0x100000)m->v=0xfffff;}}
            else if(m->v>0xffffe){m->st=m->f6?4:3;if(m->v>=0x100000)m->v=0xfffff;}
            break;
    case 2: break;
    case 3: if(!m->f7&&(m->f4||!m->f10))m->st=4; break;
    case 4: if(m->f7)m->st=1;
            else{m->v=s32(u32(m->v)-(uint32_t)m->rate_dn);
                 if(m->v<=0){m->v=0;m->st=m->f4?1:0;}}
            break;
    default: break;
    }
    if(m->curve!=1&&m->curve!=2)return (uint16_t)((u32(m->v)>>4)&0xffffu);
    {const uint8_t*c=m->curve==1?m->env1:m->env2;uint32_t raw,idx,nx;int32_t f,a,z;
     if(!c)return 0;
     raw=u32(m->v);idx=(raw>>10)&0x7ffu;nx=(idx+1)&0x7ffu;f=(int32_t)(raw&0x3ffu);
     a=(int32_t)tab16(c,idx);z=(int32_t)tab16(c,nx);
     return (uint16_t)(a+asr(mullo(z-a,f),10));}
}

/* --- shared noise sample/hold (base 0x60) -------------------------------- */
static uint32_t res_rnd(pk_cf_res_rng*r){
    const uint32_t a=0x5851f42d,b=0x4c957f2d;
    uint32_t ol=r->low,oh=r->high,acc=pk_cf_mul_lo_u32(ol,a),pl=pk_cf_mul_lo_u32(ol,b),
             ph=pk_cf_render_rng_hi(ol),nl,carry,nh;
    acc+=pk_cf_mul_lo_u32(oh,b);nl=pl+1u;carry=nl<pl;nh=acc+ph+carry;
    r->low=nl;r->high=nh;return nh&0x7fffffffu;
}
static inline void __attribute__((always_inline)) res_noise_load(res_noise_l*m,const uint8_t*s){
    m->counter=r16(s,0x60u);m->reload=r16(s,0x62u);m->held=s16(r16(s,0x70u));
}
static inline void __attribute__((always_inline)) res_noise_store(uint8_t*s,const res_noise_l*m){
    w16(s,0x60u,m->counter);w16(s,0x70u,(uint16_t)m->held);
}

/* --- 257-entry interpolation -------------------------------------------- */
static uint16_t res_interp(const uint8_t*tab,uint32_t phase){
    uint32_t idx=(phase>>24)&0xffu,fraction=(phase>>8)&0xffffu;
    /* idx <= 255: the pair ends inside the 257-entry table, even at
     * its last interval. One load/byte-reverse supplies both u16 values. */
    uint32_t pair=r32(tab,idx*2u),a=pair&0xffffu,d;
    d=(uint32_t)((int32_t)(pair>>16)-(int32_t)a);
    return (uint16_t)(a+((fraction*d)>>16));
}

/* --- resonator ---------------------------------------------------------- */
typedef struct { size_t dirty,pitch_a,pitch_b,coeff_b,coeff_a,mod,bypass,position,velocity; } res_map;

static inline void __attribute__((always_inline)) res_core_load(res_core_l*m,const uint8_t*s,const res_map*rm){
    m->dirty=s[rm->dirty];
    m->pitch_a=s16(r16(s,rm->pitch_a));
    m->pitch_b=s16(r16(s,rm->pitch_b));
    m->coeff_a=r32(s,rm->coeff_a);
    m->coeff_b=r32(s,rm->coeff_b);
    m->modulation=r32(s,rm->mod);
    m->bypass=s[rm->bypass];
    m->position=r32(s,rm->position);
    m->velocity=r32(s,rm->velocity);
}
static inline void __attribute__((always_inline)) res_core_store(uint8_t*s,const res_map*rm,const res_core_l*m){
    /* The bass renderer re-latches the resonator's pitch when the pitch offset
     * moves, so the field has to go back with the rest of the working state.
     * The snare never writes it, and storing the value it loaded is a
     * no-op there. */
    w16(s,rm->pitch_a,(uint16_t)m->pitch_a);
    w16(s,rm->pitch_b,(uint16_t)m->pitch_b);
    w32(s,rm->coeff_a,m->coeff_a);
    w32(s,rm->coeff_b,m->coeff_b);
    w32(s,rm->position,m->position);
    w32(s,rm->velocity,m->velocity);
    s[rm->dirty]=m->dirty;
}
/* Coefficients are refreshed at a pitch-run boundary by bass_tone_block. */
static int32_t res_core_step(res_core_l*m,int32_t input,int32_t*out_velocity){
    {int32_t coeff_a=s32(m->coeff_a),position=s32(m->position),
            modulation=s32(m->modulation),coeff_b=s32(m->coeff_b),scale,velocity,filtered;
     if(modulation){
        scale=0x80;
        if(position>0x1000){coeff_a=add(coeff_a,asr(sub(position,0x800),3));scale=asr(position,4);}
        coeff_b=add(coeff_b,asr(mullo(scale,modulation),9));
     }
     velocity=s32(m->velocity);
     filtered=input;
     if(!m->bypass)filtered=sub(input,asr(mullo(velocity,coeff_a),15));
     position=clamp32767(add(position,asr(mullo(velocity,coeff_b),15)));
     m->position=u32(position);
     filtered=sub(filtered,position);
     velocity=clamp32767(add(velocity,asr(mullo(coeff_b,filtered),15)));
     m->velocity=u32(velocity);
     *out_velocity=velocity;
     return position;}
}

/* Bass NOISE_MAP alone has modulation=0 and bypass=0. Snare controls can
 * set bypass, so the packed snare routine below must retain that branch. */
/* The snare's resonators keep coeff_a/coeff_b in 0..65535 (res_interp's
 * range) and position/velocity clamped to +-32767, so their loop-carried state
 * fits in 16-bit halves.  Packing halves the register footprint of the three
 * resonators (the snare's biggest spill source). */
typedef struct { uint16_t coeff_a,coeff_b; int16_t position,velocity; int32_t pitch_a,pitch_b; uint8_t dirty,bypass; } res_core_fast_l;
static inline void __attribute__((always_inline)) res_core_fast_load(res_core_fast_l*m,const uint8_t*s,const res_map*rm){
    m->bypass=s[rm->bypass];
    m->dirty=s[rm->dirty];
    m->pitch_a=s16(r16(s,rm->pitch_a));
    m->pitch_b=s16(r16(s,rm->pitch_b));
    m->coeff_a=(uint16_t)r32(s,rm->coeff_a);
    m->coeff_b=(uint16_t)r32(s,rm->coeff_b);
    m->position=(int16_t)r32(s,rm->position);
    m->velocity=(int16_t)r32(s,rm->velocity);
}
static inline void __attribute__((always_inline)) res_core_fast_store(uint8_t*s,const res_map*rm,const res_core_fast_l*m){
    w32(s,rm->coeff_a,(uint32_t)m->coeff_a);
    w32(s,rm->coeff_b,(uint32_t)m->coeff_b);
    w32(s,rm->position,(uint32_t)(int32_t)m->position);
    w32(s,rm->velocity,(uint32_t)(int32_t)m->velocity);
    s[rm->dirty]=m->dirty;
}
/* --- multiplicative decay ramp ------------------------------------------ */
typedef struct { size_t mul,count,value,sign,min; } dec_map;

static inline void __attribute__((always_inline)) res_dec_load(res_dec_l*m,const uint8_t*s,const dec_map*d){
    m->mul=r32(s,d->mul);
    m->value=r32(s,d->value);
    m->min=s32(r32(s,d->min));
    m->count=s32(r32(s,d->count));
    m->sign=s32(r32(s,d->sign));
}
static inline void __attribute__((always_inline)) res_dec_store(uint8_t*s,const dec_map*d,const res_dec_l*m){
    w32(s,d->value,m->value);
    w32(s,d->count,u32(m->count));
}
static uint32_t res_dec_step(res_dec_l*m,int add_constant,uint32_t constant){
    uint32_t value=(pk_cf_mul_lo_u32(m->mul,m->value))>>12;
    int32_t count,sign;int use_constant;
    if(s32(value)<m->min)value=u32(m->min);
    count=m->count;sign=m->sign;
    m->value=value;
    use_constant=add_constant&&count!=0;
    if(count>0){count=sub(count,1);m->count=count;
        if(count==0){value=u32(add(s32(value),abs_arm(sign)));m->value=value;use_constant=0;}}
    if(sign<0)value=u32(neg(s32(value)));
    if(use_constant)value=u32(add(s32(value),(int32_t)constant));
    return value;
}

static int16_t res_velocity_scale(uint8_t velocity,int32_t value){
    int32_t o=asr(mullo(value,(int32_t)velocity),8);
    if(o>32767)o=32767;else if(o<-32768)o=-32768;
    return (int16_t)o;
}

static void __attribute__((noinline))
res_advance_envelope(uint8_t*s,uint32_t n,const pk_cf_res_tables*t){
    res_env_l env;res_env_load(&env,s,0x74u,t);
    while(n){
        /* These renderers retain the envelope state but never consume its
         * sample value. A run that stays in attack/decay is exact integer
         * addition/subtraction; preserve each transition with the original
         * one-sample step. Corrupt/out-of-range values retain that step too. */
        if(env.st==1&&env.v>=0&&env.v<=0xffffe){
            uint32_t total=(uint32_t)env.v+(uint32_t)env.rate_up*n;
            if(total<=0xffffeu){env.v=(int32_t)total;break;}
            /* The crossing is within this block; rate_up is nonzero here. */
            n-=(0xffffeu-(uint32_t)env.v)/(uint32_t)env.rate_up+1u;
            env.v=0xfffff;env.st=(env.f4||env.f6)?4u:3u;continue;
        }else if(env.st==4&&!env.f7&&env.v>0&&env.v<=0xfffff){
            uint32_t decrement=(uint32_t)env.rate_dn*n;
            if((uint32_t)env.v>decrement){env.v-=(int32_t)decrement;break;}
            n-=((uint32_t)env.v+(uint32_t)env.rate_dn-1u)/(uint32_t)env.rate_dn;
            env.v=0;env.st=env.f4?1u:0u;continue;
        }else if((env.st==0&&!env.f7&&!env.f4)||env.st==2||
                 (env.st==3&&(env.f7||(!env.f4&&env.f10)))||env.st>4){
            break;
        }
        (void)res_env_step(&env);--n;
    }
    res_env_store(s,0x74u,&env);
}

static inline void __attribute__((always_inline))
res_decay_block(uint8_t *s,const dec_map *map,int32_t *buffer,uint32_t n,
           int accumulate,int add_constant,uint32_t constant){
    res_dec_l decay;
    uint32_t i;
    res_dec_load(&decay,s,map);
    /* Until the positive countdown reaches zero, its only effects are a
     * fixed output bias/sign and one final decrement. Split at the block
     * boundary, retaining the original sample step for crossing blocks. */
    if(decay.count<=0||u32(decay.count)>n){
        const uint32_t mask=u32(decay.sign>>31);
        const uint32_t bias=(add_constant&&decay.count!=0)?constant:0u;
        uint32_t next_value=pk_cf_mul_lo_u32(decay.mul,decay.value)>>12;
        if(s32(next_value)<decay.min)next_value=u32(decay.min);
        /* Equality proves every remaining recurrence step is identical. The
         * outer guard excludes the count-zero sign bump from this block. */
        if(next_value==decay.value){
            const int32_t out=s32(((next_value^mask)-mask)+bias);
            for(i=0;i<n;i++)buffer[i]=accumulate?add(buffer[i],out):out;
        }else{
            for(i=0;i<n;i++){
                uint32_t value=pk_cf_mul_lo_u32(decay.mul,decay.value)>>12;
                if(s32(value)<decay.min)value=u32(decay.min);
                decay.value=value;
                const int32_t out=s32(((value^mask)-mask)+bias);
                buffer[i]=accumulate?add(buffer[i],out):out;
            }
        }
        if(decay.count>0)decay.count-=n;
    }else{
        for(i=0;i<n;i++){
            int32_t value=s32(res_dec_step(&decay,add_constant,constant));
            buffer[i]=accumulate?add(buffer[i],value):value;
        }
    }
    res_dec_store(s,map,&decay);
}

static void __attribute__((noinline))
res_noise_block(uint8_t *s,pk_cf_res_rng *rng,int32_t *buffer,uint32_t n){
    res_noise_l noise;
    uint32_t i,run;
    res_noise_load(&noise,s);
    /* Emit the already-held prefix without touching RNG state. Counter is
     * the number of OLD-value samples left, not the time to the new sample. */
    run=noise.counter<n?noise.counter:n;
    for(i=0;i<run;i++)buffer[i]=noise.held;
    noise.counter=(uint16_t)(noise.counter-run);buffer+=run;n-=run;
    if(n){
        pk_cf_res_rng local=*rng;
        if(!noise.reload){
            /* White noise: every remaining sample consumes one RNG value. */
            for(i=0;i<n;i++){
                noise.held=s16((uint16_t)res_rnd(&local));buffer[i]=noise.held;
            }
        }else{
            /* Each new value covers its own sample plus reload held samples.
             * Use u32 for reload+1 so 65535 cannot wrap the run to zero. */
            do{
                noise.held=s16((uint16_t)res_rnd(&local));
                run=(uint32_t)noise.reload+1u;if(run>n)run=n;
                for(i=0;i<run;i++)buffer[i]=noise.held;
                noise.counter=(uint16_t)((uint32_t)noise.reload-(run-1u));
                buffer+=run;n-=run;
            }while(n);
        }
        *rng=local;
    }
    res_noise_store(s,&noise);
}

/* ======================= Resonant Bass (0x178) ========================== */
static const res_map TONE_MAP={0xC4,0xC6,0xC8,0xD0,0xD4,0xCC,0xD8,0xDC,0xE0};
static const res_map NOISE_MAP={0x158,0x15A,0x15C,0x164,0x168,0x160,0x16C,0x170,0x174};
static const dec_map BASS_A={0xF8,0xFC,0x100,0x104,0x108};
static const dec_map BASS_B={0x110,0x114,0x118,0x11C,0x120};
static const dec_map BASS_C={0x128,0x12C,0x130,0x134,0x138};
static const dec_map BASS_L={0x144,0x148,0x14C,0x150,0x154};

static void __attribute__((noinline))
bass_drive_block(uint8_t*s,int32_t*drive,uint32_t n){
    uint32_t i;
    {res_dec_l decay;res_dec_load(&decay,s,&BASS_A);
     for(i=0;i<n;i++){
        uint32_t value=pk_cf_mul_lo_u32(decay.mul,decay.value)>>12;
        int32_t count=decay.count;
        if(s32(value)<decay.min)value=u32(decay.min);
        decay.value=value;
        if(count>0){count=sub(count,1);decay.count=count;
            if(count==0){value=u32(add(s32(value),abs_arm(decay.sign)));decay.value=value;}}
        drive[i]=s32(value);
     }
     res_dec_store(s,&BASS_A,&decay);}
    {res_dec_l decay;res_dec_load(&decay,s,&BASS_B);
     for(i=0;i<n;i++){
        uint32_t value=pk_cf_mul_lo_u32(decay.mul,decay.value)>>12;
        int32_t count=decay.count,first=drive[i];
        if(s32(value)<decay.min)value=u32(decay.min);
        if(count<0)first=neg(first);
        first=add(first,count!=0?(1<<14):0);
        decay.value=value;
        if(count>0){count=sub(count,1);decay.count=count;
            if(count==0){value=u32(add(s32(value),abs_arm(decay.sign)));decay.value=value;}}
        if(decay.sign<0)value=u32(neg(s32(value)));
        drive[i]=add(first,s32(value));
     }
     res_dec_store(s,&BASS_B,&decay);}
}
/* Pitch modulation has only one possible transition in a render block:
 * countdown 1 -> 0. Return the number of samples before that transition;
 * the decay value still advances exactly even though pitch does not use it. */
static uint32_t __attribute__((noinline))
bass_pitch_block(uint8_t*s,uint32_t n){
    res_dec_l decay;uint32_t i,split;
    res_dec_load(&decay,s,&BASS_C);
    if(decay.count<=0)split=decay.count==0?0u:n;
    else{split=u32(decay.count)-1u;if(split>n)split=n;}
    if(decay.count<=0||u32(decay.count)>n){
        for(i=0;i<n;i++){
            uint32_t value=pk_cf_mul_lo_u32(decay.mul,decay.value)>>12;
            if(s32(value)<decay.min)value=u32(decay.min);
            decay.value=value;
        }
        if(decay.count>0)decay.count-=n;
    }else{
        for(i=0;i<n;i++)(void)res_dec_step(&decay,0,0u);
    }
    res_dec_store(s,&BASS_C,&decay);
    return split;
}
static void __attribute__((noinline))
bass_tone_block(uint8_t*s,const int32_t*drive,uint32_t split,
                int32_t*acc,uint32_t n,const pk_cf_res_tables*t){
    res_core_l tone;uint32_t i=0,part;
    const uint16_t raw=r16(s,0xf0u);
    int32_t state=s32(r32(s,0xe8u)),mix=s32(r32(s,0xecu));
    res_core_load(&tone,s,&TONE_MAP);
    for(part=0;part<2;part++){
        const uint32_t end=part?n:split;
        const uint16_t pitch=(uint16_t)(raw+(part?0u:0x880u));
        if(i==end)continue;
        if(tone.dirty||s16((uint16_t)tone.pitch_a)!=s16(pitch)){
            tone.pitch_a=(int32_t)pitch;
            tone.coeff_b=res_interp(t->interp_a,(uint32_t)tone.pitch_a<<17);
            tone.coeff_a=res_interp(t->interp_b,(uint32_t)tone.pitch_b<<17);
            tone.dirty=0;
        }
        do{
            int32_t velocity,input,delta;
            (void)res_core_step(&tone,drive[i],&velocity);
            input=add(velocity,asr(drive[i],4));delta=sub(input,state);
            state=add(state,asr(mullo(mix,delta),15));acc[i]=state;
        }while(++i<end);
    }
    res_core_store(s,&TONE_MAP,&tone);w32(s,0xe8u,u32(state));
}
static void __attribute__((noinline))
bass_noise_mix(uint8_t*s,const int32_t*input,const int32_t*level,
               const int32_t*acc,int16_t*d,uint32_t n,const pk_cf_res_tables*t){
    res_core_l noise;uint32_t i;uint8_t amplitude=s[6];
    res_core_load(&noise,s,&NOISE_MAP);
    if(noise.dirty&&n){
        noise.coeff_b=res_interp(t->interp_a,(uint32_t)noise.pitch_a<<17);
        noise.coeff_a=res_interp(t->interp_b,(uint32_t)noise.pitch_b<<17);noise.dirty=0;}
    int32_t position=s32(noise.position),velocity=s32(noise.velocity);
    int32_t ca=s32(noise.coeff_a),cb=s32(noise.coeff_b);
    for(i=0;i<n;i++){
        int32_t filtered=sub(input[i],asr(mullo(velocity,ca),15)),mixed;
        position=clamp32767(add(position,asr(mullo(velocity,cb),15)));
        filtered=sub(filtered,position);
        velocity=clamp32767(add(velocity,asr(mullo(cb,filtered),15)));
        mixed=add(acc[i],asr(mullo(velocity,level[i]),16));
        d[i]=res_velocity_scale(amplitude,add(mixed,add(mixed,mixed)));
    }
    noise.position=u32(position);noise.velocity=u32(velocity);
    res_core_store(s,&NOISE_MAP,&noise);
}
static void __attribute__((noinline))
bass_level(uint8_t*s,int32_t*buffer,uint32_t n){
    res_decay_block(s,&BASS_L,buffer,n,0,0,0u);
}
static void bass_chunk(uint8_t*s,int16_t*d,uint32_t n,const pk_cf_res_tables*t,pk_cf_res_rng*rng){
    int32_t drive[16],acc[16],level[16];uint32_t split;
    res_advance_envelope(s,n,t);
    bass_drive_block(s,drive,n);split=bass_pitch_block(s,n);
    bass_tone_block(s,drive,split,acc,n,t);
    bass_level(s,level,n);
    res_noise_block(s,rng,drive,n);
    bass_noise_mix(s,drive,level,acc,d,n,t);
}
int pk_cf_res_bass_render(uint8_t*s,int16_t*d,uint32_t n,const pk_cf_res_tables*t,pk_cf_res_rng*rng){
    if(!s||!d||!t||!rng||!t->envelope1||!t->envelope2||!t->interp_a||!t->interp_b)return 0;
    if(!n)return 1;
    volatile pk_cf_render_math_context context=pk_cf_render_math_begin();
    do{
        uint32_t count=n>16u?16u:n;bass_chunk(s,d,count,t,rng);
        d+=count;n-=count;
    }while(n);
    pk_cf_render_math_end_saved(&context);
    return 1;
}

/* ====================== Resonant Snare (0x1d4) ========================== */
static const res_map RES1_MAP={0xF8,0xFA,0xFC,0x104,0x108,0x100,0x10C,0x110,0x114};
static const res_map RES2_MAP={0x11C,0x11E,0x120,0x128,0x12C,0x124,0x130,0x134,0x138};
static const res_map RES3_MAP={0x140,0x142,0x144,0x14C,0x150,0x148,0x154,0x158,0x15C};
static const dec_map SNARE_A={0x174,0x178,0x17C,0x180,0x184};
static const dec_map SNARE_B={0x18C,0x190,0x194,0x198,0x19C};
static const dec_map SNARE_C={0x1A4,0x1A8,0x1AC,0x1B0,0x1B4};
static const dec_map SNARE_D={0x1BC,0x1C0,0x1C4,0x1C8,0x1CC};

static void __attribute__((noinline))
snare_decay_a(uint8_t*s,int32_t*buffer,uint32_t n){
    res_decay_block(s,&SNARE_A,buffer,n,0,0,0u);
}
static void __attribute__((noinline))
snare_decay_b(uint8_t*s,int32_t*buffer,uint32_t n){
    res_decay_block(s,&SNARE_B,buffer,n,1,1,0x0a3du);
}
static void __attribute__((noinline))
snare_decay_c(uint8_t*s,int32_t*buffer,uint32_t n){
    res_decay_block(s,&SNARE_C,buffer,n,0,1,0x3333u);
}
static void __attribute__((noinline))
snare_decay_d(uint8_t*s,int32_t*buffer,uint32_t n){
    res_decay_block(s,&SNARE_D,buffer,n,0,0,0u);
}

/* Separate independent recurrences into short block passes. Each recurrence
 * still visits samples in exactly the original order; only independent state
 * machines move relative to one another. The noise pass is the sole RNG user.
 * This bounds the live register set instead of spilling all three resonators
 * and all four decays on every sample. */
static inline void __attribute__((always_inline))
snare_core(uint8_t *s,const res_map *map,const int32_t *input,
           int32_t *acc,const int32_t *level,uint32_t n,int32_t mix,
           int accumulate,const pk_cf_res_tables *t,int16_t *dst){
    res_core_fast_l core;
    uint32_t i;
    res_core_fast_load(&core,s,map);
    if(core.dirty&&n){
        core.coeff_b=(uint16_t)res_interp(t->interp_a,(uint32_t)core.pitch_a<<17);
        core.coeff_a=(uint16_t)res_interp(t->interp_b,(uint32_t)core.pitch_b<<17);
        core.dirty=0;
    }
    int32_t position=core.position,velocity=core.velocity;
    const int32_t coeff_a=core.coeff_a,coeff_b=core.coeff_b;
    for(i=0;i<n;i++){
        int32_t term,filtered=input[i];
        if(!core.bypass)filtered=sub(filtered,asr(mullo(velocity,coeff_a),15));
        position=clamp32767(add(position,asr(mullo(velocity,coeff_b),15)));
        filtered=sub(filtered,position);
        velocity=clamp32767(add(velocity,asr(mullo(coeff_b,filtered),15)));
        if(level)term=asr(mullo(velocity,level[i]),15);
        else term=asr(mullo(add(velocity,asr(input[i],4)),mix),15);
        if(dst){
            int32_t mixed=add(acc[i],term);
            dst[i]=res_velocity_scale(s[6],add(mixed,mixed));
        }else acc[i]=accumulate?add(acc[i],term):term;
    }
    core.position=(int16_t)position;core.velocity=(int16_t)velocity;
    res_core_fast_store(s,map,&core);
}

/* These passes have different fixed maps and mixing roles. Compile each
 * with its actual constants so no sample selects map offsets or mix policy. */
static void __attribute__((noinline))
snare_first(uint8_t*s,const int32_t*input,int32_t*acc,uint32_t n,const pk_cf_res_tables*t){
    snare_core(s,&RES1_MAP,input,acc,0,n,s32(r32(s,0x164u)),0,t,0);
}
static void __attribute__((noinline))
snare_second(uint8_t*s,const int32_t*input,int32_t*acc,uint32_t n,const pk_cf_res_tables*t){
    snare_core(s,&RES2_MAP,input,acc,0,n,s32(r32(s,0x168u)),1,t,0);
}
static void __attribute__((noinline))
snare_noise(uint8_t*s,const int32_t*input,int32_t*acc,const int32_t*level,int16_t*dst,uint32_t n,const pk_cf_res_tables*t){
    snare_core(s,&RES3_MAP,input,acc,level,n,0,1,t,dst);
}

static void snare_chunk(uint8_t *s,int16_t *d,uint32_t n,
                        const pk_cf_res_tables *t,pk_cf_res_rng *rng){
    int32_t drive[16],acc[16],level[16];
    res_advance_envelope(s,n,t);
    snare_decay_a(s,drive,n);
    snare_decay_b(s,drive,n);
    snare_first(s,drive,acc,n,t);
    snare_decay_c(s,drive,n);
    snare_second(s,drive,acc,n,t);
    snare_decay_d(s,level,n);
    res_noise_block(s,rng,drive,n);
    snare_noise(s,drive,acc,level,d,n,t);
}

/* Empty packed rendering only normalizes the upper halves of four LE
 * words per core. Preserve malformed-state behavior without round-tripping
 * unchanged lower halves, pitches, bypass and dirty bytes. */
static inline __attribute__((always_inline)) void
res_core_empty_normalize(uint8_t*s,const res_map*rm){
    uint8_t position=(s[rm->position+1u]&0x80u)?0xffu:0u;
    uint8_t velocity=(s[rm->velocity+1u]&0x80u)?0xffu:0u;
    s[rm->coeff_a+2u]=0;s[rm->coeff_a+3u]=0;
    s[rm->coeff_b+2u]=0;s[rm->coeff_b+3u]=0;
    s[rm->position+2u]=position;s[rm->position+3u]=position;
    s[rm->velocity+2u]=velocity;s[rm->velocity+3u]=velocity;
}

int pk_cf_res_snare_render(uint8_t*s,int16_t*d,uint32_t n,const pk_cf_res_tables*t,pk_cf_res_rng*rng){
    if(!s||!d||!t||!rng||!t->envelope1||!t->envelope2||!t->interp_a||!t->interp_b)return 0;
    if(!n){
        /* The original empty packed renderer narrows these twelve words even
         * for malformed state. Preserve that behavior without all block passes. */
        res_core_empty_normalize(s,&RES1_MAP);
        res_core_empty_normalize(s,&RES2_MAP);
        res_core_empty_normalize(s,&RES3_MAP);
        return 1;
    }
    volatile pk_cf_render_math_context context=pk_cf_render_math_begin();
    do{
        uint32_t count=n>16u?16u:n;
        snare_chunk(s,d,count,t,rng);
        d+=count;n-=count;
    }while(n);
    pk_cf_render_math_end_saved(&context);
    return 1;
}

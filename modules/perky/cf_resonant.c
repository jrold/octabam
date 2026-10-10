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
 * The arithmetic and the order of every read-modify-write are unchanged, so
 * the object bytes and the PCM stay identical; only the traffic moved. */
#include "cf_resonant.h"
#include "cf_math.h"
#include <limits.h>

static uint16_t r16(const uint8_t*p,size_t o){return pk_cf_ld16(p,o);}
static uint32_t r32(const uint8_t*p,size_t o){return pk_cf_ld32(p,o);}
static void w16(uint8_t*p,size_t o,uint16_t v){pk_cf_st16(p,o,v);}
static void w32(uint8_t*p,size_t o,uint32_t v){pk_cf_st32(p,o,v);}
static int16_t s16(uint16_t u){return (u&0x8000u)?(int16_t)(-1-(int16_t)(uint16_t)~u):(int16_t)u;}
static int32_t s32(uint32_t u){return (u&0x80000000u)?-1-(int32_t)~u:(int32_t)u;}
static uint32_t u32(int32_t s){return s>=0?(uint32_t)s:~(uint32_t)(-1-s);}
static int32_t asr(int32_t v,unsigned n){uint32_t b;if(!n)return v;b=u32(v)>>n;if(v<0)b|=(~0u)<<(32u-n);return s32(b);}
static int32_t mullo(int32_t a,int32_t b){return s32(pk_cf_mul_lo_u32(u32(a),u32(b)));}
static int32_t add(int32_t a,int32_t b){return s32(u32(a)+u32(b));}
static int32_t sub(int32_t a,int32_t b){return s32(u32(a)-u32(b));}
static int32_t neg(int32_t v){return s32(0u-u32(v));}
static int32_t abs_arm(int32_t v){return v<0?neg(v):v;}
static int32_t clamp32767(int32_t v){if(v<-32767)return -32767;if(v>=32767)return 32767;return v;}
static uint16_t tab16(const uint8_t*t,size_t i){return r16(t,i*2u);}

/* --- block working state -------------------------------------------------- */
typedef struct { int32_t v; uint16_t rate_up,rate_dn; uint8_t st,curve,f4,f6,f7,f10;
                 const uint8_t*env1,*env2; } res_env_l;
typedef struct { uint32_t mul,value; int32_t min,count,sign; } res_dec_l;
typedef struct { uint32_t coeff_a,coeff_b,position,velocity,modulation;
                 int32_t pitch_a,pitch_b; uint8_t bypass,dirty; } res_core_l;
typedef struct { uint16_t counter,reload; int16_t held; } res_noise_l;

/* --- shared envelope (base 0x74), identical to the other CF engines ------- */
static void res_env_load(res_env_l*m,const uint8_t*s,size_t b,const pk_cf_res_tables*t){
    m->st=s[b];
    m->v=s32(r32(s,b+0xc));
    m->f4=s[b+4];m->f6=s[b+6];m->f7=s[b+7];m->f10=s[b+0x10];
    m->curve=s[b+1];
    m->rate_up=r16(s,b+0x20);m->rate_dn=r16(s,b+0x22);
    m->env1=t->envelope1;m->env2=t->envelope2;
}
static void res_env_store(uint8_t*s,size_t b,const res_env_l*m){
    s[b]=(uint8_t)m->st;
    w32(s,b+0xc,u32(m->v));
}
static uint16_t res_env_step(res_env_l*m){
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
             ph=pk_cf_mul_hi_u32(ol,b),nl,carry,nh;
    acc+=pk_cf_mul_lo_u32(oh,b);nl=pl+1u;carry=nl<pl;nh=acc+ph+carry;
    r->low=nl;r->high=nh;return nh&0x7fffffffu;
}
static void res_noise_load(res_noise_l*m,const uint8_t*s){
    m->counter=r16(s,0x60u);m->reload=r16(s,0x62u);m->held=s16(r16(s,0x70u));
}
static void res_noise_store(uint8_t*s,const res_noise_l*m){
    w16(s,0x60u,m->counter);w16(s,0x70u,(uint16_t)m->held);
}
static int32_t res_noise_step(res_noise_l*m,pk_cf_res_rng*r){
    if(m->counter){m->counter=(uint16_t)(m->counter-1u);return m->held;}
    m->counter=m->reload;m->held=s16((uint16_t)res_rnd(r));return m->held;
}

/* --- 257-entry interpolation -------------------------------------------- */
static uint16_t res_interp(const uint8_t*tab,uint32_t phase){
    uint32_t idx=(phase>>24)&0xffu,fraction=(phase>>8)&0xffffu;
    uint32_t a=tab16(tab,idx),d;
    d=(uint32_t)((int32_t)tab16(tab,idx+1u)-(int32_t)a);
    return (uint16_t)(a+((fraction*d)>>16));
}

/* --- resonator ---------------------------------------------------------- */
typedef struct { size_t dirty,pitch_a,pitch_b,coeff_b,coeff_a,mod,bypass,position,velocity; } res_map;

static void res_core_load(res_core_l*m,const uint8_t*s,const res_map*rm){
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
static void res_core_store(uint8_t*s,const res_map*rm,const res_core_l*m){
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
static int32_t res_core_step(res_core_l*m,int32_t input,
                             const uint8_t*ia,const uint8_t*ib,int32_t*out_velocity){
    if(m->dirty){
        m->coeff_b=(uint32_t)res_interp(ia,(uint32_t)m->pitch_a<<17);
        m->coeff_a=(uint32_t)res_interp(ib,(uint32_t)m->pitch_b<<17);
        m->dirty=0;
    }
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

/* --- multiplicative decay ramp ------------------------------------------ */
typedef struct { size_t mul,count,value,sign,min; } dec_map;

static void res_dec_load(res_dec_l*m,const uint8_t*s,const dec_map*d){
    m->mul=r32(s,d->mul);
    m->value=r32(s,d->value);
    m->min=s32(r32(s,d->min));
    m->count=s32(r32(s,d->count));
    m->sign=s32(r32(s,d->sign));
}
static void res_dec_store(uint8_t*s,const dec_map*d,const res_dec_l*m){
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

/* ======================= Resonant Bass (0x178) ========================== */
static const res_map TONE_MAP={0xC4,0xC6,0xC8,0xD0,0xD4,0xCC,0xD8,0xDC,0xE0};
static const res_map NOISE_MAP={0x158,0x15A,0x15C,0x164,0x168,0x160,0x16C,0x170,0x174};
static const dec_map BASS_A={0xF8,0xFC,0x100,0x104,0x108};
static const dec_map BASS_B={0x110,0x114,0x118,0x11C,0x120};
static const dec_map BASS_C={0x128,0x12C,0x130,0x134,0x138};
static const dec_map BASS_L={0x144,0x148,0x14C,0x150,0x154};

int pk_cf_res_bass_render(uint8_t*s,int16_t*d,uint32_t n,const pk_cf_res_tables*t,pk_cf_res_rng*rng){
    res_env_l env;res_dec_l la,lb,lc,ll;res_core_l tone,noise;res_noise_l nz;
    uint32_t i,mix_ec,raw_pitch;
    int32_t res_state;
    uint8_t vel_byte;
    if(!s||!d||!t||!rng||!t->envelope1||!t->envelope2||!t->interp_a||!t->interp_b)return 0;
    res_env_load(&env,s,0x74u,t);
    res_dec_load(&la,s,&BASS_A);res_dec_load(&lb,s,&BASS_B);
    res_dec_load(&lc,s,&BASS_C);res_dec_load(&ll,s,&BASS_L);
    res_core_load(&tone,s,&TONE_MAP);res_core_load(&noise,s,&NOISE_MAP);
    res_noise_load(&nz,s);
    mix_ec=(uint32_t)s32(r32(s,0xECu));
    raw_pitch=r16(s,0xF0u);
    res_state=s32(r32(s,0xE8u));
    vel_byte=s[6];
    for(i=0;i<n;i++){
        uint32_t mod_a,mod_b,mod_c,level;
        int32_t count_a,count_b,count_c,drive,drive_quarter,pitch,signed_pitch;
        int32_t tone_velocity,noise_velocity,res_input,res_delta,product,mixed,tripled;
        int skip_pitch_offset;
        (void)res_env_step(&env);
        /* mod A */
        mod_a=(pk_cf_mul_lo_u32(la.mul,la.value))>>12;
        if(s32(mod_a)<la.min)mod_a=u32(la.min);
        la.value=mod_a;
        count_a=la.count;
        if(count_a>0){count_a=sub(count_a,1);la.count=count_a;
            if(count_a==0){mod_a=u32(add(s32(mod_a),abs_arm(la.sign)));la.value=mod_a;}}
        /* mod B */
        count_b=lb.count;
        mod_b=(pk_cf_mul_lo_u32(lb.mul,lb.value))>>12;
        if(s32(mod_b)<lb.min)mod_b=u32(lb.min);
        if(count_b<0)mod_a=u32(neg(s32(mod_a)));
        lb.value=mod_b;
        mod_a=u32(add(s32(mod_a),count_b!=0?(1<<14):0));
        if(count_b>0){count_b=sub(count_b,1);lb.count=count_b;
            if(count_b==0){mod_b=u32(add(s32(mod_b),abs_arm(lb.sign)));lb.value=mod_b;}}
        if(lb.sign<0)mod_b=u32(neg(s32(mod_b)));
        drive=add(s32(mod_a),s32(mod_b));
        /* mod C: pitch-offset timer */
        mod_c=(pk_cf_mul_lo_u32(lc.mul,lc.value))>>12;
        if(s32(mod_c)<lc.min)mod_c=u32(lc.min);
        count_c=lc.count;
        lc.value=mod_c;
        skip_pitch_offset=(count_c==0);
        if(count_c>0){count_c=sub(count_c,1);lc.count=count_c;
            if(count_c==0){mod_c=u32(add(s32(mod_c),abs_arm(lc.sign)));lc.value=mod_c;skip_pitch_offset=1;}}
        pitch=(int32_t)raw_pitch;
        if(!skip_pitch_offset)pitch=(pitch+0x880)&0xffff;
        signed_pitch=s16((uint16_t)pitch);
        drive_quarter=asr(drive,4);
        if(tone.dirty||s16((uint16_t)tone.pitch_a)!=signed_pitch){
            tone.pitch_a=(int32_t)(uint16_t)pitch;tone.dirty=1;}
        (void)res_core_step(&tone,drive,t->interp_a,t->interp_b,&tone_velocity);
        res_input=add(tone_velocity,drive_quarter);
        res_delta=sub(res_input,res_state);
        level=res_dec_step(&ll,0,0u);
        res_state=add(res_state,asr(mullo((int32_t)mix_ec,res_delta),15));
        {int32_t nv=res_noise_step(&nz,rng);
         (void)res_core_step(&noise,nv,t->interp_a,t->interp_b,&noise_velocity);}
        product=mullo(noise_velocity,s32(level));
        mixed=add(res_state,asr(product,16));
        tripled=add(mixed,add(mixed,mixed));
        d[i]=res_velocity_scale(vel_byte,tripled);
    }
    res_env_store(s,0x74u,&env);
    res_dec_store(s,&BASS_A,&la);res_dec_store(s,&BASS_B,&lb);
    res_dec_store(s,&BASS_C,&lc);res_dec_store(s,&BASS_L,&ll);
    res_core_store(s,&TONE_MAP,&tone);res_core_store(s,&NOISE_MAP,&noise);
    res_noise_store(s,&nz);
    w32(s,0xE8u,u32(res_state));
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

int pk_cf_res_snare_render(uint8_t*s,int16_t*d,uint32_t n,const pk_cf_res_tables*t,pk_cf_res_rng*rng){
    res_env_l env;res_dec_l da,db,dc,dd_;res_core_l r1,r2,r3;res_noise_l nz;
    uint32_t i;
    int32_t mix164,mix168;
    uint8_t vel_byte;
    if(!s||!d||!t||!rng||!t->envelope1||!t->envelope2||!t->interp_a||!t->interp_b)return 0;
    res_env_load(&env,s,0x74u,t);
    res_dec_load(&da,s,&SNARE_A);res_dec_load(&db,s,&SNARE_B);
    res_dec_load(&dc,s,&SNARE_C);res_dec_load(&dd_,s,&SNARE_D);
    res_core_load(&r1,s,&RES1_MAP);res_core_load(&r2,s,&RES2_MAP);res_core_load(&r3,s,&RES3_MAP);
    res_noise_load(&nz,s);
    mix164=s32(r32(s,0x164u));mix168=s32(r32(s,0x168u));
    vel_byte=s[6];
    for(i=0;i<n;i++){
        uint32_t a,b,cv,dd;
        int32_t first_drive,first_mix,second_mix,velocity1,velocity2,velocity3;
        int32_t random_value,term1,term2,term3,mixed;
        (void)res_env_step(&env);
        a=res_dec_step(&da,0,0u);
        b=res_dec_step(&db,1,0x0A3Du);
        first_drive=add(s32(a),s32(b));
        (void)res_core_step(&r1,first_drive,t->interp_a,t->interp_b,&velocity1);
        cv=res_dec_step(&dc,1,0x3333u);
        first_mix=add(velocity1,asr(first_drive,4));
        (void)res_core_step(&r2,s32(cv),t->interp_a,t->interp_b,&velocity2);
        second_mix=add(velocity2,asr(s32(cv),4));
        dd=res_dec_step(&dd_,0,0u);
        random_value=res_noise_step(&nz,rng);
        (void)res_core_step(&r3,random_value,t->interp_a,t->interp_b,&velocity3);
        term1=asr(mullo(second_mix,mix168),15);
        term2=asr(mullo(mix164,first_mix),15);
        term3=asr(mullo(velocity3,s32(dd)),15);
        mixed=add(add(term1,term2),term3);
        d[i]=res_velocity_scale(vel_byte,add(mixed,mixed));
    }
    res_env_store(s,0x74u,&env);
    res_dec_store(s,&SNARE_A,&da);res_dec_store(s,&SNARE_B,&db);
    res_dec_store(s,&SNARE_C,&dc);res_dec_store(s,&SNARE_D,&dd_);
    res_core_store(s,&RES1_MAP,&r1);res_core_store(s,&RES2_MAP,&r2);res_core_store(s,&RES3_MAP,&r3);
    res_noise_store(s,&nz);
    return 1;
}

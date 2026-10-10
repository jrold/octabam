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
 */
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

/* --- shared envelope (base 0x74), identical to the other CF engines ------- */
static uint16_t res_env(uint8_t*s,const pk_cf_res_tables*t){
    const size_t b=0x74u;uint8_t st=s[b];int32_t v=s32(r32(s,b+0xc));
    switch(st){
    case 0: if(s[b+7]||s[b+4])s[b]=1; break;
    case 1: v=s32(u32(v)+(uint32_t)r16(s,b+0x20));w32(s,b+0xc,u32(v));
            if(s[b+4]){if(v>0xffffe){s[b]=4;if(v>=0x100000){v=0xfffff;w32(s,b+0xc,u32(v));}}}
            else if(v>0xffffe){s[b]=s[b+6]?4:3;if(v>=0x100000){v=0xfffff;w32(s,b+0xc,u32(v));}}
            break;
    case 2: break;
    case 3: if(!s[b+7]&&(s[b+4]||!s[b+0x10]))s[b]=4; break;
    case 4: if(s[b+7])s[b]=1;
            else{v=s32(u32(v)-(uint32_t)r16(s,b+0x22));w32(s,b+0xc,u32(v));
                 if(v<=0){v=0;w32(s,b+0xc,0);s[b]=s[b+4]?1:0;}}
            break;
    default: break;
    }
    if(s[b+1]!=1&&s[b+1]!=2)return (uint16_t)((u32(v)>>4)&0xffffu);
    {const uint8_t*c=s[b+1]==1?t->envelope1:t->envelope2;uint32_t raw,idx,nx;int32_t f,a,z;
     if(!c)return 0;
     raw=u32(v);idx=(raw>>10)&0x7ffu;nx=(idx+1)&0x7ffu;f=(int32_t)(raw&0x3ffu);
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
static int32_t res_noise(uint8_t*s,pk_cf_res_rng*r){
    const size_t b=0x60u;uint16_t c=r16(s,b);int16_t x;
    if(c){w16(s,b,(uint16_t)(c-1));return s16(r16(s,b+0x10));}
    w16(s,b,r16(s,b+2));x=s16((uint16_t)res_rnd(r));w16(s,b+0x10,(uint16_t)x);return x;
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

static int32_t res_core(uint8_t*s,const res_map*m,int32_t input,
                        const uint8_t*ia,const uint8_t*ib,int32_t*out_velocity){
    if(s[m->dirty]){
        int32_t pa=s16(r16(s,m->pitch_a)),pb=s16(r16(s,m->pitch_b));
        w32(s,m->coeff_b,(uint32_t)res_interp(ia,(uint32_t)pa<<17));
        w32(s,m->coeff_a,(uint32_t)res_interp(ib,(uint32_t)pb<<17));
        s[m->dirty]=0;
    }
    {int32_t coeff_a=s32(r32(s,m->coeff_a)),position=s32(r32(s,m->position)),
            modulation=s32(r32(s,m->mod)),coeff_b=s32(r32(s,m->coeff_b)),scale,velocity,filtered;
     if(modulation){
        scale=0x80;
        if(position>0x1000){coeff_a=add(coeff_a,asr(sub(position,0x800),3));scale=asr(position,4);}
        coeff_b=add(coeff_b,asr(mullo(scale,modulation),9));
     }
     velocity=s32(r32(s,m->velocity));
     filtered=input;
     if(!s[m->bypass])filtered=sub(input,asr(mullo(velocity,coeff_a),15));
     position=clamp32767(add(position,asr(mullo(velocity,coeff_b),15)));
     w32(s,m->position,u32(position));
     filtered=sub(filtered,position);
     velocity=clamp32767(add(velocity,asr(mullo(coeff_b,filtered),15)));
     w32(s,m->velocity,u32(velocity));
     *out_velocity=velocity;
     return position;}
}

/* --- multiplicative decay ramp ------------------------------------------ */
typedef struct { size_t mul,count,value,sign,min; } dec_map;

static uint32_t res_decay(uint8_t*s,const dec_map*m,int add_constant,uint32_t constant){
    uint32_t value=(pk_cf_mul_lo_u32(r32(s,m->mul),r32(s,m->value)))>>12;
    int32_t minimum=s32(r32(s,m->min));
    int32_t count,sign;int use_constant;
    if(s32(value)<minimum)value=u32(minimum);
    count=s32(r32(s,m->count));sign=s32(r32(s,m->sign));
    w32(s,m->value,value);
    use_constant=add_constant&&count!=0;
    if(count>0){count=sub(count,1);w32(s,m->count,u32(count));
        if(count==0){value=u32(add(s32(value),abs_arm(sign)));w32(s,m->value,value);use_constant=0;}}
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
    uint32_t i;
    if(!s||!d||!t||!rng||!t->envelope1||!t->envelope2||!t->interp_a||!t->interp_b)return 0;
    for(i=0;i<n;i++){
        uint32_t mod_a,mod_b,mod_c,level;
        int32_t count_a,count_b,count_c,drive,drive_quarter,pitch,signed_pitch;
        int32_t tone_velocity,noise_velocity,res_state,res_input,res_delta,product,mixed,tripled;
        int skip_pitch_offset;
        (void)res_env(s,t);
        /* mod A */
        mod_a=(pk_cf_mul_lo_u32(r32(s,BASS_A.mul),r32(s,BASS_A.value)))>>12;
        if(s32(mod_a)<s32(r32(s,BASS_A.min)))mod_a=r32(s,BASS_A.min);
        w32(s,BASS_A.value,mod_a);
        count_a=s32(r32(s,BASS_A.count));
        if(count_a>0){count_a=sub(count_a,1);w32(s,BASS_A.count,u32(count_a));
            if(count_a==0){mod_a=u32(add(s32(mod_a),abs_arm(s32(r32(s,BASS_A.sign)))));w32(s,BASS_A.value,mod_a);}}
        /* mod B */
        count_b=s32(r32(s,BASS_B.count));
        mod_b=(pk_cf_mul_lo_u32(r32(s,BASS_B.mul),r32(s,BASS_B.value)))>>12;
        if(s32(mod_b)<s32(r32(s,BASS_B.min)))mod_b=r32(s,BASS_B.min);
        if(count_b<0)mod_a=u32(neg(s32(mod_a)));
        w32(s,BASS_B.value,mod_b);
        mod_a=u32(add(s32(mod_a),count_b!=0?(1<<14):0));
        if(count_b>0){count_b=sub(count_b,1);w32(s,BASS_B.count,u32(count_b));
            if(count_b==0){mod_b=u32(add(s32(mod_b),abs_arm(s32(r32(s,BASS_B.sign)))));w32(s,BASS_B.value,mod_b);}}
        if(s32(r32(s,BASS_B.sign))<0)mod_b=u32(neg(s32(mod_b)));
        drive=add(s32(mod_a),s32(mod_b));
        /* mod C: pitch-offset timer */
        mod_c=(pk_cf_mul_lo_u32(r32(s,BASS_C.mul),r32(s,BASS_C.value)))>>12;
        if(s32(mod_c)<s32(r32(s,BASS_C.min)))mod_c=r32(s,BASS_C.min);
        count_c=s32(r32(s,BASS_C.count));
        w32(s,BASS_C.value,mod_c);
        skip_pitch_offset=(count_c==0);
        if(count_c>0){count_c=sub(count_c,1);w32(s,BASS_C.count,u32(count_c));
            if(count_c==0){mod_c=u32(add(s32(mod_c),abs_arm(s32(r32(s,BASS_C.sign)))));w32(s,BASS_C.value,mod_c);skip_pitch_offset=1;}}
        pitch=r16(s,0xF0);
        if(!skip_pitch_offset)pitch=(pitch+0x880)&0xffff;
        signed_pitch=s16((uint16_t)pitch);
        drive_quarter=asr(drive,4);
        if(s[TONE_MAP.dirty]||s16(r16(s,TONE_MAP.pitch_a))!=signed_pitch){
            w16(s,TONE_MAP.pitch_a,(uint16_t)pitch);s[TONE_MAP.dirty]=1;}
        (void)res_core(s,&TONE_MAP,drive,t->interp_a,t->interp_b,&tone_velocity);
        res_state=s32(r32(s,0xE8));
        res_input=add(tone_velocity,drive_quarter);
        res_delta=sub(res_input,res_state);
        level=res_decay(s,&BASS_L,0,0u);
        res_state=add(res_state,asr(mullo(s32(r32(s,0xEC)),res_delta),15));
        w32(s,0xE8,u32(res_state));
        {int32_t noise=res_noise(s,rng);
         (void)res_core(s,&NOISE_MAP,noise,t->interp_a,t->interp_b,&noise_velocity);}
        product=mullo(noise_velocity,s32(level));
        mixed=add(res_state,asr(product,16));
        tripled=add(mixed,add(mixed,mixed));
        d[i]=res_velocity_scale(s[6],tripled);
    }
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
    uint32_t i;
    if(!s||!d||!t||!rng||!t->envelope1||!t->envelope2||!t->interp_a||!t->interp_b)return 0;
    for(i=0;i<n;i++){
        uint32_t a,b,cv,dd;
        int32_t first_drive,first_mix,second_mix,velocity1,velocity2,velocity3;
        int32_t random_value,term1,term2,term3,mixed;
        (void)res_env(s,t);
        a=res_decay(s,&SNARE_A,0,0u);
        b=res_decay(s,&SNARE_B,1,0x0A3Du);
        first_drive=add(s32(a),s32(b));
        (void)res_core(s,&RES1_MAP,first_drive,t->interp_a,t->interp_b,&velocity1);
        cv=res_decay(s,&SNARE_C,1,0x3333u);
        first_mix=add(velocity1,asr(first_drive,4));
        (void)res_core(s,&RES2_MAP,s32(cv),t->interp_a,t->interp_b,&velocity2);
        second_mix=add(velocity2,asr(s32(cv),4));
        dd=res_decay(s,&SNARE_D,0,0u);
        random_value=res_noise(s,rng);
        (void)res_core(s,&RES3_MAP,random_value,t->interp_a,t->interp_b,&velocity3);
        term1=asr(mullo(second_mix,s32(r32(s,0x168))),15);
        term2=asr(mullo(s32(r32(s,0x164)),first_mix),15);
        term3=asr(mullo(velocity3,s32(dd)),15);
        mixed=add(add(term1,term2),term3);
        d[i]=res_velocity_scale(s[6],add(mixed,mixed));
    }
    return 1;
}

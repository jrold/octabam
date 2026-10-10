/* ColdFire renderer for the PĒRKONS v1.2.1 Noise Hat family (engine 010).
 *
 * Mirrors modules/perky/noise_hat_compact.py and noise_hat_pulse_compact.py,
 * which are exact against the real firmware's captured PCM/state/ring/hold/RNG
 * (out/perky/engine-fixtures/engine-10-*).
 *
 * Panel mapping: M1 -> firmware mode 1 (white), M2 -> mode 0 (metallic),
 * M3 -> mode 2 (pulse stack).  Layout inside the 0x2dd8 classic object:
 *   mute 0x0B8; limb 0 0x0C4 (6 pulses at +0x118 step 0x34, 4 filters at
 *   +0x9C/+0xC4/+0xE0/+0xFC, envelope +0x74); limb 1 0x318 (envelope +0x74,
 *   noise +0x60, filter +0x9C, use-second +0xC2, mute +0xB8, hold reload
 *   +0xC4, mix +0xC6, range +0xC8); delay 0x3E4 (5 taps, 5 gains, a 4805-sample
 *   ring at +0x14, write index at +0x259E); delay mix 0x2DD4.  The Pulse Stack
 *   limb is the separate 0x160 object at wrapper +0x2C98.
 *
 * ⚠️ THE RENDER STATE IS CACHED FOR THE BLOCK.  The payload runs from the
 * Octatrack's slow DRAM arena, so per-sample loads and stores through the
 * object dominated the cost, not the arithmetic.  Fields the renderer only
 * reads are hoisted, and every field it modifies lives in a local until the
 * block ends.  The arithmetic and its order are unchanged, so output and the
 * resulting object stay bit-identical.
 */
#include "cf_noise_hat.h"
#include "cf_math.h"
#include <limits.h>

#define NH_RING_LEN 0x12C5u
#define NH_MUTE     0x0B8u
#define NH_C0       0x0C4u
#define NH_C1       0x318u
#define NH_DL       0x3E4u
#define NH_RING     (NH_DL+0x14u)
#define NH_IDX      (NH_DL+0x259Eu)
#define NH_DELAY_MIX 0x2DD4u

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
static int32_t sat_filter(int32_t v){if(v>32767)return 32767;if(v<-32767)return -32767;return v;}
static int16_t sat16(int32_t v){if(v>32767)return 32767;if(v<-32768)return -32768;return (int16_t)v;}
static uint16_t tab16(const uint8_t*t,size_t i){return r16(t,i*2u);}

/* --- envelope ------------------------------------------------------------ */
typedef struct {
    uint8_t shape,flag4,flag6,trigger,hold;
    uint16_t attack,decay;
    const uint8_t *curve1,*curve2;
} nh_env_cfg;

static void nh_env_load(nh_env_cfg*c,const uint8_t*s,size_t b,const pk_cf_nh_tables*t){
    c->shape=s[b+1];c->flag4=s[b+4];c->flag6=s[b+6];c->trigger=s[b+7];c->hold=s[b+0x10];
    c->attack=r16(s,b+0x20);c->decay=r16(s,b+0x22);
    c->curve1=t->envelope1;c->curve2=t->envelope2;
}

static uint16_t nh_env_step(uint8_t*st,const nh_env_cfg*c,int32_t*v){
    switch(*st){
    case 0: if(c->trigger||c->flag4)*st=1; break;
    case 1: *v=s32(u32(*v)+(uint32_t)c->attack);
            if(c->flag4){if(*v>0xffffe){*st=4;if(*v>=0x100000)*v=0xfffff;}}
            else if(*v>0xffffe){*st=c->flag6?4:3;if(*v>=0x100000)*v=0xfffff;}
            break;
    case 2: break;
    case 3: if(!c->trigger&&(c->flag4||!c->hold))*st=4; break;
    case 4: if(c->trigger)*st=1;
            else{*v=s32(u32(*v)-(uint32_t)c->decay);if(*v<=0){*v=0;*st=c->flag4?1:0;}}
            break;
    default: break;
    }
    if(c->shape!=1u&&c->shape!=2u)return (uint16_t)((u32(*v)>>4)&0xffffu);
    {const uint8_t*cv=c->shape==1u?c->curve1:c->curve2;uint32_t raw,idx,nx;int32_t f,a,z;
     if(!cv)return 0;
     raw=u32(*v);idx=(raw>>10)&0x7ffu;nx=(idx+1)&0x7ffu;f=(int32_t)(raw&0x3ffu);
     a=(int32_t)tab16(cv,idx);z=(int32_t)tab16(cv,nx);
     return (uint16_t)(a+asr(mullo(z-a,f),10));}
}

/* --- noise generator ---------------------------------------------------- */
static uint32_t nh_rnd(pk_cf_nh_rng*r){
    const uint32_t a=0x5851f42d,b=0x4c957f2d;
    uint32_t ol=r->low,oh=r->high,acc=pk_cf_mul_lo_u32(ol,a),pl=pk_cf_mul_lo_u32(ol,b),
             ph=pk_cf_mul_hi_u32(ol,b),nl,carry,nh;
    acc+=pk_cf_mul_lo_u32(oh,b);nl=pl+1u;carry=nl<pl;nh=acc+ph+carry;
    r->low=nl;r->high=nh;return nh&0x7fffffffu;
}
static int16_t nh_velocity_scale(uint8_t velocity,int32_t value){
    return sat16(asr(mullo(value,(int32_t)velocity),8));
}

/* --- filter stage ------------------------------------------------------- */
typedef struct { uint16_t damp,coeff; int32_t first,second,velocity; } nh_filter_c;
static void nh_filter_load(nh_filter_c*f,const uint8_t*s,size_t b){
    f->damp=r16(s,b+0x0c);f->coeff=r16(s,b+0x0e);
    f->first=s32(r32(s,b+0x10));f->second=s32(r32(s,b+0x14));f->velocity=s32(r32(s,b+0x18));
}
static void nh_filter_store(const nh_filter_c*f,uint8_t*s,size_t b){
    w32(s,b+0x10,u32(f->first));w32(s,b+0x14,u32(f->second));w32(s,b+0x18,u32(f->velocity));
}
static void nh_filter_step(nh_filter_c*f,int32_t input){
    int32_t product=mullo(f->velocity,(int32_t)f->coeff),second,feedback;
    if(product<0)product=s32(u32(product)+0xffffu);
    f->first=sat_filter(add(f->first,asr(product,16)));
    second=sub(input,f->first);
    f->second=sat_filter(sub(second,asr(mullo(f->velocity,(int32_t)f->damp),10)));
    feedback=mullo(f->second,(int32_t)f->coeff);
    if(feedback<0)feedback=s32(u32(feedback)+0xffffu);
    f->velocity=sat_filter(add(f->velocity,asr(feedback,16)));
}

/* --- post-engine delay -------------------------------------------------- */
typedef struct { uint16_t delay[5],gain[5]; uint32_t index; int32_t mix; } nh_delay_c;
static void nh_delay_load(nh_delay_c*d,const uint8_t*s){
    unsigned i;
    for(i=0;i<5u;i++){d->delay[i]=r16(s,NH_DL+2u*i);d->gain[i]=r16(s,NH_DL+0x0au+2u*i);}
    d->index=r16(s,NH_IDX);d->mix=s16(r16(s,NH_DELAY_MIX));
}
static int32_t nh_delay_step(uint8_t*s,nh_delay_c*d,int32_t input){
    unsigned tap,next_index=d->index+1u;
    int32_t stage=input,wet,output;
    if(next_index>NH_RING_LEN-1u)next_index=0;
    for(tap=0;tap<5u;tap++){
        uint32_t delay=d->delay[tap],gain=d->gain[tap];
        uint32_t read_index=d->index>=delay?(d->index-delay):(NH_RING_LEN+d->index-delay);
        int32_t delayed=s16(r16(s,NH_RING+2u*read_index));
        stage=sat_filter(asr(add(mullo(stage,sub((int32_t)gain,0x10)),
                                mullo((int32_t)gain,delayed)),4));
    }
    w16(s,NH_RING+2u*next_index,(uint16_t)stage);
    d->index=next_index;
    wet=asr(mullo(stage,5),1);
    output=add(mullo(input,0xFFF-d->mix),mullo(d->mix,wet));
    return asr(output,12);
}

/* --- metallic (firmware mode 0) ----------------------------------------- */
static int nh_block_metallic(uint8_t*s,int16_t*dst,uint32_t n,const pk_cf_nh_tables*t){
    static const size_t fb[4]={NH_C0+0x9cu,NH_C0+0xc4u,NH_C0+0xe0u,NH_C0+0xfcu};
    struct { uint32_t phase,inc; uint16_t width,reload; } p[6];
    nh_filter_c f[4];nh_env_cfg ec;nh_delay_c dly;
    uint8_t est;unsigned i,k;int32_t ev,amp,value;
    if(s[NH_MUTE]){for(i=0;i<n;i++)dst[i]=0;return 1;}
    for(k=0;k<6u;k++){
        size_t b=NH_C0+0x118u+0x34u*k;
        p[k].phase=r32(s,b+4);p[k].inc=r32(s,b+8);
        p[k].width=r16(s,b+0x24);p[k].reload=r16(s,b+0x26);
    }
    for(k=0;k<4u;k++)nh_filter_load(&f[k],s,fb[k]);
    nh_env_load(&ec,s,NH_C0+0x74u,t);est=s[NH_C0+0x74];ev=s32(r32(s,NH_C0+0x74+0x0c));
    nh_delay_load(&dly,s);
    for(i=0;i<n;i++){
        int32_t total=0,pulse,inner;
        for(k=0;k<6u;k++){
            uint32_t phase=p[k].phase+p[k].inc;
            p[k].phase=phase;
            if(s32(phase)>0x100000){phase-=0x100000u;p[k].phase=phase;p[k].width=p[k].reload;}
            pulse=p[k].width>asr(s32(phase),8)?32767:-32767;
            total=add(total,s16((uint16_t)(((uint32_t)pulse>>5)&0xffffu)));
        }
        nh_filter_step(&f[0],total);
        nh_filter_step(&f[1],f[0].first);
        nh_filter_step(&f[2],f[1].second);
        nh_filter_step(&f[3],f[2].second);
        amp=nh_env_step(&est,&ec,&ev);
        value=asr(mullo(f[3].velocity,amp),11);
        inner=nh_velocity_scale(s[NH_C0+6],value);
        dst[i]=s16((uint16_t)nh_delay_step(s,&dly,inner));
    }
    for(k=0;k<6u;k++){
        size_t b=NH_C0+0x118u+0x34u*k;
        w32(s,b+4,p[k].phase);w16(s,b+0x24,p[k].width);
    }
    for(k=0;k<4u;k++)nh_filter_store(&f[k],s,fb[k]);
    s[NH_C0+0x74]=est;w32(s,NH_C0+0x74+0x0c,u32(ev));
    w16(s,NH_IDX,(uint16_t)dly.index);
    return 1;
}

/* --- white (firmware mode 1) -------------------------------------------- */
static int nh_block_white(uint8_t*s,int16_t*dst,uint32_t n,const pk_cf_nh_tables*t,
                          pk_cf_nh_rng*rng,pk_cf_nh_hold hold){
    size_t fb=NH_C1+0x9cu;
    nh_filter_c f;nh_env_cfg ec;nh_delay_c dly;
    uint8_t est;unsigned i;
    int32_t ev,amp,sample;
    const uint16_t noise_reload=r16(s,NH_C1+0x60u+2u);
    uint16_t noise_count=r16(s,NH_C1+0x60u),noise_value=r16(s,NH_C1+0x60u+0x10u);
    const uint8_t use_second=s[NH_C1+0xc2u],limb_mute=s[NH_C1+0xb8u];
    const uint16_t hold_reload=r16(s,NH_C1+0xc4u),mix=r16(s,NH_C1+0xc6u);
    const int32_t ratio=s32((int32_t)r16(s,NH_C1+0xc8u)-1-(int32_t)mix);
    const uint8_t velocity=s[NH_C1+6];
    nh_env_load(&ec,s,NH_C1+0x74u,t);est=s[NH_C1+0x74];ev=s32(r32(s,NH_C1+0x74+0x0c));
    nh_filter_load(&f,s,fb);
    nh_delay_load(&dly,s);
    for(i=0;i<n;i++){
        int32_t first,second,mixed,inner;
        amp=nh_env_step(&est,&ec,&ev);
        if(hold[0]){hold[0]=(uint16_t)(hold[0]-1u);sample=s16(hold[1]);}
        else{
            if(noise_count){noise_count=(uint16_t)(noise_count-1u);sample=s16(noise_value);}
            else{noise_count=noise_reload;noise_value=(uint16_t)nh_rnd(rng);sample=s16(noise_value);}
            hold[1]=(uint16_t)sample;hold[0]=hold_reload;
        }
        nh_filter_step(&f,sample);
        nh_filter_step(&f,sample);
        first=f.first;second=use_second?f.second:first;
        /* A muted limb still feeds the delay with zero, exactly as the
         * per-sample version did, so the tail keeps ringing. */
        if(limb_mute)inner=0;
        else{
            mixed=add(mullo(second,ratio),mullo((int32_t)mix,sample));
            mixed=asr(mixed,7);
            mixed=asr(mullo(amp,mixed),16);
            inner=nh_velocity_scale(velocity,mixed);
        }
        dst[i]=s16((uint16_t)nh_delay_step(s,&dly,inner));
    }
    nh_filter_store(&f,s,fb);
    s[NH_C1+0x74]=est;w32(s,NH_C1+0x74+0x0c,u32(ev));
    w16(s,NH_C1+0x60u,noise_count);w16(s,NH_C1+0x60u+0x10u,noise_value);
    w16(s,NH_IDX,(uint16_t)dly.index);
    return 1;
}

/* --- pulse stack (firmware mode 2) -------------------------------------- */
static int nh_block_pulse(uint8_t*s,int16_t*dst,uint32_t n,const pk_cf_nh_tables*t){
    static const size_t phase_off[6]={0x100,0x0fc,0x104,0x108,0x10c,0x110};
    static const size_t incr_off[6]={0x11c,0x118,0x120,0x124,0x128,0x12c};
    uint32_t ph[6],inc[6],random_phase,random_inc,random;
    nh_filter_c fa,fb;nh_env_cfg ec;
    uint8_t est;unsigned i,k;int32_t ev,second_input,previous,target,mix,value;
    const uint8_t velocity=s[6];
    for(k=0;k<6u;k++){ph[k]=r32(s,phase_off[k]);inc[k]=r32(s,incr_off[k]);}
    random_phase=r32(s,0x114);random_inc=r32(s,0x130);random=r32(s,0x134);
    nh_filter_load(&fa,s,0xc4u);nh_filter_load(&fb,s,0xe0u);
    nh_env_load(&ec,s,0x74u,t);est=s[0x74];ev=s32(r32(s,0x74+0x0c));
    mix=s16(r16(s,0x138));
    for(i=0;i<n;i++){
        uint32_t old_phase=random_phase;
        int32_t sign_count=0,pulse_stack,filtered,amp;
        random_phase=old_phase+random_inc;
        if(random_phase<old_phase)random=(random*0x0019660du+0x3c6ef35fu);
        for(k=0;k<6u;k++){
            uint32_t phase=ph[k]+inc[k];
            ph[k]=phase;
            sign_count+=(int32_t)(phase>>31);
        }
        pulse_stack=mullo(sign_count-3,0x1555);
        nh_filter_step(&fa,pulse_stack);
        second_input=(int32_t)((random>>16)&0xffffu)-0x8000;
        previous=fa.velocity;
        nh_filter_step(&fb,second_input);
        target=fb.second;
        filtered=add(previous,asr(mullo(mix,sub(target,previous)),15));
        amp=nh_env_step(&est,&ec,&ev);
        value=asr(mullo(filtered,amp),16);
        value=asr(mullo(value,(int32_t)velocity),8);
        dst[i]=sat16(value);
    }
    for(k=0;k<6u;k++){w32(s,phase_off[k],ph[k]);}
    w32(s,0x114,random_phase);w32(s,0x134,random);
    nh_filter_store(&fa,s,0xc4u);nh_filter_store(&fb,s,0xe0u);
    s[0x74]=est;w32(s,0x74+0x0c,u32(ev));
    return 1;
}

int pk_cf_nh_render(uint8_t*state,int16_t*dst,uint32_t n,unsigned firmware_mode,
                    const pk_cf_nh_tables*t,pk_cf_nh_rng*rng,pk_cf_nh_hold hold){
    if(!state||!dst||!t||!t->envelope1||!t->envelope2)return 0;
    if(firmware_mode>2u)return 0;
    if(firmware_mode==2u)return nh_block_pulse(state,dst,n,t);
    if(!rng||!hold)return 0;
    return firmware_mode==0u?nh_block_metallic(state,dst,n,t)
                            :nh_block_white(state,dst,n,t,rng,hold);
}

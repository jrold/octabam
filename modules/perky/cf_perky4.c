#include "cf_perky4.h"
#include <stddef.h>
#include "cf_math.h"

#define PK4_DEFAULT_WAVE 0x080222a0u
#define PK4_SIMPLE_OSC_RENDER 0x0802819du
#define PK4_M1_WAVE_DEFAULT 0x080310e0u
#define U32_MASK 0xffffffffu

static uint16_t r16(const uint8_t *p, size_t o){return (uint16_t)p[o]|(uint16_t)((uint16_t)p[o+1]<<8);}
static uint32_t r32(const uint8_t *p, size_t o){return (uint32_t)p[o]|((uint32_t)p[o+1]<<8)|((uint32_t)p[o+2]<<16)|((uint32_t)p[o+3]<<24);}
static void w16(uint8_t *p,size_t o,uint16_t v){p[o]=(uint8_t)v;p[o+1]=(uint8_t)(v>>8);}
static void w32(uint8_t *p,size_t o,uint32_t v){p[o]=(uint8_t)v;p[o+1]=(uint8_t)(v>>8);p[o+2]=(uint8_t)(v>>16);p[o+3]=(uint8_t)(v>>24);}
static int16_t s16(uint16_t v){return (v&0x8000u)?(int16_t)(-1-(int16_t)(uint16_t)~v):(int16_t)v;}
static int32_t s32(uint32_t v){return (v&0x80000000u)?-1-(int32_t)~v:(int32_t)v;}
static uint32_t clamp12s(int32_t v){if(v<0)return 0;if(v>4095)return 4095;return (uint32_t)v;}
static uint32_t target7(uint8_t v){v&=0x7fu;return v==127u?4095u:(uint32_t)v<<5;}
static uint32_t smooth(uint32_t old,uint32_t target){return (3u*target+5u*old)>>3;}
static uint16_t table16(const uint8_t *p,uint32_t i){return (uint16_t)p[2u*i]|(uint16_t)((uint16_t)p[2u*i+1u]<<8);}
static uint32_t pitch_at(const pk4_assets *a,uint32_t i){return table16(a->pitch,i);}
static int32_t note_offset(uint8_t note,const pk4_assets *a){uint32_t n=(uint32_t)note+3u,oct=n/12u,step=n%12u;return (int32_t)s16((uint16_t)(table16(a->chromatic,step)+(oct<<9)));}

static uint16_t time_parameter(uint16_t prepared){
    uint32_t q=0x7fffu+((uint32_t)prepared<<2),mant=(q&0xfffu)+0x1000u,exp=(q>>12)&0xfu,v;
    if(exp>11u)v=(mant<<(exp-12u))&0xffffu;else v=(mant>>(12u-exp))&0xffffu;
    v=(v-1u)&U32_MASK;v=(v>>1)&0x7fffu;return (uint16_t)((v-0x7fu)&0xffffu);
}
static uint16_t env_rate_cfg(const uint8_t *s,size_t base,uint16_t param,int decay){
    size_t c=base+(decay?0x1cu:0x18u);uint32_t off=r16(s,c),scale=r16(s,c+2u);
    uint32_t prod=(48u*((scale-1u)&0xffffu)*(uint32_t)param)&U32_MASK;
    uint32_t den=(48u*((off+1u)&0xffffu)+(prod>>12))&U32_MASK;
    return den? (uint16_t)(0xfffffu/den):0;
}
static void envelope_trigger(uint8_t*s,size_t b){s[b+0x10]=1;s[b]=1;if(s[b+8])w32(s,b+0x0c,0);}

/* ⚠️ OBJECT+8 = THE SUSTAIN THRESHOLD, 0x0FF0 -- and it is NOT set by the
 * engine init.  The original voice-default pass (0x0802775c..0x080277a6)
 * writes the default velocity/note pair 0x3FFF at engine+6 and then
 * strh 0x0FF0 at engine+8 (base 0x200001e0, offset 0x16C -> 0x2000034C,
 * which is wrapper 0x20000280 + 0xC4 + 8).  common_init (0x080246ac) never
 * writes offset 8, so the 0x0FF0 survives re-init.
 * common_update (0x08024714) then does, every pass:
 *     obj[0x7B] = (u16(obj+8) <= decay)      ; ldrh r3,[ip,#8]; cmp r3,r4;
 *                                            ; ite hi; movhi #0; movls #1
 * obj[0x7B] is the envelope's re-trigger/sustain gate (PerkyBits
 * renderEnvelope case 0/3/4).  With obj+8 wrongly zeroed the comparison is
 * always true, so the amplitude envelope re-attacks forever and never
 * releases: DECAY becomes inaudible, trigs stack into a drone, and the level
 * pins at full scale.  Verified against the real firmware: every one of the
 * 12 wrapper captures in out/perky/engine-fixtures has u16(engine+8)=0x0FF0,
 * and engine[0x7B] tracks (0x0FF0 <= decay) exactly (0 at control corners
 * 0x000/0x800, 1 at 0xFFF).  See docs/PK4_OBJ8_SUSTAIN.md. */
static void common_init(uint8_t*s,size_t n){
    size_t zi; for(zi=0;zi<n;++zi)s[zi]=0;w16(s,8,0x0ff0u);w32(s,0x38,PK4_DEFAULT_WAVE);w32(s,0x3c,PK4_DEFAULT_WAVE);w32(s,0x58,PK4_SIMPLE_OSC_RENDER);w32(s,0x60,0x00020000u);w16(s,0xa8,0x0800u);s[0x7a]=1;s[0x7c]=1;w32(s,0x8c,0x00020001u);w32(s,0x90,0x0fa00019u);
    w16(s,0x94,env_rate_cfg(s,0x74,0x1000,0));w16(s,0x96,env_rate_cfg(s,0x74,0x1000,1));
}
static void common_trigger(uint8_t*s,uint8_t velocity,uint8_t note){s[6]=velocity?velocity:1;if(note)s[7]=note;envelope_trigger(s,0x74);}
static void common_update(uint8_t*s,const uint32_t t[4],const pk4_assets*a,uint32_t out[4]){
    unsigned i;for(i=0;i<4u;i++){out[i]=smooth(r32(s,0x1c+4u*i),t[i]);w32(s,0x1c+4u*i,out[i]);}
    {
        uint16_t tune=(uint16_t)out[0],decay=(uint16_t)out[1],p1=(uint16_t)out[2],p2=(uint16_t)out[3];
        int32_t pi=(int32_t)s16((uint16_t)(tune-0x800u+(uint16_t)note_offset(s[7],a)));uint32_t ix=clamp12s(pi);
        w16(s,0xba,(uint16_t)ix);w16(s,0xbc,decay);w16(s,0xbe,p1);w16(s,0xc0,p2);w32(s,0x34,pitch_at(a,ix));s[0x7b]=(uint8_t)(r16(s,8)<=decay);
        w16(s,0x94,env_rate_cfg(s,0x74,time_parameter(r16(s,0x0a)),0));w16(s,0x96,env_rate_cfg(s,0x74,time_parameter(decay),1));
    }
}
static int control_dirty(const pk4_control*c,const uint8_t raw[4],uint8_t mode){unsigned i;if(!c->valid||c->last_mode!=mode)return 1;for(i=0;i<4u;i++)if(c->last_raw[i]!=raw[i])return 1;return 0;}
static void control_commit(pk4_control*c,const uint8_t raw[4],uint8_t mode){unsigned i;for(i=0;i<4;i++){c->last_raw[i]=raw[i];c->targets[i]=target7(raw[i]);}c->last_mode=mode;c->valid=1;}

static void fold_pitch_env_init(uint8_t*s){s[0xc5]=1;s[0xca]=1;s[0xcc]=1;w32(s,0xdc,0x00010000u);w32(s,0xe0,0x03e80000u);w16(s,0xe4,env_rate_cfg(s,0xc4,0x1000,0));w16(s,0xe6,env_rate_cfg(s,0xc4,0x0800,1));}
static uint8_t fold_mode(uint8_t m){static const uint8_t map[3]={1,2,0};return map[m<3?m:2];}
static void fold1_init(uint8_t*s,uint8_t mode,uint8_t vel,uint8_t note){common_init(s,PK_CF_FOLD1_STATE_BYTES);fold_pitch_env_init(s);s[5]=fold_mode(mode);s[6]=vel?vel:1;s[7]=note; s[0x7c]=0;w32(s,0x90,0x1c700032u);w16(s,0x94,env_rate_cfg(s,0x74,time_parameter(r16(s,0x0a)),0));w16(s,0x96,env_rate_cfg(s,0x74,time_parameter(0),1));}
static void fold2_init(uint8_t*s,uint32_t obj,uint8_t mode,uint8_t vel,uint8_t note){common_init(s,PK_CF_FOLD2_STATE_BYTES);fold_pitch_env_init(s);s[5]=fold_mode(mode);s[6]=vel?vel:1;s[7]=note;s[0x7c]=0;w32(s,0x90,0x1c700032u);w16(s,0x94,env_rate_cfg(s,0x74,time_parameter(r16(s,0x0a)),0));w16(s,0x96,env_rate_cfg(s,0x74,time_parameter(0),1));w32(s,0x100,PK4_DEFAULT_WAVE);w32(s,0x104,PK4_DEFAULT_WAVE);w32(s,0x120,PK4_SIMPLE_OSC_RENDER);w32(s,0x128,obj+0x2c);w32(s,0x12c,obj+0xf4);}
static void fold_update(uint8_t*s,const uint32_t t[4],const pk4_assets*a){uint32_t p[4];common_update(s,t,a,p);w16(s,0xee,r16(s,0xc0));w16(s,0xf0,r16(s,0xbe));}
static void fold1_trigger(uint8_t*s,uint8_t vel,uint8_t note){common_trigger(s,vel,note);envelope_trigger(s,0xc4);w16(s,0xec,0);}
static void fold2_trigger(uint8_t*s,uint32_t obj,uint8_t vel,uint8_t note){uint8_t old;uint32_t a=obj+0x2c,z=obj+0xf4,pri,sec;fold1_trigger(s,vel,note);old=s[0xf2];s[0xf2]=(uint8_t)!old;if(old==0){pri=z;sec=a;}else{pri=a;sec=z;}w32(s,0x128,pri);w32(s,0x12c,sec);w32(s,(size_t)(pri-obj)+4u,0);w16(s,0x132,r16(s,0x130));}

static uint8_t karplus_mode(uint8_t m){static const uint8_t map[3]={1,0,2};return map[m<3?m:2];}
static void karplus_init(uint8_t*s,uint8_t mode,uint8_t vel,uint8_t note){common_init(s,PK_CF_KARPLUS_STATE_BYTES);s[5]=karplus_mode(mode);s[6]=vel?vel:1;s[7]=note;w32(s,0x90,0x1c700032u);w16(s,0x9c+0x0c,0x0800u);w16(s,0x94,env_rate_cfg(s,0x74,time_parameter(r16(s,0x0a)),0));w16(s,0x96,env_rate_cfg(s,0x74,time_parameter(0),1));}
static uint16_t karplus_coeff(uint16_t p){uint32_t product=((uint32_t)p*0x6486cu)&U32_MASK;return (uint16_t)(pk_cf_mul_hi_u32(product,0x057619f1u)>>10);}
static uint32_t karplus_delay(uint32_t tune,uint8_t note,const pk4_assets*a){int32_t ix=(3*(int32_t)s16((uint16_t)tune)>>3)-0x514+note_offset(note,a);uint32_t p,rec,freq,fd;if(ix<0)ix=0;else if(ix>4095)ix=4095;p=pitch_at(a,(uint32_t)ix);rec=p?0x100000u/p:0;freq=rec?0x17700u/rec:0;fd=freq?(0x05dc0000u/freq-0x400u):0xffffffffu;return fd<=0x400000u?fd>>11:0x800u;}
static void karplus_update(uint8_t*s,const uint32_t t[4],const pk4_assets*a){uint32_t p[4],tune;common_update(s,t,a,p);tune=smooth(p[0],t[0]);w32(s,0x1c,tune);s[0x10dc]=(uint8_t)(r16(s,0xbc)>r16(s,8));w16(s,0xc2,r16(s,0xc0)>>1);w32(s,0x10c8,karplus_delay(tune,s[7],a));w16(s,0xaa,karplus_coeff(r16(s,0xbe)));}
static void karplus_trigger(uint8_t*s,uint8_t vel,uint8_t note){common_trigger(s,vel,note);w16(s,0xc4,0);w32(s,0x10d8,0);}

static uint8_t nt_mode(uint8_t m){static const uint8_t map[3]={1,0,2};return map[m<3?m:2];}
static uint32_t nt_wave_for_fw(uint8_t fw){return fw==0?0x080226a0u:(fw==2?0x080228a0u:PK4_DEFAULT_WAVE);}
static int32_t osc_increment(uint16_t value){int32_t shifted=s32((uint32_t)value<<20);int32_t high=pk_cf_mul_hi_s32(shifted,s32(0x057619f1u));return (high>>10)-(shifted>>31);}
static void nt_init(uint8_t*s,uint8_t panel_mode,int m1,uint8_t vel,uint8_t note,const pk4_assets*a){uint8_t fw=nt_mode(panel_mode);common_init(s,PK_CF_NT_STATE_BYTES);w32(s,0x58,0);s[5]=fw;s[6]=vel?vel:1;s[7]=note;s[0x7a]=1;s[0x7c]=1;w32(s,0x8c,0x00020001u);w32(s,0x90,0x0fa00019u);if(m1){w16(s,0xc4,1);w32(s,0x8c,0x0fa00000u);w32(s,0x90,0x0fa00003u);w32(s,0xe4,a->m1_wave_address?a->m1_wave_address:PK4_M1_WAVE_DEFAULT);w32(s,0xe8,a->m1_wave_address?a->m1_wave_address:PK4_M1_WAVE_DEFAULT);}else{s[0xc4]=0;w32(s,0xd0,PK4_DEFAULT_WAVE);w32(s,0xd4,PK4_DEFAULT_WAVE);s[0x7c]=0;w32(s,0x90,0x0fa00002u);}w16(s,0x94,env_rate_cfg(s,0x74,0x1000,0));w16(s,0x96,env_rate_cfg(s,0x74,0x1000,1));}
static void nt_trigger(uint8_t*s,uint8_t vel,uint8_t note){common_trigger(s,vel,note);}
static void nt_update(uint8_t*s,const uint32_t t[4],const pk4_assets*a,int m1){uint32_t p[4];uint8_t fw;common_update(s,t,a,p);fw=s[5];if(m1){uint32_t tune=smooth(p[0],t[0]);int32_t ix;w32(s,0x1c,tune);ix=(int32_t)s16((uint16_t)((tune&0x0f80u)-0x0800u+(uint16_t)note_offset(s[7],a)));if(ix<0)ix=0;else if(ix>4095)ix=4095;w32(s,0xdc,pitch_at(a,(uint32_t)ix));w16(s,0x0a,r16(s,0xc0));w32(s,0xc8,(0x000ce364u-199u*(uint32_t)r16(s,0xbe))&U32_MASK);return;}w32(s,0x3c,nt_wave_for_fw(fw));w16(s,0xaa,karplus_coeff(r16(s,0xbe)));{uint32_t ix=clamp12s((int32_t)s16(r16(s,0xba)));uint32_t base=(0xbb80u*pitch_at(a,ix))>>20;uint16_t scaled=(uint16_t)((base*((r16(s,0xc0)+0x0800u)&0xffffu))>>12);w32(s,0xcc,(uint32_t)osc_increment(scaled));w32(s,0xf8,r16(s,0xbe));}}

/* The original wrapper settles controls by calling update repeatedly.  Only the
 * four smoothed words feed the next iteration; all derived pitch/envelope/
 * filter/oscillator fields are overwritten by the final update.  Preserve the
 * exact integer recurrence here, including Karplus/M1's second TUNE smoothing,
 * and run the expensive derive only for the last surviving state. */
static void common_smooth_only(uint8_t*s,const uint32_t t[4]){unsigned i;for(i=0;i<4u;i++)w32(s,0x1c+4u*i,smooth(r32(s,0x1c+4u*i),t[i]));}
static void karplus_smooth_only(uint8_t*s,const uint32_t t[4]){common_smooth_only(s,t);w32(s,0x1c,smooth(r32(s,0x1c),t[0]));}
static void nt_smooth_only(uint8_t*s,const uint32_t t[4],int m1){common_smooth_only(s,t);if(m1){w32(s,0x1c,smooth(r32(s,0x1c),t[0]));w16(s,0x0a,r16(s,0x28));}}

static void prepare_fold(pk4_control*c,uint8_t*s,int fold2,uint32_t obj,const uint8_t raw[4],uint8_t mode,uint8_t vel,uint8_t note,int trig,const pk4_assets*a){unsigned i;if(control_dirty(c,raw,mode)){common_smooth_only(s,c->targets);common_smooth_only(s,c->targets);s[5]=fold_mode(mode);control_commit(c,raw,mode);if(trig){for(i=0;i<16;i++)common_smooth_only(s,c->targets);}else{for(i=0;i<15;i++)common_smooth_only(s,c->targets);fold_update(s,c->targets,a);}}if(trig){if(fold2)fold2_trigger(s,obj,vel,note);else fold1_trigger(s,vel,note);fold_update(s,c->targets,a);}}
static void prepare_karp(pk4_control*c,uint8_t*s,const uint8_t raw[4],uint8_t mode,uint8_t vel,uint8_t note,int trig,const pk4_assets*a){unsigned i;if(control_dirty(c,raw,mode)){karplus_smooth_only(s,c->targets);karplus_smooth_only(s,c->targets);s[5]=karplus_mode(mode);control_commit(c,raw,mode);if(trig){for(i=0;i<16;i++)karplus_smooth_only(s,c->targets);}else{for(i=0;i<15;i++)karplus_smooth_only(s,c->targets);karplus_update(s,c->targets,a);}}if(trig){karplus_trigger(s,vel,note);karplus_update(s,c->targets,a);}}
static void prepare_nt(pk4_control*c,uint8_t*s,int m1,const uint8_t raw[4],uint8_t mode,uint8_t vel,uint8_t note,int trig,const pk4_assets*a){unsigned i;if(control_dirty(c,raw,mode)){nt_smooth_only(s,c->targets,m1);nt_smooth_only(s,c->targets,m1);s[5]=nt_mode(mode);control_commit(c,raw,mode);if(trig){for(i=0;i<16;i++)nt_smooth_only(s,c->targets,m1);}else{for(i=0;i<15;i++)nt_smooth_only(s,c->targets,m1);nt_update(s,c->targets,a,m1);}}if(trig){nt_trigger(s,vel,note);nt_update(s,c->targets,a,m1);}}

/* ==================== Resonant Drums control path ========================
 * Recovered from the original ARM routines and validated byte-for-byte against
 * the real firmware's captured objects (out/perky/engine-fixtures/engine-7-*):
 *   bass  init 0x08026790  update 0x0802682C  trigger 0x080268DC
 *   snare init 0x08025F8C  update 0x08026030  trigger 0x08026108
 *   pitch helper 0x0802844C = s16(min(index,0xFFF)*3 + 0x800)
 * The panel modes are M1 = snare, M2 = bass, M3 = the shared Noise/Tone path.
 * The firmware allocates one 0x1d4 object per mode; the bass update still writes
 * 0x17C, outside the 0x178 prefix its renderer reads.
 */
#define PK4_RES_FAMILY_BYTES PK_CF_RES_SNARE_STATE_BYTES

static int32_t res_pitch_helper(uint16_t index){uint32_t i=index>0xfffu?0xfffu:index;return s16((uint16_t)(i*3u+0x800u));}

static void res_init_bass(uint8_t*s,uint8_t vel,uint8_t note){
    common_init(s,PK4_RES_FAMILY_BYTES);
    w32(s,0xf8,0x00000d0cu); s[0xc4]=1; w32(s,0x10c,0x30u); s[0x158]=1;
    w32(s,0x110,0x00000c00u); w32(s,0x124,0xc0u); w32(s,0xc6,0x40001080u);
    w32(s,0xf4,0); w32(s,0x108,0); w32(s,0x120,0); w32(s,0x130,0); w32(s,0x138,0);
    w32(s,0xdc,0); w32(s,0xe0,0); w32(s,0xcc,0x40u); w32(s,0x154,0); w32(s,0x160,0);
    w32(s,0x90,0x0fa00005u); w32(s,0x128,0x00000ffdu); w32(s,0x12c,0);
    w32(s,0x140,0); w32(s,0x144,0x00000ffdu);
    w32(s,0xfc,0); w32(s,0x100,0);
    w32(s,0x114,0); w32(s,0x118,0);
    w32(s,0x148,0); w32(s,0x14c,0);
    w32(s,0x170,0); w32(s,0x174,0);
    w32(s,0x15a,0x07d01080u);
    s[6]=vel?vel:1;s[7]=note;
}
static void res_init_snare(uint8_t*s,uint8_t vel,uint8_t note){
    common_init(s,PK4_RES_FAMILY_BYTES);
    w32(s,0x174,0x600u); w32(s,0x1a0,0x30u); w32(s,0x170,0);
    w32(s,0x184,0); w32(s,0x19c,0); w32(s,0x1ac,0); w32(s,0x1b4,0); w32(s,0x1b8,0);
    w32(s,0x1cc,0); s[0xf8]=1; w32(s,0x100,0); s[0x11c]=1; w32(s,0x124,0);
    w32(s,0x188,0x30u); w32(s,0x18c,0x00000c00u);
    w32(s,0xfa,0x40001080u); w32(s,0x11e,0x07d01080u);
    w32(s,0x1a4,0x4b0u); w32(s,0x1a8,0);
    w32(s,0x178,0); w32(s,0x17c,0);
    w32(s,0x190,0); w32(s,0x194,0);
    w32(s,0x1c0,0); w32(s,0x1c4,0);
    w32(s,0x110,0); w32(s,0x114,0);
    w32(s,0x134,0); w32(s,0x138,0);
    w32(s,0x158,0); w32(s,0x15c,0);
    w32(s,0x1bc,0x00000ffdu); s[0x140]=1; w32(s,0x148,0);
    w32(s,0x142,0x07d01080u); w32(s,0x90,0x0fa00005u);
    s[6]=vel?vel:1;s[7]=note;
}

static void res_update_bass(uint8_t*s,const uint32_t t[4],const pk4_assets*a){
    uint32_t p[4],mod_a,mod_b,mod_c,r2,r3;uint16_t obj8,decay,p1,p2;int32_t count_a,count_b,count_c,index;
    common_update(s,t,a,p);
    obj8=r16(s,8);decay=r16(s,0xbc);p1=r16(s,0xbe);p2=r16(s,0xc0);
    s[0xd8]=(uint8_t)(decay>obj8);
    if(decay>obj8){r2=(uint32_t)((p1<<4)&0xffffu);}
    else{
        uint32_t r1=(uint32_t)((0xfffu-decay)&0xffffu);
        s[0xc4]=1;w32(s,0x144,(uint32_t)(decay>>10)+0xffcu);
        r3=(r1*r1);r3>>=8;r3=(r1*r3)&U32_MASK;r3>>=14;
        r3=(0x7f80u-r3)&U32_MASK;
        w16(s,0xc8,(uint16_t)r3);
        r2=0;
    }
    w16(s,0x154,(uint16_t)r2);
    index=(int32_t)r16(s,0xba);
    {uint8_t nd=s[0x158];
     r3=(uint32_t)((index*7)>>3)&0xffffu;
     w16(s,0xf0,(uint16_t)(r3+0xc00u));
     r3=(uint32_t)(uint16_t)s16((uint16_t)(r3+0x2400u));
     if(!nd)nd=(uint8_t)((s16(r16(s,0x15a))-(int16_t)r3)!=0);
     w16(s,0x15a,(uint16_t)r3);
     r3=((uint32_t)p2*p2)>>8;r3&=0xffffu;
     w16(s,0x17c,p1);
     w32(s,0xec,0xc1e8u);
     s[0x158]=nd?1:0;
     r3=(r3*r3)&U32_MASK;
     w32(s,0xcc,r3>>24);}
    (void)mod_a;(void)mod_b;(void)mod_c;(void)count_a;(void)count_b;(void)count_c;
}

static void res_update_snare(uint8_t*s,const uint32_t t[4],const pk4_assets*a){
    uint32_t p[4];uint16_t obj8,decay,p1,p2;uint32_t r2,r3;int32_t r0;uint8_t d1,d2,d3;
    common_update(s,t,a,p);
    obj8=r16(s,8);decay=r16(s,0xbc);p1=r16(s,0xbe);p2=r16(s,0xc0);
    {uint8_t v=(uint8_t)(decay>obj8);s[0x10c]=v;s[0x130]=v;}
    if(decay>obj8){w32(s,0x1cc,(uint32_t)((p2<<4)&0xffffu));}
    else{
        s[0xf8]=1;
        w16(s,0xfc,(uint16_t)(0x6fffu+decay));
        w16(s,0x120,(uint16_t)(0x6784u+decay));
        s[0x11c]=1;
        w32(s,0x1bc,(uint32_t)(decay>>10)+0xffcu);
    }
    r0=res_pitch_helper(r16(s,0xba));
    d1=s[0xf8];
    if(!d1)d1=(uint8_t)((s16(r16(s,0xfa))-r0)!=0);
    r3=(uint32_t)(uint16_t)r0;
    s[0xf8]=d1?1:0;
    w16(s,0xfa,(uint16_t)r3);
    r2=(uint32_t)(uint16_t)s16((uint16_t)(r3+0x600u));
    d2=s[0x11c];
    if(!d2)d2=(uint8_t)((s16(r16(s,0x11e))-(int16_t)r2)!=0);
    s[0x11c]=d2?1:0;
    w16(s,0x11e,(uint16_t)r2);
    r3=(uint32_t)(uint16_t)s16((uint16_t)(r3+0x1800u));
    d3=s[0x140];
    if(!d3)d3=(uint8_t)((s16(r16(s,0x142))-(int16_t)r3)!=0);
    s[0x140]=d3?1:0;
    w16(s,0x142,(uint16_t)r3);
    w32(s,0x164,(0x55f0u-((uint32_t)p1<<2))&U32_MASK);
    w32(s,0x168,(0x55f0u+((uint32_t)p1<<2))&U32_MASK);
    w16(s,0x16c,p2);
}

static void res_trigger_bass(uint8_t*s,uint8_t vel,uint8_t note){
    common_trigger(s,vel,note);
    w32(s,0x11c,0xffffca3du); w32(s,0x104,0x00043333u);
    w32(s,0x12c,(r32(s,0x124)+1u)&U32_MASK);
    w32(s,0xfc,(r32(s,0xf4)+1u)&U32_MASK);
    w32(s,0x114,(r32(s,0x10c)+1u)&U32_MASK);
    w32(s,0x150,((uint32_t)r16(s,0x17c)<<4)&0xffffu);
    w32(s,0x134,0x4650u);
    w32(s,0x148,(r32(s,0x140)+1u)&U32_MASK);
}
static void res_trigger_snare(uint8_t*s,uint8_t vel,uint8_t note){
    common_trigger(s,vel,note);
    w32(s,0x198,0xffff8000u); w32(s,0x180,0x00078000u);
    w32(s,0x178,(r32(s,0x170)+1u)&U32_MASK);
    w32(s,0x190,(r32(s,0x188)+1u)&U32_MASK);
    w32(s,0x1a8,(r32(s,0x1a0)+1u)&U32_MASK);
    w32(s,0x1c0,(r32(s,0x1b8)+1u)&U32_MASK);
    w32(s,0x1b0,0x3333u);
    w32(s,0x1c8,(((uint32_t)(uint16_t)s16(r16(s,0x16c)))<<4));
}

/* The recovered sequence is exactly sixteen control updates after the targets
 * change (validated against the firmware captures), then trigger + one update. */
static void prepare_res(pk4_control*c,uint8_t*s,int bass,const uint8_t raw[4],uint8_t mode,uint8_t vel,uint8_t note,int trig,const pk4_assets*a){
    unsigned i;
    if(control_dirty(c,raw,mode)){
        control_commit(c,raw,mode);
        for(i=0;i<16;i++){if(bass)res_update_bass(s,c->targets,a);else res_update_snare(s,c->targets,a);}
    }
    if(trig){
        if(bass){res_trigger_bass(s,vel,note);res_update_bass(s,c->targets,a);}
        else{res_trigger_snare(s,vel,note);res_update_snare(s,c->targets,a);}
    }
}

/* ======================= Noise Hat control path ==========================
 * Recovered from the Voice-4 wrapper and validated byte-for-byte against the
 * real firmware's captured objects (out/perky/engine-fixtures/engine-10-*):
 *   wrapper update 0x080255C0 / trigger 0x08025524, obj[4]=family obj[5]=MODE
 *   metallic limb +0x0C4 init 0x080263AC update 0x08026454
 *   white    limb +0x318 init 0x08025750 update 0x08025770
 *   pulse    limb +0x2C98 init 0x08026ED0 update 0x08026F34
 * Helper laws: 0x080288C0 damp=min(v,0x800); 0x080288D0 = the Karplus
 * coefficient law; 0x08028464 = the oscillator increment law.
 * The wrapper update stores PARAM1 into the post-engine delay mix at +0x2DD4.
 */
#define NH_LIMB0 0x0c4u
static uint32_t u32(int32_t s){return s>=0?(uint32_t)s:~(uint32_t)(-1-s);}
#define NH_LIMB1 0x318u
#define NH_PULSE 0x2c98u
#define NH_DELAY_MIX 0x2dd4u

static int32_t nh_asr(int32_t v,unsigned n){uint32_t b;if(!n)return v;b=u32(v)>>n;if(v<0)b|=(~0u)<<(32u-n);return s32(b);}
static void nh_damp(uint8_t*s,size_t b,uint16_t v){w16(s,b+0x0c,(uint16_t)(v>0x800u?0x800u:v));}
static void nh_coeff(uint8_t*s,size_t b,uint16_t v){w16(s,b+0x0e,karplus_coeff(v));}

static void nh_common_init_at(uint8_t*s,size_t b,uint8_t note){
    w32(s,b+0x38,PK4_DEFAULT_WAVE);w32(s,b+0x3c,PK4_DEFAULT_WAVE);
    w32(s,b+0x58,PK4_SIMPLE_OSC_RENDER);w32(s,b+0x60,0x00020000u);
    w16(s,b+0xa8,0x0800u);
    s[b+0x7a]=1;s[b+0x7c]=1;
    w32(s,b+0x8c,0x00020001u);w32(s,b+0x90,0x0fa00019u);
    w16(s,b+8,0x0ff0u);
    s[b+6]=255;s[b+7]=note;
    w16(s,b+0x94,env_rate_cfg(s,b+0x74,time_parameter(0),0));
    w16(s,b+0x96,env_rate_cfg(s,b+0x74,time_parameter(0),1));
}

static void nh_init_limb0(uint8_t*s){
    unsigned i;static const uint16_t seeds[6]={0x021cu,0x0320u,0x0277u,0x0170u,0x01beu,0x00f8u};
    static const uint16_t coeffs[4]={0x1b58u,0x1a90u,0x1a90u,0x04b0u};
    static const uint16_t offsets[4]={0x9cu,0xc4u,0xe0u,0xfcu};
    nh_common_init_at(s,NH_LIMB0,63);
    w32(s,NH_LIMB0+0x8c,0x02ee0009u);w32(s,NH_LIMB0+0x90,0x02ee0009u);
    s[NH_LIMB0+0x7c]=1;
    for(i=0;i<6u;i++){
        size_t b=NH_LIMB0+0x118u+0x34u*i;
        w32(s,b+0x00,4u);
        w32(s,b+0x24,0x08000800u);
        w32(s,b+8,seeds[i]);
        w32(s,b+4,0);
        w32(s,b+0x2c,0x080282adu);
    }
    for(i=0;i<4u;i++){
        size_t b=NH_LIMB0+offsets[i];
        nh_damp(s,b,i==0u?0x06abu:0x02abu);
        nh_coeff(s,b,coeffs[i]);
        w32(s,b+0x10,0);w32(s,b+0x14,0);w32(s,b+0x18,0);
    }
}

static void nh_init_limb1(uint8_t*s){
    nh_common_init_at(s,NH_LIMB1,63);
    w32(s,NH_LIMB1+0x8c,0x0fa00000u);w32(s,NH_LIMB1+0x90,0x0fa00003u);
    w16(s,NH_LIMB1+0xc4,0x0001u);      /* hold reload */
    w16(s,NH_LIMB1+0xc8,0x0080u);      /* range, constant in every capture */
    w32(s,NH_LIMB1+0x60,0x00020000u);
    nh_damp(s,NH_LIMB1+0x9c,0x0800u);
    nh_coeff(s,NH_LIMB1+0x9c,0x0800u);
    w32(s,NH_LIMB1+0x9c+0x10,0);w32(s,NH_LIMB1+0x9c+0x14,0);w32(s,NH_LIMB1+0x9c+0x18,0);
}

static void nh_init_pulse(uint8_t*s){
    unsigned i;
    nh_common_init_at(s,NH_PULSE,63);
    s[NH_PULSE+0x7c]=1;
    w32(s,NH_PULSE+0x8c,0x02ee0009u);w32(s,NH_PULSE+0x90,0x02ee0012u);
    for(i=0;i<0x38u;i++)s[NH_PULSE+0xfcu+i]=0;
    nh_damp(s,NH_PULSE+0xc4,0x03e8u);nh_coeff(s,NH_PULSE+0xc4,0x0b40u);
    nh_damp(s,NH_PULSE+0xe0,0x0640u);nh_coeff(s,NH_PULSE+0xe0,0x0b40u);
    for(i=0;i<2u;i++){
        size_t b=NH_PULSE+(i?0xe0u:0xc4u);
        w32(s,b+0x10,0);w32(s,b+0x14,0);w32(s,b+0x18,0);
    }
}

/* The wrapper owns a five-tap delay whose taps are constants. */
static void nh_init_delay(uint8_t*s){
    static const uint16_t taps[5]={0x023du,0x04b1u,0x0602u,0x0c43u,0x12c4u};
    static const uint16_t gains[5]={0x0001u,0x0001u,0x0003u,0x0005u,0x0007u};
    unsigned i;
    for(i=0;i<5u;i++){w16(s,0x3e4u+2u*i,taps[i]);w16(s,0x3eeu+2u*i,gains[i]);}
    for(i=0;i<0x258au;i++)s[0x3f8u+i]=0;   /* the ring, cleared by 0x08024364 */
    w16(s,0x2982u,0);
    w16(s,NH_DELAY_MIX,0);
}

/* common_update 0x08024714 applied at an arbitrary base. */
static void nh_common_update(uint8_t*s,size_t b,const uint32_t t[4],const pk4_assets*a){
    uint32_t out[4];unsigned i;
    for(i=0;i<4u;i++){out[i]=smooth(r32(s,b+0x1c+4u*i),t[i]);w32(s,b+0x1c+4u*i,out[i]);}
    {uint16_t tune=(uint16_t)out[0],decay=(uint16_t)out[1],p1=(uint16_t)out[2],p2=(uint16_t)out[3];
     int32_t pi=(int32_t)s16((uint16_t)(tune-0x800u+(uint16_t)note_offset(s[b+7],a)));
     uint32_t ix=clamp12s(pi);
     w16(s,b+0xba,(uint16_t)ix);w16(s,b+0xbc,decay);w16(s,b+0xbe,p1);w16(s,b+0xc0,p2);
     w32(s,b+0x34,pitch_at(a,ix));
     s[b+0x7b]=(uint8_t)(r16(s,b+8)<=decay);
     w16(s,b+0x94,env_rate_cfg(s,b+0x74,time_parameter(r16(s,b+0x0a)),0));
     w16(s,b+0x96,env_rate_cfg(s,b+0x74,time_parameter(decay),1));}
}

static void nh_update_limb0(uint8_t*s,const uint32_t t[4],const pk4_assets*a){
    static const uint16_t seeds[6]={0x021cu,0x0320u,0x0277u,0x0170u,0x01beu,0x00f8u};
    unsigned i;int32_t delta;
    nh_common_update(s,NH_LIMB0,t,a);
    w16(s,NH_LIMB0+0x0a,r16(s,NH_LIMB0+0xc0));
    delta=nh_asr((int32_t)r16(s,NH_LIMB0+0xba),2)-0xc8;
    for(i=0;i<6u;i++)
        w32(s,NH_LIMB0+0x118u+0x34u*i+8,(uint32_t)osc_increment((uint16_t)s16((uint16_t)(seeds[i]+delta))));
}

static void nh_update_limb1(uint8_t*s,const uint32_t t[4],const pk4_assets*a){
    uint16_t index,rng,threshold;
    nh_common_update(s,NH_LIMB1,t,a);
    w16(s,NH_LIMB1+0x0a,r16(s,NH_LIMB1+0xc0));
    index=r16(s,NH_LIMB1+0xba);
    rng=r16(s,NH_LIMB1+0xc8);
    if(index<0x800u){
        s[NH_LIMB1+0xc2]=0;
        nh_coeff(s,NH_LIMB1+0x9c,(uint16_t)(index<<1));
        threshold=(uint16_t)(0x800u-rng);
        w16(s,NH_LIMB1+0xc6,index>threshold?(uint16_t)(index+rng-0x800u):0);
    }else{
        s[NH_LIMB1+0xc2]=2;
        nh_coeff(s,NH_LIMB1+0x9c,(uint16_t)(index-0x800u));
        threshold=(uint16_t)(rng+0x800u);
        w16(s,NH_LIMB1+0xc6,index>=threshold?0:(uint16_t)(rng+0x7ffu-index));
    }
}

static void nh_update_pulse(uint8_t*s,const uint32_t t[4],const pk4_assets*a){
    uint32_t base,q;uint16_t step;
    nh_common_update(s,NH_PULSE,t,a);
    w16(s,NH_PULSE+0x0a,r16(s,NH_PULSE+0xc0));
    step=(uint16_t)s16((uint16_t)((r16(s,NH_PULSE+0xba)>>1)+0x708u));
    base=(uint32_t)pitch_at(a,step>4095u?4095u:step)<<12;
    q=base>>10;
    w32(s,NH_PULSE+0x118,base);
    w32(s,NH_PULSE+0x11c,(q*0x5ed1u)>>4);
    w32(s,NH_PULSE+0x120,(q*0x3111u)>>4);
    w32(s,NH_PULSE+0x124,(q*0x47f1u)>>4);
    w32(s,NH_PULSE+0x128,(q*0x57b4u)>>4);
    w32(s,NH_PULSE+0x12c,(q*0x7c72u)>>4);
    w32(s,NH_PULSE+0x130,((base+((uint32_t)pitch_at(a,step>4095u?4095u:step)<<13))<<3)&U32_MASK);
    w16(s,NH_PULSE+0x138,(uint16_t)(r16(s,NH_PULSE+0xbe)<<3));
}

/* Panel MODE -> firmware limb: M1 white, M2 metallic, M3 pulse stack. */
static unsigned nh_mode(uint8_t m){static const uint8_t map[3]={1u,0u,2u};return map[m<3u?m:2u];}
static size_t nh_limb(unsigned fw){return fw==0u?NH_LIMB0:(fw==1u?NH_LIMB1:NH_PULSE);}

static void nh_update(uint8_t*s,unsigned fw,const uint32_t t[4],const pk4_assets*a){
    size_t b=nh_limb(fw);
    nh_common_update(s,0,t,a);                       /* the wrapper's own pass */
    w16(s,b+0xba,r16(s,0xba));
    w16(s,b+0xbe,r16(s,0xbe));
    s[b+4]=0;s[b+5]=(uint8_t)fw;
    if(fw==0u)nh_update_limb0(s,t,a);
    else if(fw==1u)nh_update_limb1(s,t,a);
    else nh_update_pulse(s,t,a);
    w16(s,NH_DELAY_MIX,r16(s,0xbe));
}

static void nh_trigger(uint8_t*s,unsigned fw,uint8_t vel,uint8_t note){
    size_t b=nh_limb(fw);
    s[b+6]=vel?vel:1;
    if(note)s[b+7]=note;
    envelope_trigger(s,b+0x74);
}

/* The firmware sequence: sixteen updates after the targets change, then the
 * trigger plus one more update (validated against the engine-10 captures). */
static void prepare_nh(pk4_control*c,uint8_t*s,const uint8_t raw[4],uint8_t mode,uint8_t vel,uint8_t note,int trig,const pk4_assets*a){
    unsigned i,fw=nh_mode(mode);
    if(control_dirty(c,raw,mode)){
        control_commit(c,raw,mode);
        for(i=0;i<16;i++)nh_update(s,fw,c->targets,a);
    }
    if(trig){nh_trigger(s,fw,vel,note);nh_update(s,fw,c->targets,a);}
}

/* The firmware's RNG object starts at (low=1, high=0) -- recovered by
 * inverting the v1.2.1 generator from the captured continuation state (see
 * tools/verify/perky4_resonant_e2e.cpp, which reproduces a cold start
 * bit-exactly). Starting the port from the same value makes its first block
 * match the unit instead of an arbitrary stream. */
void pk4_init(pk4_engine*e,const pk4_assets*a){unsigned i;uint8_t*z;if(!e)return;z=(uint8_t*)e;for(i=0;i<sizeof(*e);++i)z[i]=0;e->assets=a;for(i=0;i<PK4_TRACK_COUNT;i++){e->tracks[i].rng_low=1u;e->tracks[i].rng_high=0u;e->tracks[i].active_algo=0xff;e->tracks[i].active_mode=0xff;}}
/* Simple Drum: the same common smoother and prepared-word slots as Fold (0x1C/0x20/0x24/0x28), but the firmware's own cadence -- seventeen passes reach the prepared word the engine-3 captures carry (2046 for panel 64, 4092 for panel 127), so a dirty+trig event runs two passes, commits, then fifteen more, and one more update after the trigger. */
static void prepare_sd(pk4_control*c,uint8_t*s,const uint8_t raw[4],uint8_t mode,uint8_t vel,uint8_t note,int trig,const pk4_assets*a){unsigned i;if(control_dirty(c,raw,mode)){common_smooth_only(s,c->targets);common_smooth_only(s,c->targets);control_commit(c,raw,mode);if(trig){for(i=0;i<15;i++)common_smooth_only(s,c->targets);}else{for(i=0;i<14;i++)common_smooth_only(s,c->targets);pk_cf_sd_update(s,mode,a->pitch);}}if(trig){pk_cf_sd_trigger(s,vel,note);pk_cf_sd_update(s,mode,a->pitch);}}
static uint32_t fold2_obj(unsigned track){return 0x20000000u+track*0x10000u;}
int pk4_prepare_event(pk4_engine*e,unsigned tr,uint8_t decay,uint8_t tune,uint8_t p1,uint8_t p2,uint8_t mode,uint8_t algo,uint8_t vel,uint8_t note,int trig){pk4_track*t;uint8_t raw[4];uint8_t bit;if(!e||!e->assets||tr>=PK4_TRACK_COUNT||algo>=PK4_ALGO_COUNT||mode>2)return 0;t=&e->tracks[tr];raw[0]=tune;raw[1]=decay;raw[2]=p1;raw[3]=p2;bit=(uint8_t)(1u<<algo);if(!(t->initialized_mask&bit)){if(algo==PK4_ALGO_FOLD1)fold1_init(t->fold1,mode,vel,note);else if(algo==PK4_ALGO_FOLD2)fold2_init(t->fold2,fold2_obj(tr),mode,vel,note);else if(algo==PK4_ALGO_KARPLUS)karplus_init(t->karplus,mode,vel,note);else if(algo==PK4_ALGO_RESONANT){res_init_snare(t->res_snare,vel,note);res_init_bass(t->res_bass,vel,note);nt_init(t->res_nt,2,0,vel,note,e->assets);}else if(algo==PK4_ALGO_NOISE_HAT){nh_init_limb0(t->nh);nh_init_limb1(t->nh);nh_init_delay(t->nh);nh_init_pulse(t->nh);}else if(algo==PK4_ALGO_SIMPLE_DRUM)pk_cf_sd_init(t->sd,mode,vel,note);else {nt_init(t->nt_m1,0,1,vel,note,e->assets);nt_init(t->nt_shared,1,0,vel,note,e->assets);}t->initialized_mask|=bit;}
if(algo==PK4_ALGO_FOLD1)prepare_fold(&t->fold1_ctl,t->fold1,0,0,raw,mode,vel,note,trig,e->assets);else if(algo==PK4_ALGO_FOLD2)prepare_fold(&t->fold2_ctl,t->fold2,1,fold2_obj(tr),raw,mode,vel,note,trig,e->assets);else if(algo==PK4_ALGO_KARPLUS)prepare_karp(&t->karplus_ctl,t->karplus,raw,mode,vel,note,trig,e->assets);else if(algo==PK4_ALGO_RESONANT){if(mode==0)prepare_res(&t->res_snare_ctl,t->res_snare,0,raw,mode,vel,note,trig,e->assets);else if(mode==1)prepare_res(&t->res_bass_ctl,t->res_bass,1,raw,mode,vel,note,trig,e->assets);else prepare_nt(&t->res_nt_ctl,t->res_nt,0,raw,2,vel,note,trig,e->assets);}else if(algo==PK4_ALGO_NOISE_HAT)prepare_nh(&t->nh_ctl,t->nh,raw,mode,vel,note,trig,e->assets);else if(algo==PK4_ALGO_SIMPLE_DRUM)prepare_sd(&t->sd_ctl,t->sd,raw,mode,vel,note,trig,e->assets);else if(mode==0)prepare_nt(&t->nt_m1_ctl,t->nt_m1,1,raw,mode,vel,note,trig,e->assets);else prepare_nt(&t->nt_shared_ctl,t->nt_shared,0,raw,mode,vel,note,trig,e->assets);t->active_algo=algo;t->active_mode=mode;return 1;}

int pk4_render(pk4_engine*e,unsigned tr,int16_t*d,uint32_t n){pk4_track*t;if(!e||!e->assets||tr>=PK4_TRACK_COUNT||!d)return 0;t=&e->tracks[tr];if(t->active_algo==PK4_ALGO_FOLD1){pk_cf_fold_tables ft;pk_cf_fold_rng r;unsigned i;ft.pitch=e->assets->pitch;ft.envelope1=e->assets->envelope1;ft.envelope2=e->assets->envelope2;for(i=0;i<4;i++)ft.waves[i]=e->assets->waves[i];r.low=t->rng_low;r.high=t->rng_high;if(!pk_cf_fold1_render(t->fold1,d,n,&ft,&r))return 0;t->rng_low=r.low;t->rng_high=r.high;return 1;}if(t->active_algo==PK4_ALGO_FOLD2){pk_cf_fold_tables ft;pk_cf_fold_rng r;unsigned i;ft.pitch=e->assets->pitch;ft.envelope1=e->assets->envelope1;ft.envelope2=e->assets->envelope2;for(i=0;i<4;i++)ft.waves[i]=e->assets->waves[i];r.low=t->rng_low;r.high=t->rng_high;if(!pk_cf_fold2_render(t->fold2,fold2_obj(tr),d,n,&ft,&r))return 0;t->rng_low=r.low;t->rng_high=r.high;return 1;}if(t->active_algo==PK4_ALGO_KARPLUS){pk_cf_karplus_tables kt={e->assets->envelope1,e->assets->envelope2};pk_cf_karplus_rng r={t->rng_low,t->rng_high};if(!pk_cf_karplus_render(t->karplus,d,n,&kt,&r))return 0;t->rng_low=r.low;t->rng_high=r.high;return 1;}if(t->active_algo==PK4_ALGO_RESONANT){pk_cf_res_tables rt;pk_cf_res_rng rr={t->rng_low,t->rng_high};rt.envelope1=e->assets->envelope1;rt.envelope2=e->assets->envelope2;rt.interp_a=e->assets->res_interp_a;rt.interp_b=e->assets->res_interp_b;if(t->active_mode==0){if(!pk_cf_res_snare_render(t->res_snare,d,n,&rt,&rr))return 0;}else if(t->active_mode==1){if(!pk_cf_res_bass_render(t->res_bass,d,n,&rt,&rr))return 0;}else{pk_cf_nt_shared_tables nt;pk_cf_nt_rng nr={t->rng_low,t->rng_high};unsigned i;nt.envelope1=e->assets->envelope1;nt.envelope2=e->assets->envelope2;for(i=0;i<4;i++){nt.waves[i].address=e->assets->waves[i].address;nt.waves[i].table=e->assets->waves[i].table;}if(!pk_cf_nt_shared_render(t->res_nt,d,n,&nt,&nr))return 0;rr.low=nr.low;rr.high=nr.high;}t->rng_low=rr.low;t->rng_high=rr.high;return 1;}if(t->active_algo==PK4_ALGO_NOISE_HAT){pk_cf_nh_tables ht;pk_cf_nh_rng hr={t->rng_low,t->rng_high};unsigned hm=nh_mode(t->active_mode);ht.envelope1=e->assets->envelope1;ht.envelope2=e->assets->envelope2;if(!pk_cf_nh_render(t->nh+(hm==2u?NH_PULSE:0),d,n,hm,&ht,&hr,e->nh_hold))return 0;t->rng_low=hr.low;t->rng_high=hr.high;return 1;}if(t->active_algo==PK4_ALGO_SIMPLE_DRUM){pk_cf_fold_tables ft;unsigned i;ft.pitch=e->assets->pitch;ft.envelope1=e->assets->envelope1;ft.envelope2=e->assets->envelope2;for(i=0;i<4;i++)ft.waves[i]=e->assets->waves[i];if(!pk_cf_sd_render(t->sd,d,n,&ft))return 0;return 1;}if(t->active_algo==PK4_ALGO_NOISE_TONE){if(t->active_mode==0){uint32_t ma=e->assets->m1_wave_address?e->assets->m1_wave_address:PK4_M1_WAVE_DEFAULT;return pk_cf_nt_m1_render(t->nt_m1,d,n,e->assets->m1_wave,ma,e->assets->m1_wave,ma);}else{pk_cf_nt_shared_tables nt;pk_cf_nt_rng r={t->rng_low,t->rng_high};unsigned i;nt.envelope1=e->assets->envelope1;nt.envelope2=e->assets->envelope2;for(i=0;i<4;i++){nt.waves[i].address=e->assets->waves[i].address;nt.waves[i].table=e->assets->waves[i].table;}if(!pk_cf_nt_shared_render(t->nt_shared,d,n,&nt,&r))return 0;t->rng_low=r.low;t->rng_high=r.high;return 1;}}for(uint32_t i=0;i<n;++i)d[i]=0;return 1;}

int pk4_process_segment(pk4_engine*e,unsigned tr,const uint8_t src[6],int event_boundary,int trig,uint8_t vel,uint8_t note,int16_t*d,uint32_t n){
    if(!e||tr>=PK4_TRACK_COUNT||!d||n>16u)return 0;
    if(event_boundary){
        if(!src)return 0;
        if(!pk4_prepare_event(e,tr,src[0],src[1],src[2],src[3],src[4],src[5],vel,note,trig))return 0;
    }
    return pk4_render(e,tr,d,n);
}

/* ⚠️ THE COUNT GOES IN THE HEADER'S LOW BYTE TOO -- d[0] = (count<<8)|count.
 * Measured 10 Oct 2026, and it is what made Perky silent on the unit AND in
 * the port: with the low byte zero the stock chain played NOTHING. It is
 * visible in any stock FLEX record -- T3's header long 4 is 0x00001010 for a
 * 16-sample segment: 16 above, 16 below -- while this encoder wrote only
 * 0x00001000, because its shape was taken from ANALOG BD, which writes a
 * magic word there instead of a stock header.
 * The DSP's own output for the track (the per-track post-FX2 read-back) is
 * zero with 0x00001000 and full audio with 0x00001010; see
 * tools/verify/verify_perky_cf_userpath.py's chain-output check. */
uint32_t pk4_encode_stock_segment(uint32_t*d,const int16_t*m,uint32_t n){uint32_t i;if(!d||!m||n>16u)return 0;d[0]=(n<<8)|n;d[1]=0;d[2]=0x04000000u;d[3]=0;for(i=0;i<n;i++){uint32_t q=(uint32_t)(int32_t)m[i]<<16;d[4+2*i]=q;d[5+2*i]=q;}return 4u+2u*n;}

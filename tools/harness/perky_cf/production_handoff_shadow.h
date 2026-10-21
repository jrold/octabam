extern void pk_prod_pack(volatile uint32_t*,const int32_t*,unsigned);
/* Probe-only nonblocking ownership handoff. The main task advances the same
 * original native body in a private shadow. Publication is one aligned long;
 * an IRQ may interrupt any other worker instruction. Neither consumer waits.
 * CF-owned frames publish post-state, avoiding a duplicate native render.
 */
extern int pk_nhb_inner_renderer(uint8_t*,int16_t*,uint32_t,unsigned,
                                const pk_cf_nh_tables*,pk_cf_nh_rng*,pk_cf_nh_hold);
#include "noise_hat_handoff_clock.h"
#include "noise_hat_handoff_carry.h"
#define NHB_QUEUE 1024u
typedef struct {
    nhr_segment segment;
    uint16_t words[121],side[6],carry_taps[5];
    unsigned apply,trig;
} nhb_half;
typedef struct {nhb_half half[2];pk_cf_native_clock clock;unsigned cf;} nhb_frame;
static nhb_frame nhb_queue[NHB_QUEUE];
static nhb_frame *nhb_building;
volatile uint32_t pk_nhb_produced,pk_nhb_completed;
uint32_t pk_nhb_switches,pk_nhb_deferred,pk_nhb_queue_peak,pk_nhb_imports,pk_nhb_overflows,pk_nhb_clock_errors,pk_nhb_retire_native;
static uint8_t nhb_raw[PK_CF_NH_WRAPPER_BYTES];
static pk_cf_nh_rng nhb_rng={1,0};
static uint16_t nhb_hold[2];
static pk_cf_native_clock nhb_clock;
static unsigned nhb_ready,nhb_dirty,nhb_valid;
uint32_t pk_nhb_cookie=0x4e484243u;
void pk_nhb_reset(void)
{
    pk_nhb_produced=pk_nhb_completed=0;nhb_ready=nhb_dirty=0;nhb_valid=1;
    pk_nhb_switches=pk_nhb_deferred=pk_nhb_queue_peak=pk_nhb_imports=0;
    pk_nhb_overflows=pk_nhb_clock_errors=pk_nhb_retire_native=0;
    nhb_rng.low=1;nhb_rng.high=0;nhb_hold[0]=nhb_hold[1]=0;
    pk_cf_native_reset(&nhb_clock);pk_nhb_owner=1;
    __asm__ volatile("":::"memory");pk_nhb_cookie=0x4e484252u;
}

static void nhb_side(uint16_t *s,const pk4_track*t)
{
    s[0]=placement_engine.nh_hold[0];s[1]=placement_engine.nh_hold[1];
    s[2]=t->rng_low;s[3]=t->rng_low>>16;s[4]=t->rng_high;s[5]=t->rng_high>>16;
}
static void nhb_begin(unsigned cf)
{
    unsigned pending=pk_nhb_produced-pk_nhb_completed;
    if(pending>pk_nhb_queue_peak)pk_nhb_queue_peak=pending;
    if(pending>=NHB_QUEUE){nhb_valid=0;pk_nhb_overflows++;pk_nhr_failures++;nhb_building=0;return;}
    nhb_building=&nhb_queue[pk_nhb_produced&(NHB_QUEUE-1)];nhb_building->cf=cf;
}
static void nhb_capture(nhr_segment*s,const uint16_t*w,unsigned apply,unsigned trig)
{
    if(!nhb_building)return;
    nhb_half*h=&nhb_building->half[apply!=0];h->segment=*s;h->apply=apply;h->trig=trig;
    unsigned first=s->mode==1?81:0,count=s->mode==0?81:s->mode==1?28:59;
    for(unsigned i=first;i<first+count;i++)h->words[i]=w[i];
}
static void nhb_publish(void)
{
    if(!nhb_building)return;
    __asm__ volatile("":::"memory");pk_nhb_produced++;nhb_building=0;
}
/* Main's original idle loop calls this with the interrupted task's ordinary
 * SR. Frame/eDMA IRQs remain enabled, and this function never changes SR.
 */
void pk_nhb_work(void)
{
    if(pk_nhb_cookie!=0x4e484252u||pk_nhb_completed==pk_nhb_produced)return;
    if(!nhb_ready){
        nh_init_limb0(nhb_raw);nh_init_limb1(nhb_raw);nh_init_delay(nhb_raw);nh_init_pulse(nhb_raw);
        nhb_ready=1;
    }
    nhb_frame*f=&nhb_queue[pk_nhb_completed&(NHB_QUEUE-1)];
    for(unsigned j=0;j<2;j++){
        nhb_half*h=&f->half[j];nhr_segment*s=&h->segment;
        if(s->epoch_reset){
            for(unsigned i=0;i<sizeof(nhb_raw);i++)nhb_raw[i]=0;
            nh_init_limb0(nhb_raw);nh_init_limb1(nhb_raw);nh_init_delay(nhb_raw);nh_init_pulse(nhb_raw);
            nhb_rng.low=1;nhb_rng.high=0;nhb_hold[0]=nhb_hold[1]=0;pk_cf_native_reset(&nhb_clock);
        }
        uint8_t*raw=nhb_raw+(s->mode==2?NH_PULSE:0);
        if(f->cf){
            if(!h->apply)continue;
            pk_nha_codec(raw,s->mode,h->words,1);
            nhb_hold[0]=h->side[0];nhb_hold[1]=h->side[1];
            nhb_rng.low=(uint32_t)h->side[2]|((uint32_t)h->side[3]<<16);
            nhb_rng.high=(uint32_t)h->side[4]|((uint32_t)h->side[5]<<16);
            continue;
        }
        if(s->reset)pk_cf_native_reset(&nhb_clock);
        if(!s->need)continue;
        if(h->apply){
            uint16_t w[121];pk_nha_codec(raw,s->mode,w,0);
            const uint8_t*k=s->mode==0?nhr_control0:s->mode==1?nhr_control1:nhr_control2;
            unsigned count=s->mode==0?sizeof(nhr_control0):s->mode==1?sizeof(nhr_control1):sizeof(nhr_control2);
            for(unsigned i=0;i<count;i++)w[k[i]]=h->words[k[i]];
            unsigned env=s->mode==0?2:s->mode==1?82:1;
            if(h->trig){
                w[env]=h->words[env];w[env+7]=h->words[env+7];
                /* All original initializers set this flag, and no control
                 * setter changes it. Capture it explicitly rather than infer
                 * it from an envelope-state value. */
                if(h->trig&2){w[env+5]=h->words[env+5];w[env+6]=h->words[env+6];}
            }
            pk_nha_codec(raw,s->mode,w,1);
        }
        nhb_raw[0xb8]=(uint8_t)s->mute;pk_cf_st16(nhb_raw,0x2dd4,(uint16_t)s->mix);
        int16_t pcm[20];unsigned have=nhb_clock.have;
        if(have)pcm[0]=(int16_t)nhb_clock.carry;
        if(pk_cf_native_needed(&nhb_clock,s->end-s->start)!=s->need){nhb_valid=0;pk_nhr_failures++;pk_nhb_clock_errors++;}
        pk_cf_nh_tables tables={placement_assets.envelope1,placement_assets.envelope2};
        if(!pk_nhb_inner_renderer(raw,pcm+have,s->need,s->mode,&tables,&nhb_rng,nhb_hold))pk_nhr_failures++;
        pk_nhb_advance_clock(&nhb_clock,pcm,s->end-s->start);
        if(nhb_clock.have&&s->mode<2&&!s->mute)nhb_clock.carry=pk_nhb_delay_carry((int16_t)nhb_clock.carry,s->mix,h->carry_taps);
    }
    if(f->cf)nhb_clock=f->clock;
    __asm__ volatile("":::"memory");pk_nhb_completed++;
}
static void nhb_select(void)
{
    if(!pk_nhr_sequence&&!pk_nhb_produced&&!pk_nhr_enabled){pk_nhb_owner=0;return;}
    if((pk_nhr_enabled!=0)==pk_nhb_owner)return;
    if(!nhb_valid||pk_nhr_failures){pk_nhb_deferred++;return;}
    if(pk_nhb_completed!=pk_nhb_produced){pk_nhb_deferred++;return;}
    pk4_track*t=&placement_engine.tracks[3];
    if(pk_nhb_owner){
        uint16_t w[121];
        for(unsigned mode=0;mode<3;mode++){
            pk_nha_codec(nhb_raw+(mode==2?NH_PULSE:0),mode,w,0);
            pk_nha_codec(t->nh+(mode==2?NH_PULSE:0),mode,w,1);
        }
        /* Outstanding DMA writes fill their old positions after takeover.
         * The next CF reads are at least 573 native samples behind the new
         * cursor; normal return latency is three frames. Never wait here.
         */
        if(!pk_nht_taps_ready(nht_issued-nht_committed)){pk_nhr_failures++;return;}
        pk_cf_st16(t->nh,0x2982,nht_ring_index);
        t->rng_low=nhb_rng.low;t->rng_high=nhb_rng.high;
        placement_engine.nh_hold[0]=nhb_hold[0];placement_engine.nh_hold[1]=nhb_hold[1];
        placement_clocks[3]=nhb_clock;pk_nhb_retire_native=0;pk_nhb_owner=0;
    }else{
        if(nhb_dirty||pk_nhr_consumed!=pk_nhr_sequence){pk_nhb_deferred++;return;}
        nhr_schedule_clock=placement_clocks[3];
        nht_ring_index=pk_cf_ld16(t->nh,0x2982);nht_issued=nht_committed;
        pk_nhb_owner=1;
    }
    pk_nhb_switches++;
}
static void nhb_cf_frame(unsigned split,volatile uint32_t*slot)
{
    pk4_track*t=&placement_engine.tracks[3];nhb_begin(1);
    nhb_frame*captured=nhb_building;
    for(unsigned j=0;j<2;j++){
        if(j&&!placement_prepare(3,placement_inputs[3],placement_inputs[3][9]!=0))placement_status=0;
        if(j&&pk_prod_last_reset[3])nhb_dirty|=7;
        unsigned mode=nh_mode(t->active_mode),start=j?split:0,end=j?16:split;
        unsigned need=pk_cf_native_needed(&placement_clocks[3],end-start);
        if(nht_issued==nht_committed)pk_nhb_retire_native=0;
        else if(mode<2&&!t->nh[0xb8]){
            pk_nhb_retire_native+=need;
            if(!pk_nht_taps_ready(nht_issued-nht_committed+pk_nhb_retire_native)){pk_nhr_failures++;placement_status=0;}
        }
        if(!placement_segment(3,start,end,j))placement_status=0;
        if(nhb_building){
            nhb_half*h=&nhb_building->half[j];nhr_segment*s=&h->segment;
            s->epoch_reset=j&&pk_prod_last_reset[3];s->generation=pk_prod_voice_generation[3];s->reset=0;
            s->mode=mode;s->start=start;s->end=end;s->need=need;s->mute=mode<2&&t->nh[0xb8];
            h->apply=end>start||j;
            if(h->apply){pk_nha_codec(t->nh+(mode==2?NH_PULSE:0),mode,h->words,0);nhb_side(h->side,t);}

        }
        if(end>start||j)nhb_dirty|=1u<<mode;
    }
    if(nhb_building)nhb_building->clock=placement_clocks[3];
    nhb_publish();
    pk_prod_pack(slot,placement_output[3],split);
    /* Export frozen inactive limbs first. Cutover is allowed only after all
     * changed limbs have been sent, and old feedback jobs have really drained.
     * Source DMA preserves these imports before the next DSP render packet.
     */
    unsigned active=nh_mode(t->active_mode),mode=active;
    for(unsigned i=0;i<3;i++)if(i!=active&&(nhb_dirty&(1u<<i))){mode=i;break;}
    uint16_t w[121];const uint16_t*words=w;
    if(captured&&captured->half[1].segment.mode==mode)words=captured->half[1].words;
    else if(captured&&captured->half[0].apply&&captured->half[0].segment.mode==mode)words=captured->half[0].words;
    else pk_nha_codec(t->nh+(mode==2?NH_PULSE:0),mode,w,0);
    volatile uint16_t*d=(volatile uint16_t*)slot+80;
    *d++=0x4e43;*d++=mode==2?0x3879:mode==1?0x3851:0x3800;
    unsigned first=mode==1?81:0,count=mode==0?81:mode==1?28:59;
    *d++=count;*d++=placement_clocks[3].phase;*d++=(uint16_t)placement_clocks[3].carry;
    for(unsigned i=0;i<count;i++)*d++=words[first+i];
    if(mode==1){uint16_t side[6];nhb_side(side,t);for(unsigned i=0;i<6;i++)*d++=side[i];}
    nhb_dirty&=~(1u<<mode);pk_nhb_imports++;
}

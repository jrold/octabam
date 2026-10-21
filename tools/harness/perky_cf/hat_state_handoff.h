/* On-demand coherent DSP state handoff. Steady DSP ownership does no CF
 * synthesis. The existing source DMA requests a frozen snapshot, ordinary
 * readback padding returns it, and main catches up only the logged tail.
 * Audio never waits for a snapshot or worker; DSP keeps producing until the
 * fully caught-up CF state is published at a frame boundary.
 */
extern void pk_prod_pack(volatile uint32_t*,const int32_t*,unsigned);
extern int pk_nhb_inner_renderer(uint8_t*,int16_t*,uint32_t,unsigned,
                                const pk_cf_nh_tables*,pk_cf_nh_rng*,pk_cf_nh_hold);
#include "noise_hat_handoff_clock.h"
#include "noise_hat_handoff_carry.h"
#define NHB_QUEUE 1024u
#define NHS_WORDS 190u
enum {NHS_OFF,NHS_ARM,NHS_COLLECT,NHS_READY,NHS_REPLAY};
typedef struct {
    nhr_segment segment;
    uint16_t words[121],side[6],carry_taps[5];
    unsigned apply,trig;
} nhb_half;
typedef struct {
    nhb_half half[2];pk_cf_native_clock clock;
    unsigned cf,sequence,generation;
} nhb_frame;
static nhb_frame nhb_queue[NHB_QUEUE];
static nhb_frame *nhb_building;
volatile uint32_t pk_nhb_produced,pk_nhb_completed;
uint32_t pk_nhb_switches,pk_nhb_deferred,pk_nhb_queue_peak,pk_nhb_imports;
uint32_t pk_nhb_overflows,pk_nhb_clock_errors,pk_nhb_retire_native;
uint32_t pk_nhb_inner_calls,pk_nhb_snapshot_requests,pk_nhb_snapshot_completed;
uint32_t pk_nhb_snapshot_rejected,pk_nhb_snapshot_words,pk_nhb_snapshot_cancelled;
uint32_t pk_nhb_replay_frames,pk_nhb_handoff_jobs;
uint32_t pk_nhb_cancelled_jobs;
static uint8_t nhb_raw[PK_CF_NH_WRAPPER_BYTES];
static pk_cf_nh_rng nhb_rng;
static uint16_t nhb_hold[2];
static pk_cf_native_clock nhb_clock;
static unsigned nhb_dirty,nhb_valid;
uint32_t nhs_transport_started;
static volatile unsigned nhs_state,nhs_epoch,nhs_log_end,nhs_worker_sequence;
static volatile unsigned nhs_imported_epoch;
static unsigned nhs_request_sequence,nhs_generation,nhs_received;
static uint16_t nhs_snapshot[NHS_WORDS];
uint32_t pk_nhb_cookie=0x4e484243u;

/* Cancellation retires pending work, but does not touch main's private raw
 * state or completion count. Main owns completion and retires cancelled work
 * before IRQ may arm another request. Thus a cancellation after main's epoch
 * check cannot resurrect state or complete a job from a newer request.
 */
static void nhb_cancel(unsigned count)
{
    if(count&&nhs_state!=NHS_OFF)pk_nhb_snapshot_cancelled++;
    nhs_epoch++;nhs_state=NHS_OFF;nhs_received=0;nhb_building=0;
    __asm__ volatile("":::"memory");
}
void pk_nhb_reset(void)
{
    pk_nhb_produced=pk_nhb_completed=0;pk_budget_cache_clear();
    nhs_epoch=1;nhs_state=NHS_OFF;nhs_received=0;nhb_dirty=0;nhb_valid=1;
    nhs_transport_started=0;
    pk_nhb_switches=pk_nhb_deferred=pk_nhb_queue_peak=pk_nhb_imports=0;
    pk_nhb_overflows=pk_nhb_clock_errors=pk_nhb_retire_native=0;
    pk_nhb_inner_calls=pk_nhb_snapshot_requests=pk_nhb_snapshot_completed=0;
    pk_nhb_snapshot_rejected=pk_nhb_snapshot_words=pk_nhb_snapshot_cancelled=0;
    pk_nhb_replay_frames=pk_nhb_handoff_jobs=0;
    pk_nhb_cancelled_jobs=0;nhs_imported_epoch=0;
    nhb_building=0;pk_nhb_owner=1;
    __asm__ volatile("":::"memory");pk_nhb_cookie=0x4e484252u;
}
static void nhb_side(uint16_t*s,const pk4_track*t)
{
    s[0]=placement_engine.nh_hold[0];s[1]=placement_engine.nh_hold[1];
    s[2]=t->rng_low;s[3]=t->rng_low>>16;s[4]=t->rng_high;s[5]=t->rng_high>>16;
}
static unsigned nhb_request_flag(unsigned half)
{return half&&nhs_state==NHS_ARM?1u<<11:0;}
static void nhb_begin(unsigned cf)
{
    nhb_building=0;
    if(cf){nhb_building=&nhb_queue[0];nhb_building->cf=1;return;}
    if(nhs_state<NHS_COLLECT)return;
    unsigned next=pk_nhr_sequence+1;
    unsigned oldest=nhs_state==NHS_COLLECT||nhs_imported_epoch!=nhs_epoch?
                    nhs_request_sequence+1:nhs_worker_sequence;
    unsigned pending=next-oldest;
    if(pending>pk_nhb_queue_peak)pk_nhb_queue_peak=pending;
    if(pending>=NHB_QUEUE){
        nhb_valid=0;pk_nhb_overflows++;pk_nhr_failures++;nhb_cancel(1);return;
    }
    nhb_building=&nhb_queue[next&(NHB_QUEUE-1)];
    nhb_building->cf=0;nhb_building->sequence=next;
    nhb_building->generation=nhs_generation;
}
static void nhb_capture(nhr_segment*s,const uint16_t*w,unsigned apply,unsigned trig)
{
    if(!nhb_building)return;
    nhb_half*h=&nhb_building->half[apply!=0];
    h->segment=*s;h->apply=apply;h->trig=trig;
    if(apply){
        const uint8_t*k=s->mode==0?nhr_control0:s->mode==1?nhr_control1:nhr_control2;
        unsigned count=s->mode==0?sizeof(nhr_control0):s->mode==1?sizeof(nhr_control1):sizeof(nhr_control2);
        for(unsigned i=0;i<count;i++)h->words[k[i]]=w[k[i]];
        unsigned env=s->mode==0?2:s->mode==1?82:1;
        h->words[env]=w[env];h->words[env+7]=w[env+7];
        if(trig&2){h->words[env+5]=w[env+5];h->words[env+6]=w[env+6];}
    }
}
static void nhb_publish(void)
{
    if(!pk_nhb_owner){nhb_building=0;return;}
    if(nhs_state==NHS_ARM){
        nhs_request_sequence=pk_nhr_sequence;
        nhs_generation=pk_prod_voice_generation[3];
        nhs_log_end=pk_nhr_sequence;nhs_received=0;
        pk_nhb_snapshot_requests++;nhs_state=NHS_COLLECT;
    }else if(nhs_state>=NHS_COLLECT){
        if(pk_prod_voice_generation[3]!=nhs_generation||
           (nhb_building&&nhb_building->half[1].segment.epoch_reset)){
            nhb_cancel(1);pk_nhb_deferred++;
        }else if(nhb_building){
            nhs_log_end=pk_nhr_sequence;
            __asm__ volatile("":::"memory");
            if(nhs_state>=NHS_READY)pk_nhb_produced++;
        }
    }
    nhb_building=0;
}
/* Called once per unique normal return, inside the existing frame ISR.
 * In-order DMA makes the request sequence in offset zero sufficient to reject
 * cancelled streams: their already-issued fragments precede the new offset0.
 */
static void nhb_snapshot_receive(unsigned total)
{
    if(nhs_state!=NHS_COLLECT||!(pk_nhr_mail[3]&0x8000u))return;
    unsigned offset=pk_nhr_mail[3]&0x7fffu;
    if(total>20||offset>=NHS_WORDS||offset!=nhs_received){pk_nhb_snapshot_rejected++;return;}
    unsigned count=20-total;if(count>NHS_WORDS-offset)count=NHS_WORDS-offset;
    if(!count)return;
    if(!offset&&pk_nhr_mail[4+total]!=(nhs_request_sequence&65535u)){
        pk_nhb_snapshot_rejected++;return;
    }
    for(unsigned i=0;i<count;i++)nhs_snapshot[offset+i]=pk_nhr_mail[4+total+i];
    nhs_received+=count;pk_nhb_snapshot_words+=count;
    if(nhs_received!=NHS_WORDS)return;
    if(pk_prod_voice_generation[3]!=nhs_generation){nhb_cancel(1);return;}
    pk_nhb_snapshot_completed++;
    __asm__ volatile("":::"memory");nhs_state=NHS_READY;
    /* Import plus every logged frame is real main work. While receiving the
     * snapshot there was no work published and no idle-loop busy polling. */
    pk_nhb_produced+=1+nhs_log_end-nhs_request_sequence;
}
void pk_nhb_work(void)
{
    if(pk_nhb_cookie!=0x4e484252u||pk_nhb_completed==pk_nhb_produced)return;
    if(nhs_state==NHS_OFF){
        pk_nhb_cancelled_jobs+=pk_nhb_produced-pk_nhb_completed;
        __asm__ volatile("":::"memory");pk_nhb_completed=pk_nhb_produced;return;
    }
    unsigned epoch=nhs_epoch;
    if(nhs_state==NHS_READY&&nhs_imported_epoch!=epoch){
        /* The existing full codec covers every read made by the inner body.
         * Its unused delay ring is neither cleared nor duplicated here. */
        pk_nha_codec(nhb_raw,0,nhs_snapshot+1,1);
        pk_nha_codec(nhb_raw,1,nhs_snapshot+1,1);
        pk_nha_codec(nhb_raw+NH_PULSE,2,nhs_snapshot+122,1);
        nhb_hold[0]=nhs_snapshot[181];nhb_hold[1]=nhs_snapshot[182];
        nhb_rng.low=(uint32_t)nhs_snapshot[183]|((uint32_t)nhs_snapshot[184]<<16);
        nhb_rng.high=(uint32_t)nhs_snapshot[185]|((uint32_t)nhs_snapshot[186]<<16);
        nhb_clock.phase=nhs_snapshot[187];nhb_clock.have=nhs_snapshot[188];
        nhb_clock.carry=(int16_t)nhs_snapshot[189];
        if(nhs_epoch!=epoch)return;
        nhs_worker_sequence=nhs_request_sequence+1;
        nhs_imported_epoch=epoch;pk_nhb_handoff_jobs++;
        __asm__ volatile("":::"memory");pk_nhb_completed++;return;
    }
    if(nhs_state!=NHS_READY)return;
    unsigned sequence=nhs_worker_sequence;
    nhb_frame*f=&nhb_queue[sequence&(NHB_QUEUE-1)];
    if(f->sequence!=sequence||f->generation!=nhs_generation){
        if(nhs_epoch==epoch){pk_nhr_failures++;nhb_valid=0;nhb_cancel(1);}return;
    }
    for(unsigned j=0;j<2;j++){
        nhb_half*h=&f->half[j];nhr_segment*s=&h->segment;
        nhb_hold[0]=h->side[0];nhb_hold[1]=h->side[1];
        nhb_rng.low=(uint32_t)h->side[2]|((uint32_t)h->side[3]<<16);
        nhb_rng.high=(uint32_t)h->side[4]|((uint32_t)h->side[5]<<16);
        if(s->external)continue;
        if(s->reset)pk_cf_native_reset(&nhb_clock);
        if(h->apply)pk_budget_controls_write(nhb_raw,s->mode,h->words,h->trig);
        nhb_raw[0xb8]=(uint8_t)s->mute;pk_cf_st16(nhb_raw,0x2dd4,(uint16_t)s->mix);
        if(!s->need)continue;
        int16_t pcm[20];unsigned have=nhb_clock.have;
        if(have)pcm[0]=(int16_t)nhb_clock.carry;
        if(pk_cf_native_needed(&nhb_clock,s->end-s->start)!=s->need){
            if(nhs_epoch==epoch){nhb_valid=0;pk_nhr_failures++;pk_nhb_clock_errors++;nhb_cancel(1);}return;
        }
        pk_cf_nh_tables tables={placement_assets.envelope1,placement_assets.envelope2};
        pk_nhb_inner_calls++;
        if(!pk_nhb_inner_renderer(nhb_raw+(s->mode==2?NH_PULSE:0),pcm+have,s->need,
                                s->mode,&tables,&nhb_rng,nhb_hold)){
            if(nhs_epoch==epoch){pk_nhr_failures++;nhb_valid=0;nhb_cancel(1);}return;
        }
        pk_nhb_advance_clock(&nhb_clock,pcm,s->end-s->start);
        if(nhb_clock.have&&s->mode<2&&!s->mute)
            nhb_clock.carry=pk_nhb_delay_carry((int16_t)nhb_clock.carry,s->mix,h->carry_taps);
    }
    if(nhs_epoch!=epoch)return;
    nhs_worker_sequence=sequence+1;pk_nhb_replay_frames++;pk_nhb_handoff_jobs++;
    __asm__ volatile("":::"memory");pk_nhb_completed++;
}
static void nhb_select(void)
{
    /* Sequence zero recurs after a full transport wrap. Only the explicit
     * boot latch may select CF without first importing the DSP history. */
    if(!nhs_transport_started&&!pk_nhr_enabled){pk_nhb_owner=0;return;}
    if((pk_nhr_enabled!=0)==pk_nhb_owner){
        if(nhs_state!=NHS_OFF)nhb_cancel(1);
        return;
    }
    if(placement_engine.tracks[3].active_algo!=PK4_ALGO_NOISE_HAT)return;
    if(!nhb_valid||pk_nhr_failures){pk_nhb_deferred++;return;}
    pk4_track*t=&placement_engine.tracks[3];
    if(pk_nhb_owner){
        if(nhs_state==NHS_OFF){
            if(pk_nhb_completed==pk_nhb_produced){nhs_epoch++;nhs_state=NHS_ARM;}
            pk_nhb_deferred++;return;
        }
        if(nhs_state!=NHS_READY||nhs_imported_epoch!=nhs_epoch||pk_nhb_completed!=pk_nhb_produced||
           nhs_worker_sequence!=pk_nhr_sequence+1||nhs_generation!=pk_prod_voice_generation[3]){
            pk_nhb_deferred++;return;
        }
        uint16_t w[121];
        for(unsigned mode=0;mode<3;mode++){
            pk_nha_codec(nhb_raw+(mode==2?NH_PULSE:0),mode,w,0);
            pk_nha_codec(t->nh+(mode==2?NH_PULSE:0),mode,w,1);
        }
        if(!pk_nht_taps_ready(nht_issued-nht_committed)){pk_nhr_failures++;return;}
        pk_cf_st16(t->nh,0x2982,nht_ring_index);
        t->rng_low=nhb_rng.low;t->rng_high=nhb_rng.high;
        placement_engine.nh_hold[0]=nhb_hold[0];placement_engine.nh_hold[1]=nhb_hold[1];
        placement_clocks[3].phase=nhb_clock.phase;
        placement_clocks[3].have=nhb_clock.have;
        placement_clocks[3].carry=nhb_clock.carry;
        pk_nhb_retire_native=0;pk_nhb_owner=0;
        nhb_cancel(0);
    }else{
        if(nhb_dirty||pk_nhr_consumed!=pk_nhr_sequence){pk_nhb_deferred++;return;}
        nhr_schedule_clock.phase=placement_clocks[3].phase;
        nhr_schedule_clock.have=placement_clocks[3].have;
        nhr_schedule_clock.carry=placement_clocks[3].carry;
        nht_ring_index=pk_cf_ld16(t->nh,0x2982);nht_issued=nht_committed;
        pk_budget_cache_clear();pk_nhb_owner=1;
    }
    pk_nhb_switches++;
}

"""Leaner exported pk_render with the PKFM22 merged-segment dispatcher's semantics.

Same calls, in the same order and with the same arguments: the stock
fallbacks, placement_prepare, placement_segment, pk_nhr_frame,
pk_prod_clear and pk_prod_pack (the frozen oracle and production witnesses
observe prepare, segment and the V4 frame). Same profiler timer reads.
What changes is only how the dispatcher reaches them:
  - the track-to-voice map is a table instead of a branch chain;
  - one read of the bank pointer and Part index serves the signature check
    and the generation observation (the ISR does not change them in between);
  - the production generation store, the voice-engine family map and the
    boundary predicate are inlined (identical expressions).
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UNITS = ()

START = 'int pk_hybrid_render(unsigned track, unsigned ping, unsigned start, unsigned end)\n    __asm__("pk_render");\n'
END_MARK = '    return 0;\n}\n'

LEAN = r'''/* PKFM27: lean exported dispatcher, PKFM22 merged-segment semantics. */
#include <stddef.h>
extern pk4_engine placement_engine;
extern uint32_t pk_prod_generation,pk_prod_voice_generation[4];
static const uint8_t pk_lean_voice[8]={0u,1u,4u,4u,2u,3u,4u,4u};
static const uint8_t pk_lean_family[4][3]={{0u,9u,6u},{1u,9u,7u},{4u,8u,2u},{5u,3u,10u}};
static const unsigned pk_lean_controls[10]={
    offsetof(pk4_track,fold1_ctl),offsetof(pk4_track,fold2_ctl),
    offsetof(pk4_track,karplus_ctl),offsetof(pk4_track,nt_shared_ctl),
    offsetof(pk4_track,res_snare_ctl),offsetof(pk4_track,nh_ctl),
    offsetof(pk4_track,sd_ctl),offsetof(pk4_track,cd_ctl),
    offsetof(pk4_track,slap_ctl),offsetof(pk4_track,wt_ctl)};
/* placement_boundary_noop(), inlined: same conditions in the same terms. */
static inline int pk_lean_noop(unsigned tr,const uint32_t *input,int trig)
{
    uint8_t algo=(uint8_t)input[0],mode=(uint8_t)input[1];
    if(trig||algo>9||mode>2||tr>2||!placement_engine.assets||placement_trace_enabled)return 0;
    const pk4_track*t=&placement_engine.tracks[tr];
    if(pk_prod_voice_generation[tr]!=pk_prod_generation||!(t->initialized_mask&(1u<<algo)))return 0;
    if(t->active_algo!=algo||t->active_mode!=mode)return 0;
    const pk4_control*c=(const pk4_control*)((const uint8_t*)t+pk_lean_controls[algo]);
    if(algo==PK4_ALGO_NOISE_TONE&&!mode)c=&t->nt_m1_ctl;
    return c->valid&&c->last_mode==mode&&c->last_raw[0]==(uint8_t)input[3]&&
           c->last_raw[1]==(uint8_t)input[2]&&c->last_raw[2]==(uint8_t)input[4]&&
           c->last_raw[3]==(uint8_t)input[5];
}
int pk_hybrid_render(unsigned track, unsigned ping, unsigned start, unsigned end)
    __asm__("pk_render");
int pk_hybrid_render(unsigned track, unsigned ping, unsigned start, unsigned end)
{
    typedef int (*stock_render)(unsigned,unsigned,unsigned,unsigned);
    unsigned voice=track<8u?pk_lean_voice[track]:4u;
    if(voice==4u)return ((stock_render)0x40004008u)(track,ping,start,end);
    const uint32_t bank=U32(BANK);const uint8_t part_index=(uint8_t)(U8(PART_IDX)&3u);
    {
        const volatile uint8_t *part=(const volatile uint8_t *)(uintptr_t)(bank+PART_OFF+part_index*PART_STRIDE);
        const volatile uint8_t *signature=part+SIG+30u*track;
        if(part[0x22u+track]!=1u||signature[0]!='P'||signature[1]!='K'||signature[2]!=2u)
            return ((stock_render)0x40004008u)(track,ping,start,end);
    }
    if(!(placement_mask&(1u<<voice))) {
        if(track==0u||track==4u)return pk_render(track,ping,start,end);
        return ((stock_render)0x40004008u)(track,ping,start,end);
    }
    if(end<start||end>16u) {
        /* Never drop a deferred prefix on an invalid continuation. */
        if(voice!=3u&&placement_deferred[voice]-1u<15u) {
            unsigned prefix=placement_deferred[voice];placement_deferred[voice]=~0u;
            if(!placement_segment(voice,0u,prefix,0u))placement_status=0;
        }
        return 0;
    }
    if(pk_hybrid_bank!=bank||pk_hybrid_part!=part_index) {
        pk_hybrid_bank=bank;pk_hybrid_part=part_index;
        ++pk_hybrid_generation;pk_hybrid_prof.handoff_generation=pk_hybrid_generation;
    }
    pk_prod_generation=pk_hybrid_generation;
    const uint32_t profile=pk_hybrid_profiler_enable;
    uint32_t begin=profile?pk_hybrid_timer_now():0u;
    if((U8(0x46104d0cu+track)&16u)!=0u)placement_trigger[voice]=1u;
    unsigned deferred=0u,merged=0u;
    if(voice!=3u){deferred=placement_deferred[voice];placement_deferred[voice]=~0u;if(deferred-1u>=15u)deferred=0u;}
    if(end==16u) {
        volatile uint16_t *fp=(volatile uint16_t *)(uintptr_t)U32(0x800062a8u);
        uint32_t *p=placement_inputs[voice];
        unsigned local=(uint8_t)(fp[ALGO_SLOT]>>8),mode=(uint8_t)(fp[MODE_SLOT_FINAL]>>8);
        p[0]=pk_lean_family[voice][local>2u?2u:local];
        p[1]=mode>2u?2u:mode;
        p[2]=(uint8_t)(fp[DECAY_SLOT]>>8);p[3]=(uint8_t)(fp[TUNE_SLOT]>>8);
        p[4]=(uint8_t)(fp[PARAM1_SLOT]>>8);p[5]=(uint8_t)(fp[PARAM2_SLOT]>>8);
        p[6]=255u;p[7]=45u;p[8]=start;p[9]=placement_trigger[voice];
        if(voice!=3u) {
            if(deferred&&deferred==start&&pk_lean_noop(voice,p,p[9]!=0))merged=1u;
            else if(deferred&&!placement_segment(voice,0u,deferred,0u))placement_status=0;
            if(!placement_prepare(voice,p,p[9]!=0))placement_status=0;
        }
    } else if(deferred&&!placement_segment(voice,0u,deferred,0u))placement_status=0;
    if(voice!=3u) {
        if(merged){if(!placement_segment(voice,0u,16u,0u))placement_status=0;}
        else if(end<16u&&!start&&end&&!placement_trace_enabled)placement_deferred[voice]=end;
        else if(!placement_segment(voice,start,end,start?1u:0u))placement_status=0;
    }
    {
        uint32_t n=end-start,words=4u+2u*n;
        volatile uint32_t *cursor=(volatile uint32_t *)(uintptr_t)U32(0x80001c80u);
        U32(0x80001c80u)=(uint32_t)(uintptr_t)pk_prod_clear(cursor,words);
    }
    if(end==16u) {
        if(voice==3u)pk_nhr_frame(start,pk_hybrid_fixed_slot(track,ping));
        else pk_prod_pack(pk_hybrid_fixed_slot(track,ping),placement_output[voice],start);
        placement_calls[voice]++;placement_trigger[voice]=0;
    }
    if(pk_hybrid_profiler_enable) {
        pk_hybrid_cur_cf_ticks+=pk_hybrid_timer_now()-begin;
        pk_hybrid_cur_voice_mask|=1u<<track;pk_hybrid_cur_has_data=1u;
    }
    return 0;
}
'''


def transform(work, source_path):
    text = Path(source_path).read_text()
    assert text.count(START) == 1, 'lean dispatcher anchor changed'
    begin = text.index(START)
    end = text.index(END_MARK, begin) + len(END_MARK)
    old = text[begin:end]
    for required in ('placement_boundary_noop(voice,p,p[9]!=0)', 'pk_nhr_frame(start,pk_hybrid_fixed_slot(track,ping))',
                     'placement_production_observe(pk_hybrid_generation);', 'pk_hybrid_observe_generation();'):
        assert required in old, ('unexpected dispatcher body', required)
    text = text[:begin] + LEAN + text[end:]
    target = Path(work) / 'placement-control-lean.c'
    target.write_text(text)
    return target

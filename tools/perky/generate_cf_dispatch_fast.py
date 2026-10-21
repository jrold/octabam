"""Direct V1-V3 source dispatch for the common deferred and merged frame.

PKFM22 routes every PERKY source call through the general dispatcher, the
boundary predicate, the full prepare, production event, segment and engine
dispatch functions. In sustained playback the frame is almost always a
deferred prefix followed by a merged continuation.

This layer exports a new pk_render that handles exactly those two calls for
V1-V3 and otherwise tail-calls the unchanged general dispatcher. Before any
fallback it has only run idempotent steps: the generation observation, the
production generation store, the trigger latch and the input refresh. The
general dispatcher repeats them with the same result.

The merged continuation still calls placement_prepare and
placement_segment(voice, 0, 16, 0): the frozen full-map oracle and the
production witnesses step at those entries (and placement_production_event),
so they are measurement seams. Profiler timer reads keep their original count;
the continuation's begin read follows the idempotent input refresh.
"""
from pathlib import Path

PLACEMENT = '''
/* PKFM23: the merged continuation is eligible exactly when the PKFM22
 * boundary predicate holds. Pure check; touches no state. */
int __attribute__((noinline)) placement_merge_eligible(unsigned tr,const uint32_t *input)
{
    return placement_boundary_noop(tr,input,input[9]!=0);
}
'''

CONTROL_DECLARATIONS = '''extern int placement_merge_eligible(unsigned,const uint32_t*);
extern uint32_t pk_prod_generation;
'''

GENERAL_HEAD = '''int pk_hybrid_render(unsigned track, unsigned ping, unsigned start, unsigned end)
    __asm__("pk_render");
int pk_hybrid_render(unsigned track, unsigned ping, unsigned start, unsigned end)
{'''
GENERAL_RENAMED = '''static int __attribute__((noinline))
pk_hybrid_render_general(unsigned track, unsigned ping, unsigned start, unsigned end)
{'''

FAST = '''
/* PKFM23 exported dispatcher: V1-V3 deferred prefix and merged continuation
 * directly; every other call is the unchanged general dispatcher. */
int pk_hybrid_render_fast(unsigned track, unsigned ping, unsigned start, unsigned end)
    __asm__("pk_render");
int pk_hybrid_render_fast(unsigned track, unsigned ping, unsigned start, unsigned end)
{
    unsigned voice=track==0u?0u:track==1u?1u:track==4u?2u:3u;
    if(voice==3u||end>16u||end<start||placement_trace_enabled||!(placement_mask&(1u<<voice))
       ||!signed_track(part_base(),track))
        return pk_hybrid_render_general(track,ping,start,end);
    pk_hybrid_observe_generation();
    pk_prod_generation=pk_hybrid_generation;
    if(end<16u) {
        if(start||!end||placement_deferred[voice]-1u<15u)
            return pk_hybrid_render_general(track,ping,start,end);
    } else if(placement_deferred[voice]!=start||start-1u>=15u)
        return pk_hybrid_render_general(track,ping,start,end);
    uint32_t begin;
    if(end<16u) {
        begin=pk_hybrid_profiler_enable?pk_hybrid_timer_now():0u;
        if((U8(0x46104d0cu+track)&16u)!=0u)placement_trigger[voice]=1u;
        placement_deferred[voice]=end;
    } else {
        /* Latch and refresh are idempotent; the general path repeats them. */
        if((U8(0x46104d0cu+track)&16u)!=0u)placement_trigger[voice]=1u;
        volatile uint16_t *fp=(volatile uint16_t *)(uintptr_t)U32(0x800062a8u);
        uint32_t *p=placement_inputs[voice];
        p[0]=fm_voice_engine(voice,(uint8_t)(fp[ALGO_SLOT]>>8));
        p[1]=(uint8_t)(fp[MODE_SLOT_FINAL]>>8);if(p[1]>2)p[1]=2;
        p[2]=(uint8_t)(fp[DECAY_SLOT]>>8);p[3]=(uint8_t)(fp[TUNE_SLOT]>>8);
        p[4]=(uint8_t)(fp[PARAM1_SLOT]>>8);p[5]=(uint8_t)(fp[PARAM2_SLOT]>>8);
        p[6]=255u;p[7]=45u;p[8]=start;p[9]=placement_trigger[voice];
        if(!placement_merge_eligible(voice,p))return pk_hybrid_render_general(track,ping,start,end);
        begin=pk_hybrid_profiler_enable?pk_hybrid_timer_now():0u;
        placement_deferred[voice]=~0u;
        /* Observable seams: the frozen oracle steps at these entries. */
        if(!placement_prepare(voice,p,p[9]!=0))placement_status=0;
        if(!placement_segment(voice,0u,16u,0u))placement_status=0;
    }
    uint32_t n=end-start,words=4u+2u*n;
    volatile uint32_t *cursor=(volatile uint32_t *)(uintptr_t)U32(0x80001c80u);
    U32(0x80001c80u)=(uint32_t)(uintptr_t)pk_prod_clear(cursor,words);
    if(end==16u) {
        pk_prod_pack(pk_hybrid_fixed_slot(track,ping),placement_output[voice],start);
        placement_calls[voice]++;placement_trigger[voice]=0;
    }
    if(pk_hybrid_profiler_enable) {
        pk_hybrid_cur_cf_ticks+=pk_hybrid_timer_now()-begin;
        pk_hybrid_cur_voice_mask|=1u<<track;pk_hybrid_cur_has_data=1u;
    }
    return 0;
}
'''


def once(text, old, new):
    assert text.count(old) == 1, ('Dispatch fast-path anchor changed', old[:80])
    return text.replace(old, new, 1)


def transform_placement(work, source_path):
    text = Path(source_path).read_text()
    marker = 'static void __attribute__((noinline)) placement_trace_empty(unsigned tr,unsigned half)\n'
    text = once(text, marker, PLACEMENT.lstrip('\n') + '\n' + marker)
    target = Path(work) / 'placement-dispatch-fast.c'
    target.write_text(text)
    return target


def transform_control(work, source_path):
    text = Path(source_path).read_text()
    marker = 'extern int placement_boundary_noop(unsigned,const uint32_t*,int);\n'
    text = once(text, marker, marker + CONTROL_DECLARATIONS)
    text = once(text, GENERAL_HEAD, GENERAL_RENAMED)
    text = text.rstrip('\n') + '\n' + FAST
    target = Path(work) / 'placement-control-dispatch.c'
    target.write_text(text)
    return target

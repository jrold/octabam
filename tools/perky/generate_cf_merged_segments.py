"""Render a CF voice's whole frame in one segment when its event boundary is a no-op.

The stock source loop calls each PERKY track twice per frame, (0, split) and
(split, 16), with only the stock per-track event routine in between. PKFM21
renders native samples in both calls and runs the control prepare between
them. In sustained playback the prepare almost always takes its
unchanged-control path, so the boundary changes nothing that rendering reads.

This layer defers the first segment of V1-V3 to the second call. There, if
the boundary is provably a rendering no-op, it runs the same prepare and then
one 0..16 segment. Otherwise it renders the deferred segment first and keeps
the original order exactly. The native clock adapter and every renderer
preserve an arbitrary block-length contract, so one segment produces the
same native samples, PCM, state and RNG as two.

V4 is not merged: its external CF halves publish per-half RNG/hold side words
to DSP-A. Diagnostic tracing also keeps the original two-segment path.
"""
from pathlib import Path

PREDICATE = '''
/* PKFM22: the event boundary is a rendering no-op exactly when the
 * unchanged-control prepare returns without a production reset, pristine
 * restore, trigger, algorithm or mode change, or control update. */
/* Loaded data, not BSS: all-ones means no deferred prefix; only 1..15 is one. */
uint32_t placement_deferred[4]={~0u,~0u,~0u,~0u};
int __attribute__((noinline)) placement_boundary_noop(unsigned tr,const uint32_t *input,int trig)
{
    uint8_t algo=(uint8_t)input[0],mode=(uint8_t)input[1];
    if(trig||algo>9||mode>2||tr>2||!placement_engine.assets||placement_trace_enabled)return 0;
    const pk4_track*t=&placement_engine.tracks[tr];
    if(pk_prod_voice_generation[tr]!=pk_prod_generation||!(t->initialized_mask&(1u<<algo)))return 0;
    if(t->active_algo!=algo||t->active_mode!=mode)return 0;
    static const unsigned offsets[10]={
        offsetof(pk4_track,fold1_ctl),offsetof(pk4_track,fold2_ctl),
        offsetof(pk4_track,karplus_ctl),offsetof(pk4_track,nt_shared_ctl),
        offsetof(pk4_track,res_snare_ctl),offsetof(pk4_track,nh_ctl),
        offsetof(pk4_track,sd_ctl),offsetof(pk4_track,cd_ctl),
        offsetof(pk4_track,slap_ctl),offsetof(pk4_track,wt_ctl)};
    const pk4_control*c=(const pk4_control*)((const uint8_t*)t+offsets[algo]);
    if(algo==PK4_ALGO_NOISE_TONE&&!mode)c=&t->nt_m1_ctl;
    return c->valid&&c->last_mode==mode&&c->last_raw[0]==(uint8_t)input[3]&&
           c->last_raw[1]==(uint8_t)input[2]&&c->last_raw[2]==(uint8_t)input[4]&&
           c->last_raw[3]==(uint8_t)input[5];
}
'''

CONTROL_DECLARATIONS = '''extern uint32_t placement_deferred[4],placement_trace_enabled;
extern int placement_boundary_noop(unsigned,const uint32_t*,int);
'''

ORIGINAL_DISPATCH = '''    if(end<start||end>16u)return 0;
'''
MERGED_DISPATCH = '''    if(end<start||end>16u) {
        /* Never drop a deferred prefix on an invalid continuation. */
        if(voice!=3u&&placement_deferred[voice]-1u<15u) {
            unsigned prefix=placement_deferred[voice];placement_deferred[voice]=~0u;
            if(!placement_segment(voice,0u,prefix,0u))placement_status=0;
        }
        return 0;
    }
'''

ORIGINAL_SEGMENTS = '''        p[6]=255u;p[7]=45u;p[8]=start;p[9]=placement_trigger[voice];
        if(voice!=3u&&!placement_prepare(voice,p,p[9]!=0))placement_status=0;
    }
    if(voice!=3u&&!placement_segment(voice,start,end,start?1u:0u))placement_status=0;
'''
MERGED_SEGMENTS = '''        p[6]=255u;p[7]=45u;p[8]=start;p[9]=placement_trigger[voice];
        if(voice!=3u) {
            if(deferred&&deferred==start&&placement_boundary_noop(voice,p,p[9]!=0))merged=1u;
            else if(deferred&&!placement_segment(voice,0u,deferred,0u))placement_status=0;
            if(!placement_prepare(voice,p,p[9]!=0))placement_status=0;
        }
    } else if(deferred&&!placement_segment(voice,0u,deferred,0u))placement_status=0;
    if(voice!=3u) {
        if(merged){if(!placement_segment(voice,0u,16u,0u))placement_status=0;}
        else if(end<16u&&!start&&end&&!placement_trace_enabled)placement_deferred[voice]=end;
        else if(!placement_segment(voice,start,end,start?1u:0u))placement_status=0;
    }
'''
ORIGINAL_HEAD = '''    if(end==16u) {
        volatile uint16_t *fp=(volatile uint16_t *)(uintptr_t)U32(0x800062a8u);'''
MERGED_HEAD = '''    unsigned deferred=0u,merged=0u;
    if(voice!=3u){deferred=placement_deferred[voice];placement_deferred[voice]=~0u;if(deferred-1u>=15u)deferred=0u;}
    if(end==16u) {
        volatile uint16_t *fp=(volatile uint16_t *)(uintptr_t)U32(0x800062a8u);'''


def once(text, old, new):
    assert text.count(old) == 1, ('Merged-segment transform anchor changed', old[:80])
    return text.replace(old, new, 1)


def transform_placement(work, source_path):
    text = Path(source_path).read_text()
    marker = 'static void __attribute__((noinline)) placement_trace_empty(unsigned tr,unsigned half)\n'
    text = once(text, marker, PREDICATE.lstrip('\n') + '\n' + marker)
    target = Path(work) / 'placement-merged-segments.c'
    target.write_text(text)
    return target


def transform_control(work, source_path):
    text = Path(source_path).read_text()
    marker = 'extern void placement_production_observe(unsigned);\n'
    text = once(text, marker, marker + CONTROL_DECLARATIONS)
    start = text.index('int pk_hybrid_render(unsigned track, unsigned ping, unsigned start, unsigned end)\n{')
    head, body = text[:start], text[start:]
    body = once(body, ORIGINAL_DISPATCH, MERGED_DISPATCH)
    body = once(body, ORIGINAL_HEAD, MERGED_HEAD)
    body = once(body, ORIGINAL_SEGMENTS, MERGED_SEGMENTS)
    target = Path(work) / 'placement-control-merged.c'
    target.write_text(head + body)
    return target

"""Merged V4 Noise/Tone frame with byte-identical DSP-A packets.

V4's external CF source is rendered and packed in two halves inside
pk_nhr_frame, and each half's packet carries side words: the Hat hold pair
and the logical voice RNG after that half. When V4 is Noise/Tone (shared
modes 1 and 2) on both halves and the event boundary is a rendering no-op,
this transform renders the frame once at the start of pk_nhr_frame, with the
Noise/Tone kernel recording the RNG after the first half's native samples
(pk_nt_capture_*). Half 0 then publishes that captured RNG and half 1 the
final one: the same packet words as two renders. placement_prepare(3, ...)
is still called at the same point (the frozen oracle steps there).

Eligibility also proves the assembly kernel will take its fast path (curve
table present, all four wave views found), so the capture always happens.
No merge while a Hat state snapshot is being built or tracing is enabled.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UNITS = ()

ELIGIBLE = '''
static inline int placement_v4_view(const pk4_assets*a,uint32_t want)
{
    return (a->waves[0].table&&a->waves[0].address==want)||(a->waves[1].table&&a->waves[1].address==want)||
           (a->waves[2].table&&a->waves[2].address==want)||(a->waves[3].table&&a->waves[3].address==want);
}
/* PKFM26: V4 Noise/Tone (shared modes) can render its frame in one segment. */
int __attribute__((noinline)) placement_v4_merge_eligible(const uint32_t *input)
{
    uint8_t algo=(uint8_t)input[0],mode=(uint8_t)input[1];
    if(input[9]||algo!=PK4_ALGO_NOISE_TONE||mode<1u||mode>2u||!placement_engine.assets||placement_trace_enabled)return 0;
    const pk4_track*t=&placement_engine.tracks[3];
    if(pk_prod_voice_generation[3]!=pk_prod_generation||!(t->initialized_mask&(1u<<algo)))return 0;
    if(t->active_algo!=algo||t->active_mode!=mode)return 0;
    const pk4_control*c=&t->nt_shared_ctl;
    if(!(c->valid&&c->last_mode==mode&&c->last_raw[0]==(uint8_t)input[3]&&
         c->last_raw[1]==(uint8_t)input[2]&&c->last_raw[2]==(uint8_t)input[4]&&
         c->last_raw[3]==(uint8_t)input[5]))return 0;
    const uint8_t*s=t->nt_shared;const pk4_assets*a=placement_engine.assets;
    if((s[0x75]==1&&!a->envelope1)||(s[0x75]==2&&!a->envelope2))return 0;
    /* findwave() succeeds for each of the four current/next views. */
    return placement_v4_view(a,pk_cf_ld32(s,0x38))&&placement_v4_view(a,pk_cf_ld32(s,0x3c))&&
           placement_v4_view(a,pk_cf_ld32(s,0xd0))&&placement_v4_view(a,pk_cf_ld32(s,0xd4));
}
'''

EXTERNAL_OLD = '''    if(!placement_segment(3,s->start,s->end,half))placement_status=0;
    uint16_t side[6];nhb_side(side,t);'''
EXTERNAL_NEW = '''    uint16_t side[6];
    if(!fm_v4_merged){if(!placement_segment(3,s->start,s->end,half))placement_status=0;nhb_side(side,t);}
    else{
        /* Rendered once at frame start: half 0 publishes the RNG after its own
         * native samples, half 1 the final RNG, as two renders would. */
        nhb_side(side,t);
        if(!half){side[2]=(uint16_t)fm_v4_split_rng[0];side[3]=(uint16_t)(fm_v4_split_rng[0]>>16);
                  side[4]=(uint16_t)fm_v4_split_rng[1];side[5]=(uint16_t)(fm_v4_split_rng[1]>>16);}
    }'''

FRAME_OLD = '''    nhr_previous=&nhr_jobs[pk_nhr_sequence&7];nhr_previous->sequence=pk_nhr_sequence;nhr_previous->split=split;
    for(unsigned j=0;j<2;j++){'''
FRAME_NEW = '''    nhr_previous=&nhr_jobs[pk_nhr_sequence&7];nhr_previous->sequence=pk_nhr_sequence;nhr_previous->split=split;
    fm_v4_merged=0;
    if(split&&!nhb_building&&placement_v4_merge_eligible(placement_inputs[3])){
        extern uint32_t pk_nt_capture_at,pk_nt_capture_done,pk_nt_capture_rng[2];
        pk_nt_capture_at=pk_cf_native_needed(&placement_clocks[3],split);pk_nt_capture_done=0;
        if(!placement_segment(3,0,16,0))placement_status=0;
        pk_nt_capture_at=~0u;
        fm_v4_merged=1;
        if(pk_nt_capture_done){fm_v4_split_rng[0]=pk_nt_capture_rng[0];fm_v4_split_rng[1]=pk_nt_capture_rng[1];}
        else{fm_v4_split_rng[0]=t->rng_low;fm_v4_split_rng[1]=t->rng_high;pk_nhr_failures++;}
    }
    for(unsigned j=0;j<2;j++){'''

STATICS_OLD = 'static void fm_external(nhr_segment*s,unsigned half)\n'
STATICS_NEW = 'static unsigned fm_v4_merged;static uint32_t fm_v4_split_rng[2];\n' + STATICS_OLD


def once(text, old, new):
    assert text.count(old) == 1, ('V4 merge transform anchor changed', old[:80])
    return text.replace(old, new, 1)


def transform(work, source_path):
    text = Path(source_path).read_text()
    marker = 'static void __attribute__((noinline)) placement_trace_empty(unsigned tr,unsigned half)\n'
    text = once(text, marker, ELIGIBLE.lstrip('\n') + '\n' + marker)
    include = next(line for line in text.splitlines()
                   if line.startswith('#include') and line.rstrip().endswith('full-map-transport-reserved.h"'))
    header = Path(include.split('"')[1])
    body = header.read_text()
    body = once(body, STATICS_OLD, STATICS_NEW)
    body = once(body, EXTERNAL_OLD, EXTERNAL_NEW)
    body = once(body, FRAME_OLD, FRAME_NEW)
    merged_header = Path(work) / 'full-map-transport-v4merge.h'
    merged_header.write_text(body)
    text = once(text, include, f'#include "{merged_header}"')
    target = Path(work) / 'placement-v4-merge.c'
    target.write_text(text)
    return target

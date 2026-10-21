#!/usr/bin/env python3
"""Build the cooperative same-frame Noise Hat experiment in its own output."""
from pathlib import Path
import json
import build_noise_hat_offload_probe as original
import build_cf_placement_probe as CF
ROOT=Path(__file__).resolve().parents[2]
WORK=ROOT/'out/perky/hybrid/noise-hat-async'

def controls(source):
    source=source.replace('static uint32_t placement_trigger[4];',
        'static uint32_t placement_trigger[4],nhaa_queued[3],nhaa_splits[3];\nextern void pk_nhaa_frame_start(unsigned);\nextern void pk_nhaa_drain(void);')
    start=source.index('    if(!placement_segment(voice,start,end,start?1u:0u))')
    end=source.index('    if(pk_hybrid_profiler_enable) {',start)
    old=source[start:end]
    # Earlier voices retain their own captured controls and trig markers.
    # Reserve their normal slots now; publish completed PCM before source DMA.
    body='''
    uint32_t n=end-start,words=4u+2u*n;
    volatile uint32_t *cursor=(volatile uint32_t *)(uintptr_t)U32(0x80001c80u);
    for(unsigned i=0;i<words;i++)cursor[i]=0;
    U32(0x80001c80u)=(uint32_t)(uintptr_t)(cursor+words);
    if(end==16u) {
        if(voice<3u){nhaa_queued[voice]=1;nhaa_splits[voice]=start;}
        else {
            pk_nhaa_frame_start(start);
            for(unsigned v=0;v<3;v++)if(nhaa_queued[v]) {
                unsigned split=nhaa_splits[v];
                if(!placement_segment(v,0,split,0)||
                   !placement_prepare(v,placement_inputs[v],placement_inputs[v][9]!=0)||
                   !placement_segment(v,split,16,1))placement_status=0;
                placement_pack(v,split);
                unsigned output_track=v==0?0:v==1?1:4;
                pk_hybrid_commit_longs(pk_hybrid_fixed_slot(output_track,ping),placement_packets[v],40u);
                placement_calls[v]++;placement_trigger[v]=0;nhaa_queued[v]=0;
            }
            pk_nhaa_drain();
            placement_pack(voice,start);
            pk_hybrid_commit_longs(pk_hybrid_fixed_slot(track,ping),placement_packets[voice],40u);
            placement_calls[voice]++;placement_trigger[voice]=0;
        }
    }
'''
    source=source[:start]+body+source[end:]
    # Preparation moves with the deferred render, retaining old prefix state.
    source=source.replace('        if(!placement_prepare(voice,p,p[9]!=0))placement_status=0;','')
    return source

def transform(name,path):
    if name not in ('pkwavetable','pkslap'):return None
    text=path.read_text()
    if name=='pkwavetable':
        needle='    for(i=0;i<n;i++){\n        const uint8_t *wn,*sn;'
    else:needle='    for(i=0;i<n;i++){\n        int16_t nv='
    assert text.count(needle)==1
    text='extern void pk_nhaa_poll(void);\n'+text.replace(needle,needle.replace('\n        ','\n        pk_nhaa_poll();\n        ',1))
    dest=WORK/(name+'-poll.c');dest.write_text(text);return dest

def build():
    WORK.mkdir(parents=True,exist_ok=True)
    original.WORK=WORK;original.VERSION='PKNHB1'
    base_build=CF.build
    def replacement(work,**kw):
        initial=kw['control_transform'];kw['control_transform']=lambda t:controls(initial(t))
        kw['additional_units']=(('pkhatrpc','cf_noise_hat_async.c'),)
        source=WORK/'placement-async.c'
        source.write_text('#include "'+str(ROOT/'tools/harness/perky_cf/placement_cf_engine.c')+'"\n#include "'+str(ROOT/'tools/harness/perky_cf/noise_hat_async_engine.c')+'"\n')
        kw['placement_source']=source;kw['source_transform']=transform;kw['build_number']=16
        return base_build(work,**kw)
    CF.build=replacement
    try:
        original.build()
        report=json.loads((WORK/'BUILD.json').read_text())
        report['experiment']='same-frame cooperative Noise Hat; deferred WT/WT and Slap'
        report['source_sha256'].update({str(p.relative_to(ROOT)):original.sha(p) for p in
            (Path(__file__),ROOT/'modules/perky/cf_noise_hat_async.c',ROOT/'tools/harness/perky_cf/noise_hat_async_engine.c')})
        report['transport_contract']='Readiness-guarded bounded polling during CF work; IPL7/HI08 reservation; explicit counted cleanup path must remain unused.'
        for p in (WORK/'BUILD.json',WORK/'EXPERIMENT_BUILD.json',WORK/'probe/BUILD.json'):
            p.write_text(json.dumps(report,indent=2)+'\n')
    finally:CF.build=base_build
if __name__=='__main__':build()

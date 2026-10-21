"""Candidate-only unchanged-control event path using authoritative engine state.

Generation/reset observation always runs. No cached copy of controls or new
readiness flag is introduced; dirty, triggered, fresh and acoustic events use
the original preparation body. The common path avoids that body's large frame.
"""
from pathlib import Path


def transform(work, source_path):
    work = Path(work)
    text = Path(source_path).read_text()
    signature = 'int placement_prepare(unsigned tr,const uint32_t *input,int trig)\n'
    assert text.count(signature) == 1
    start = text.index(signature)
    end = text.index('\nint placement_segment(', start)
    body = text[start:end]
    observation = '''    placement_production_event(tr,algo);
    pk_prod_algorithms[tr]=algo;pk_prod_modes[tr]=mode;
'''
    assert body.count(observation) == 1
    body = body.replace(observation, '', 1).replace(
        signature, 'static int __attribute__((noinline)) placement_prepare_slow(unsigned tr,const uint32_t *input,int trig)\n', 1)
    wrapper = '''
int __attribute__((noinline)) placement_prepare(unsigned tr,const uint32_t *input,int trig)
{
    uint8_t algo=(uint8_t)input[0],mode=(uint8_t)input[1];
    if(algo>10||mode>2||tr>3)return 0;
    placement_production_event(tr,algo);
    pk_prod_algorithms[tr]=algo;pk_prod_modes[tr]=mode;
    pk4_track*t=&placement_engine.tracks[tr];
    if(!trig&&algo<10&&placement_engine.assets&&(t->initialized_mask&(1u<<algo))){
        static const unsigned offsets[10]={
            offsetof(pk4_track,fold1_ctl),offsetof(pk4_track,fold2_ctl),
            offsetof(pk4_track,karplus_ctl),offsetof(pk4_track,nt_shared_ctl),
            offsetof(pk4_track,res_snare_ctl),offsetof(pk4_track,nh_ctl),
            offsetof(pk4_track,sd_ctl),offsetof(pk4_track,cd_ctl),
            offsetof(pk4_track,slap_ctl),offsetof(pk4_track,wt_ctl)};
        const pk4_control*c=(const pk4_control*)((const uint8_t*)t+offsets[algo]);
        if(algo==PK4_ALGO_NOISE_TONE&&!mode)c=&t->nt_m1_ctl;
        if(c->valid&&c->last_mode==mode&&c->last_raw[0]==(uint8_t)input[3]&&
           c->last_raw[1]==(uint8_t)input[2]&&c->last_raw[2]==(uint8_t)input[4]&&
           c->last_raw[3]==(uint8_t)input[5]){
            if(t->active_algo!=algo)pk_cf_native_reset(&placement_clocks[tr]);
            t->active_algo=algo;t->active_mode=mode;
            return 1;
        }
    }
    return placement_prepare_slow(tr,input,trig);
}
'''
    target = work / 'placement-fast-prepare.c'
    target.write_text(text[:start] + body + wrapper + text[end:])
    return target

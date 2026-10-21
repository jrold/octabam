"""Extend the frozen G3 transport with exact external-PCM segments."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def once(text,old,new):
 assert text.count(old)==1,old[:100]
 return text.replace(old,new,1)

def generate(work):
 work=Path(work)
 shadow=(ROOT/'tools/harness/perky_cf/production_handoff_shadow.h').read_text()
 shadow=once(shadow,'        if(f->cf){','''        if(!f->cf){
            nhb_hold[0]=h->side[0];nhb_hold[1]=h->side[1];
            nhb_rng.low=(uint32_t)h->side[2]|((uint32_t)h->side[3]<<16);
            nhb_rng.high=(uint32_t)h->side[4]|((uint32_t)h->side[5]<<16);
            if(s->external)continue;
        }
        if(f->cf){''')
 shadow=once(shadow,'    if((pk_nhr_enabled!=0)==pk_nhb_owner)return;','''    if((pk_nhr_enabled!=0)==pk_nhb_owner)return;
    if(placement_engine.tracks[3].active_algo!=PK4_ALGO_NOISE_HAT)return;''')
 shadow=once(shadow,'        else if(mode<2&&!t->nh[0xb8]){','        else if(t->active_algo==PK4_ALGO_NOISE_HAT&&mode<2&&!t->nh[0xb8]){')
 shadow=once(shadow,'            s->mode=mode;s->start=start;', '            s->external=t->active_algo!=PK4_ALGO_NOISE_HAT;\n            s->mode=mode;s->start=start;')
 shadow=once(shadow,'        if(j&&!placement_prepare(3,placement_inputs[3],placement_inputs[3][9]!=0))placement_status=0;','''        unsigned fresh=j&&!(t->initialized_mask&(1u<<PK4_ALGO_NOISE_HAT));
        if(j&&!placement_prepare(3,placement_inputs[3],placement_inputs[3][9]!=0))placement_status=0;
        unsigned hat_fresh=fresh&&t->active_algo==PK4_ALGO_NOISE_HAT;''')
 shadow=once(shadow,'if(j&&pk_prod_last_reset[3])nhb_dirty|=7;','if(j&&(pk_prod_last_reset[3]||hat_fresh))nhb_dirty|=7;')
 shadow=once(shadow,'s->epoch_reset=j&&pk_prod_last_reset[3];','s->epoch_reset=j&&(pk_prod_last_reset[3]||hat_fresh);')
 shadow_path=work/'full-map-shadow.h';shadow_path.write_text(shadow)
 text=(ROOT/'tools/harness/perky_cf/production_handoff_engine.c').read_text()
 text=once(text,'unsigned ring_start,generation,epoch_reset;','unsigned ring_start,generation,epoch_reset,external;')
 text=once(text,'if(s->mode==2||s->mute)continue;','if(s->external||s->mode==2||s->mute)continue;')
 text=once(text,'#include "production_handoff_shadow.h"','#include "'+str(shadow_path)+'"\n#include "'+str(ROOT/'tools/harness/perky_cf/full_map_rng.h')+'"')
 begin=text.index('    if(!need||!apply)nhr_put(0);')
 end=text.index('    nhb_capture(seg,w,apply,',begin)
 text=text[:begin]+'''    const uint8_t*keys=mode==0?nhr_control0:mode==1?nhr_control1:nhr_control2;
    unsigned count=apply?(mode==0?sizeof(nhr_control0):mode==1?sizeof(nhr_control1):sizeof(nhr_control2)):0;
    unsigned env=mode==0?2:mode==1?82:1;
    uint8_t*raw=t->nh+(mode==2?NH_PULSE:nh_limb(mode));
    int reset=trig&&raw[0x7c];
    nhr_put(count+6+(trig?2:0)+(reset?2:0));
    uint16_t side[6];nhb_side(side,t);
    for(unsigned i=0;i<6;i++){nhr_put(0x3970+i);nhr_put(side[i]);}
    for(unsigned i=0;i<count;i++)nhr_patch(mode,keys[i],w[keys[i]]);
    if(trig){nhr_patch(mode,env,w[env]);nhr_patch(mode,env+7,w[env+7]);}
    if(reset){nhr_patch(mode,env+5,w[env+5]);nhr_patch(mode,env+6,w[env+6]);}
'''+text[end:]
 marker='    seg->ring_start=nht_ring_index;'
 text=once(text,marker,'    if(nhb_building)nhb_side(nhb_building->half[apply!=0].side,t);\n'+marker)
 begin=text.index('void pk_nhr_frame(')
 text=text[:begin]+'''/* The native producer for each half is either DSP Hat or CF PCM. ALGO
 * changes retain every engine object and the original shared voice RNG. */
static void fm_external(nhr_segment*s,unsigned half)
{
    pk4_track*t=&placement_engine.tracks[3];
    if(!placement_segment(3,s->start,s->end,half))placement_status=0;
    nhr_put((s->end-s->start)|(1u<<10)|(s->epoch_reset<<9));nhr_put(0);nhr_put(6);
    uint16_t side[6];nhb_side(side,t);
    for(unsigned i=0;i<6;i++){nhr_put(0x3970+i);nhr_put(side[i]);}
    for(unsigned i=s->start;i<s->end;i++){
        unsigned pcm=(uint32_t)placement_output[3][i];nhr_put((pcm>>16)&255);nhr_put(pcm&65535);
    }
    if(nhb_building){nhb_half*h=&nhb_building->half[half];h->segment=*s;h->apply=half;for(unsigned i=0;i<6;i++)h->side[i]=side[i];}
}
void pk_nhr_frame(unsigned split,volatile uint32_t *slot)
{
    nhr_finish_previous();nhb_select();
    if(!pk_nhb_owner){nhb_cf_frame(split,slot);return;}
    nhb_begin(0);
    if(!nht_ready){nht_ring_index=pk_cf_ld16(placement_engine.tracks[3].nh,0x2982);nht_ready=1;}
    pk4_track*t=&placement_engine.tracks[3];unsigned trig=placement_inputs[3][9]!=0;
    nhr_used=0;nhr_put(0x4e54);nhr_put((++pk_nhr_sequence)&65535);
    nhr_previous=&nhr_jobs[pk_nhr_sequence&7];nhr_previous->sequence=pk_nhr_sequence;nhr_previous->split=split;
    for(unsigned j=0;j<2;j++){
        nhr_segment*s=&nhr_previous->seg[j];s->start=j?split:0;s->end=j?16:split;
        unsigned previous=t->active_algo,fresh=0;
        if(j){
            fresh=!(t->initialized_mask&(1u<<PK4_ALGO_NOISE_HAT));
            pk_cf_native_clock clock=placement_clocks[3];
            if(!placement_prepare(3,placement_inputs[3],trig))placement_status=0;
            if(!pk_prod_last_reset[3]&&previous==t->active_algo&&t->active_algo==PK4_ALGO_NOISE_HAT)placement_clocks[3]=clock;
        }
        s->external=t->active_algo!=PK4_ALGO_NOISE_HAT;
        s->mode=nh_mode(t->active_mode);s->generation=pk_prod_voice_generation[3];
        s->epoch_reset=j&&(pk_prod_last_reset[3]||(!s->external&&fresh));
        s->reset=j&&(trig||s->epoch_reset||previous!=t->active_algo);
        s->mute=s->mode<2&&t->nh[0xb8];s->mix=(int16_t)pk_cf_ld16(t->nh,0x2dd4);s->need=0;
        if(s->epoch_reset)nht_ring_index=0;
        if(s->external){fm_external(s,j);continue;}
        if(s->reset)pk_cf_native_reset(&nhr_schedule_clock);
        s->need=nhr_needed(s->end-s->start);placement_native_samples[3]+=s->need;
        int init=s->need&&!(nhr_initialized&(1u<<s->mode));
        nhr_emit(s->mode,s->need,init,j&&trig,j!=0);
        if(!s->mute)fm_hat_noise(s->mode,s->need);
        if(init)nhr_initialized|=1u<<s->mode;
    }
    nhb_publish();pk_nhr_packet_words+=nhr_used;
    volatile uint16_t*tail=(volatile uint16_t*)slot;
    for(unsigned i=0;i<nhr_used;i++)tail[i]=nhr_commands[i];
}
'''
 path=work/'full-map-transport.h';path.write_text(text)
 return path

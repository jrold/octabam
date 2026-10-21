"""Opt-in bounded packet reservations with the checked original fallback.

Only publication into the private command array changes. Snapshot controls,
generation state, callbacks, scheduled tap gather and feedback remain intact.
"""
from pathlib import Path
import re


def header(text):
    begin = text.index('    nhr_put(count+6+(trig?2:0)+(reset?2:0));')
    end = text.index('    nhb_capture(seg,w,apply,', begin)
    original = text[begin:end]
    replacement = '''    unsigned words=13u+2u*count+(trig?4u:0u)+(reset?4u:0u);
    if(mode<=2u && count<=19u && nhr_used<=168u && words<=168u-nhr_used){
        uint16_t*out=nhr_commands+nhr_used;
        *out++=(uint16_t)(count+6+(trig?2:0)+(reset?2:0));
        uint16_t side[6];nhb_side(side,t);
        for(unsigned i=0;i<6;i++){*out++=(uint16_t)(0x3970+i);*out++=side[i];}
        unsigned base=mode==2?0x3879:0x3800;
        for(unsigned i=0;i<count;i++){unsigned k=dirty[i];*out++=(uint16_t)(base+k);*out++=w[k];}
        if(trig){*out++=(uint16_t)(base+env);*out++=w[env];*out++=(uint16_t)(base+env+7);*out++=w[env+7];}
        if(reset){*out++=(uint16_t)(base+env+5);*out++=w[env+5];*out++=(uint16_t)(base+env+6);*out++=w[env+6];}
        nhr_used+=words;
    }else{
''' + original + '    }\n'
    text = text[:begin] + replacement + text[end:]
    begin = text.index('    nhr_put((s->end-s->start)|(1u<<10)')
    end = text.index('    if(nhb_building){nhb_half*h=', begin)
    original = text[begin:end]
    assert original.count('    uint16_t side[6];nhb_side(side,t);\n') == 1
    fallback = original.replace('    uint16_t side[6];nhb_side(side,t);\n', '', 1)
    replacement = '''    uint16_t side[6];nhb_side(side,t);
    unsigned samples=s->end-s->start,words=15u+2u*samples;
    if(s->start<=s->end && s->end<=16u && nhr_used<=168u && words<=168u-nhr_used){
        uint16_t*out=nhr_commands+nhr_used;
        *out++=(uint16_t)(samples|(1u<<10)|(s->epoch_reset<<9)|nhb_request_flag(half));*out++=0;*out++=6;
        for(unsigned i=0;i<6;i++){*out++=(uint16_t)(0x3970+i);*out++=side[i];}
        for(unsigned i=s->start;i<s->end;i++){
            unsigned pcm=(uint32_t)placement_output[3][i];*out++=(uint16_t)((pcm>>16)&255);*out++=(uint16_t)pcm;
        }
        nhr_used+=words;
    }else{
''' + fallback + '    }\n'
    return text[:begin] + replacement + text[end:]


def transform(work, source_path):
    work = Path(work)
    source = Path(source_path).read_text()
    match = re.findall(r'^#include "([^"\n]*full-map-transport\.h)"$', source, re.M)
    assert len(match) == 1, 'Expected exactly one current transport header'
    original = Path(match[0]);target = work / 'full-map-transport-reserved.h'
    target.write_text(header(original.read_text()))
    destination = work / 'placement-reserved-packets.c'
    destination.write_text(source.replace('"' + str(original) + '"', '"' + str(target) + '"', 1))
    return destination

"""Probe-local exact WT envelope blocks after PKFM17 oscillator assembly.

Crossing blocks and unusual state retain the original single-step state
machine. A proven unchanged state or uninterrupted arithmetic run avoids
redispatching that state machine for each native sample.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ASSEMBLY = ROOT / 'tools/harness/perky_cf/wt_oscillator_block.s'


def helper(name, output_type):
    return '''static void __attribute__((noinline))
NAME(wt_env_cfg*c,wt_env*e,TYPE*dst,uint32_t n){
    uint32_t i;int32_t delta=0,value=e->v;
    if(!n)return;
    if((e->st==0&&!c->f7&&!c->f4)||e->st==2||e->st>4||
       (e->st==3&&(c->f7||(!c->f4&&c->f10)))){
        uint16_t sample=wt_env_step(c,e);
        for(i=0;i<n;i++)dst[i]=sample;
        return;
    }
    if(e->st==1&&value>=0&&value<=0xffffe&&
       (uint32_t)value+(uint32_t)c->rate_up*n<=0xffffeu){
        delta=(int32_t)c->rate_up;
    }else if(e->st==4&&!c->f7&&value>0&&
             (uint32_t)value>(uint32_t)c->rate_dn*n){
        delta=-(int32_t)c->rate_dn;
    }else{
        for(i=0;i<n;i++)dst[i]=wt_env_step(c,e);
        return;
    }
    if(c->curve!=1&&c->curve!=2){
        for(i=0;i<n;i++){
            value=s32(u32(value)+u32(delta));
            dst[i]=(uint16_t)(u32(value)>>4);
        }
    }else{
        const uint8_t*ct=c->curve==1?c->e1:c->e2;
        if(!ct){
            for(i=0;i<n;i++)dst[i]=wt_env_step(c,e);
            return;
        }else{
            uint32_t cached_index=c->cached_index,cached_pair=c->cached_pair;
            for(i=0;i<n;i++){
                uint32_t raw,idx,nx;int32_t a,z,f;
                value=s32(u32(value)+u32(delta));raw=u32(value);
                idx=(raw>>10)&0x7ffu;nx=(idx+1)&0x7ffu;f=(int32_t)(raw&0x3ffu);
                if(cached_index!=idx){
                    cached_pair=nx?pk_cf_ld32(ct,2u*idx):
                        (uint32_t)tab16(ct,idx)|((uint32_t)tab16(ct,nx)<<16);
                    cached_index=idx;
                }
                a=(int32_t)(cached_pair&0xffffu);z=(int32_t)(cached_pair>>16);
                dst[i]=(uint16_t)(a+asr(mullo(z-a,f),10));
            }
            c->cached_index=cached_index;c->cached_pair=cached_pair;
        }
    }
    e->v=value;
}

'''.replace('NAME', name).replace('TYPE', output_type)


def transform_text(text, **unused):
    marker = 'static int32_t pitch(uint16_t raw,const uint8_t*t){'
    assert text.count(marker) == 1
    text = text.replace(marker, helper('wt_amplitude_block', 'uint16_t') +
                        helper('wt_pitch_envelope_block', 'uint32_t') + marker, 1)
    old = ('    for(i=0;i<n;i++)amplitudes[i]=wt_env_step(&ea_cfg,&ea);\n'
           '    for(i=0;i<n;i++)steps[i]=wt_env_step(&ep_cfg,&ep);')
    assert text.count(old) == 1
    return text.replace(old, '    wt_amplitude_block(&ea_cfg,&ea,amplitudes,n);\n'
                        '    wt_pitch_envelope_block(&ep_cfg,&ep,steps,n);', 1)


def transform(work, source_path):
    destination = Path(work) / 'wavetable-envelope-blocks.c'
    destination.write_text(transform_text(Path(source_path).read_text()))
    return destination

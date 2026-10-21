"""Probe-local WT linear amplitude runs; retain curved and crossing paths."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ASSEMBLY = ROOT / 'tools/harness/perky_cf/wt_linear_envelope.s'


def transform_text(text, **unused):
    marker = 'static int32_t pitch(uint16_t raw,const uint8_t*t){'
    assert text.count(marker) == 1
    helper = '''extern uint32_t pk_cf_wt_linear_envelope(uint16_t*,uint32_t,uint32_t,int32_t);
static inline __attribute__((always_inline)) int
wt_linear_amplitude(wt_env_cfg*c,wt_env*e,uint16_t*dst,uint32_t n){
    int32_t delta,value=e->v;
    if(c->curve==1||c->curve==2)return 0;
    if((e->st==0&&!c->f7&&!c->f4)||e->st==2||e->st>4||
       (e->st==3&&(c->f7||(!c->f4&&c->f10))))delta=0;
    else if(e->st==1&&value>=0&&value<=0xffffe&&
            (uint32_t)value+(uint32_t)c->rate_up*n<=0xffffeu)
        delta=(int32_t)c->rate_up;
    else if(e->st==4&&!c->f7&&value>0&&
            (uint32_t)value>(uint32_t)c->rate_dn*n)
        delta=-(int32_t)c->rate_dn;
    else return 0;
    e->v=s32(pk_cf_wt_linear_envelope(dst,n,u32(value),delta));
    return 1;
}

'''
    text = text.replace(marker, helper + marker, 1)
    old = '    for(i=0;i<n;i++)amplitudes[i]=wt_env_step(&ea_cfg,&ea);'
    assert text.count(old) == 1
    return text.replace(old, '    if(!wt_linear_amplitude(&ea_cfg,&ea,amplitudes,n))\n'
                        '        for(i=0;i<n;i++)amplitudes[i]=wt_env_step(&ea_cfg,&ea);', 1)


def transform(work, source_path):
    destination = Path(work) / 'wavetable-linear-envelope.c'
    destination.write_text(transform_text(Path(source_path).read_text()))
    return destination

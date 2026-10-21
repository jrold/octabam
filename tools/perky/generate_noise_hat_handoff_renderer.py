#!/usr/bin/env python3
"""Transpose independent metallic-Hat stages to fit the CF register file."""
import hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
ORIGINAL_SHA256='18aac652089aa04d7e6f751dd8bba3314f63aa1a8bf7dfb1016fd421f7df8776'
def generate(destination):
 path=ROOT/'modules/perky/cf_noise_hat.c';text=path.read_text();assert hashlib.sha256(path.read_bytes()).hexdigest()==ORIGINAL_SHA256,'original Hat renderer drift'
 start=text.index('static int nh_block_metallic(');end=text.index('/* --- white ',start)
 old=text[start:end];fallback=old.replace('nh_block_metallic(','nh_block_metallic_original(',1)
 new='''/* Same oscillator/filter/envelope/delay recurrences and stage order. Each
 * independent stage advances over the block before the next stage. This
 * keeps one oscillator/filter history live instead of spilling all of them
 * across each sample on ColdFire. Large external calls retain the original. */
static int nh_block_metallic(uint8_t*s,int16_t*dst,uint32_t n,const pk_cf_nh_tables*t){
    static const size_t fb[4]={NH_C0+0x9cu,NH_C0+0xc4u,NH_C0+0xe0u,NH_C0+0xfcu};
    int32_t scratch[20];unsigned i,k;
    if(n>20u)return nh_block_metallic_original(s,dst,n,t);
    if(s[NH_MUTE]){for(i=0;i<n;i++)dst[i]=0;return 1;}
    for(i=0;i<n;i++)scratch[i]=0;
    for(k=0;k<6u;k++){
        size_t b=NH_C0+0x118u+0x34u*k;
        uint32_t phase=r32(s,b+4),inc=r32(s,b+8);
        uint16_t width=r16(s,b+0x24),reload=r16(s,b+0x26);
        for(i=0;i<n;i++){
            int32_t pulse;phase+=inc;
            if(s32(phase)>0x100000){phase-=0x100000u;width=reload;}
            pulse=width>asr(s32(phase),8)?32767:-32767;
            scratch[i]=add(scratch[i],s16((uint16_t)(((uint32_t)pulse>>5)&0xffffu)));
        }
        w32(s,b+4,phase);w16(s,b+0x24,width);
    }
    for(k=0;k<4u;k++){
        nh_filter_c f;nh_filter_load(&f,s,fb[k]);
        for(i=0;i<n;i++){
            nh_filter_step(&f,scratch[i]);
            scratch[i]=k==0?f.first:k==3?f.velocity:f.second;
        }
        nh_filter_store(&f,s,fb[k]);
    }
    nh_env_cfg ec;nh_delay_c dly;uint8_t est;int32_t ev;
    nh_env_load(&ec,s,NH_C0+0x74u,t);est=s[NH_C0+0x74];ev=s32(r32(s,NH_C0+0x74+0x0c));
    nh_delay_load(&dly,s);
    for(i=0;i<n;i++){
        int32_t amp=nh_env_step(&est,&ec,&ev);
        int32_t value=asr(mullo(scratch[i],amp),11);
        int32_t inner=nh_velocity_scale(s[NH_C0+6],value);
        dst[i]=s16((uint16_t)nh_delay_step(s,&dly,inner));
    }
    s[NH_C0+0x74]=est;w32(s,NH_C0+0x74+0x0c,u32(ev));
    w16(s,NH_IDX,(uint16_t)dly.index);return 1;
}

'''
 Path(destination).write_text(text[:start]+fallback+new+text[end:])
 return dict(original_sha256=ORIGINAL_SHA256,native_block_bound=20,stage_schedule='six independent oscillator blocks; four serial filter blocks; original envelope and delay block',fallback='original unmodified body for n>20')

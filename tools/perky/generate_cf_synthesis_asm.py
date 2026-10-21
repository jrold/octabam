#!/usr/bin/env python3
"""Probe-local original synthesis with the exact CF five-stage delay block."""
import hashlib
from pathlib import Path
import generate_noise_hat_handoff_renderer as metallic
ROOT=Path(__file__).resolve().parents[2]
SLAP_SHA='e0e0a62c8112ceb5b9fe8bb7108feb7e7e396f89f43099e2e55f4107d692ab2b'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
DECL='''#if defined(__mcoldfire__)
extern void pk_cf_nh_delay_dispatch(uint8_t*,void*,int16_t*,uint32_t);
extern void pk_cf_slap_delay_block(void*,uint8_t*,int32_t*,uint32_t);
#endif
'''
def generate(work):
 work=Path(work);hat=work/'noise-hat-synthesis.c';metallic.generate(hat);s=hat.read_text()
 # Preserve the complete original n>20 path. Only the short-block functions
 # generated below delay ring work until all ring-independent inner samples exist.
 for name in ('metallic','white'):
  begin=s.index('static int nh_block_'+name+'(');end=s.index('/* --- '+('white' if name=='metallic' else 'pulse stack'),begin)
  body=s[begin:end];fallback=body.replace('nh_block_'+name+'(','nh_block_'+name+'_c_delay(',1)
  header=body.index('{')+1
  args='s,dst,n,t'+(',rng,hold' if name=='white' else '')
  new=body[:header]+'\n    if(n>20u)return nh_block_'+name+'_c_delay('+args+');'+body[header:]
  old='dst[i]=s16((uint16_t)nh_delay_step(s,&dly,inner));';assert new.count(old)==1
  new=new.replace(old,'dst[i]=(int16_t)inner;')
  marker='    w16(s,NH_IDX,(uint16_t)dly.index);';assert new.count(marker)==1
  new=new.replace(marker,'''    pk_cf_nh_delay_dispatch(s,&dly,dst,n);
'''+marker)
  s=s[:begin]+'#if defined(__mcoldfire__)\n'+fallback+new+'#else\n'+body+'#endif\n\n'+s[end:]
 helper='/* The original velocity scaler returns int16_t in both classic modes.\n * This typed buffer makes the bounded delay input explicit. Check every tap\n * word on every call; arbitrary metadata retains the original C recurrence. */\nextern void pk_cf_nh_delay_i16(void*,uint8_t*,int16_t*,uint32_t);\nvoid pk_cf_nh_delay_dispatch(uint8_t*s,void*state,int16_t*data,uint32_t n){\n    nh_delay_c*d=state;static const uint16_t delay[5]={573,1201,1538,3139,4804},gain[5]={1,1,3,5,7};\n    unsigned ok=d->index<4805u;\n    for(unsigned k=0;k<5;k++)if(d->delay[k]!=delay[k]||d->gain[k]!=gain[k])ok=0;\n    if(ok)pk_cf_nh_delay_i16(d,s+NH_RING,data,n);\n    else for(unsigned i=0;i<n;i++)data[i]=(int16_t)nh_delay_step(s,d,data[i]);\n}\n\n'
 marker='/* --- metallic (firmware mode 0)'
 assert s.count(marker)==1
 s=s.replace(marker,helper+marker,1)
 hat.write_text(s.replace('/* --- envelope',DECL+'\n/* --- envelope',1))
 original=ROOT/'modules/perky/cf_slap.c';assert sha(original)==SLAP_SHA,'original Slap renderer drift'
 s=original.read_text();start=s.index('int pk_cf_slap_render(');body=s[start:];assert body.rstrip().endswith('}')
 fallback=body.replace('pk_cf_slap_render(','pk_cf_slap_render_c_delay(',1)
 new=body.replace('    uint32_t i,k;','    uint32_t i,k;\n    if(n>20u)return pk_cf_slap_render_c_delay(s,d,n,t,rng);\n    int32_t inner_block[20];',1)
 old='d[i]=slap_velocity(velocity,slap_delay_step(s,&ds,scaled));';assert new.count(old)==1
 new=new.replace(old,'inner_block[i]=scaled;')
 marker='    w16(s,0x60,ns.count);';assert new.count(marker)==1
 new=new.replace(marker,'''    pk_cf_slap_delay_block(&ds,s+PK_CF_SLAP_RING_OFF,inner_block,n);
    for(i=0;i<n;i++)d[i]=slap_velocity(velocity,inner_block[i]);
'''+marker)
 slap=work/'slap-synthesis.c';slap.write_text(s[:start]+DECL+'\n#if defined(__mcoldfire__)\n'+fallback+'\n'+new+'\n#else\n'+body+'\n#endif\n')
 return dict(hat=str(hat),slap=str(slap),original_slap_sha256=SLAP_SHA,original_hat_sha256=metallic.ORIGINAL_SHA256)

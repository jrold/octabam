#!/usr/bin/env python3
"""Card-sized complete map: immutable Acoustic assets loaded by the UI task."""
import json,re,struct,zlib
from pathlib import Path
import build_perky_full_map_all_fx as a
ROOT=a.ROOT;W=ROOT/'out/perky/hybrid/full-map-release'
def main():
 W.mkdir(parents=True,exist_ok=True);a.W=W;a.b.WORK=W
 data=b''.join((ROOT/'out/perky/hybrid/cf-placement/assets'/f'{n}.bin').read_bytes() for n in ('closed','open','ride'));assert len(data)==452108
 crc=zlib.crc32(data);asset=W/'PERKYAH.DAT';asset.write_bytes(struct.pack('>4I',0x504b4148,1,len(data),crc)+data)
 original=a.b.G.h.CF.build;module=a.b.G.h.CF.base.build_hybrid_module
 def build(work,**kw):
  transform=kw['control_transform']
  def controls(s):
   s=transform(s).replace('extern const uint8_t pk_placement_closed[]','extern uint8_t pk_placement_closed[]');s=f'#define FMA_EXPECTED_CRC 0x{crc:08x}u\n#include "{ROOT}/modules/perky/full_map_card_assets.h"\n'+s
   cold='    pk_hybrid_pcm_cookie = PK_HYB_PCM_COLD;';assert s.count(cold)==1
   s=s.replace(cold,cold+'\n    fma_reset();')
   marker='    ++pk_hybrid_prof.ui_tick_count;';assert s.count(marker)==1
   return s.replace(marker,'    fma_tick();\n'+marker)
  kw['control_transform']=controls
  src=kw['placement_source'];s=src.read_text();marker='    pk_cf_native_clock*c=&placement_clocks[tr];'
  # Put the readiness check inside the actual segment producer. All normal
  # algorithms, controls and owned histories remain the existing implementation.
  start=s.index('int placement_segment(');brace=s.index('{',start)+1
  s=s[:brace]+'''\n    extern uint32_t fma_ready;
    if(tr==3&&placement_engine.tracks[3].active_algo==10&&fma_ready!=0x41484f4bu){for(unsigned i=start;i<end;i++)placement_output[tr][i]=0;return 1;}
'''+s[brace:];src.write_text(s)
  return original(work,**kw)
 def compact(*args,**kw):
  r=module(*args,**kw);directory=kw['generated_dir']
  hats=directory/'pkhats.s';hats.write_text('.section .bss\n'+''.join(f'.balign 4\n.globl pk_placement_{n}\npk_placement_{n}:\n.space {size}\n' for n,size in (('closed',20202),('open',172800),('ride',259106))))
  rpc=directory/'pkhatrpc.s';s=rpc.read_text();removed=[]
  for name in ('nha_port','pk_nha_unused_renderer','pk_cf_nh_offload','pk_nha_bind_port','pk_nhr_delay'):
   pattern=r'\s*\.section\s+\.text\.'+name+r',.*?(?=\s*\.section|\Z)'
   s,n=re.subn(pattern,'\n',s,flags=re.S);assert n==1,(name,n);removed.append(name)
  rpc.write_text(s);(W/'REMOVED_PROTOTYPES.json').write_text(json.dumps(removed,indent=2)+'\n');return r
 a.b.G.h.CF.build=build;a.b.G.h.CF.base.build_hybrid_module=compact
 # The all-FX builder uses its version only inside this wrapper's call.
 original_main=a.b.main
 def versioned():a.b.VERSION='PKFM6';return original_main()
 a.b.main=versioned
 try:a.main()
 finally:a.b.G.h.CF.build=original;a.b.G.h.CF.base.build_hybrid_module=module;a.b.main=original_main
 p=W/'BUILD.json';r=json.loads(p.read_text());r['asset_file']=dict(path=str(asset),sha256=a.b.sha(asset),payload_crc32=crc,bytes=asset.stat().st_size,required_card_path='/PERKYAH.DAT',loading='UI task, 4096-byte bounded chunks; CRC before audio readiness',missing_behavior='Acoustic source silent; other algorithms remain available; retries while transport is stopped')
 r['source_sha256'].update({str(p.relative_to(ROOT)):a.b.sha(p) for p in (Path(__file__).resolve(),ROOT/'modules/perky/full_map_card_assets.h')});r['status']='BUILT_CARD_ASSET_CANDIDATE_NOT_QUALIFIED';p.write_text(json.dumps(r,indent=2)+'\n');print(r['status'])
if __name__=='__main__':main()

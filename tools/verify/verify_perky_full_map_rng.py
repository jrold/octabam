#!/usr/bin/env python3
"""The CF RNG/hold tracker versus the untouched complete Hat renderer."""
import ctypes as C,hashlib,json,os,random,struct,subprocess
from pathlib import Path
import verify_perky_hybrid_runtime as rt
ROOT=rt.ROOT;W=Path(os.environ.get('PERKY_FULL_MAP_WORK',str(ROOT/'out/perky/hybrid/full-map'))).resolve()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 out=W/'rng-gate';out.mkdir(exist_ok=True)
 source=out/'oracle.c';source.write_text('''#include <string.h>
#include "cf_perky4.h"
pk4_engine placement_engine;
#include "'''+str(ROOT/'tools/harness/perky_cf/full_map_rng.h')+'''"
int check(const unsigned char*input,unsigned lo,unsigned hi,unsigned h0,unsigned h1,unsigned n,unsigned*expected){
 unsigned char raw[PK_CF_NH_WRAPPER_BYTES];memcpy(raw,input,sizeof(raw));
 unsigned char curves[4100]={0};pk_cf_nh_tables tables={curves,curves};
 pk_cf_nh_rng rng={lo,hi};uint16_t hold[2]={h0,h1};int16_t pcm[20];
 if(!pk_cf_nh_render(raw,pcm,n,1,&tables,&rng,hold))return 1;
 memcpy(placement_engine.tracks[3].nh,input,sizeof(raw));
 placement_engine.tracks[3].rng_low=lo;placement_engine.tracks[3].rng_high=hi;
 placement_engine.nh_hold[0]=h0;placement_engine.nh_hold[1]=h1;fm_hat_noise(1,n);
 expected[0]=rng.low;expected[1]=rng.high;expected[2]=hold[0];expected[3]=hold[1];
 expected[4]=pk_cf_ld16(raw,0x378);expected[5]=pk_cf_ld16(raw,0x388);
 return placement_engine.tracks[3].rng_low!=rng.low||placement_engine.tracks[3].rng_high!=rng.high||
 placement_engine.nh_hold[0]!=hold[0]||placement_engine.nh_hold[1]!=hold[1]||
 pk_cf_ld16(placement_engine.tracks[3].nh,0x378)!=expected[4]||pk_cf_ld16(placement_engine.tracks[3].nh,0x388)!=expected[5];
}
''')
 lib=out/'oracle.dylib';subprocess.run(['cc','-O3','-shared','-fPIC','-I'+str(ROOT/'modules/perky'),str(source),str(ROOT/'modules/perky/cf_noise_hat.c'),'-o',str(lib)],check=True)
 native=C.CDLL(str(lib));native.check.argtypes=[C.c_void_p,*[C.c_uint]*5,C.c_void_p]
 rng=random.Random(0x464d524e);cases=[]
 for k in range(4096):
  raw=bytearray(rng.randbytes(0x2df8));raw[0xb8]=0
  for i,delay in enumerate((573,1201,1538,3139,4804)):raw[0x3e4+2*i:0x3e6+2*i]=delay.to_bytes(2,'little')
  raw[0x2982:0x2984]=rng.randrange(4805).to_bytes(2,'little')
  for at in (0x378,0x37a,0x3dc):raw[at:at+2]=rng.choice((0,0,1,2,17,65535)).to_bytes(2,'little')
  raw[0x38d]=0;lo=rng.randrange(1<<32);hi=rng.randrange(1<<32);hold=rng.choice((0,0,1,2,17,65535));value=rng.randrange(65536);n=k%21
  expected=(C.c_uint*6)();assert native.check(C.c_char_p(bytes(raw)),lo,hi,hold,value,n,expected)==0,k
  cases.append((bytes(raw),lo,hi,hold,value,n,list(expected)))
 print('Original-renderer native tracker cases:',len(cases),flush=True)
 version=json.loads((W/'BUILD.json').read_text()).get('version','PKFM1');image=W/'probe'/f'mainos_{version}.bin';elf=image.parent/'platform/runtime.elf'
 boot=rt.g.emu.boot;rt.g.emu.boot=lambda image:boot(image,count=200000000)
 r,s=rt.machine(image,elf,True);u=r.uc;layout=s['placement_layout'];stride=rt.word(u,layout)
 # ABI-independent offsets exported by the target placement ledger.
 raw_at=s['placement_engine']+3*stride
 fields=out/'offsets.c';fields.write_text('#include <stdio.h>\n#include <stddef.h>\n#pragma pack(push,2)\n#include "cf_perky4.h"\n#pragma pack(pop)\nint main(void){printf("%zu %zu %zu\\n",offsetof(pk4_track,nh),offsetof(pk4_track,rng_low),offsetof(pk4_engine,nh_hold));}\n')
 subprocess.run(['cc','-I'+str(ROOT/'modules/perky'),str(fields),'-o',str(out/'offsets')],check=True)
 nh,ro,hp=map(int,subprocess.check_output([str(out/'offsets')],text=True).split())
 hp=rt.word(u,layout+48) # target pointer is four bytes; host pointers are eight
 for k,(raw,lo,hi,hold,value,n,expected) in enumerate(cases):
  u.mem_write(raw_at+nh,raw);u.mem_write(raw_at+ro,struct.pack('>II',lo,hi));u.mem_write(s['placement_engine']+hp,struct.pack('>HH',hold,value))
  rt.g.emu._call(u,s['fm_hat_noise'],(1,n))
  got=[rt.word(u,raw_at+ro),rt.word(u,raw_at+ro+4),*struct.unpack('>HH',u.mem_read(s['placement_engine']+hp,4)),int.from_bytes(u.mem_read(raw_at+nh+0x378,2),'little'),int.from_bytes(u.mem_read(raw_at+nh+0x388,2),'little')]
  assert got==expected,(k,got,expected)
  after=bytearray(u.mem_read(raw_at+nh,len(raw)));after[0x378:0x37a]=raw[0x378:0x37a];after[0x388:0x38a]=raw[0x388:0x38a];assert after==raw,(k,'unowned raw state')
 result=dict(status='PASS_ORIGINAL_WHITE_RENDERER_AND_LINKED_CF_TRACKER',native_cases=len(cases),target_cases=len(cases),image_sha256=sha(image),elf_sha256=sha(elf),source_sha256={str(p.relative_to(ROOT)):sha(p) for p in (Path(__file__).resolve(),ROOT/'tools/harness/perky_cf/full_map_rng.h',ROOT/'modules/perky/cf_noise_hat.c',source)})
 (W/'RNG_GATE.json').write_text(json.dumps(result,indent=2)+'\n');print(result['status'])
if __name__=='__main__':main()

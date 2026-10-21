#!/usr/bin/env python3
"""Actual-image sparse restores: tails, fallback, full dirty objects and ABI."""
import hashlib,json,subprocess
from pathlib import Path
import verify_perky_hybrid_runtime as rt
import unicorn.m68k_const as reg
ROOT=rt.ROOT;W=ROOT/'out/perky/hybrid/noise-hat-production'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 image=W/'probe/mainos_PKNHG3.bin';elf=image.parent/'platform/runtime.elf'
 boot=rt.g.emu.boot;rt.g.emu.boot=lambda image:boot(image,count=200000000)
 r,s=rt.machine(image,elf,True);u=r.uc
 if not any(lo<=0x48000000 and hi>=0x480fffff for lo,hi,_ in u.mem_regions()):u.mem_map(0x48000000,0x100000)
 out=W/'sparse-gate';out.mkdir(exist_ok=True)
 fields=('nh','nh_ctl','slap','slap_ctl','rng_low','rng_high','initialized_mask')
 layout=out/'layout.c';layout.write_text('#include <stddef.h>\n#include <stdio.h>\n#pragma pack(push,2)\n#include "cf_perky4.h"\n#pragma pack(pop)\nint main(void){printf("track %zu 0\\n",sizeof(pk4_track));\n'+''.join(f'printf("{f} %zu %zu\\n",offsetof(pk4_track,{f}),sizeof(((pk4_track*)0)->{f}));\n' for f in fields)+'}\n')
 subprocess.run(['cc','-I'+str(ROOT/'modules/perky'),str(layout),'-o',str(out/'layout')],check=True)
 offsets={f:(int(o),int(n)) for f,o,n in (line.split() for line in subprocess.check_output([str(out/'layout')],text=True).splitlines())}
 stride=rt.word(u,s['placement_layout']);assert stride==offsets['track'][0]
 canaries={getattr(reg,f'UC_M68K_REG_{p}{k}'):0x12340000+16*k for p,ks in (('D',range(2,8)),('A',range(2,7))) for k in ks}
 def call(name,args):
  for k,v in canaries.items():u.reg_write(k,v)
  rt.g.emu._call(u,s[name],args)
  assert all(u.reg_read(k)==v for k,v in canaries.items()),(name,'callee ABI')
 vectors=0
 for da in (0,2):
  for pa in (0,2):
   for n in [*range(130),9840,11768]:
    for dense in (False,True):
     src=0x48000020;dst=0x48040020+da;desc=0x48020020+pa
     blob=bytearray(n)
     for i in range(n):
      if dense or i%128<4:blob[i]=(i*73+(i>>8)*11+23)&255
     patches=[(i,int.from_bytes(blob[i:i+4],'big')) for i in range(0,n&~3,4) if any(blob[i:i+4])]
     count=len(patches) if len(patches)<=96 else 97
     packed=count.to_bytes(4,'big')+b''.join(i.to_bytes(4,'big')+v.to_bytes(4,'big') for i,v in patches[:96])
     u.mem_write(src-16,b'\x69'*16+bytes(blob)+b'\x96'*16);u.mem_write(dst-16,b'\xa5'*(n+32));u.mem_write(desc,packed)
     call('pk_prod_sparse_restore',(dst,src,n,desc))
     assert bytes(u.mem_read(dst-16,n+32))==b'\xa5'*16+bytes(blob)+b'\xa5'*16,(da,pa,n,dense,'restore')
     assert bytes(u.mem_read(src-16,n+32))==b'\x69'*16+bytes(blob)+b'\x96'*16,(n,'source')
     assert bytes(u.mem_read(desc,len(packed)))==packed,(n,'descriptor')
     vectors+=1
 # Whole-engine comparison: only the selected object/control, RNG, mask and
 # documented shared hold may change. The pristine oracle stays untouched.
 size=rt.sizes(elf)['placement_engine'];base=s['placement_engine'];pristine=bytes(u.mem_read(s['placement_pristine'],size));holds=rt.word(u,s['placement_layout']+48)
 generation=1;rt.w32(u,s['pk_prod_generation'],generation)
 for tr in range(4):call('placement_production_event',(tr,5))
 desc_size=4+96*8;desc_bytes={f:bytes(u.mem_read(s['pk_prod_sparse_'+f],4*desc_size)) for f in ('slap','hat')}
 cases=0;counts={}
 for tr in range(4):
  for field,algo,which in (('nh',5,'hat'),('slap',8,'slap')):
   desc=s['pk_prod_sparse_'+which]+desc_size*tr;count=rt.word(u,desc);assert count<=96;counts[f'{tr}:{field}']=count
   for fallback in (False,True):
    for corner in range(32):
     for f in (field,field+'_ctl'):
      off,n=offsets[f];u.mem_write(base+tr*stride+off,bytes((17*i+37*corner+91)&255 for i in range(n)))
     for f in ('rng_low','rng_high','initialized_mask'):
      off,n=offsets[f];u.mem_write(base+tr*stride+off,b'\xa5'*n)
     before=bytearray(u.mem_read(base,size));expected=bytearray(before)
     for f in (field,field+'_ctl'):
      off,n=offsets[f];at=tr*stride+off;expected[at:at+n]=pristine[at:at+n]
     for f,value in (('rng_low',1),('rng_high',0),('initialized_mask',1<<algo)):
      off,n=offsets[f];at=tr*stride+off;expected[at:at+n]=value.to_bytes(n,'big')
     if tr==3:expected[holds:holds+4]=bytes(4)
     generation+=1;rt.w32(u,s['pk_prod_generation'],generation)
     if fallback:rt.w32(u,desc,97)
     call('placement_production_event',(tr,algo))
     assert bytes(u.mem_read(base,size))==expected,(tr,field,fallback,corner,'whole engine')
     assert bytes(u.mem_read(s['placement_clocks']+12*tr,12))==bytes(12)
     if fallback:rt.w32(u,desc,count)
     cases+=1
 assert bytes(u.mem_read(s['placement_pristine'],size))==pristine
 for f,b in desc_bytes.items():assert bytes(u.mem_read(s['pk_prod_sparse_'+f],len(b)))==b
 result=dict(status='PASS_SPARSE_RESTORE_BYTES_TAILS_FALLBACK_FULL_ENGINE_AND_ABI',vectors=vectors,dirty_generation_cases=cases,patch_counts=counts,image_sha256=sha(image),elf_sha256=sha(elf),source_sha256={str(p.relative_to(ROOT)):sha(p) for p in (Path(__file__),ROOT/'tools/harness/perky_cf/production_sparse.h',ROOT/'modules/perky/production_sparse.s')})
 (W/'SPARSE_GATE.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()

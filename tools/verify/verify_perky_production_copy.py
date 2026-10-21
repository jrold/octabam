#!/usr/bin/env python3
"""Execute final-image pristine restore with guards and ABI canaries."""
import json,hashlib,subprocess
from pathlib import Path
import verify_perky_hybrid_runtime as rt
import unicorn.m68k_const as reg
ROOT=rt.ROOT;W=ROOT/'out/perky/hybrid/noise-hat-production'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 image=W/'probe/mainos_PKNHG3.bin';elf=W/'probe/platform/runtime.elf'
 boot=rt.g.emu.boot;rt.g.emu.boot=lambda image:boot(image,count=200000000)
 r,s=rt.machine(image,elf,True);u=r.uc
 if not any(lo<=0x48000000 and hi>=0x480fffff for lo,hi,_ in u.mem_regions()):u.mem_map(0x48000000,0x100000)
 lengths=[*range(97),9838,9840,11768,118096];cases=0
 for da in (0,2):
  for sa in (0,2):
   for n in lengths:
    src=0x48000020+sa;dst=0x48040020+da
    content=bytes(((i*73+(i>>8)*11)&255) for i in range(n))
    u.mem_write(src-16,b'\x69'*16+content+b'\x96'*16)
    u.mem_write(dst-16,b'\xa5'*(n+32))
    canaries={getattr(reg,f'UC_M68K_REG_{prefix}{k}'):0x12340000+16*k for prefix,ks in (('D',range(2,8)),('A',range(2,7))) for k in ks}
    for k,v in canaries.items():u.reg_write(k,v)
    rt.g.emu._call(u,s['pk_prod_copy'],(dst,src,n))
    assert bytes(u.mem_read(dst-16,n+32))==b'\xa5'*16+content+b'\xa5'*16,(da,sa,n,'destination')
    assert bytes(u.mem_read(src-16,n+32))==b'\x69'*16+content+b'\x96'*16,(da,sa,n,'source')
    assert all(u.reg_read(k)==v for k,v in canaries.items()),(da,sa,n,'ABI')
    cases+=1
 result=dict(status='PASS_LINKED_COPY_BYTES_GUARDS_AND_CALLEE_ABI',cases=cases,lengths=lengths,alignments=[0,2],image_sha256=sha(image),elf_sha256=sha(elf),source_sha256={str(p.relative_to(ROOT)):sha(p) for p in (Path(__file__),ROOT/'modules/perky/production_copy.s')})
 (W/'COPY_GATE.json').write_text(json.dumps(result,indent=2)+'\n');print(result['status'],cases)
if __name__=='__main__':main()

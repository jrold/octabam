#!/usr/bin/env python3
"""Target assembly vs the original wrapping Slap filter arithmetic."""
import argparse,json,random,struct
from pathlib import Path
import verify_perky_hybrid_runtime as rt
import calibrate_perky_hybrid_budget as c
import unicorn.m68k_const as regs
def s32(v):return (v+0x80000000)%0x100000000-0x80000000
def clamp(v):return max(-32767,min(32767,v))
def step(s,nv):
 coeff,damp,first,second,velocity=s
 p=s32(velocity*coeff)
 if p<0:p+=65535
 first=clamp(s32(first+(p>>16)))
 second=clamp(s32(s32(nv-first)-(s32(velocity*damp)>>10)))
 p=s32(second*coeff)
 if p<0:p+=65535
 velocity=clamp(s32(velocity+(p>>16)))
 return [coeff,damp,first,second,velocity]
def main():
 p=argparse.ArgumentParser();p.add_argument('--work',type=Path,required=True);a=p.parse_args();w=a.work.resolve()
 build=json.loads((w/'BUILD.json').read_text());image=w/'probe'/('mainos_'+build['version']+'.bin');elf=image.parent/'platform/runtime.elf'
 boot=rt.g.emu.boot;rt.g.emu.boot=lambda image:boot(image,count=200000000)
 r,s=rt.machine(image,elf,True);u=r.uc
 if not any(lo<=0x48000000 and hi>=0x480fffff for lo,hi,_ in u.mem_regions()):u.mem_map(0x48000000,0x100000)
 raw,noise,out=0x48040000,0x48041000,0x48042000;rng=random.Random(0x53464c54)
 edges=[-0x80000000,-32768,-32767,-1,0,1,32767,32768,0x7fffffff]
 for case in range(4096):
  n=(0,1,17,20)[case%4];state=[rng.randrange(65536),rng.randrange(65536),*(rng.choice(edges) if case<1024 else rng.randrange(-0x80000000,0x80000000) for _ in range(3))]
  pcm=[rng.choice((-32768,-32767,-1,0,1,32767)) if case<1024 else rng.randrange(-32768,32768) for _ in range(n)]
  u.mem_write(raw,struct.pack('>5i',*state));u.mem_write(noise,struct.pack('>'+str(n)+'h',*pcm)+b'\xa5\x5a');u.mem_write(out,b'\xa5'*84)
  preserved={getattr(regs,'UC_M68K_REG_'+name):((0x9e3779b9*(i+1))^case)&0xffffffff for i,name in enumerate(('D2','D3','D4','D5','D6','D7','A2','A3','A4','A5','A6'))}
  for reg,value in preserved.items():u.reg_write(reg,value)
  rt.g.emu._call(u,s['pk_budget_slap_filter'],(raw,noise,out,n))
  assert all(u.reg_read(reg)==value for reg,value in preserved.items()),(case,'callee registers')
  expected=[]
  for nv in pcm:
   state=step(step(state,nv),nv);expected.append(state[2])
  assert bytes(u.mem_read(raw,20))==struct.pack('>5i',*state),(case,'state')
  assert bytes(u.mem_read(out,84))==struct.pack('>'+str(n)+'i',*expected)+b'\xa5'*(84-4*n),(case,'samples')
 result=dict(status='PASS_ORIGINAL_WRAP_CLAMP_FILTER',cases=4096,native_counts=[0,1,17,20],callee_registers_preserved=True,image_sha256=c.sha(image),elf_sha256=c.sha(elf),source_sha256={str(p.relative_to(c.ROOT)):c.sha(p) for p in (Path(__file__).resolve(),c.ROOT/'modules/perky/budget_transport.s')})
 c.save(w/'FILTER_GATE.json',result);print(result)
if __name__=='__main__':main()

#!/usr/bin/env python3
"""Exhaust the fixed-tap assembly at every ring cursor, including wraps."""
import argparse,json,struct
from pathlib import Path
import verify_perky_hybrid_runtime as rt
import calibrate_perky_hybrid_budget as c
import unicorn.m68k_const as regs
def main():
 p=argparse.ArgumentParser();p.add_argument('--work',type=Path,required=True);a=p.parse_args();w=a.work.resolve()
 build=json.loads((w/'BUILD.json').read_text());image=w/'probe'/('mainos_'+build['version']+'.bin');elf=image.parent/'platform/runtime.elf'
 boot=rt.g.emu.boot;rt.g.emu.boot=lambda image:boot(image,count=200000000)
 r,s=rt.machine(image,elf,True);u=r.uc
 if not any(lo<=0x48000000 and hi>=0x480fffff for lo,hi,_ in u.mem_regions()):u.mem_map(0x48000000,0x100000)
 ring=0x48040000;out=0x48050000;last=0x48051000
 values=[((i*16381)^(i>>3)^0xa55a)&65535 for i in range(4805)]
 u.mem_write(ring,struct.pack('<4805H',*values)+b'\xa5\x5a');cases=0
 for cursor in range(4805):
  for n in (0,1,17,20):
   u.mem_write(out,b'\xa5'*210);u.mem_write(last,b'\x5a'*14)
   preserved={getattr(regs,'UC_M68K_REG_'+name):((0x9e3779b9*(i+1))^cursor^n)&0xffffffff for i,name in enumerate(('D2','D3','D4','D5','D6','D7','A2','A3','A4','A5','A6'))}
   for reg,value in preserved.items():u.reg_write(reg,value)
   rt.g.emu._call(u,s['pk_budget_gather_taps'],(ring,out,cursor,n,last))
   assert all(u.reg_read(reg)==value for reg,value in preserved.items()),(cursor,n,'callee registers')
   from unicorn.m68k_const import UC_M68K_REG_D0
   assert u.reg_read(UC_M68K_REG_D0)==(cursor+n)%4805
   expected=[values[(cursor+i-delay)%4805] for i in range(n) for delay in (573,1201,1538,3139,4804)]
   raw=struct.pack('>'+str(5*n)+'H',*expected)
   assert bytes(u.mem_read(out,210))==raw+b'\xa5'*(210-len(raw)),(cursor,n,'packet')
   want=struct.pack('>5H',*expected[-5:]) if n else b'\x5a'*10
   assert bytes(u.mem_read(last,14))==want+b'\x5a'*4,(cursor,n,'carry taps')
   cases+=1
 result=dict(status='PASS_ALL_RING_CURSORS_PACKET_AND_CARRY',cases=cases,native_counts=[0,1,17,20],callee_registers_preserved=True,image_sha256=c.sha(image),elf_sha256=c.sha(elf),source_sha256={str(p.relative_to(c.ROOT)):c.sha(p) for p in (Path(__file__).resolve(),c.ROOT/'modules/perky/budget_transport.s')})
 c.save(w/'TAP_GATE.json',result);print(result)
if __name__=='__main__':main()

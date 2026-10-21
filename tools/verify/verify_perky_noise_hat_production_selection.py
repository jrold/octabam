#!/usr/bin/env python3
"""Execute linked production signature/persistence hooks for all four voices."""
import json
from pathlib import Path
from unicorn.m68k_const import UC_M68K_REG_A0,UC_M68K_REG_D0,UC_M68K_REG_D1
import verify_perky_hybrid_runtime as rt
ROOT=rt.ROOT;W=ROOT/'out/perky/hybrid/noise-hat-production'
def main():
 image=W/'probe/mainos_PKNHG3.bin';elf=W/'probe/platform/runtime.elf'
 boot=rt.g.emu.boot
 rt.g.emu.boot=lambda image:boot(image,count=200000000)
 r,s=rt.machine(image,elf,True);u=r.uc;call=rt.g.emu._call
 if not any(lo<=0x100a0000<=hi for lo,hi,_ in u.mem_regions()):u.mem_map(0x100a0000,0x10000)
 bank=rt.word(u,rt.g.emu.PART_PTR);u.mem_map(bank+0x100000,0x100000);u.mem_write(bank+0x100000,bytes(u.mem_read(bank,0x100000)))
 cases=[]
 for b in range(2):
  for part in range(4):
   rt.w32(u,rt.g.emu.PART_PTR,bank+b*0x100000);u.mem_write(0x100b14cf,bytes((part,)))
   base=bank+b*0x100000+0x8ed80+part*0x18b2
   for voice,track in enumerate((0,1,4,5)):
    u.mem_write(base+0x22+track,b'\x01')
    def mark(on):
     u.reg_write(UC_M68K_REG_A0,base);u.reg_write(UC_M68K_REG_D0,track);u.reg_write(UC_M68K_REG_D1,int(on));call(u,s['pk_sig_write'])
    mark(False);mark(True)
    values=bytes((17+part,94,(b+part)%(2 if voice==3 else 3),73,25,(voice+part)%3))
    u.mem_write(base+48+30*track,values)
    mark(True)
    assert bytes(u.mem_read(base+48+30*track,6))==values,'reselect overwrote saved selectors'
    assert bytes(u.mem_read(base+60+30*track,3))==b'PK\x01'
    assert bytes(u.mem_read(0x100a4ece+part*0x18b2+60+30*track,3))==b'PK\x01'
    # Actual stock validation adapter must restore all twelve source bytes.
    before=bytes(u.mem_read(base+48+30*track,6))+bytes(u.mem_read(base+0x1e0+30*track,6))
    call(u,s['pk_validate_part'],(base,))
    after=bytes(u.mem_read(base+48+30*track,6))+bytes(u.mem_read(base+0x1e0+30*track,6))
    assert after==before,'validator changed saved PERKY selectors'
    cases.append(dict(bank=b,part=part,track=track+1,controls=list(values)))
 # UI ticks do not own source state or generation resets.
 size=rt.sizes(elf)['placement_engine'];before=bytes(u.mem_read(s['placement_engine'],size))
 for t in (0,1,4,5,2,7):u.mem_write(0x100b14cc,bytes((t,)));call(u,s['pk_ui_tick'])
 assert before==bytes(u.mem_read(s['placement_engine'],size))
 report=dict(status='PASS_LINKED_SIGNATURE_VALIDATION_AND_UI_SCOPES',cases=cases,image_sha256=rt.digest(image),elf_sha256=rt.digest(elf),source_sha256={str(Path(__file__).resolve().relative_to(ROOT)):rt.digest(Path(__file__))},scope='Two bank pointers, all four Parts and T1/T2/T5/T6. Linked signature writer and stock validation adapter; UI does not reset synthesis. File save/reload is separate.')
 (W/'SELECTION.json').write_text(json.dumps(report,indent=2)+'\n');print(report['status'],len(cases))
if __name__=='__main__':main()

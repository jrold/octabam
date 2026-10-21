#!/usr/bin/env python3
"""Versioned project signatures, all family selectors and stock validation."""
import json
from pathlib import Path
from unicorn.m68k_const import UC_M68K_REG_A0,UC_M68K_REG_D0,UC_M68K_REG_D1
import verify_perky_hybrid_runtime as rt
import measure_perky_full_map as f
ROOT=rt.ROOT;W=f.W
def main():
 image=W/'probe'/f'mainos_{f.image_name()}.bin';elf=image.parent/'platform/runtime.elf';boot=rt.g.emu.boot;rt.g.emu.boot=lambda image:boot(image,count=200000000)
 r,s=rt.machine(image,elf,True);u=r.uc;call=rt.g.emu._call
 if not any(lo<=0x100a0000<=hi for lo,hi,_ in u.mem_regions()):u.mem_map(0x100a0000,0x10000)
 bank=rt.word(u,rt.g.emu.PART_PTR);u.mem_map(bank+0x100000,0x100000);u.mem_write(bank+0x100000,bytes(u.mem_read(bank,0x100000)))
 cases=[]
 for b in range(2):
  for part in range(4):
   rt.w32(u,rt.g.emu.PART_PTR,bank+b*0x100000);u.mem_write(0x100b14cf,bytes((part,)));base=bank+b*0x100000+0x8ed80+part*0x18b2
   for voice,track in enumerate((0,1,4,5)):
    u.mem_write(base+0x22+track,b'\x01');at=base+60+30*track
    def check():u.reg_write(UC_M68K_REG_A0,base);u.reg_write(UC_M68K_REG_D0,track);call(u,s['pk_sig_check']);return u.reg_read(UC_M68K_REG_D0)
    def mark():u.reg_write(UC_M68K_REG_A0,base);u.reg_write(UC_M68K_REG_D0,track);u.reg_write(UC_M68K_REG_D1,1);call(u,s['pk_sig_write'])
    u.mem_write(at,b'PK\x01');u.mem_write(base+48+30*track,bytes((17,94,2,73,25,2)));assert check()==0,'legacy selector layout admitted'
    mark();assert check()==1;assert bytes(u.mem_read(at,3))==b'PK\x02';assert bytes(u.mem_read(base+48+30*track,6))==bytes((64,64,0,64,64,0)),'legacy layout did not receive fresh defaults'
    values=bytes((17+part,94,2,73,25,(voice+part)%3));u.mem_write(base+48+30*track,values);mark();assert bytes(u.mem_read(base+48+30*track,6))==values
    assert bytes(u.mem_read(0x100a4ece+part*0x18b2+60+30*track,3))==b'PK\x02'
    call(u,s['pk_validate_part'],(base,));assert bytes(u.mem_read(base+48+30*track,6))==values
    u.mem_write(0x100b14cc,bytes((track,)));call(u,s['pk_track_page'],(base+0x22+track,));page=u.reg_read(UC_M68K_REG_D0);desc=page-0x38
    assert rt.word(u,desc+0xd2+8)==3 and rt.word(u,desc+0xd2+20)==3,'family or MODE count wrong'
    cases.append(dict(bank=b,part=part,voice=voice,track=track+1,legacy_rejected=True,fresh_defaults=True,reselect_preserves=True,algo_count=3,mode_count=3,controls=list(values)))
 size=rt.sizes(elf)['placement_engine'];before=bytes(u.mem_read(s['placement_engine'],size))
 for track in (0,1,4,5,2,7):u.mem_write(0x100b14cc,bytes((track,)));call(u,s['pk_ui_tick'])
 assert bytes(u.mem_read(s['placement_engine'],size))==before
 result=dict(status='PASS_FULL_MAP_V2_SIGNATURE_SELECTION_VALIDATION_AND_UI',cases=cases,image_sha256=rt.digest(image),elf_sha256=rt.digest(elf),source_sha256={str(Path(__file__).resolve().relative_to(ROOT)):rt.digest(Path(__file__))},policy='PK/1 layouts are not admitted as PK/2. Explicit machine creation seeds new layout defaults; PK/2 reselect preserves all controls. No legacy project is modified automatically.')
 (W/'SELECTION.json').write_text(json.dumps(result,indent=2)+'\n');print(result['status'],len(cases))
if __name__=='__main__':main()

#!/usr/bin/env python3
"""Actual ColdFire repeated initialization cannot retain asset readiness."""
import json
from pathlib import Path
import measure_perky_full_map as f
import verify_perky_hybrid_runtime as rt
ROOT=f.ROOT;W=f.W
def main():
 image=W/'probe'/f'mainos_{f.image_name()}.bin';elf=W/'probe/platform/runtime.elf';boot=rt.g.emu.boot;rt.g.emu.boot=lambda image:boot(image,count=200000000)
 r,s=rt.machine(image,elf,True);u=r.uc;cases=[]
 for status in (2,-1,1):
  rt.w32(u,s['fma_ready'],0x41484f4b);rt.w32(u,s['fma_status'],status&0xffffffff)
  for name,n in (('closed',20202),('open',172800),('ride',259106)):u.mem_write(s['pk_placement_'+name],b'\xa5'*n)
  rt.g.emu._call(u,s['pk_hybrid_boot_init']);assert u.reg_read(rt.g.emu.UC_M68K_REG_D0)==1
  assert rt.word(u,s['fma_ready'])==0x41484e4f and rt.word(u,s['fma_status'])==0
  for name,n in (('closed',20202),('open',172800),('ride',259106)):assert bytes(u.mem_read(s['pk_placement_'+name],n))==bytes(n)
  cases.append(dict(prior_status=status,readiness_invalidated=True,all_asset_BSS_cleared=True,boot_succeeded=True))
 result=dict(status='PASS_LINKED_CF_REPEATED_BOOT_INVALIDATES_CARD_ASSET_READINESS',cases=cases,image_sha256=f.c.sha(image),elf_sha256=f.c.sha(elf),source_sha256={str(p):f.c.sha(p) for p in (Path(__file__),ROOT/'modules/perky/full_map_card_assets.h',ROOT/'tools/perky/build_perky_full_map_card.py')})
 (W/'CARD_RESET_GATE.json').write_text(json.dumps(result,indent=2)+'\n');print(result['status'])
if __name__=='__main__':main()

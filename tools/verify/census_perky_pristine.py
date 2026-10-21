#!/usr/bin/env python3
"""Read-only census of boot-initialized candidate algorithm objects."""
import ctypes,json,subprocess
from pathlib import Path
import verify_perky_hybrid_runtime as rt
ROOT=rt.ROOT;W=ROOT/'out/perky/hybrid/pristine-census'
FIELDS=('fold1','fold2','karplus','res_snare','res_bass','res_nt','nh','sd','cd','slap','wt','nt_m1','nt_shared')
def main():
 W.mkdir(exist_ok=True)
 c=W/'layout.c';c.write_text('#include <stddef.h>\n#include <stdio.h>\n#pragma pack(push,2)\n#include "cf_perky4.h"\n#pragma pack(pop)\nint main(void){\n'+''.join(f'printf("{f} %zu %zu\\n",offsetof(pk4_track,{f}),sizeof(((pk4_track*)0)->{f}));\n' for f in FIELDS)+'}\n')
 subprocess.run(['cc','-I'+str(ROOT/'modules/perky'),str(c),'-o',str(W/'layout')],check=True)
 fields=[(f,int(o),int(n)) for f,o,n in (line.split() for line in subprocess.check_output([str(W/'layout')],text=True).splitlines())]
 image=ROOT/'out/perky/hybrid/noise-hat-production-g2/probe/mainos_PKNHG2.bin';elf=image.parent/'platform/runtime.elf'
 boot=rt.g.emu.boot;rt.g.emu.boot=lambda image:boot(image,count=200000000)
 r,syms=rt.machine(image,elf,True);u=r.uc;out=[]
 stride=int.from_bytes(u.mem_read(syms['placement_layout'],4),'big')
 for tr in range(4):
  rows={}
  for f,o,n in fields:
   blob=bytes(u.mem_read(syms['placement_pristine']+tr*stride+o,n));words=[blob[i:i+4] for i in range(0,n,4)]
   rows[f]=dict(bytes=n,nonzero_bytes=sum(bool(x) for x in blob),nonzero_words=sum(any(x) for x in words),word_zero_runs=sum(not any(x) and (i==0 or any(words[i-1])) for i,x in enumerate(words)))
  out.append(rows)
 (W/'CENSUS.json').write_text(json.dumps(dict(stride=stride,tracks=out),indent=2)+'\n')
 print(json.dumps(out[3],indent=2))
if __name__=='__main__':main()

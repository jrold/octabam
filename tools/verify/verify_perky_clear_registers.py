#!/usr/bin/env python3
"""Compare stock/modified startup's complete continuation register contract.

Complements the all-Y-word differential. This checks accumulators, operands,
condition flags, OMR, loop state, stack depth and every R/N/M register. PC and
the inactive stack backing words naturally depend on the routine address.
"""
import os, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'tools/verify'),str(ROOT/'tools'),str(ROOT/'tools/build'),str(ROOT/'tools/perky'),str(ROOT/'modules/perky')]
os.environ.setdefault('REMIX','perky-machine')
import verify_perky_controlled_voice_exec as c
import perky_fragmented_image as F
from verify_perky_shard_emit import shipping_payload


def main():
    c.OUT.mkdir(parents=True,exist_ok=True);c.build_host()
    work=ROOT/'out/perky/clear-registers';work.mkdir(parents=True,exist_ok=True)
    asm=shipping_payload()
    # Exact guarded stock words from install(), including the generic B
    # mailbox move. The all-Y differential independently checks the stores.
    stock={'A':[0x57f400,0x8000,0x64f400,0x4000,0x65f413,0x30000,0x06cf00,0x49,0x5e5c00,0x5e5d00],
           'B':[0x57f400,0x8100,0x64f400,0x3f00,0x65f400,0x37f00,0x200013,0x06cf00,0x4a,0x5e5c00,0x5e5d00]}
    script=work/'one.script';script.write_text(' '.join(['0']*12+['-1'])+'\n')
    data=work/'empty.data';data.write_text('')
    for tag in ('A','B'):
        rows=[]
        origin,modified=F.plan(asm,tag)[0][-1]
        for name,start,words in [('stock',0x40,stock[tag]+[0x00000c]),('protected',origin,modified)]:
            binary=work/f'{tag}-{name}.bin';binary.write_bytes(b''.join(w.to_bytes(3,'little') for w in words))
            registers=work/f'{tag}-{name}.regs'
            cmd=[str(c.HOST),'-code',str(binary),'-org',f'{start:x}','-entry',f'{start:x}','-data',str(data),'-script',str(script),'-out',str(work/'unused.raw'),'-registers',str(registers)]
            p=subprocess.run(cmd,cwd=ROOT,text=True,capture_output=True,check=True)
            (work/f'{tag}-{name}.log').write_text(p.stdout+p.stderr)
            rows.append(registers.read_text().split())
        assert rows[0]==rows[1],(tag,[(i,a,b) for i,(a,b) in enumerate(zip(*rows)) if a!=b])
        print(f'[PASS] {tag}: stock/tail-preserving startup register state identical ({len(rows[0])} accumulator/operand/control/R/N/M fields)')


if __name__=='__main__':main()

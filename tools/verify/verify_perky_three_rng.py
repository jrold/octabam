#!/usr/bin/env python3
"""Execute Fold's optimized 64-bit LCG against independent integer arithmetic."""
import random, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'tools/verify'),str(ROOT/'tools/perky')]
import verify_perky_controlled_voice_exec as c
import fold_rng_source


def main():
    c.OUT=ROOT/'out/perky/three-rng';c.OUT.mkdir(parents=True,exist_ok=True)
    c.build_host()
    source='pk_controlled_voice_exec:\n        move #>$200,r5\n'
    for i in range(4):
        source+=f'''        move x:>${0x102+3*i:x},a
        asl #$7,a,a
        move x:>${0x101+3*i:x},x0
        add x0,a
        asl #$7,a,a
        move x:>${0x100+3*i:x},x0
        add x0,a
        move a1,x:(r5+${i:x})
'''
    source+='        jsrl pk_rng_step\n        rts\n'+fold_rng_source.generate()
    binary,entry=c.assemble(source)
    rng=random.Random(0x504b5931)
    cases=[0,1,(1<<64)-1,0xffff,0xffffffff,0xffffffffffff]
    cases+=[1<<i for i in range(64)]+[((1<<64)-1)^(1<<i) for i in range(64)]
    cases+=[rng.getrandbits(64) for _ in range(5000)]
    blocks=[]
    for value in cases:
        blocks.append((tuple(bit for i in range(4) for bit in
                             ((value>>(16*i))&127,(value>>(16*i+7))&127,(value>>(16*i+14))&3)),-1))
    _,states,_=c.run(binary,entry,'carry',list([0]*58+[0]*4),[],blocks)
    for seed,state in zip(cases,states):
        expected=(seed*0x5851f42d4c957f2d+1)&((1<<64)-1)
        limbs=[(expected>>(16*i))&65535 for i in range(4)]
        assert state[:4]==limbs,(hex(seed),'persistent limbs',state[:4],limbs)
        assert [state[i] for i in (8,9,16,17)]==limbs,(hex(seed),'caller scratch ABI')
    print(f'[PASS] Fold RNG: {len(cases)} independent 64-bit carry/edge/random cases, exact state and scratch ABI')


if __name__=='__main__':main()

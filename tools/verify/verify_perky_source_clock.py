#!/usr/bin/env python3
"""Execute the native-rate FIFO adapter against exact rational interpolation."""
import random, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'tools/verify'),str(ROOT/'tools/perky')]
import verify_perky_controlled_voice_exec as c
import source_clock as clock

WRAPPER='''pk_controlled_voice_exec:
        move #>$ffffff,m0
        move #>$ffffff,m1
        move #>$ffffff,m2
        move #>$ffffff,m3
        ; The caller's M7 is not ours to reset. Coefficient lookup uses M3,
        ; which the source dispatcher explicitly sets to linear mode.
        move #>$3f,m7
        move #>$0,r0
        clr a
        do #>$20,p3clock_clear
        move a1,x:(r0)+
p3clock_clear:
        nop
        move a1,x:>$39b3
        move x:>$100,n7
        jsrl pk_clock_prepare
        move x:>$39b8,r2
        move #>$1000,r3
        do n7,p3clock_fill
        move r2,n3
        move y:(r3+n3),a
        move a1,x:(r0)+
        move a1,x:(r0)+
        move (r2)+
p3clock_fill:
        nop
        move r2,x:>$39b8
        jsrl pk_clock_finish
        move #>$39b0,r1
        move #>$200,r2
        do #>$9,p3clock_capture
        move x:(r1)+,a
        move a1,x:(r2)+
p3clock_capture:
        nop
        rts
'''


def main():
    c.OUT=ROOT/'out/perky/source-clock';c.OUT.mkdir(parents=True,exist_ok=True)
    c.build_host();c.CYCLE_METER=True
    binary,entry=c.assemble(WRAPPER+clock.PREPARE+clock.FINISH)
    generator=random.Random(160147)
    samples=[generator.randrange(-32768,32768) for _ in range(2048)]
    count=0;meters=[]
    for phase in range(147):
        valid=int(phase>=13)
        def data(path,state,tables):
            path.write_text(f'X 39b0 {phase:06x} {valid:06x} {samples[0]&0xffffff:06x} 000000 000000 000000 000000 000000 {valid:06x}\n'
                            +'Y f3f '+' '.join(f'{v:06x}' for v in clock.coefficient_words())+'\n'
                            +'Y 1000 '+' '.join(f'{v&0xffffff:06x}' for v in samples)+'\n')
            return []
        c.write_data=data
        lengths=list(range(1,17))+[generator.randrange(1,17) for _ in range(64)]
        audio,states,_=c.run(binary,entry,'phase',[],[],[(tuple([n]+[0]*11),-1) for n in lengths])
        oracle=clock.Clock();oracle.phase=phase;oracle.tail=[samples[0]] if valid else []
        index=valid
        for n,pcm,state in zip(lengths,audio,states):
            needed=oracle.needed(n)
            expected=oracle.render(samples[index:index+needed],n);index+=needed
            assert all(abs(a-b)<=1 for a,b in zip(pcm[:n],expected)),(phase,n,'rational PCM',pcm[:n],expected)
            assert not any(pcm[n:]),(phase,n,'output extent')
            assert state[0]==oracle.phase and state[1]==len(oracle.tail),(phase,n,'FIFO phase/valid')
            if oracle.tail:assert state[2]==(oracle.tail[0]&0xffffff),(phase,n,'carry PCM')
            assert state[8]==index,(phase,n,'native render count',state[8],index)
            count+=1
        meters+=list(map(int,(c.OUT/'phase.meter').read_text().split()))
    print(f'[PASS] native 48000 -> OT 44100 FIFO: {count} executed segments, all 147 phases, lengths 1..16, continuity; <=1 signed24 LSB vs rational interpolation; worst {max(meters)} modeled adapter cycles')


if __name__=='__main__':main()

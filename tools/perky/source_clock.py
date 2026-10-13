"""48 kHz native FIFO clock to 44.1 kHz stock blocks, ratio 160/147.

The renderer always computes original native samples. This adapter owns
only buffered PCM, fractional position and integration gain. A trigger clears
the FIFO as PerkyBits does. It never rewrites oscillator/envelope state.
"""
BASE=0x39b0
BUFFER=0x3980
COEFFICIENTS=0xf3f

PREPARE='''pk_clock_reset:
        clr a
        move a1,x:>$39b0
        move a1,x:>$39b1
        move a1,x:>$39b2
        rts
pk_clock_prepare:
        move n7,a
        move a1,x:>$39b4
        move a1,x0
        move #>$d,y0
        mpy y0,x0,a
        asr a
        move a0,b
        move x:>$39b0,x0
        add x0,b
        move #>$0,x1
        cmp #>$93,b
        blt p3clock_small
        sub #>$93,b
        move #>$1,x1
        cmp #>$93,b
        blt p3clock_small
        sub #>$93,b
        move #>$2,x1
p3clock_small:
        move b1,x:>$39b6
        move #>$0,a
        cmp #>$d,b
        blt p3clock_tail
        move #>$1,a
p3clock_tail:
        move a1,x:>$39b7
        move a1,y0
        move x:>$39b4,a
        add x1,a
        move a1,x:>$39b5
        add y0,a
        move x:>$39b1,x0
        sub x0,a
        move a1,n7
        move #>$3980,r0
        tst x0
        beq p3clock_ready
        move x:>$39b2,a
        move a1,x:(r0)+
        move a1,x:(r0)+
p3clock_ready:
        rts
'''.replace('        tst x0','        move x0,a\n        tst a')

FINISH='''pk_clock_finish:
        move #>$3980,r1
        move #>$f3f,r3
        move x:>$39b3,a
        asl a
        move a1,r0
        move x:>$39b0,a
        move a1,n3
        move x:>$39b4,b
        ; Use stock's DO B form (06cf00), not the unprobed B1 form.
        do b,p3clock_loop
        move x:(r1),a
        asl #$5,a,a
        move a1,x1
        move x:(r1+$2),a
        asl #$5,a,a
        sub x1,a
        move a1,x0
        ; Indexed Y -> accumulator is the hardware-tested table-reader form.
        move y:(r3+n3),a
        move a1,y0
        mpy y0,x0,a
        move a1,x0
        move x1,a
        add x0,a
        move a1,x:(r0)+
        move a1,x:(r0)+
        move (r1)+
        move (r1)+
        move n3,a
        add #>$d,a
        cmp #>$93,a
        blt p3clock_phase
        sub #>$93,a
        move (r1)+
        move (r1)+
p3clock_phase:
        move a1,n3
p3clock_loop:
        nop
        move x:>$39b7,a
        move a1,x:>$39b1
        tst a
        beq p3clock_done
        move x:(r1),a
        move a1,x:>$39b2
p3clock_done:
        move x:>$39b6,a
        move a1,x:>$39b0
        move x:>$39b3,a
        move x:>$39b4,x0
        add x0,a
        move a1,x:>$39b3
        rts
'''


def coefficient_words():
    return [(i*(1<<23))//147 for i in range(147)]


class Clock:
    """Independent rational oracle, using integer PCM and exact fractions."""
    def __init__(self):self.phase=0;self.tail=[]
    def reset(self):self.phase=0;self.tail=[]
    def needed(self,n):
        consumed,phase=divmod(self.phase+160*n,147)
        return consumed+(phase>=13)-len(self.tail)
    def render(self,pcm,n):
        data=self.tail+list(pcm);out=[];index=0;phase=self.phase
        for _ in range(n):
            a=data[index];b=data[index+1] if phase else a
            out.append((a<<5)+(((b-a)<<5)*phase//147))
            advance,phase=divmod(phase+160,147);index+=advance
        self.tail=data[index:]
        assert len(self.tail)==(phase>=13),(phase,len(self.tail))
        self.phase=phase
        return out

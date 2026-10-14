; GATE VERB: the reverb of Mutable Instruments Clouds (clouds/dsp/fx/reverb.h,
; MIT, Copyright 2014 Emilie Gillet), a Griesinger/Dattorro plate: four input
; allpasses, then two halves of two allpasses and a delay, with a smeared first
; allpass and a modulated second delay. Port, not a copy: fixed point, the delay
; lengths scaled by 0.984 (16,120 words in one ring, the top 256 words of the
; allocator's 16,384 are never written: the mailbox and LOAD METER sit there),
; 24-bit buffer words instead of Clouds' 12-bit (a value is held as value/8, so
; the buffer's range matches Clouds' +-8), parabolic LFOs updated once a block. A gate on the wet output
; (p5 GATE): hold 2048 + 256 k samples after the input falls under a threshold, then a
; ramp to silence; the tank keeps ringing underneath.
;
; Layout (cell k of line j is y:(r5 - base_j - k), r5 the write pointer, modulo 16120):
;   ap1    base     0 length  111
;   ap2    base   112 length  159
;   ap3    base   272 length  237
;   ap4    base   510 length  393
;   dap1a  base   904 length 1627
;   dap1b  base  2532 length 2005
;   del1   base  4538 length 3356
;   dap2a  base  7895 length 1882
;   dap2b  base  9778 length 1636
;   del2   base 11415 length 4705
;
; Scalars at x:(r7+n): $20 ring base, $21 write pointer, $22 clear calls left,
; $23 clear pointer, $24 AMT, $25 GC (input gain/4), $26 KRT, $27 KAP, $28 KLP
; (smoothed), $29 $2a LFO phases, $2c $2d the smear and delay fractions, $2e $2f
; the smear and delay offsets, $30 $31 the damping states, $32 apout, $33 input envelope,
; $34 hold counter, $35 gate gain (smoothed), $36 hold length (0x7fffff = gate off).
; Knobs: p0 AMNT amount, p1 GAIN input gain, p2 TIME reverb time, p3 DIFF
; diffusion, p4 TONE damping, p5 GATE hold (0 off).

init:
        move    #>$ffffff,m4
        move    r7,r4
        move    #>$20,n4
        move    (r4)+n4
        clr     a
        do      #32,>gv_zero
        move    a,x:(r4)+
gv_zero:
        nop
        move    x:>$213,r4
        move    x:(r4),a
        move    a,x:(r7+$20)
        move    a,x:(r7+$21)
        move    a,x:(r7+$23)
        move    #>52,a
        move    a,x:(r7+$22)
        rts

proc:
; Bounded clearing: 310 words a call, 52 calls, the output dry until the ring is clean.
        move    x:(r7+$22),a
        tst     a
        beq     gv_ready
        sub     #>$1,a
        move    a,x:(r7+$22)
        move    x:(r7+$23),r4
        move    #>$ffffff,m4
        clr     a
        do      #>310,>gv_clear
        move    a,y:(r4)+
gv_clear:
        nop
        move    r4,x:(r7+$23)
        rts
gv_ready:
; Knob words carry a non-zero low byte under an LFO: masked before any use.
        move    x:(r6+$0),a
        and     #>$7f0000,a
        move    a1,x0
        move    x0,a
        move    x:(r7+$24),b
        sub     b,a
        asr     #$4,a,a
        add     b,a
        move    a,x:(r7+$24)
        move    x:(r6+$1),a
        and     #>$7f0000,a
        move    a1,x0
        move    x0,a
        asr     #$3,a,a
        move    x:(r7+$25),b
        sub     b,a
        asr     #$4,a,a
        add     b,a
        move    a,x:(r7+$25)
        move    x:(r6+$2),a
        and     #>$7f0000,a
        move    a1,x0
        move    #>$50a3d7,y1
        mpy     x0,y1,a
        move    #>$2ccccd,x1
        add     x1,a
        move    x:(r7+$26),b
        sub     b,a
        asr     #$4,a,a
        add     b,a
        move    a,x:(r7+$26)
        move    x:(r6+$3),a
        and     #>$7f0000,a
        move    a1,x0
        move    #>$666666,y1
        mpy     x0,y1,a
        move    x:(r7+$27),b
        sub     b,a
        asr     #$4,a,a
        add     b,a
        move    a,x:(r7+$27)
        move    x:(r6+$4),a
        and     #>$7f0000,a
        move    a1,x0
        move    #>$79999a,y1
        mpy     x0,y1,a
        move    #>$066666,x1
        add     x1,a
        move    x:(r7+$28),b
        sub     b,a
        asr     #$4,a,a
        add     b,a
        move    a,x:(r7+$28)
; GATE: 0 is off (hold length at maximum); k > 0 holds 2048 + 256 k samples.
        move    x:(r6+$5),a
        and     #>$7f0000,a
        move    a1,x0
        move    x0,a
        asr     #$10,a,a
        tst     a
        bne     gv_gon
        move    #>$7fffff,a
        move    a1,x:(r7+$34)
        bra     gv_gdone
gv_gon:
        asl     #$8,a,a
        add     #>2048,a
gv_gdone:
        move    a1,x:(r7+$36)
; LFO phases advance a block at a time; the parabola 4x(1-|x|) stands for the cosine.
        move    x:(r7+$29),a
        move    #>190,x1
        do      n7,>gv_p29
        add     x1,a
gv_p29:
        nop
        move    a1,x:(r7+$29)
        move    x:(r7+$2a),a
        move    #>114,x1
        do      n7,>gv_p2a
        add     x1,a
gv_p2a:
        nop
        move    a1,x:(r7+$2a)
        move    x:(r7+$29),a
        abs     a
        move    a,x0
        move    #>$7fffff,b
        sub     x0,b
        move    b,x0
        move    x:(r7+$29),y1
        mpy     x0,y1,a
        asl     #$2,a,a
        move    a,x0
; smear: offset 10 + 60 * lfo1 samples in Q12; whole part and fraction.
        move    #>$03c000,y1
        mpy     x0,y1,a
        add     #>$00a000,a
        move    a1,x0
        move    x0,a
        asr     #$c,a,b
        move    b1,x1
        and     #>$000fff,a
        asl     #$b,a,a
        move    a1,x:(r7+$2c)
        clr     a
        sub     x1,a
        move    a1,x:(r7+$2e)
        move    x:(r7+$2a),a
        abs     a
        move    a,x0
        move    #>$7fffff,b
        sub     x0,b
        move    b,x0
        move    x:(r7+$2a),y1
        mpy     x0,y1,a
        asl     #$2,a,a
        move    a,x0
; delay 2: offset 4605 + 98 * lfo2 samples.
        move    #>$062000,y1
        mpy     x0,y1,a
        move    a1,x0
        move    x0,a
        asr     #$c,a,b
        move    b1,x1
        move    #>4605,b
        add     x1,b
        move    b1,x1
        and     #>$000fff,a
        asl     #$b,a,a
        move    a1,x:(r7+$2d)
        move    #>$ffd369,a
        sub     x1,a
        move    a1,x:(r7+$2f)
; block setup
        move    #>$1,n0
        move    #>16119,m4
        move    #>16119,m5
        move    x:(r7+$21),r5
        do      n7,>gv_end
; smear: the first allpass line read at 10 + 60 lfo1, written back at 100
        move    x:(r7+$2e),n5
        lua     (r5+n5),r4
        move    y:(r4)-,b
        move    y:(r4),a
        sub     b,a
        move    a,x0
        move    x:(r7+$2c),y0
        mpy     y0,x0,a
        add     b,a
        move    #>$ffff9c,n5
        move    a,y:(r5+n5)
; input: (L + R)/2 times the gain
        move    x:(r0),a
        move    x:(r0+n0),x0
        add     x0,a
        asr     #$1,a,a
        move    a,y0
        abs     a
        move    a,x1
; gate: input envelope (instant attack, 1/512 release), hold counter, smoothed gain
        move    x:(r7+$33),a
        asr     #$9,a,b
        sub     b,a
        move    x1,b
        sub     a,b
        move    #0,x0
        tst     b
        tmi     x0,b
        add     b,a
        move    a1,x:(r7+$33)
        move    x:(r7+$34),b
        sub     #>$1,b
        move    #0,x0
        tst     b
        tmi     x0,b
        sub     #>$010000,a
        move    x:(r7+$36),x1
        tst     a
        tgt     x1,b
        move    b1,x:(r7+$34)
        move    #>128,x1
        move    b,a
        sub     x1,a
        tst     a
        tge     x1,b
        asl     #$10,b,a
        move    a,x0
        move    x:(r7+$35),b
        move    x0,a
        sub     b,a
        asr     #$5,a,a
        add     b,a
        move    a,x:(r7+$35)
        move    y0,x0
        move    x:(r7+$25),y1
        mpy     x0,y1,a
; four input allpasses
        move    x:(r7+$27),y1
        move    #>$ffff92,n5
        move    y:(r5+n5),x0
        mac     x0,y1,a
        move    x0,b
        move    #>$000000,n5
        move    a,y:(r5+n5)
        move    a,x0
        move    b,a
        mac     -x0,y1,a
        move    #>$fffef2,n5
        move    y:(r5+n5),x0
        mac     x0,y1,a
        move    x0,b
        move    #>$ffff90,n5
        move    a,y:(r5+n5)
        move    a,x0
        move    b,a
        mac     -x0,y1,a
        move    #>$fffe04,n5
        move    y:(r5+n5),x0
        mac     x0,y1,a
        move    x0,b
        move    #>$fffef0,n5
        move    a,y:(r5+n5)
        move    a,x0
        move    b,a
        mac     -x0,y1,a
        move    #>$fffc7a,n5
        move    y:(r5+n5),x0
        mac     x0,y1,a
        move    x0,b
        move    #>$fffe02,n5
        move    a,y:(r5+n5)
        move    a,x0
        move    b,a
        mac     -x0,y1,a
        move    a,x:(r7+$32)
; loop, first half: delay 2 (modulated) -> damping -> dap1a -> dap1b -> delay 1; left out
        move    x:(r7+$2f),n5
        lua     (r5+n5),r4
        move    y:(r4)-,b
        move    y:(r4),a
        sub     b,a
        move    a,x0
        move    x:(r7+$2d),y0
        mpy     y0,x0,a
        add     b,a
        move    a,x0
        move    x:(r7+$26),y1
        mpy     x0,y1,a
        move    x:(r7+$32),x0
        add     x0,a
        move    x:(r7+$30),b
        sub     b,a
        move    a,x0
        move    x:(r7+$28),y1
        mpy     x0,y1,a
        add     b,a
        move    a,x:(r7+$30)
        move    x:(r7+$27),y1
        move    #>$fff61e,n5
        move    y:(r5+n5),x0
        mac     -x0,y1,a
        move    x0,b
        move    #>$fffc78,n5
        move    a,y:(r5+n5)
        move    a,x0
        move    b,a
        mac     x0,y1,a
        move    #>$ffee48,n5
        move    y:(r5+n5),x0
        mac     x0,y1,a
        move    x0,b
        move    #>$fff61c,n5
        move    a,y:(r5+n5)
        move    a,x0
        move    b,a
        mac     -x0,y1,a
        move    #>$ffee46,n5
        move    a,y:(r5+n5)
        asl     #$1,a,a
        move    a,x0
        move    x:(r7+$35),y1
        mpy     x0,y1,a
        move    a,x0
        move    x:(r7+$24),y1
        mpy     x0,y1,b
        asl     #$3,b,b
        move    x:(r0),x0
        move    x0,a
        add     b,a
        mac     -x0,y1,a
        move    a,x:(r0)+
; second half: delay 1 tail -> damping -> dap2a -> dap2b -> delay 2; right out
        move    x:(r7+$32),a
        move    #>$ffe12b,n5
        move    y:(r5+n5),x0
        move    x:(r7+$26),y1
        mac     x0,y1,a
        move    x:(r7+$31),b
        sub     b,a
        move    a,x0
        move    x:(r7+$28),y1
        mpy     x0,y1,a
        add     b,a
        move    a,x:(r7+$31)
        move    x:(r7+$27),y1
        move    #>$ffd9d0,n5
        move    y:(r5+n5),x0
        mac     x0,y1,a
        move    x0,b
        move    #>$ffe129,n5
        move    a,y:(r5+n5)
        move    a,x0
        move    b,a
        mac     -x0,y1,a
        move    #>$ffd36b,n5
        move    y:(r5+n5),x0
        mac     -x0,y1,a
        move    x0,b
        move    #>$ffd9ce,n5
        move    a,y:(r5+n5)
        move    a,x0
        move    b,a
        mac     x0,y1,a
        move    #>$ffd369,n5
        move    a,y:(r5+n5)
        asl     #$1,a,a
        move    a,x0
        move    x:(r7+$35),y1
        mpy     x0,y1,a
        move    a,x0
        move    x:(r7+$24),y1
        mpy     x0,y1,b
        asl     #$3,b,b
        move    x:(r0),x0
        move    x0,a
        add     b,a
        mac     -x0,y1,a
        move    a,x:(r0)+
        move    (r5)+
gv_end:
        nop
        move    r5,x:(r7+$21)
        move    #>$ffffff,m4
        move    #>$ffffff,m5
        rts

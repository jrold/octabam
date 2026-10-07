; Complex Drum DSP candidate. State is 42 X words:
; main oscillator 2..9, modulation oscillator 10..17, amp envelope 18..28,
; pitch envelope 29..39, raw pitch 40, pitch amount 41.
; This source is intentionally not in the shipping dispatcher until its
; executable gate and cycle/memory placement checks are complete.
pk_complex_voice:
        move    r6,a
        move    a1,x:(r5+$60)
        do      n7,pkcv_done
        move    x:(r5+$60),r6
        lua     (r6+$12),r6
        jsr     pk_simple_envelope
        move    a1,x:(r5+$61)
        move    x:(r5+$60),r6
        lua     (r6+$1d),r6
        jsr     pk_simple_envelope
        move    a1,x:(r5+$62)

        move    x:(r5+$60),r6
        lua     (r6+$a),r7
        jsr     pk_simple_oscillator
        asr     #$6,a,a
        move    a1,x:(r5+$63)

        move    x:(r5+$60),r6
        move    x:(r6+$28),a
        and     #>$ffff,a
        move    a1,x0
        jsr     pk_complex_base
        move    a1,x0
        move    x0,x:(r5+$64)
        move    x:(r5+$62),y0
        move    #>$2000,b
        and     y0,b
        ; factor = ((low13 + 0x2000) >> (13-high)) - 1
        move    y0,b
        and     #>$1fff,b
        add     #>$2000,b
        move    b1,x1
        move    y0,a
        lsr     #$d,a
        move    a1,y1
        move    #>$d,b
        sub     y1,b
        move    b1,x0
        move    x1,b
        asr     x0,b,b
        sub     #>$1,b
        move    x:(r6+$29),y0
        move    b1,x0
        mpyuu   x0,y0,a
        asr     #$b,a,a
        move    a0,b
        move    x:(r5+$64),x0
        add     x0,b
        move    x:(r5+$63),x0
        add     x0,b
        move    b1,x0
        jsr     pk_simple_frequency
        move    a1,b
        and     #>$ffff,b
        move    b1,x:(r6+$4)
        asr     #$10,a,a
        and     #>$ffff,a
        move    a1,x:(r6+$5)
        lua     (r6+$2),r7
        jsr     pk_simple_oscillator
        move    x:(r6+$1),b
        tst     b
        bne     pkcv_muted
        move    a1,x0
        move    x:(r5+$61),y0
        mpysu   x0,y0,a
        asr     #$11,a,a
        move    a0,x0
        move    x:(r6),y0
        mpysu   x0,y0,a
        asr     #$9,a,a
        move    a0,a
        move    a1,x:(r0)+
        move    a1,x:(r0)+
        bra     pkcv_next
pkcv_muted:
        clr     a
        move    a1,x:(r0)+
        move    a1,x:(r0)+
pkcv_next:
        move    x:(r5+$60),r6
pkcv_done:
        nop
        rts

; Prepared raw pitch -> exact v1.2.1 pitch table basis. This mirrors the
; Simple Drum control-rate converter, reading Complex raw pitch at +$28.
pk_complex_base:
        move    r6,a
        move    a1,x:(r5+$60)
        move    x:(r6+$28),a
        lsr     #$9,a
        move    a1,x:(r5+$49)
        move    x:(r6+$28),a
        and     #>$1ff,a
        move    a1,x0
        move    #>$3964,r4
        move    #>$efb,r1
        move    #>$32,y0
        move    #>$6,y1
        move    #>$2,n3
        jsr     pk_simple_delta_at
        move    #>$7,b
        move    x:(r5+$49),x0
        sub     x0,b
        move    b1,x0
        asr     x0,a,a
        move    a1,x0
        move    #>$bb80,y0
        mpyuu   x0,y0,a
        asr     #$15,a,a
        move    a0,a
        move    x:(r5+$60),r6
        rts

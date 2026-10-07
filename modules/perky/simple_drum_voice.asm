; Complete Simple Drum sample renderer, 34 live words + 2 base-frequency limbs.
; r6=voice, r5=100-word shared scratch, r0=stereo output, n7=sample count.
; Exact native arithmetic; raw prepared pitch is u16. Base frequency is prepared
; once per block independently of the per-sample pitch-envelope modulation.
; Scratch $60/$61 are saved voice pointer / amplitude; primitives use $52..$59.
pk_simple_voice:
        lua     (r6+$22),r4
        move    r6,a
        move    a1,x:(r5+$60)
        do      n7,pksdv_done
        move    x:(r5+$60),r6
        lua     (r6+$a),r6
        jsr     pk_simple_envelope
        move    a1,x:(r5+$61)
        move    x:(r5+$60),r6
        lua     (r6+$15),r6
        jsr     pk_simple_envelope
        move    x:(r5+$60),r6
        move    a1,x0
        move    x:(r6+$21),y0
        mpyuu   x0,y0,a
        asr     #$b,a,a
        move    a0,x0
        move    x:(r6+$20),y0
        mpyuu   x0,y0,a
        asr     #$11,a,a
        move    a0,a
        ; Converter consumes only low 12 frequency bits. High base limb drops
        ; out of those bits exactly, even for modulo-32 overflow.
        move    x:(r6+$34),x0
        add     x0,a
        move    a1,x0
        jsr     pk_simple_frequency
        move    a1,b
        and     #>$00ffff,b
        move    b1,x:(r6+$4)
        asr     #$10,a,a
        and     #>$00ffff,a
        move    a1,x:(r6+$5)
        lua     (r6+$2),r7
        jsr     pk_simple_oscillator
        move    x:(r6+$1),b
        tst     b
        bne     pksdv_muted
        move    a1,x0
        move    x:(r5+$61),y0
        mpysu   x0,y0,a
        asr     #$12,a,a
        move    a0,x0
        move    x:(r6),y0
        mpysu   x0,y0,a
        asr     #$9,a,a
        move    a0,a
        cmp     #>$007fff,a
        ble     pksdv_lower
        move    #>$007fff,a
pksdv_lower:
        cmp     #>$ff8000,a
        bge     pksdv_output
        move    #>$ff8000,a
        bra     pksdv_output
pksdv_muted:
        clr     a
pksdv_output:
        move    a1,x:(r0)+
        move    a1,x:(r0)+
pksdv_done:
        nop
        move    x:(r5+$60),r6
        rts

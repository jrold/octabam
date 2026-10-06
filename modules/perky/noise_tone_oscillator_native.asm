; PERKY Noise/Tone oscillator/interpolator using the shipping packed Y stream.
;
; Same standalone ABI/state as noise_tone_oscillator.asm:
;   r5 base
;   +40/+41 phase u32 lo/hi
;   +42/+43 increment u32 lo/hi
;   +44/+45 current 32-bit wave identity lo/hi
;   +46/+47 next    32-bit wave identity lo/hi
;   +48 returned signed16 bit-pattern
; Scratch +0..+19 and +52..+59.
;
; The four wave identities are build-time substitutions so real extracted
; firmware addresses can replace the synthetic gate identities without
; changing renderer code:
;   @W0L@ @W0H@ -> ordinal 0, global sample base   0
;   @W1L@ @W1H@ -> ordinal 1, global sample base 256
;   @W2L@ @W2H@ -> ordinal 2, global sample base 512
;   @W3L@ @W3H@ -> ordinal 3, global sample base 768
;
; Packed stream base is the shipping private-Y address Y:$07a5. Three signed16
; samples occupy two 24-bit words, LSB-first (noise_tone_tables.py).

pk_osc_packed_probe:
        ; Both live phase and increment are bounded below 2^24. Assemble
        ; their limbs in the DSP accumulator without four scratch copies.
        move x:(r7+$1),a
        asl #$10,a,a
        move x:(r7+$0),x0
        add x0,a
        move x:(r7+$3),b
        asl #$10,b,b
        move x:(r7+$2),x0
        add x0,b
        add b,a
        move a1,b
        and #>$00ffff,b
        move b1,x:(r7+$0)
        lsr #$10,a
        and #>$00ffff,a
        move a1,x:(r7+$1)

        ; signed32(phase) > $00100000 -- strictly greater, exactly as native.
        move    x:(r7+$1),a
        btst    #15,a1
        jcc     pkop_phase_positive
        bra     pkop_phase_ready
pkop_phase_positive:
        cmp     #>$0010,a
        bgt     pkop_phase_wrap
        blt     pkop_phase_ready
        move    x:(r7+$0),a
        tst     a
        bgt     pkop_phase_wrap
        bra     pkop_phase_ready

pkop_phase_wrap:
        move    x:(r7+$1),a
        sub     #>$0010,a
        and     #>$00ffff,a
        move    a1,x:(r7+$1)

        ; Deferred table switch occurs only at the wrap.
        move    x:(r7+$4),a
        move    x:(r7+$6),x0
        cmp     x0,a
        bne     pkop_switch_table
        move    x:(r7+$5),a
        move    x:(r7+$7),x0
        cmp     x0,a
        beq     pkop_phase_ready
pkop_switch_table:
        move    x:(r7+$6),a
        move    a1,x:(r7+$4)
        move    x:(r7+$7),a
        move    a1,x:(r7+$5)

pkop_phase_ready:
        ; The four synthetic identities are 0x10000000 + ordinal*512.
        ; Exact ordinal extraction replaces a per-sample four-way lookup.
        move x:(r7+$4),a
        lsr a
        and #>$000300,a
        move a1,x:(r5+$59)
        bra pkop_have_wave
pkop_have_wave:
        ; local index = (phase >> 12) & $ff.
        move    x:(r7+$0),a
        move    a1,b
        and     #>$00f000,b
        lsr     #$c,b
        move    b1,x0
        move    x:(r7+$1),a
        and     #>$00000f,a
        asl     #$4,a,a
        add     x0,a
        and     #>$0000ff,a
        move    a1,x:(r5+$52)

        ; fraction = phase & $fff.
        move    x:(r7+$0),a
        and     #>$000fff,a
        move    a1,x:(r5+$53)

        ; first = packed signed16 wave[local index].
        move    x:(r5+$52),a
        move    x:(r5+$59),x0
        add     x0,a
        move    a1,x0                   ; global 0..1023 index
        jsr     pkop_read_s16
        move    a1,x:(r5+$54)

        ; Adjacent samples share the packed pair. Only local index255
        ; wraps back to this wave's first sample and needs another division.
        move x:(r5+$52),a
        cmp #>$ff,a
        beq pkon_wrap_next
        jsr pkon_read_next
        bra pkon_store_next
pkon_wrap_next:
        move x:(r5+$59),x0
        jsr pkop_read_s16
pkon_store_next:
        move a1,x:(r5+$55)

        ; A signed17 delta times unsigned12 fraction fits signed32.
        ; MPY's fractional alignment accounts for the extra right shift.
        move x:(r5+$55),a
        move x:(r5+$54),x0
        sub x0,a
        move a1,x0
        move x:(r5+$53),y0
        mpy y0,x0,a
        asr #$d,a,a
        move a0,a
        move x:(r5+$54),x0
        add x0,a
        and #>$00ffff,a
        move a1,x:(r5+$48)
        rts

pkon_read_next:
        move y1,a
        tst a
        beq pkop_read_r1
        cmp #>$1,a
        beq pkop_read_r2
        move y:(r2+$2),a
        and #>$00ffff,a
        bra pkop_read_sign

; Input x0 = global sample index 0..1023. Return A1 = signed 24-bit sample.
pkop_read_s16:
        move x0,x:(r5+$18)
        move #>$2aaaab,y0
        mpyuu x0,y0,a
        asr #$18,a,a
        move a0,b
        move b1,x1
        asl b
        move b1,n1
        add x1,b
        move b1,y0
        move x:(r5+$18),a
        sub y0,a
        move a1,y1
        move #>$0007a5,r1
        lua (r1+n1),r2

        move    y1,a
        tst     a
        beq     pkop_read_r0
        cmp     #>$1,a
        beq     pkop_read_r1
pkop_read_r2:
        move    y:(r2+$1),a
        lsr     #$8,a
        and     #>$00ffff,a
        bra     pkop_read_sign
pkop_read_r1:
        move    y:(r2),a
        lsr     #$10,a
        and     #>$0000ff,a
        move    a1,x1
        move    y:(r2+$1),b
        and     #>$0000ff,b
        asl     #$8,b,b
        add     x1,b
        and     #>$00ffff,b
        move    b1,a
        bra     pkop_read_sign
pkop_read_r0:
        move    y:(r2),a
        and     #>$00ffff,a
pkop_read_sign:
        asl #$8,a,a
        move a1,a
        asr #$8,a,a
pkop_read_done:
        rts

; ---- exact two-limb helpers, same arithmetic as the raw-table probe -------
pkop_add:
        move    x:(r5+$0),a
        move    x:(r5+$2),x0
        add     x0,a
        move    #>$0,y0
        btst    #16,a1
        jcc     pkop_add_no_carry
        move    #>$1,y0
pkop_add_no_carry:
        and     #>$00ffff,a
        move    a1,x:(r5+$8)
        move    x:(r5+$1),b
        move    x:(r5+$3),x0
        add     x0,b
        add     y0,b
        and     #>$00ffff,b
        move    b1,x:(r5+$9)
        rts

pkop_asr:
        move    x:(r5+$1),a
        btst    #15,a1
        jcc     pkop_shift_sign_ready
        sub     #>$010000,a
pkop_shift_sign_ready:
        move    x:(r5+$0),b
        lsl     #$8,b
        move    b1,a0
        move    x:(r5+$4),x0
        asr     x0,a,a
        move    a1,b
        and     #>$00ffff,b
        move    b1,x:(r5+$9)
        move    a0,b
        lsr     #$8,b
        and     #>$00ffff,b
        move    b1,x:(r5+$8)
        rts

pkop_mul_low:
        move    x:(r5+$0),x0
        move    x:(r5+$2),y0
        mpyuu   x0,y0,a
        asr     #$1,a,a                 ; remove fractional multiply alignment
        move    a0,x1
        move    x1,b
        and     #>$00ffff,b
        move    b1,x:(r5+$8)
        asr     #$10,a,a
        move    a0,x1
        move    x1,b
        and     #>$00ffff,b
        move    b1,y1

        move    x:(r5+$0),x0
        move    x:(r5+$3),y0
        mpyuu   x0,y0,a
        asr     #$1,a,a                 ; remove fractional multiply alignment
        move    a0,a
        and     #>$00ffff,a
        move    a1,x1
        move    y1,b
        add     x1,b

        move    x:(r5+$1),x0
        move    x:(r5+$2),y0
        mpyuu   x0,y0,a
        asr     #$1,a,a                 ; remove fractional multiply alignment
        move    a0,a
        and     #>$00ffff,a
        move    a1,x1
        add     x1,b
        and     #>$00ffff,b
        move    b1,x:(r5+$9)
        rts

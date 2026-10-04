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
; Packed stream base is the shipping private-Y address Y:$0795. Three signed16
; samples occupy two 24-bit words, LSB-first (noise_tone_tables.py).

pk_osc_packed_probe:
        ; phase = phase + increment, modulo 2^32.
        move    x:(r5+$40),a
        move    a1,x:(r5+$0)
        move    x:(r5+$41),a
        move    a1,x:(r5+$1)
        move    x:(r5+$42),a
        move    a1,x:(r5+$2)
        move    x:(r5+$43),a
        move    a1,x:(r5+$3)
        jsr     pkop_add
        move    x:(r5+$8),a
        move    a1,x:(r5+$40)
        move    x:(r5+$9),a
        move    a1,x:(r5+$41)

        ; signed32(phase) > $00100000 -- strictly greater, exactly as native.
        move    x:(r5+$41),a
        btst    #15,a1
        jcc     pkop_phase_positive
        bra     pkop_phase_ready
pkop_phase_positive:
        cmp     #>$0010,a
        bgt     pkop_phase_wrap
        blt     pkop_phase_ready
        move    x:(r5+$40),a
        tst     a
        bgt     pkop_phase_wrap
        bra     pkop_phase_ready

pkop_phase_wrap:
        move    x:(r5+$41),a
        sub     #>$0010,a
        and     #>$00ffff,a
        move    a1,x:(r5+$41)

        ; Deferred table switch occurs only at the wrap.
        move    x:(r5+$44),a
        move    x:(r5+$46),x0
        cmp     x0,a
        bne     pkop_switch_table
        move    x:(r5+$45),a
        move    x:(r5+$47),x0
        cmp     x0,a
        beq     pkop_phase_ready
pkop_switch_table:
        move    x:(r5+$46),a
        move    a1,x:(r5+$44)
        move    x:(r5+$47),a
        move    a1,x:(r5+$45)

pkop_phase_ready:
        ; Resolve current 32-bit identity -> global packed sample base.
        move    x:(r5+$44),a
        cmp     #>@W0L@,a
        bne     pkop_try_w1
        move    x:(r5+$45),a
        cmp     #>@W0H@,a
        bne     pkop_try_w1
        clr     a
        move    a1,x:(r5+$59)
        bra     pkop_have_wave
pkop_try_w1:
        move    x:(r5+$44),a
        cmp     #>@W1L@,a
        bne     pkop_try_w2
        move    x:(r5+$45),a
        cmp     #>@W1H@,a
        bne     pkop_try_w2
        move    #>$000100,a
        move    a1,x:(r5+$59)
        bra     pkop_have_wave
pkop_try_w2:
        move    x:(r5+$44),a
        cmp     #>@W2L@,a
        bne     pkop_try_w3
        move    x:(r5+$45),a
        cmp     #>@W2H@,a
        bne     pkop_try_w3
        move    #>$000200,a
        move    a1,x:(r5+$59)
        bra     pkop_have_wave
pkop_try_w3:
        move    x:(r5+$44),a
        cmp     #>@W3L@,a
        bne     pkop_missing_wave
        move    x:(r5+$45),a
        cmp     #>@W3H@,a
        bne     pkop_missing_wave
        move    #>$000300,a
        move    a1,x:(r5+$59)
        bra     pkop_have_wave
pkop_missing_wave:
        clr     a
        move    a1,x:(r5+$48)
        rts

pkop_have_wave:
        ; local index = (phase >> 12) & $ff.
        move    x:(r5+$40),a
        move    a1,b
        and     #>$00f000,b
        lsr     #$c,b,b
        move    b1,x0
        move    x:(r5+$41),a
        and     #>$00000f,a
        asl     #$4,a,a
        add     x0,a
        and     #>$0000ff,a
        move    a1,x:(r5+$52)

        ; fraction = phase & $fff.
        move    x:(r5+$40),a
        and     #>$000fff,a
        move    a1,x:(r5+$53)

        ; first = packed signed16 wave[local index].
        move    x:(r5+$52),a
        move    x:(r5+$59),x0
        add     x0,a
        move    a1,x0                   ; global 0..1023 index
        jsr     pkop_read_s16
        move    a1,x:(r5+$54)

        ; second = packed signed16 wave[(local index+1)&$ff].
        move    x:(r5+$52),a
        add     #>$1,a
        and     #>$0000ff,a
        move    x:(r5+$59),x0
        add     x0,a
        move    a1,x0
        jsr     pkop_read_s16
        move    a1,x:(r5+$55)

        ; delta = second - first, sign-extended to the two 16-bit limbs used
        ; by the exact low32 multiplier.
        move    x:(r5+$55),a
        move    x:(r5+$54),x0
        sub     x0,a
        move    a1,x:(r5+$56)
        move    a1,b
        and     #>$00ffff,b
        move    b1,x:(r5+$0)
        move    #>$0,x0
        tst     a
        jpl     pkop_delta_sign_ready
        move    #>$00ffff,x0
pkop_delta_sign_ready:
        move    x0,x:(r5+$1)
        move    x:(r5+$53),a
        move    a1,x:(r5+$2)
        clr     a
        move    a1,x:(r5+$3)
        jsr     pkop_mul_low

        ; interp = arithmeticShiftRight(low32(delta*fraction), 12).
        move    x:(r5+$8),a
        move    a1,x:(r5+$0)
        move    x:(r5+$9),a
        move    a1,x:(r5+$1)
        move    #>$c,a
        move    a1,x:(r5+$4)
        jsr     pkop_asr
        move    x:(r5+$8),a
        move    a1,x:(r5+$57)
        move    x:(r5+$9),a
        move    a1,x:(r5+$58)

        ; result = signed16(first + interp).
        move    x:(r5+$54),a
        move    a1,b
        and     #>$00ffff,b
        move    b1,x:(r5+$0)
        move    #>$0,x0
        tst     a
        jpl     pkop_first_sign_ready
        move    #>$00ffff,x0
pkop_first_sign_ready:
        move    x0,x:(r5+$1)
        move    x:(r5+$57),a
        move    a1,x:(r5+$2)
        move    x:(r5+$58),a
        move    a1,x:(r5+$3)
        jsr     pkop_add
        move    x:(r5+$8),a
        and     #>$00ffff,a
        move    a1,x:(r5+$48)
        rts

; Input x0 = global sample index 0..1023. Return A1 = signed 24-bit sample.
pkop_read_s16:
        move    x0,a
        move    a1,x:(r5+$18)           ; preserve n
        move    #>$00aaab,y0
        mpyuu   x0,y0,a
        lsr     #$10,a,a
        move    a0,x1
        move    x1,b
        and     #>$00ffff,b
        lsr     b
        move    b1,x1                   ; q=floor(n/3)

        ; r=n-3*q.
        move    x1,b
        asl     b
        add     x1,b
        move    b1,y0
        move    x:(r5+$18),a
        sub     y0,a
        move    a1,y1

        ; pair = Y:$0795 + 2*q.
        move    x1,b
        asl     b
        move    b1,n1
        move    #>$000795,r1
        lua     (r1+n1),r2

        move    y1,a
        tst     a
        beq     pkop_read_r0
        cmp     #>$1,a
        beq     pkop_read_r1
pkop_read_r2:
        move    y:(r2+$1),a
        lsr     #$8,a,a
        and     #>$00ffff,a
        bra     pkop_read_sign
pkop_read_r1:
        move    y:(r2),a
        lsr     #$10,a,a
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
        btst    #15,a1
        jcc     pkop_read_done
        sub     #>$010000,a
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
        move    x:(r5+$0),x1
        move    x:(r5+$1),y0
        move    y0,a
        btst    #15,a1
        jcc     pkop_asr_sign_done
        move    #>$010000,x0
        sub     x0,a
pkop_asr_sign_done:
        move    a1,y0
        move    x:(r5+$4),x0
        move    #>$008000,y1
        do      x0,pkop_asr_loop_done
        move    x1,b
        lsr     b
        move    b1,x1
        move    y0,a
        asr     a
        add     y1,b ifcs
        move    b1,x1
        move    a1,y0
pkop_asr_loop_done:
        nop
        move    x1,a
        and     #>$00ffff,a
        move    a1,x:(r5+$8)
        move    y0,b
        and     #>$00ffff,b
        move    b1,x:(r5+$9)
        rts

pkop_mul_low:
        move    x:(r5+$0),x0
        move    x:(r5+$2),y0
        mpyuu   x0,y0,a
        move    a0,x1
        move    x1,b
        and     #>$00ffff,b
        move    b1,x:(r5+$8)
        lsr     #$10,a,a
        move    a0,x1
        move    x1,b
        and     #>$00ffff,b
        move    b1,y1

        move    x:(r5+$0),x0
        move    x:(r5+$3),y0
        mpyuu   x0,y0,a
        and     #>$00ffff,a
        move    a1,x1
        move    y1,b
        add     x1,b

        move    x:(r5+$1),x0
        move    x:(r5+$2),y0
        mpyuu   x0,y0,a
        and     #>$00ffff,a
        move    a1,x1
        add     x1,b
        and     #>$00ffff,b
        move    b1,x:(r5+$9)
        rts

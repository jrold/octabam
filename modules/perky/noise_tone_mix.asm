; PERKY Noise/Tone final sample mixer standalone DSP56300 probe.
;
; Exact scalar tail from NativeV121NoiseToneShared::renderBlock(). It consumes
; already-computed envelope/noise/oscillator values and proves the low32
; multiply, arithmetic-shift and final int16 saturation chain independently of
; the stateful primitives.
;
; bd909_host state at r5:
;   +40/+41 mix u32 lo/hi
;   +42 noise sample signed16 bit-pattern
;   +43 oscillator 1 signed16 bit-pattern
;   +44 oscillator 2 signed16 bit-pattern
;   +45 amplitude u16
;   +46 velocity byte/word
;   +47 returned saturated signed16 bit-pattern
;   +48/+49 debug final pre-clamp u32
; Scratch +0..+19 and +52..+59.

pk_mix_probe:
        ; accumulator = ASR32(low32(mix * signext(noise)), 13)
        move    x:(r5+$40),a
        move    a1,x:(r5+$0)
        move    x:(r5+$41),a
        move    a1,x:(r5+$1)
        move    x:(r5+$42),a
        jsr     pkm_s16_to_b
        move    b1,x:(r5+$2)
        move    b0,x:(r5+$3)
        jsr     pkm_mul_low
        move    x:(r5+$8),a
        move    a1,x:(r5+$0)
        move    x:(r5+$9),a
        move    a1,x:(r5+$1)
        move    #>$d,a
        move    a1,x:(r5+$4)
        jsr     pkm_asr
        move    x:(r5+$8),a
        move    a1,x:(r5+$52)
        move    x:(r5+$9),a
        move    a1,x:(r5+$53)

        ; oscillatorSum = ASR32(signext(osc1) + signext(osc2), 4)
        move    x:(r5+$43),a
        jsr     pkm_s16_to_b
        move    b1,x:(r5+$0)
        move    b0,x:(r5+$1)
        move    x:(r5+$44),a
        jsr     pkm_s16_to_b
        move    b1,x:(r5+$2)
        move    b0,x:(r5+$3)
        jsr     pkm_add
        move    x:(r5+$8),a
        move    a1,x:(r5+$0)
        move    x:(r5+$9),a
        move    a1,x:(r5+$1)
        move    #>$4,a
        move    a1,x:(r5+$4)
        jsr     pkm_asr
        move    x:(r5+$8),a
        move    a1,x:(r5+$54)
        move    x:(r5+$9),a
        move    a1,x:(r5+$55)

        ; tonal factor = signed32($00000fff - mix), modulo 2^32.
        move    #>$000fff,a
        move    a1,x:(r5+$0)
        clr     a
        move    a1,x:(r5+$1)
        move    x:(r5+$40),a
        move    a1,x:(r5+$2)
        move    x:(r5+$41),a
        move    a1,x:(r5+$3)
        jsr     pkm_sub

        ; tonal = low32(factor * oscillatorSum)
        move    x:(r5+$54),a
        move    a1,x:(r5+$2)
        move    x:(r5+$55),a
        move    a1,x:(r5+$3)
        move    x:(r5+$8),a
        move    a1,x:(r5+$0)
        move    x:(r5+$9),a
        move    a1,x:(r5+$1)
        jsr     pkm_mul_low
        move    x:(r5+$8),a
        move    a1,x:(r5+$0)
        move    x:(r5+$9),a
        move    a1,x:(r5+$1)
        move    #>$9,a
        move    a1,x:(r5+$4)
        jsr     pkm_asr

        ; accumulator += tonal >> 9.
        move    x:(r5+$52),a
        move    a1,x:(r5+$0)
        move    x:(r5+$53),a
        move    a1,x:(r5+$1)
        move    x:(r5+$8),a
        move    a1,x:(r5+$2)
        move    x:(r5+$9),a
        move    a1,x:(r5+$3)
        jsr     pkm_add
        move    x:(r5+$8),a
        move    a1,x:(r5+$52)
        move    x:(r5+$9),a
        move    a1,x:(r5+$53)

        ; output = ASR32(low32(accumulator * amplitude), 16)
        move    x:(r5+$52),a
        move    a1,x:(r5+$0)
        move    x:(r5+$53),a
        move    a1,x:(r5+$1)
        move    x:(r5+$45),a
        and     #>$00ffff,a
        move    a1,x:(r5+$2)
        clr     a
        move    a1,x:(r5+$3)
        jsr     pkm_mul_low
        move    x:(r5+$8),a
        move    a1,x:(r5+$0)
        move    x:(r5+$9),a
        move    a1,x:(r5+$1)
        move    #>$10,a
        move    a1,x:(r5+$4)
        jsr     pkm_asr

        ; output = ASR32(low32(output * velocity), 8)
        move    x:(r5+$8),a
        move    a1,x:(r5+$0)
        move    x:(r5+$9),a
        move    a1,x:(r5+$1)
        move    x:(r5+$46),a
        and     #>$0000ff,a
        move    a1,x:(r5+$2)
        clr     a
        move    a1,x:(r5+$3)
        jsr     pkm_mul_low
        move    x:(r5+$8),a
        move    a1,x:(r5+$0)
        move    x:(r5+$9),a
        move    a1,x:(r5+$1)
        move    #>$8,a
        move    a1,x:(r5+$4)
        jsr     pkm_asr
        move    x:(r5+$8),a
        move    a1,x:(r5+$48)
        move    x:(r5+$9),a
        move    a1,x:(r5+$49)

        ; Final native clamp is the full int16 range [-32768, 32767].
        move    x:(r5+$8),a
        move    a1,x:(r5+$0)
        move    x:(r5+$9),a
        move    a1,x:(r5+$1)
        jsr     pkm_clamp_i16
        move    x:(r5+$8),a
        and     #>$00ffff,a
        move    a1,x:(r5+$47)
        rts

; Convert the low16 of A into a signed 32-bit value in B as limbs:
; B1 = low limb, B0 = high limb. (B is used only as a convenient pair holder.)
pkm_s16_to_b:
        and     #>$00ffff,a
        move    a1,b
        move    #>$0,b0
        btst    #15,a1
        jcc     pkm_s16_done
        move    #>$00ffff,b0
pkm_s16_done:
        rts

pkm_add:
        move    x:(r5+$0),a
        move    x:(r5+$2),x0
        add     x0,a
        move    #>$0,y0
        btst    #16,a1
        jcc     pkm_branch_add_no_carry
        move    #>$1,y0
pkm_branch_add_no_carry:
        and     #>$00ffff,a
        move    a1,x:(r5+$8)
        move    x:(r5+$1),b
        move    x:(r5+$3),x0
        add     x0,b
        add     y0,b
        and     #>$00ffff,b
        move    b1,x:(r5+$9)
        rts

pkm_sub:
        move    x:(r5+$0),a
        move    x:(r5+$2),x0
        sub     x0,a
        move    #>$0,y0
        jpl     pkm_branch_sub_no_borrow
        move    #>$1,y0
pkm_branch_sub_no_borrow:
        and     #>$00ffff,a
        move    a1,x:(r5+$8)
        move    x:(r5+$1),b
        move    x:(r5+$3),x0
        sub     x0,b
        sub     y0,b
        and     #>$00ffff,b
        move    b1,x:(r5+$9)
        rts

pkm_asr:
        move    x:(r5+$1),a
        btst    #15,a1
        jcc     pkm_shift_sign_ready
        sub     #>$010000,a
pkm_shift_sign_ready:
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

pkm_mul_low:
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

; Clamp signed32 +0/+1 to [-32768,32767], output +8/+9.
pkm_clamp_i16:
        move    x:(r5+$1),a
        btst    #15,a1
        jcc     pkm_clamp_positive

        ; In-range negatives have high=$ffff and low >= $8000.
        cmp     #>$00ffff,a
        bne     pkm_clamp_low
        move    x:(r5+$0),a
        cmp     #>$008000,a
        blt     pkm_clamp_low
        bra     pkm_clamp_copy

pkm_clamp_positive:
        tst     a
        bne     pkm_clamp_high
        move    x:(r5+$0),a
        cmp     #>$007fff,a
        bgt     pkm_clamp_high
        bra     pkm_clamp_copy

pkm_clamp_high:
        move    #>$007fff,a
        move    a1,x:(r5+$8)
        clr     a
        move    a1,x:(r5+$9)
        rts

pkm_clamp_low:
        move    #>$008000,a
        move    a1,x:(r5+$8)
        move    #>$00ffff,a
        move    a1,x:(r5+$9)
        rts

pkm_clamp_copy:
        move    x:(r5+$0),a
        move    a1,x:(r5+$8)
        move    x:(r5+$1),a
        move    a1,x:(r5+$9)
        rts

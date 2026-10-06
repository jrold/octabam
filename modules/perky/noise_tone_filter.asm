; PERKY Noise/Tone resonant-noise filter standalone DSP56300 probe.
;
; This is the exact state transition used by NativeV121NoiseToneShared's
; advanceFilter(), kept separate from the audio hook until the emulator gate
; proves its integer behaviour.  Firmware 32-bit values are represented as two
; unsigned 16-bit limbs in X memory; all products deliberately keep only the
; low 32 bits, exactly like the ARM implementation.
;
; bd909_host probe ABI:
;   r5 = X state base, r6 = parameter block (unused except by host)
;
; Direct probe state:
;   +44 coefficient u16
;   +45 damping coefficient u16
;   +46/+47 first     u32 low/high limbs
;   +48/+49 second    u32 low/high limbs (output)
;   +50/+51 velocity  u32 low/high limbs
;   +52 input sample  signed-16 bit pattern
;
; Scratch +0..+19 belongs to the helpers below.

pk_filter_probe:
        ; product = low32(velocity * coefficient)
        move    x:(r5+$50),a
        move    a1,x:(r5+$0)
        move    x:(r5+$51),a
        move    a1,x:(r5+$1)
        move    x:(r5+$44),a
        and     #>$00ffff,a
        move    a1,x:(r5+$2)
        clr     a
        move    a1,x:(r5+$3)
        jsr     pkf_mul_low

        ; Firmware quirk: negative product gets +0xffff before >>16.
        move    x:(r5+$9),a
        btst    #15,a1
        jcc     pkf_first_product_ready
        move    x:(r5+$8),a
        move    a1,x:(r5+$0)
        move    x:(r5+$9),a
        move    a1,x:(r5+$1)
        move    #>$00ffff,a
        move    a1,x:(r5+$2)
        clr     a
        move    a1,x:(r5+$3)
        jsr     pkf_add
pkf_first_product_ready:
        move    x:(r5+$8),a
        move    a1,x:(r5+$0)
        move    x:(r5+$9),a
        move    a1,x:(r5+$1)
        move    #>$10,a
        move    a1,x:(r5+$4)
        jsr     pkf_asr
        move    x:(r5+$8),a
        move    a1,x:(r5+$18)
        move    x:(r5+$9),a
        move    a1,x:(r5+$19)

        ; first = clamp(first + (product >> 16), -32767, 32767)
        move    x:(r5+$46),a
        move    a1,x:(r5+$0)
        move    x:(r5+$47),a
        move    a1,x:(r5+$1)
        move    x:(r5+$18),a
        move    a1,x:(r5+$2)
        move    x:(r5+$19),a
        move    a1,x:(r5+$3)
        jsr     pkf_add
        move    x:(r5+$8),a
        move    a1,x:(r5+$0)
        move    x:(r5+$9),a
        move    a1,x:(r5+$1)
        jsr     pkf_clamp_s16ish
        move    x:(r5+$8),a
        move    a1,x:(r5+$46)
        move    x:(r5+$9),a
        move    a1,x:(r5+$47)

        ; second = sign_extend(input) - first
        move    x:(r5+$52),a
        and     #>$00ffff,a
        move    a1,x:(r5+$0)
        move    #>$0,x0
        btst    #15,a1
        jcc     pkf_input_sign_ready
        move    #>$00ffff,x0
pkf_input_sign_ready:
        move    x0,x:(r5+$1)
        move    x:(r5+$46),a
        move    a1,x:(r5+$2)
        move    x:(r5+$47),a
        move    a1,x:(r5+$3)
        jsr     pkf_sub
        move    x:(r5+$8),a
        move    a1,x:(r5+$18)
        move    x:(r5+$9),a
        move    a1,x:(r5+$19)

        ; damping = low32(velocity * dampingCoefficient) >> 10
        move    x:(r5+$50),a
        move    a1,x:(r5+$0)
        move    x:(r5+$51),a
        move    a1,x:(r5+$1)
        move    x:(r5+$45),a
        and     #>$00ffff,a
        move    a1,x:(r5+$2)
        clr     a
        move    a1,x:(r5+$3)
        jsr     pkf_mul_low
        move    x:(r5+$8),a
        move    a1,x:(r5+$0)
        move    x:(r5+$9),a
        move    a1,x:(r5+$1)
        move    #>$a,a
        move    a1,x:(r5+$4)
        jsr     pkf_asr

        ; second -= damping; clamp to the firmware's [-32767,32767].
        move    x:(r5+$18),a
        move    a1,x:(r5+$0)
        move    x:(r5+$19),a
        move    a1,x:(r5+$1)
        move    x:(r5+$8),a
        move    a1,x:(r5+$2)
        move    x:(r5+$9),a
        move    a1,x:(r5+$3)
        jsr     pkf_sub
        move    x:(r5+$8),a
        move    a1,x:(r5+$0)
        move    x:(r5+$9),a
        move    a1,x:(r5+$1)
        jsr     pkf_clamp_s16ish
        move    x:(r5+$8),a
        move    a1,x:(r5+$48)
        move    x:(r5+$9),a
        move    a1,x:(r5+$49)

        ; feedback = low32(second * coefficient)
        move    x:(r5+$48),a
        move    a1,x:(r5+$0)
        move    x:(r5+$49),a
        move    a1,x:(r5+$1)
        move    x:(r5+$44),a
        and     #>$00ffff,a
        move    a1,x:(r5+$2)
        clr     a
        move    a1,x:(r5+$3)
        jsr     pkf_mul_low

        ; Same negative-product rounding quirk as the first leg.
        move    x:(r5+$9),a
        btst    #15,a1
        jcc     pkf_feedback_ready
        move    x:(r5+$8),a
        move    a1,x:(r5+$0)
        move    x:(r5+$9),a
        move    a1,x:(r5+$1)
        move    #>$00ffff,a
        move    a1,x:(r5+$2)
        clr     a
        move    a1,x:(r5+$3)
        jsr     pkf_add
pkf_feedback_ready:
        move    x:(r5+$8),a
        move    a1,x:(r5+$0)
        move    x:(r5+$9),a
        move    a1,x:(r5+$1)
        move    #>$10,a
        move    a1,x:(r5+$4)
        jsr     pkf_asr
        move    x:(r5+$8),a
        move    a1,x:(r5+$18)
        move    x:(r5+$9),a
        move    a1,x:(r5+$19)

        ; velocity = clamp(velocity + (feedback >> 16), -32767, 32767)
        move    x:(r5+$50),a
        move    a1,x:(r5+$0)
        move    x:(r5+$51),a
        move    a1,x:(r5+$1)
        move    x:(r5+$18),a
        move    a1,x:(r5+$2)
        move    x:(r5+$19),a
        move    a1,x:(r5+$3)
        jsr     pkf_add
        move    x:(r5+$8),a
        move    a1,x:(r5+$0)
        move    x:(r5+$9),a
        move    a1,x:(r5+$1)
        jsr     pkf_clamp_s16ish
        move    x:(r5+$8),a
        move    a1,x:(r5+$50)
        move    x:(r5+$9),a
        move    a1,x:(r5+$51)
        rts

; ---- exact two-limb helpers ------------------------------------------------

pkf_add:
        move    x:(r5+$0),a
        move    x:(r5+$2),x0
        add     x0,a
        move    #>$0,y0
        btst    #16,a1
        jcc     pkf_branch_add_no_carry
        move    #>$1,y0
pkf_branch_add_no_carry:
        and     #>$00ffff,a
        move    a1,x:(r5+$8)
        move    x:(r5+$1),b
        move    x:(r5+$3),x0
        add     x0,b
        add     y0,b
        and     #>$00ffff,b
        move    b1,x:(r5+$9)
        rts

pkf_sub:
        move    x:(r5+$0),a
        move    x:(r5+$2),x0
        sub     x0,a
        move    #>$0,y0
        jpl     pkf_branch_sub_no_borrow
        move    #>$1,y0
pkf_branch_sub_no_borrow:
        and     #>$00ffff,a
        move    a1,x:(r5+$8)
        move    x:(r5+$1),b
        move    x:(r5+$3),x0
        sub     x0,b
        sub     y0,b
        and     #>$00ffff,b
        move    b1,x:(r5+$9)
        rts

pkf_asr:
        move    x:(r5+$1),a
        btst    #15,a1
        jcc     pkf_shift_sign_ready
        sub     #>$010000,a
pkf_shift_sign_ready:
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

pkf_mul_low:
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

; Input +0/+1 is a signed 32-bit value. Output +8/+9 is clamped to the exact
; range used by the firmware: -32767 ($ffff8001) .. +32767 ($00007fff).
pkf_clamp_s16ish:
        move    x:(r5+$1),a
        btst    #15,a1
        jcs     pkf_clamp_negative

        ; Positive: any non-zero high limb, or low > $7fff, clips high.
        tst     a
        bne     pkf_clamp_high
        move    x:(r5+$0),a
        cmp     #>$007fff,a
        bgt     pkf_clamp_high
        bra     pkf_clamp_copy

pkf_clamp_negative:
        ; Negative values in range have high=$ffff and low >= $8001.
        cmp     #>$00ffff,a
        bne     pkf_clamp_low
        move    x:(r5+$0),a
        cmp     #>$008001,a
        blt     pkf_clamp_low
        bra     pkf_clamp_copy

pkf_clamp_high:
        move    #>$007fff,a
        move    a1,x:(r5+$8)
        clr     a
        move    a1,x:(r5+$9)
        rts

pkf_clamp_low:
        move    #>$008001,a
        move    a1,x:(r5+$8)
        move    #>$00ffff,a
        move    a1,x:(r5+$9)
        rts

pkf_clamp_copy:
        move    x:(r5+$0),a
        move    a1,x:(r5+$8)
        move    x:(r5+$1),a
        move    a1,x:(r5+$9)
        rts

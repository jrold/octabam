; PĒRKONS v1.2.1 Noise Hat / Pulse Stack one-pass state-variable filter.
;
; Compact 8-word state at X:(r6):
;   +0 damping u16
;   +1 coefficient u16
;   +2/+3 first s32 low16/high16 (bounded to +/-32767)
;   +4/+5 second s32 low16/high16 (bounded to +/-32767)
;   +6/+7 velocity s32 low16/high16 (bounded to +/-32767)
;
; Input:  signed value in X:(r5+$61)
; Output: updated compact state.  The implementation intentionally mirrors the
; ARM renderer's low32 multiply, negative-product rounding and clamps.  Because
; first/second/velocity are clamped to signed16 after every call, their live
; arithmetic can stay in native signed DSP registers while the state remains
; lossless ARM-shaped two-limb s32.

pk_noise_hat_filter:
        ; coefficient and damping are unsigned 16-bit and therefore positive
        ; in the DSP's 24-bit data registers.
        move    x:(r6+$1),y0
        move    x:(r6+$0),y1

        ; first = sign_extend16(low limb)
        move    x:(r6+$2),a
        asl     #$8,a,a
        move    a1,a
        asr     #$8,a,a
        move    a1,x1

        ; velocity = sign_extend16(low limb)
        move    x:(r6+$6),a
        asl     #$8,a,a
        move    a1,a
        asr     #$8,a,a
        move    a1,x0

        ; Keep the signed input in r1 across the multiply sequence.
        move    x:(r5+$61),a
        move    a1,r1

        ; product = low32(velocity * coefficient)
        ; if product < 0: product += 0xffff
        ; first += product >> 16
        ; This sequence is the already-qualified native Noise/Tone filter
        ; arithmetic, specialized to one pass instead of the two-pass helper.
        mpy     y0,x0,a
        asr     #$1,a,a
        tst     a
        jpl     pknhf_first_rounded
        clr     b
        move    #>$00ffff,b0
        add     b,a
pknhf_first_rounded:
        asr     #$10,a,a
        move    a0,a
        add     x1,a
        cmp     #>$007fff,a
        ble     pknhf_first_clamped_low
        move    #>$007fff,a
pknhf_first_clamped_low:
        cmp     #>$ff8001,a
        bge     pknhf_first_clamped_ok
        move    #>$ff8001,a
pknhf_first_clamped_ok:
        move    a1,x1

        ; second = input - first - ((velocity * damping) >> 10)
        move    r1,a
        sub     x1,a
        move    a1,r2
        mpy     x0,y1,a
        asr     #$b,a,a
        move    a0,a
        move    a1,b
        move    r2,a
        sub     b,a
        cmp     #>$007fff,a
        ble     pknhf_second_clamped_low
        move    #>$007fff,a
pknhf_second_clamped_low:
        cmp     #>$ff8001,a
        bge     pknhf_second_clamped_ok
        move    #>$ff8001,a
pknhf_second_clamped_ok:
        move    a1,r2

        ; velocity += rounded((second * coefficient) >> 16)
        move    x0,r3
        move    a1,x0
        mpy     y0,x0,a
        asr     #$1,a,a
        tst     a
        jpl     pknhf_feedback_rounded
        clr     b
        move    #>$00ffff,b0
        add     b,a
pknhf_feedback_rounded:
        asr     #$10,a,a
        move    a0,a
        move    r3,b
        add     b,a
        cmp     #>$007fff,a
        ble     pknhf_velocity_clamped_low
        move    #>$007fff,a
pknhf_velocity_clamped_low:
        cmp     #>$ff8001,a
        bge     pknhf_velocity_clamped_ok
        move    #>$ff8001,a
pknhf_velocity_clamped_ok:
        move    a1,x0

        ; Store exact signed32 limbs.  Values are signed16-bounded, so the high
        ; limb is either 0000 or ffff.
        move    x1,a
        move    a1,b
        and     #>$00ffff,b
        move    b1,x:(r6+$2)
        clr     b
        tst     a
        jpl     pknhf_write_first
        move    #>$00ffff,b
pknhf_write_first:
        move    b1,x:(r6+$3)

        move    r2,a
        move    a1,b
        and     #>$00ffff,b
        move    b1,x:(r6+$4)
        clr     b
        tst     a
        jpl     pknhf_write_second
        move    #>$00ffff,b
pknhf_write_second:
        move    b1,x:(r6+$5)

        move    x0,a
        move    a1,b
        and     #>$00ffff,b
        move    b1,x:(r6+$6)
        clr     b
        tst     a
        jpl     pknhf_write_velocity
        move    #>$00ffff,b
pknhf_write_velocity:
        move    b1,x:(r6+$7)
        rts

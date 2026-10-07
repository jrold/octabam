; PĒRKONS v1.2.1 Noise Hat classic firmware mode 1 (panel M1 / white noise).
;
; One-sample inner renderer only: the wrapper-owned 4,805-word delay is kept
; separate so this engine/RNG path can be PCM-qualified independently first.
;
; ABI:
;   r6 = 121-word classic compact state base
;   r5 = scratch base
;   result A1 = signed int16 inner sample (before wrapper delay)
;
; Sideband at scratch (persistent across calls):
;   X:(r5+$70)       outer hold count u16
;   X:(r5+$71)       outer held sample u16
;   X:(r5+$72..+$73) global RNG low  u32 lo/hi limbs
;   X:(r5+$74..+$75) global RNG high u32 lo/hi limbs
;
; Classic compact offsets used here:
;   +$51 velocity u8
;   +$52..+$5c envelope
;   +$5d..+$5f inner sample/hold noise state
;   +$60..+$67 filter
;   +$68 use-second
;   +$69 local mute
;   +$6a outer hold reload
;   +$6b mix
;   +$6c range
;
; Dependencies:
;   pk_noise_hat_envelope
;   pk_noise_hat_filter
;   pk_noise_step / pk_rng_step
;   pk_u32_add / pk_u32_asr / pk_u32_mul_low
;
; Integer products and partial products preserve native low32 overflow before
; arithmetic shifts, including the signed25 intermediate in the mix path.

pk_noise_hat_classic_inner1:
        ; Rebase hot scratch so raw A0 stores use the stock one-word X form.
        move    r5,a
        add     #>$40,a
        move    a1,r7
        move    r6,a
        move    a1,x:(r7+$26)

        move    #>$52,n6
        move    (r6)+n6
        jsr     pk_noise_hat_envelope
        move    a1,x:(r7+$27)
        move    x:(r7+$26),r6

        ; ---- outer sample/hold ------------------------------------------------
        move    x:(r7+$30),a
        and     #>$00ffff,a
        tst     a
        beq     pknhc1_outer_refresh
        sub     #>$1,a
        and     #>$00ffff,a
        move    a1,x:(r7+$30)
        move    x:(r7+$31),a
        and     #>$00ffff,a
        move    a1,x:(r7+$28)
        bra     pknhc1_outer_ready

pknhc1_outer_refresh:
        move    x:(r6+$5d),a
        move    a1,x:(r7+$0)
        move    x:(r6+$5e),a
        move    a1,x:(r7+$1)
        move    x:(r6+$5f),a
        move    a1,x:(r7+$2)

        move    x:(r7+$32),a
        move    a1,x:(r5+$0)
        move    x:(r7+$33),a
        move    a1,x:(r5+$1)
        move    x:(r7+$34),a
        move    a1,x:(r5+$2)
        move    x:(r7+$35),a
        move    a1,x:(r5+$3)
        jsr     pk_noise_step

        move    x:(r7+$0),a
        move    a1,x:(r6+$5d)
        move    x:(r7+$1),a
        move    a1,x:(r6+$5e)
        move    x:(r7+$2),a
        move    a1,x:(r6+$5f)
        move    x:(r5+$0),a
        move    a1,x:(r7+$32)
        move    x:(r5+$1),a
        move    a1,x:(r7+$33)
        move    x:(r5+$2),a
        move    a1,x:(r7+$34)
        move    x:(r5+$3),a
        move    a1,x:(r7+$35)

        move    x:(r5+$12),a
        and     #>$00ffff,a
        move    a1,x:(r7+$28)
        move    a1,x:(r7+$31)
        move    x:(r6+$6a),a
        and     #>$00ffff,a
        move    a1,x:(r7+$30)

pknhc1_outer_ready:
        move    x:(r7+$28),a
        move    a1,x:(r7+$21)
        move    #>$60,n6
        move    (r6)+n6
        jsr     pk_noise_hat_filter
        jsr     pk_noise_hat_filter
        move    x:(r7+$26),r6

        move    x:(r6+$62),a
        move    x:(r6+$68),b
        tst     b
        beq     pknhc1_filter_chosen
        move    x:(r6+$64),a
pknhc1_filter_chosen:
        and     #>$00ffff,a
        move    a1,x:(r7+$29)

        move    x:(r6+$69),a
        tst     a
        beq     pknhc1_mix
        clr     a
        rts

pknhc1_mix:
        ; ratio = unsigned16(range) - 1 - unsigned16(mix), signed17.
        move    x:(r6+$6c),a
        sub     #>$1,a
        move    x:(r6+$6b),x0
        sub     x0,a
        move    a1,y0
        move    x:(r7+$29),a
        asl     #$8,a,a
        move    a1,a
        asr     #$8,a,a
        move    a1,x0
        mpy     y0,x0,a
        asr     #$1,a,a
        move    a0,x:(r7+$3)
        move    a1,x:(r7+$4)

        move    x:(r7+$28),a
        asl     #$8,a,a
        move    a1,a
        asr     #$8,a,a
        move    a1,x0
        move    x:(r6+$6b),y0
        mpy     y0,x0,a
        asr     #$1,a,a
        move    x:(r7+$4),b
        move    x:(r7+$3),b0
        add     b,a
        ; Wrap the raw sum to signed32, then shift7 (native mixed value).
        asl     #$18,a,a
        asr     #$1f,a,a

        ; (low32(mixed * amplitude) >>16) is signed16. Compute its bits
        ; from two unsigned16 partial products, without dropping mixed's
        ; 25th bit: high16 = low16(high16(lo*amp) + hi*amp).
        move    a0,b
        and     #>$00ffff,b
        move    b1,x0                   ; mixed low16
        asr     #$10,a,a
        move    a0,b
        and     #>$00ffff,b
        move    b1,x1                   ; mixed high16
        move    x:(r7+$27),y0
        mpyuu   x0,y0,a
        asr     #$11,a,a
        move    a0,b                    ; upper16 of low partial product
        move    x1,x0
        mpyuu   x0,y0,a
        asr     #$1,a,a
        move    a0,a
        add     b,a
        and     #>$00ffff,a
        asl     #$8,a,a
        move    a1,a
        asr     #$8,a,a
        move    a1,x0

        ; signed16 * velocity_u8 >>8 already fits the native int16 clamp.
        move    x:(r6+$51),a
        and     #>$0000ff,a
        move    a1,y0
        mpy     y0,x0,a
        asr     #$9,a,a
        move    a0,a
        rts

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
; The generic limb helpers are intentionally used for the post-filter mix and
; gain path: the two signed products can overflow signed32 when added, and the
; ARM code explicitly keeps only low32 before arithmetic shifts.

pk_noise_hat_classic_mode1:
        move    r6,a
        move    a1,x:(r5+$66)

        lua     (r6+$52),r6
        jsr     pk_noise_hat_envelope
        move    a1,x:(r5+$67)
        move    x:(r5+$66),r6

        ; ---- outer sample/hold ------------------------------------------------
        move    x:(r5+$70),a
        and     #>$00ffff,a
        tst     a
        beq     pknhc1_outer_refresh
        sub     #>$1,a
        and     #>$00ffff,a
        move    a1,x:(r5+$70)
        move    x:(r5+$71),a
        and     #>$00ffff,a
        move    a1,x:(r5+$68)
        bra     pknhc1_outer_ready

pknhc1_outer_refresh:
        move    x:(r6+$5d),a
        move    a1,x:(r5+$40)
        move    x:(r6+$5e),a
        move    a1,x:(r5+$41)
        move    x:(r6+$5f),a
        move    a1,x:(r5+$42)

        move    x:(r5+$72),a
        move    a1,x:(r5+$0)
        move    x:(r5+$73),a
        move    a1,x:(r5+$1)
        move    x:(r5+$74),a
        move    a1,x:(r5+$2)
        move    x:(r5+$75),a
        move    a1,x:(r5+$3)
        jsr     pk_noise_step

        move    x:(r5+$40),a
        move    a1,x:(r6+$5d)
        move    x:(r5+$41),a
        move    a1,x:(r6+$5e)
        move    x:(r5+$42),a
        move    a1,x:(r6+$5f)
        move    x:(r5+$0),a
        move    a1,x:(r5+$72)
        move    x:(r5+$1),a
        move    a1,x:(r5+$73)
        move    x:(r5+$2),a
        move    a1,x:(r5+$74)
        move    x:(r5+$3),a
        move    a1,x:(r5+$75)

        move    x:(r5+$12),a
        and     #>$00ffff,a
        move    a1,x:(r5+$68)
        move    a1,x:(r5+$71)
        move    x:(r6+$6a),a
        and     #>$00ffff,a
        move    a1,x:(r5+$70)

pknhc1_outer_ready:
        move    x:(r5+$68),a
        move    a1,x:(r5+$61)
        lua     (r6+$60),r6
        jsr     pk_noise_hat_filter
        jsr     pk_noise_hat_filter
        move    x:(r5+$66),r6

        move    x:(r6+$62),a
        move    x:(r6+$68),b
        tst     b
        beq     pknhc1_selected
        move    x:(r6+$64),a
pknhc1_selected:
        and     #>$00ffff,a
        move    a1,x:(r5+$69)

        move    x:(r6+$69),a
        tst     a
        beq     pknhc1_mix
        clr     a
        rts

pknhc1_mix:
        ; ratio = u16(range) - 1 - u16(mix), as signed32 limbs.
        move    x:(r6+$6c),a
        and     #>$00ffff,a
        sub     #>$1,a
        move    x:(r6+$6b),b
        and     #>$00ffff,b
        move    b1,x0
        sub     x0,a
        move    a1,b
        and     #>$00ffff,b
        move    b1,x:(r5+$46)
        clr     b
        tst     a
        jpl     pknhc1_ratio_sign
        move    #>$00ffff,b
pknhc1_ratio_sign:
        move    b1,x:(r5+$47)

        ; product1 = low32(selected * ratio).
        move    x:(r5+$69),a
        and     #>$00ffff,a
        move    a1,x:(r5+$0)
        clr     b
        btst    #15,a1
        jcc     pknhc1_selected_sign
        move    #>$00ffff,b
pknhc1_selected_sign:
        move    b1,x:(r5+$1)
        move    x:(r5+$46),a
        move    a1,x:(r5+$2)
        move    x:(r5+$47),a
        move    a1,x:(r5+$3)
        jsr     pk_u32_mul_low
        move    x:(r5+$8),a
        move    a1,x:(r5+$43)
        move    x:(r5+$9),a
        move    a1,x:(r5+$44)

        ; product2 = low32(u16(mix) * signed16(sample)).
        move    x:(r6+$6b),a
        and     #>$00ffff,a
        move    a1,x:(r5+$0)
        clr     a
        move    a1,x:(r5+$1)
        move    x:(r5+$68),a
        and     #>$00ffff,a
        move    a1,x:(r5+$2)
        clr     b
        btst    #15,a1
        jcc     pknhc1_sample_sign
        move    #>$00ffff,b
pknhc1_sample_sign:
        move    b1,x:(r5+$3)
        jsr     pk_u32_mul_low
        move    x:(r5+$8),a
        move    a1,x:(r5+$45)
        move    x:(r5+$9),a
        move    a1,x:(r5+$46)

        ; mixed = asr32(low32(product1 + product2), 7).
        move    x:(r5+$43),a
        move    a1,x:(r5+$0)
        move    x:(r5+$44),a
        move    a1,x:(r5+$1)
        move    x:(r5+$45),a
        move    a1,x:(r5+$2)
        move    x:(r5+$46),a
        move    a1,x:(r5+$3)
        jsr     pk_u32_add
        move    x:(r5+$8),a
        move    a1,x:(r5+$0)
        move    x:(r5+$9),a
        move    a1,x:(r5+$1)
        move    #>$7,a
        move    a1,x:(r5+$4)
        jsr     pk_u32_asr

        ; mixed = asr32(low32(amplitude * mixed), 16).
        move    x:(r5+$8),a
        move    a1,x:(r5+$0)
        move    x:(r5+$9),a
        move    a1,x:(r5+$1)
        move    x:(r5+$67),a
        and     #>$00ffff,a
        move    a1,x:(r5+$2)
        clr     a
        move    a1,x:(r5+$3)
        jsr     pk_u32_mul_low
        move    x:(r5+$8),a
        move    a1,x:(r5+$0)
        move    x:(r5+$9),a
        move    a1,x:(r5+$1)
        move    #>$10,a
        move    a1,x:(r5+$4)
        jsr     pk_u32_asr

        ; output = asr32(low32(mixed * velocity_u8), 8).
        move    x:(r5+$8),a
        move    a1,x:(r5+$0)
        move    x:(r5+$9),a
        move    a1,x:(r5+$1)
        move    x:(r6+$51),a
        and     #>$0000ff,a
        move    a1,x:(r5+$2)
        clr     a
        move    a1,x:(r5+$3)
        jsr     pk_u32_mul_low
        move    x:(r5+$8),a
        move    a1,x:(r5+$0)
        move    x:(r5+$9),a
        move    a1,x:(r5+$1)
        move    #>$8,a
        move    a1,x:(r5+$4)
        jsr     pk_u32_asr

        ; Saturate signed32 limbs to native velocity() [-32768,32767].
        move    x:(r5+$9),a
        and     #>$00ffff,a
        tst     a
        beq     pknhc1_positive_high_zero
        cmp     #>$00ffff,a
        beq     pknhc1_negative_high_ffff
        btst    #15,a1
        jcc     pknhc1_sat_positive
        bra     pknhc1_sat_negative
pknhc1_sat_positive:
        move    #>$007fff,a
        rts

pknhc1_positive_high_zero:
        move    x:(r5+$8),a
        and     #>$00ffff,a
        cmp     #>$007fff,a
        ble     pknhc1_return_positive
        move    #>$007fff,a
pknhc1_return_positive:
        rts

pknhc1_negative_high_ffff:
        move    x:(r5+$8),a
        and     #>$00ffff,a
        cmp     #>$008000,a
        bge     pknhc1_return_negative
pknhc1_sat_negative:
        move    #>$008000,a
pknhc1_return_negative:
        asl     #$8,a,a
        move    a1,a
        asr     #$8,a,a
        rts

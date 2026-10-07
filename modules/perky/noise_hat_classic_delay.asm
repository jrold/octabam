; PĒRKONS v1.2.1 Noise Hat classic wrapper delay.
;
; The ARM wrapper owns a 4,805-sample signed16 ring.  Keep that ring out of the
; 121-word hot X state: caller supplies r4 = Y ring base.  This is the memory
; shape we need on Octatrack once stock-FX Y space is reclaimed.
;
; ABI:
;   r6 = 121-word classic compact state base
;   r5 = scratch base
;   r4 = Y ring base, 4,805 words
;   X:(r5+$60) = signed16 input bit-pattern
;   result A1 = final wrapper result narrowed/sign-extended to int16
;
; Classic delay state in X:r6:
;   +$6d..+$71 five delay offsets u16
;   +$72..+$76 five gains u16
;   +$77         ring index u16
;   +$78         wrapper mix signed16
;
; Dependencies: pk_u32_add / pk_u32_asr / pk_u32_mul_low.
; All products/adds use explicit 32-bit limbs because native arithmetic wraps
; modulo 2^32 before shifts. The five intermediate stages saturate only to
; [-32767,32767]; the final wrapper output is NOT saturated, merely narrowed.

pk_noise_hat_classic_delay:
        move    x:(r5+$60),a
        and     #>$00ffff,a
        move    a1,x:(r5+$64)           ; original input bit-pattern
        move    a1,x:(r5+$62)           ; current stage bit-pattern

        move    x:(r6+$77),a
        and     #>$00ffff,a
        move    a1,x:(r5+$65)           ; current index
        add     #>$1,a
        cmp     #>$12c4,a
        ble     pknhcd_next_ready
        clr     a
pknhcd_next_ready:
        move    a1,x:(r5+$66)           ; next index

        move    r6,r1
        move    #>$6d,n1
        move    (r1)+n1                 ; delay pointer
        move    r6,r2
        move    #>$72,n2
        move    (r2)+n2                 ; gain pointer
        jsr     pknhcd_tap
        jsr     pknhcd_tap
        jsr     pknhcd_tap
        jsr     pknhcd_tap
        jsr     pknhcd_tap

        ; ring[nextIndex] = saturated stage; publish next index.
        move    x:(r5+$66),a
        move    a1,n3
        move    r4,r3
        move    (r3)+n3
        move    x:(r5+$62),a
        and     #>$00ffff,a
        move    a1,y:(r3)
        move    x:(r5+$66),a
        move    a1,x:(r6+$77)

        ; wet = asr32(low32(stage * 5), 1).
        move    x:(r5+$62),a
        and     #>$00ffff,a
        move    a1,x:(r5+$0)
        clr     b
        btst    #15,a1
        jcc     pknhcd_wet_stage_sign
        move    #>$00ffff,b
pknhcd_wet_stage_sign:
        move    b1,x:(r5+$1)
        move    #>$5,a
        move    a1,x:(r5+$2)
        clr     a
        move    a1,x:(r5+$3)
        jsr     pk_u32_mul_low
        move    x:(r5+$8),a
        move    a1,x:(r5+$0)
        move    x:(r5+$9),a
        move    a1,x:(r5+$1)
        move    #>$1,a
        move    a1,x:(r5+$4)
        jsr     pk_u32_asr
        move    x:(r5+$8),a
        move    a1,x:(r5+$43)           ; wet lo
        move    x:(r5+$9),a
        move    a1,x:(r5+$44)           ; wet hi

        ; Decode signed16 mix and factor=(0x0fff-mix) as signed32 limbs.
        move    x:(r6+$78),a
        and     #>$00ffff,a
        move    a1,x:(r5+$45)           ; mix lo
        clr     b
        btst    #15,a1
        jcc     pknhcd_mix_sign_ready
        move    #>$00ffff,b
pknhcd_mix_sign_ready:
        move    b1,x:(r5+$46)           ; mix hi
        asl     #$8,a,a
        move    a1,a
        asr     #$8,a,a                 ; signed mix in A
        move    #>$000fff,b
        sub     a,b                      ; signed factor in B
        move    b1,a
        move    a1,x0
        and     #>$00ffff,a
        move    a1,x:(r5+$47)           ; factor lo
        move    x0,a
        clr     b
        tst     a
        jpl     pknhcd_factor_sign_ready
        move    #>$00ffff,b
pknhcd_factor_sign_ready:
        move    b1,x:(r5+$48)           ; factor hi

        ; p1 = low32(signed16(input) * factor).
        move    x:(r5+$64),a
        and     #>$00ffff,a
        move    a1,x:(r5+$0)
        clr     b
        btst    #15,a1
        jcc     pknhcd_input_sign_ready
        move    #>$00ffff,b
pknhcd_input_sign_ready:
        move    b1,x:(r5+$1)
        move    x:(r5+$47),a
        move    a1,x:(r5+$2)
        move    x:(r5+$48),a
        move    a1,x:(r5+$3)
        jsr     pk_u32_mul_low
        move    x:(r5+$8),a
        move    a1,x:(r5+$49)
        move    x:(r5+$9),a
        move    a1,x:(r5+$4a)

        ; p2 = low32(signed32(mix) * signed32(wet)).
        move    x:(r5+$45),a
        move    a1,x:(r5+$0)
        move    x:(r5+$46),a
        move    a1,x:(r5+$1)
        move    x:(r5+$43),a
        move    a1,x:(r5+$2)
        move    x:(r5+$44),a
        move    a1,x:(r5+$3)
        jsr     pk_u32_mul_low
        move    x:(r5+$8),a
        move    a1,x:(r5+$4b)
        move    x:(r5+$9),a
        move    a1,x:(r5+$4c)

        ; output32 = asr32(low32(p1+p2), 12).
        move    x:(r5+$49),a
        move    a1,x:(r5+$0)
        move    x:(r5+$4a),a
        move    a1,x:(r5+$1)
        move    x:(r5+$4b),a
        move    a1,x:(r5+$2)
        move    x:(r5+$4c),a
        move    a1,x:(r5+$3)
        jsr     pk_u32_add
        move    x:(r5+$8),a
        move    a1,x:(r5+$0)
        move    x:(r5+$9),a
        move    a1,x:(r5+$1)
        move    #>$c,a
        move    a1,x:(r5+$4)
        jsr     pk_u32_asr

        ; Native wrapper performs s16(uint16_t(output32)): discard high32 and
        ; sign-extend only the low 16 bits. Deliberately no saturation here.
        move    x:(r5+$8),a
        and     #>$00ffff,a
        asl     #$8,a,a
        move    a1,a
        asr     #$8,a,a
        rts

; ---------------------------------------------------------------------------
; One of the five serial delay stages. r1/r2 post-increment through delay/gain
; arrays. X:(r5+$62) holds signed16 stage; X:(r5+$65) is the pre-write index.
; ---------------------------------------------------------------------------
pknhcd_tap:
        move    x:(r1)+,a
        and     #>$00ffff,a
        move    a1,x:(r5+$67)           ; delay
        move    x:(r2)+,a
        and     #>$00ffff,a
        move    a1,x:(r5+$68)           ; gain

        ; p1 = low32(stage * (gain - 0x10)).
        move    x:(r5+$62),a
        and     #>$00ffff,a
        move    a1,x:(r5+$0)
        clr     b
        btst    #15,a1
        jcc     pknhcd_stage_sign_ready
        move    #>$00ffff,b
pknhcd_stage_sign_ready:
        move    b1,x:(r5+$1)

        move    x:(r5+$68),a
        sub     #>$10,a
        move    a1,b
        and     #>$00ffff,b
        move    b1,x:(r5+$2)
        clr     b
        tst     a
        jpl     pknhcd_gain_factor_sign
        move    #>$00ffff,b
pknhcd_gain_factor_sign:
        move    b1,x:(r5+$3)
        jsr     pk_u32_mul_low
        move    x:(r5+$8),a
        move    a1,x:(r5+$43)
        move    x:(r5+$9),a
        move    a1,x:(r5+$44)

        ; readIndex = index>=delay ? index-delay : 4805+index-delay.
        move    x:(r5+$65),a
        move    x:(r5+$67),x0
        cmp     x0,a
        bge     pknhcd_read_subtract
        add     #>$12c5,a
pknhcd_read_subtract:
        sub     x0,a
        move    a1,x:(r5+$69)
        move    a1,n3
        move    r4,r3
        move    (r3)+n3
        move    y:(r3),a
        and     #>$00ffff,a
        move    a1,x:(r5+$6a)           ; delayed signed16 bit-pattern

        ; p2 = low32(u16(gain) * signed16(delayed)).
        move    x:(r5+$68),a
        move    a1,x:(r5+$0)
        clr     a
        move    a1,x:(r5+$1)
        move    x:(r5+$6a),a
        move    a1,x:(r5+$2)
        clr     b
        btst    #15,a1
        jcc     pknhcd_delayed_sign_ready
        move    #>$00ffff,b
pknhcd_delayed_sign_ready:
        move    b1,x:(r5+$3)
        jsr     pk_u32_mul_low
        move    x:(r5+$8),a
        move    a1,x:(r5+$45)
        move    x:(r5+$9),a
        move    a1,x:(r5+$46)

        ; stage32 = asr32(low32(p1+p2), 4).
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
        move    #>$4,a
        move    a1,x:(r5+$4)
        jsr     pk_u32_asr

        ; Saturate stage to [-32767,32767], storing a 16-bit bit-pattern.
        move    x:(r5+$9),a
        and     #>$00ffff,a
        tst     a
        beq     pknhcd_stage_positive_high_zero
        cmp     #>$00ffff,a
        beq     pknhcd_stage_negative_high_ffff
        btst    #15,a1
        jcc     pknhcd_stage_sat_positive
        bra     pknhcd_stage_sat_negative
pknhcd_stage_sat_positive:
        move    #>$007fff,a
        move    a1,x:(r5+$62)
        rts
pknhcd_stage_positive_high_zero:
        move    x:(r5+$8),a
        and     #>$00ffff,a
        cmp     #>$007fff,a
        ble     pknhcd_stage_store
        move    #>$007fff,a
        bra     pknhcd_stage_store
pknhcd_stage_negative_high_ffff:
        move    x:(r5+$8),a
        and     #>$00ffff,a
        cmp     #>$008001,a
        bge     pknhcd_stage_store
pknhcd_stage_sat_negative:
        move    #>$008001,a
pknhcd_stage_store:
        move    a1,x:(r5+$62)
        rts

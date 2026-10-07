; PĒRKONS v1.2.1 Slap renderer, matching NativeV121Slap.
; r6=40-word compact X state, r5=128-word scratch, r4=4,805-word Y ring,
; r0=interleaved stereo output, n7=count. Scratch +$72..$75 holds global RNG.
; Dependencies: common envelope/filter/noise and pk_slap_delay (composed from
; the qualified classic delay with Slap's field offsets and signed32 output).
; Mute is absent from this original renderer. Filter runs twice per sample.

pk_slap_voice:
        move    r6,a
        move    a1,x:(r5+$7e)
        move    r4,a
        move    a1,x:(r5+$7f)
        do      n7,pkslv_done
        jsr     pk_slap_sample
        move    a1,x:(r0)+
        move    a1,x:(r0)+
pkslv_done:
        nop
        rts

pk_slap_sample:
        move    x:(r5+$7e),r6
        jsr     pk_slap_noise
        move    a1,x:(r5+$61)
        lua     (r6+$10),r6
        jsr     pk_noise_hat_filter
        jsr     pk_noise_hat_filter
        move    x:(r5+$7e),r6

        move    x:(r6+$18),a           ; first count
        move    x:(r6+$1b),x0          ; first target
        cmp     x0,a
        bge     pkslv_second_count
        add     #>$1,a
        and     #>$00ffff,a
        move    a1,x:(r6+$18)
        bra     pkslv_envelope
pkslv_second_count:
        move    x:(r6+$19),a
        move    x:(r6+$1a),x0
        cmp     x0,a
        bge     pkslv_envelope
        add     #>$1,a
        and     #>$00ffff,a
        move    a1,x:(r6+$19)
        clr     a
        move    a1,x:(r6+$18)
        move    x:(r6+$8),a            ; envelope hold low-byte reset
        and     #>$00ff00,a
        or      #>$1,a
        move    a1,x:(r6+$8)
        move    #>$1,a
        move    a1,x:(r6+$1)
        move    x:(r6+$c),a            ; reset envelope value if requested
        tst     a
        beq     pkslv_envelope
        clr     a
        move    a1,x:(r6+$6)
        move    a1,x:(r6+$7)

pkslv_envelope:
        lua     (r6+$1),r6
        jsr     pk_noise_hat_envelope
        move    a1,y0
        move    x:(r5+$7e),r6
        move    x:(r6+$12),a           ; filter first, signed16 bounded
        asl     #$8,a,a
        move    a1,a
        asr     #$8,a,a
        move    a1,x0
        mpy     y0,x0,a
        asr     #$11,a,a              ; remove alignment, then >>16
        move    a0,a
        and     #>$00ffff,a
        move    a1,x:(r5+$60)
        move    x:(r5+$7f),r4
        jsr     pk_slap_delay
        move    a1,x0
        move    x:(r6+$0),y0
        mpy     y0,x0,a
        asr     #$9,a,a               ; exact >>8 velocity scaling
        move    a0,a
        cmp     #>$007fff,a
        ble     pkslv_clamp_low
        move    #>$007fff,a
pkslv_clamp_low:
        cmp     #>$ff8000,a
        bge     pkslv_sample_ready
        move    #>$ff8000,a
pkslv_sample_ready:
        rts

; Compact noise at +$0d. Held samples avoid touching the RNG math scratch.
; Global RNG remains at scratch +$72..$75 and advances only on refresh.
pk_slap_noise:
        move    x:(r6+$d),a
        tst     a
        beq     pkslv_noise_refresh
        sub     #>$1,a
        and     #>$00ffff,a
        move    a1,x:(r6+$d)
        move    x:(r6+$f),a
        rts
pkslv_noise_refresh:
        move    x:(r6+$e),a
        move    a1,x:(r6+$d)
        move    x:(r5+$72),a
        move    a1,x:(r5+$0)
        move    x:(r5+$73),a
        move    a1,x:(r5+$1)
        move    x:(r5+$74),a
        move    a1,x:(r5+$2)
        move    x:(r5+$75),a
        move    a1,x:(r5+$3)
        jsr     pk_rng_step
        move    x:(r5+$0),a
        move    a1,x:(r5+$72)
        move    x:(r5+$1),a
        move    a1,x:(r5+$73)
        move    x:(r5+$2),a
        move    a1,x:(r5+$74)
        move    x:(r5+$3),a
        move    a1,x:(r5+$75)
        move    x:(r5+$10),a
        and     #>$00ffff,a
        move    a1,x:(r6+$f)
        rts

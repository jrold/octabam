; PĒRKONS v1.2.1 Karplus / NativeV121Karplus exact compact renderer.
; r6=32-word compact X state, r5=128-word scratch, r4=2,048-word Y ring,
; r0=stereo output, n7=count. Global RNG at scratch +$72..$75.
; The feedback-ring load is UNSIGNED u16, unlike the Slap delay taps.
; All state advances under mute. The transient age freezes after $210.

pk_karplus_voice:
        move    r6,a
        move    a1,x:(r5+$7e)
        move    r4,a
        move    a1,x:(r5+$7f)
        do      n7,pkkv_done
        jsr     pk_karplus_sample
        move    a1,x:(r0)+
        move    a1,x:(r0)+
pkkv_done:
        nop
        rts

pk_karplus_sample:
        move    x:(r5+$7e),r6
        lua     (r6+$3),r6
        jsr     pk_noise_hat_envelope
        move    a1,x:(r5+$7c)
        move    x:(r5+$7e),r6
        clr     a
        move    a1,x:(r5+$60)
        move    x:(r6+$1a),a
        move    x:(r6+$19),x0
        cmp     x0,a
        bge     pkkv_excitation_end
        add     #>$1,a
        and     #>$00ffff,a
        move    a1,x:(r6+$1a)
        jsr     pk_karplus_noise
        asl     #$8,a,a
        move    a1,a
        asr     #$8,a,a
        move    a1,x:(r5+$60)
        bra     pkkv_feedback
pkkv_excitation_end:
        move    #>$00ffff,a
        move    a1,x:(r6+$1a)
pkkv_feedback:
        move    x:(r6+$1d),a
        move    x:(r6+$1b),x0          ; low delay is sufficient modulo 2048
        sub     x0,a
        and     #>$0007ff,a
        move    a1,n3
        move    x:(r5+$7f),r4
        move    r4,r3
        move    (r3)+n3
        move    y:(r3),a
        and     #>$00ffff,a           ; native unsigned ring load
        move    x:(r5+$60),x0
        add     x0,a
        move    a1,x:(r5+$61)
        lua     (r6+$11),r6
        jsr     pk_karplus_filter
        move    x:(r5+$7e),r6

        move    x:(r6+$13),a          ; first low16, write before transient
        move    a1,x:(r5+$7b)
        move    x:(r6+$1d),a
        move    a1,b
        and     #>$0007ff,b
        move    b1,n3
        move    x:(r5+$7f),r4
        move    r4,r3
        move    (r3)+n3
        move    x:(r5+$7b),b
        move    b1,y:(r3)
        add     #>$1,a
        and     #>$00ffff,a
        move    a1,x:(r6+$1d)
        move    x:(r5+$7b),a
        asl     #$8,a,a
        move    a1,a
        asr     #$8,a,a
        move    a1,x:(r5+$7b)

        move    x:(r6+$1f),a
        tst     a
        bne     pkkv_output
        move    x:(r6+$1e),a
        cmp     #>$210,a
        bgt     pkkv_output
        move    a1,x:(r5+$7a)
        move    x:(r6+$2),a
        and     #>$ff,a
        tst     a
        beq     pkkv_transient_short
        cmp     #>$2,a
        beq     pkkv_transient_long
        bra     pkkv_age_step

pkkv_transient_short:
        jsr     pk_karplus_noise
        move    a1,x:(r5+$60)
        move    x:(r5+$7a),a
        cmp     #>$110,a
        bgt     pkkv_clip_short
        cmp     #>$8f,a
        ble     pkkv_noise_early
        move    #>$110,b
        sub     a,b
        move    b1,y0
        move    x:(r5+$60),a
        asl     #$8,a,a
        move    a1,a
        asr     #$8,a,a
        move    a1,x0
        mpy     y0,x0,a
        asr     #$9,a,a
        move    a0,x0                 ; logical low32 >>8 (unsigned24)
        move    #>$2c,y0
        mpyuu   x0,y0,a
        asr     #$1,a,a
        asl     #$18,a,a              ; low32 wrap before >>6
        asr     #$6,a,a
        bra     pkkv_add_short

pkkv_transient_long:
        jsr     pk_karplus_noise
        move    a1,x:(r5+$60)
        move    x:(r5+$7a),a
        cmp     #>$ef,a
        ble     pkkv_noise_early
        move    #>$2f0,b
        sub     a,b
        move    b1,y0
        move    x:(r5+$60),a
        asl     #$8,a,a
        move    a1,a
        asr     #$8,a,a
        move    a1,x0
        mpy     y0,x0,a
        asr     #$b,a,a
        move    a0,a
        and     #>$3fffff,a           ; logical low32 >>10 (unsigned22)
        move    a1,x0
        move    #>$2c,y0
        mpyuu   x0,y0,a
        asr     #$1,a,a
        asl     #$18,a,a
        asr     #$6,a,a
        bra     pkkv_add_short

pkkv_noise_early:
        move    x:(r5+$60),a
        asl     #$8,a,a
        move    a1,a
        asr     #$8,a,a
        move    a1,x0
        move    #>$b,y0
        mpy     y0,x0,a
        asr     #$5,a,a               ; signed bitfield(noise*11,4,26)
        move    a0,a
pkkv_add_short:
        move    x:(r5+$7b),x0
        add     x0,a
        move    x:(r6+$2),b
        tst     b
        bne     pkkv_clip_long
pkkv_clip_short:
        ; Short mode saturates even when its age is above $110.
        move    x:(r5+$7a),b
        cmp     #>$110,b
        ble     pkkv_clip_positive
        move    x:(r5+$7b),a
pkkv_clip_positive:
        cmp     #>$007fff,a
        ble     pkkv_clip_negative
        move    #>$007fff,a
pkkv_clip_negative:
        cmp     #>$ff8000,a
        bge     pkkv_park_sample
        move    #>$ff8000,a
        bra     pkkv_park_sample
pkkv_clip_long:
        cmp     #>$007fff,a
        ble     pkkv_long_negative
        move    #>$007fff,a
pkkv_long_negative:
        cmp     #>$ff8001,a
        bge     pkkv_park_sample
        move    #>$ff8001,a
pkkv_park_sample:
        move    a1,x:(r5+$7b)
pkkv_age_step:
        move    x:(r5+$7a),a
        add     #>$1,a
        move    a1,x:(r6+$1e)

pkkv_output:
        move    x:(r6+$1),a
        tst     a
        bne     pkkv_silent
        move    x:(r5+$7b),x0
        move    x:(r5+$7c),y0
        mpy     y0,x0,a
        asr     #$11,a,a
        move    a0,x0
        move    x:(r6+$0),y0
        mpy     y0,x0,a
        asr     #$9,a,a
        move    a0,a
        cmp     #>$007fff,a
        ble     pkkv_final_negative
        move    #>$007fff,a
pkkv_final_negative:
        cmp     #>$ff8000,a
        bge     pkkv_ready
        move    #>$ff8000,a
pkkv_ready:
        rts
pkkv_silent:
        clr     a
        rts

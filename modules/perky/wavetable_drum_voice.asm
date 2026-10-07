; Wavetable V1/V2 candidate. 41 live words, derived frequency at +$34/$35.
; Standalone logical packed wave bank at Y:$1000 is NOT a shipping placement.
; r6 voice, r5 scratch, r0 stereo output, n7 samples.
pk_wavetable_voice:
        move r6,a
        move a1,x:(r5+$60)
        do n7,pkwv_done
        move x:(r5+$60),r6
        lua (r6+$a),r6
        jsr pk_simple_envelope
        move a1,x:(r5+$5d)
        move x:(r5+$60),r6
        lua (r6+$15),r6
        jsr pk_simple_envelope
        move x:(r5+$60),r6
        move a1,b
        lsr #$d,b
        move b1,x0
        move #>$d,b
        sub x0,b
        move b1,x0
        and #>$1fff,a
        add #>$2000,a
        asr x0,a,a
        sub #>$1,a
        move a1,x0
        move x:(r6+$21),y0
        mpyuu x0,y0,a
        asr #$a,a,a
        move a0,a
        move x:(r6+$34),x0
        add x0,a
        move x:(r6+$28),b
        cmp #>$1,b
        bne pkwv_pitch_ready
        lsr a
pkwv_pitch_ready:
        move a1,x0
        jsr pk_simple_frequency
        move a1,b
        and #>$ffff,b
        move b1,x:(r6+$4)
        asr #$10,a,a
        and #>$ffff,a
        move a1,x:(r6+$5)
        lua (r6+$2),r7
        jsr pk_wavetable_oscillator
        move x:(r6+$1),b
        tst b
        bne pkwv_muted
        move a1,x0
        move x:(r5+$5d),y0
        mpysu x0,y0,a
        asr #$11,a,a
        move a0,x0
        move x:(r6),y0
        mpysu x0,y0,a
        asr #$9,a,a
        move a0,a
        bra pkwv_store
pkwv_muted:
        clr a
pkwv_store:
        move a1,x:(r0)+
        move a1,x:(r0)+
pkwv_done:
        nop
        move x:(r5+$60),r6
        rts

pk_wavetable_oscillator:
        move x:(r7),a
        move x:(r7+$2),x0
        add x0,a
        move #>$0,y0
        btst #16,a1
        bcc pkwto_no_carry
        move #>$1,y0
pkwto_no_carry:
        move a1,b
        and #>$ffff,b
        move b1,x:(r7)
        move x:(r7+$1),a
        move x:(r7+$3),x0
        add x0,a
        add y0,a
        and #>$ffff,a
        move a1,x:(r7+$1)
        btst #15,a1
        bcs pkwto_phase_ready
        cmp #>$10,a
        bgt pkwto_wrap
        blt pkwto_phase_ready
        move x:(r7),a
        tst a
        ble pkwto_phase_ready
pkwto_wrap:
        move x:(r7+$1),a
        sub #>$10,a
        and #>$ffff,a
        move a1,x:(r7+$1)
        move x:(r6+$27),a
        move a1,x:(r6+$26)
        move x:(r7+$4),a
        move x:(r7+$6),x0
        cmp x0,a
        bne pkwto_switch
        move x:(r7+$5),a
        move x:(r7+$7),x0
        cmp x0,a
        beq pkwto_phase_ready
pkwto_switch:
        move x:(r7+$6),a
        move a1,x:(r7+$4)
        move x:(r7+$7),a
        move a1,x:(r7+$5)
        move x:(r6+$24),a
        move a1,x:(r6+$22)
        move x:(r6+$25),a
        move a1,x:(r6+$23)
pkwto_phase_ready:
        move x:(r7),a
        lsr #$9,a
        move a1,x0
        move x:(r7+$1),a
        and #>$f,a
        asl #$7,a,a
        add x0,a
        and #>$7ff,a
        move a1,x:(r5+$52)
        move x:(r7),a
        and #>$1ff,a
        move a1,x:(r5+$53)
        clr a
        move a1,x:(r5+$5a)
        move x:(r5+$52),a
        cmp #>$7ff,a
        bne pkwto_targets_ready
        move x:(r7+$4),a
        move x:(r7+$6),x0
        cmp x0,a
        bne pkwto_pending
        move x:(r7+$5),a
        move x:(r7+$7),x0
        cmp x0,a
        beq pkwto_targets_ready
pkwto_pending:
        move #>$1,a
        move a1,x:(r5+$5a)
pkwto_targets_ready:
        move x:(r5+$52),x0
        move x:(r7+$4),y0
        move x:(r7+$5),y1
        jsr pkwt_fetch_wave
        move a1,x:(r5+$54)
        move x:(r5+$5a),a
        tst a
        beq pkwto_current_next
        move x:(r7+$6),y0
        move x:(r7+$7),y1
        bra pkwto_first_next
pkwto_current_next:
        move x:(r7+$4),y0
        move x:(r7+$5),y1
pkwto_first_next:
        move x:(r5+$52),a
        add #>$1,a
        and #>$7ff,a
        move a1,x0
        jsr pkwt_fetch_wave
        move a1,x:(r5+$55)
        move x:(r5+$52),x0
        move x:(r6+$22),y0
        move x:(r6+$23),y1
        jsr pkwt_fetch_wave
        move a1,x:(r5+$56)
        move x:(r5+$5a),a
        tst a
        beq pkwto_secondary_next
        move x:(r6+$24),y0
        move x:(r6+$25),y1
        bra pkwto_second_next
pkwto_secondary_next:
        move x:(r6+$22),y0
        move x:(r6+$23),y1
pkwto_second_next:
        move x:(r5+$52),a
        add #>$1,a
        and #>$7ff,a
        move a1,x0
        jsr pkwt_fetch_wave
        move a1,x:(r5+$57)
        move x:(r5+$55),a
        move x:(r5+$54),x0
        sub x0,a
        move a1,x0
        move x:(r5+$53),y0
        mpy y0,x0,a
        asr #$a,a,a
        move a0,a
        move x:(r5+$54),x0
        add x0,a
        asl #$8,a,a
        move a1,a
        asr #$8,a,a
        move a1,x:(r5+$54)
        move x:(r5+$57),a
        move x:(r5+$56),x0
        sub x0,a
        move a1,x0
        move x:(r5+$53),y0
        mpy y0,x0,a
        asr #$a,a,a
        move a0,a
        move x:(r5+$56),x0
        add x0,a
        asl #$8,a,a
        move a1,a
        asr #$8,a,a
        move a1,x0
        move x:(r6+$26),y0
        mpysu x0,y0,a
        asr #$1,a,a
        move a0,x:(r5+$57)
        move #>$ff,a
        sub y0,a
        move a1,y0
        move x:(r5+$54),x0
        mpy y0,x0,a
        asr #$1,a,a
        move a0,a
        move x:(r5+$57),x0
        add x0,a
        ; Native result takes bits 8..23 then casts to signed16.
        move a1,a
        asr #$8,a,a
        rts

pkwt_fetch_wave:
        move x0,x:(r5+$5b)
        move y1,a
        and #>$ff,a
        asl #$10,a,a
        add y0,a
        cmp #>$0222a0,a
        beq pkwt_initial_wave
        sub #>$0327cc,a
        lsr #$c,a
        add #>$1,a
        bra pkwt_wave_index_ready
pkwt_initial_wave:
        clr a
pkwt_wave_index_ready:
        asl #$b,a,a
        move x:(r5+$5b),x0
        add x0,a
        move a1,x0
        jsr pkwt_packed_s16
        rts

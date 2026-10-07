; Fold Drum 1 candidate renderer: shared exact Simple Drum primitives.
; 40 live words, prepared base at +$34/$35. Private scratch as Simple Drum.
; Not dispatched by PERKY3 until controls/trigger/integration gates qualify it.
pk_fold_voice:
        move r6,a
        move a1,x:(r5+$60)
        do n7,pkfd_samples_done
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
        move a1,x0
        jsr pk_simple_frequency
        move a1,b
        and #>$ffff,b
        move b1,x:(r6+$4)
        asr #$10,a,a
        and #>$ffff,a
        move a1,x:(r6+$5)
        lua (r6+$2),r7
        jsr pk_simple_oscillator
        move a1,x:(r5+$5e)
        move a1,x0
        move x:(r6+$24),a
        asl #$8,a,a
        move a1,a
        asr #$8,a,a
        add #>$100,a
        move a1,y0
        mpy y0,x0,a
        asr #$9,a,a
        move a0,a
        add #>$8000,a
        and #>$1ffff,a
        move a1,a
        cmp #>$10000,a
        blt pkfd_rising
        move a1,x0
        move #>$18000,a
        sub x0,a
        bra pkfd_folded
pkfd_rising:
        sub #>$8000,a
pkfd_folded:
        move a1,x:(r5+$5f)
        move x:(r6+$23),a
        cmp #>$210,a
        bgt pkfd_transient_done
        move x:(r6+$22),a
        tst a
        beq pkfd_pulse
        cmp #>$2,a
        bne pkfd_counter_step
        ; Existing qualified noise helper uses +$c/$d/$e state fields.
        ; Offset its voice base to Fold's +$25/$26/$27 sample-hold fields.
        lua (r6+$19),r6
        jsr pknv_noise
        move x:(r5+$60),r6
        move x:(r5+$61),a
        asl #$8,a,a
        move a1,a
        asr #$8,a,a
        move a1,x0
        move x:(r6+$23),a
        cmp #>$110,a
        bgt pkfd_counter_step
        cmp #>$8f,a
        bgt pkfd_noise_tail
        move #>$b,y0
        mpysu x0,y0,a
        asr #$5,a,a
        move a0,a
        bra pkfd_add_noise
pkfd_noise_tail:
        move a1,y0
        move #>$110,a
        sub y0,a
        move a1,y0
        mpysu x0,y0,a
        asr #$9,a,a
        move a0,x0
        move #>$2c,y0
        mpysu x0,y0,a
        asr #$7,a,a
        move a0,a
pkfd_add_noise:
        move x:(r5+$5f),x0
        add x0,a
        move a1,x:(r5+$5f)
        bra pkfd_counter_step
pkfd_pulse:
        move x:(r5+$5f),a
        add #>$3fff,a
        move a1,x:(r5+$5f)
pkfd_counter_step:
        move x:(r6+$23),a
        add #>$1,a
        move a1,x:(r6+$23)
pkfd_transient_done:
        move x:(r6+$1),a
        tst a
        bne pkfd_muted
        move x:(r5+$5f),a
        move x:(r5+$5e),x0
        add x0,a
        asr #$1,a,a
        move a1,x0
        move x:(r5+$5d),y0
        mpysu x0,y0,a
        asr #$11,a,a
        ; Cast the high half of low32(product) to signed16 before velocity.
        move a0,a
        asl #$8,a,a
        move a1,a
        asr #$8,a,a
        move a1,x0
        move x:(r6),y0
        mpysu x0,y0,a
        asr #$9,a,a
        move a0,a
        bra pkfd_store
pkfd_muted:
        clr a
pkfd_store:
        move a1,x:(r0)+
        move a1,x:(r0)+
pkfd_samples_done:
        nop
        move x:(r5+$60),r6
        rts

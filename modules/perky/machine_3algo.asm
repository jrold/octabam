; Composed reduced Perky DSP machine: Fold Drum 1 + Resonant Bass +
; Resonant Snare, one algorithm per track, one Perky track per core.
pk3d_source:
        move    a,x:>$20e               ; replay displaced stock op
        move    x:>$418,b               ; this core's track slot
        tst     b
        bne     pk3v_not_admitted
        move    x:>$209,r4              ; current source record
        move    #>$00504b,x0
        move    x:(r4),b
        and     #>$ffff,b
        cmp     x0,b
        bne     pk3v_not_admitted
        move    #>$005931,x0
        move    x:(r4+$2),b
        and     #>$ffff,b
        cmp     x0,b
        bne     pk3v_not_admitted
        bra     pk3v_hit
pk3v_not_admitted:
        rts                             ; stock/other source runs
pk3v_hit:
        ; One Perky voice per core: the first admitted PERKY record wins
        ; for the whole frame; every later one renders silence.
        move    x:>$38ed,a
        tst     a
        bne     pk3c_silence
        move    #>$1,a
        move    a1,x:>$38ed
        ; Consume the same FLEX ring slot advance as the qualified seam.
        move    x:>$20b,a
        add     #>$80,a
        move    a,x:>$20b
        ; Engine id: low half of the record word at ENGINE_ID_OFFSET.
        move    x:(r4+$13),b
        and     #>$ffff,b
        move    b1,x0                   ; x0 = engine id
        move    x:>$38ec,a
        move    a,x:>$38ec
        move    #>$003800,r6            ; this core has exactly one voice
        move    #>$3940,r5
        move    #>$ffffff,m0
        move    #>$ffffff,m1
        move    #>$ffffff,m2
        move    #>$ffffff,m3
        move    #>$ffffff,m4
        move    #>$ffffff,m5
        move    #>$ffffff,m6
        move    #$0,r0                  ; stock source buffer X:0
        ; Record words 4..7 carry this block's prepared controls.
        move    x:(r4+$8),a
        move    a1,x:(r6+$67)
        move    x:(r4+$a),b
        move    x:(r4+$c),a
        move    a1,x:(r5+$70)
        move    b1,x:(r5+$71)
        move    x:(r4+$e),a
        move    a1,x:(r5+$72)
        ; Dispatch on the masked engine id.
        move    x0,a
        cmp     #>$0,a
        beq     pk3e_entry
        cmp     #>$a,a
        beq     pk3n_entry
        cmp     #>$b,a
        beq     pk3a_entry
        bra     pk3c_silence
pk3e_entry:
        jsrl    pk_simple_base
        jsrl    pk_fold_voice
        bra     pk3i_finish
pk3n_entry:
        jsrl    pk3d_bass_voice
        bra     pk3i_finish
pk3a_entry:
        jsrl    pk3d_snare_voice
pk3i_finish:
        bra     pk3z_scale
pk3c_silence:
        move    #>$ffffff,m0
        move    #$0,r0
        clr     a
        do      #$20,pk3y_silence_done
        move    a1,x:(r0)+
pk3y_silence_done:
        nop
pk3z_scale:
        move    #$0,r0
        do      #$20,pk3x_scaled
        move    x:(r0),a
        asl     a
        asl     a
        asl     a
        asl     a
        asl     a
        asl     a
        asl     a
        asl     a
        move    a1,x:(r0)+
pk3x_scaled:
        nop
        move    #>$10,n7
        move    ssh,x0
        jmp     @CONT@

; ===== BEGIN resonant_bass.asm =====

pk3d_bass_voice:
        move r5,a
        add #>$40,a
        move a1,r4
        move r6,a
        move a1,x:(r5+$3e)
        do n7,pk3b_pkr_samples_done
        move x:(r5+$3e),r6
        lua (r6+$1),r6
        jsrl pk_noise_hat_envelope
        move x:(r5+$3e),r6
        move #>$0,a
        move a1,x:(r5+$36)
        move #>$0,a
        move a1,x:(r5+$37)
        move r6,a
        add #>$22,a
        move a1,r6
        jsrl pk_resonant_decay
        move x:(r5+$3e),r6
        move x:(r4+$0),a
        move a1,x:(r4+$1c)
        move x:(r4+$1),a
        move a1,x:(r4+$1d)
        move #>$000000,a
        move #>$000000,a0
        move a1,x1
        move a0,y1
        move x:(r6+$2f),a
        asl #$8,a,a
        move a1,a
        asr #$8,a,a
        move x:(r6+$2e),b
        lsl #$8,b
        move b1,a0
        move x1,b
        move y1,b0
        cmp b,a
        bge pk3b_pkr_label_00001
        move x:(r4+$1d),a
        move x:(r4+$1c),b
        lsl #$8,b
        move b1,a0
        move a1,x1
        move a0,y1
        move #>$000000,a
        move #>$000000,a0
        move x1,b
        move y1,b0
        sub b,a
        move a1,b
        and #>$00ffff,b
        move b1,x:(r4+$1d)
        move a0,b
        lsr #$8,b
        and #>$00ffff,b
        move b1,x:(r4+$1c)
pk3b_pkr_label_00001:
        move #>$000000,a
        move #>$000000,a0
        move a1,x1
        move a0,y1
        move x:(r6+$2f),a
        asl #$8,a,a
        move a1,a
        asr #$8,a,a
        move x:(r6+$2e),b
        lsl #$8,b
        move b1,a0
        move x1,b
        move y1,b0
        cmp b,a
        beq pk3b_pkr_label_00002
        move #>$000000,a
        move #>$400000,a0
        move a1,x1
        move a0,y1
        move x:(r4+$1d),a
        move x:(r4+$1c),b
        lsl #$8,b
        move b1,a0
        move x1,b
        move y1,b0
        add b,a
        move a1,b
        and #>$00ffff,b
        move b1,x:(r4+$1d)
        move a0,b
        lsr #$8,b
        and #>$00ffff,b
        move b1,x:(r4+$1c)
pk3b_pkr_label_00002:
        move #>$1,a
        move a1,x:(r5+$36)
        move #>$0,a
        move a1,x:(r5+$37)
        move r6,a
        add #>$2c,a
        move a1,r6
        jsrl pk_resonant_decay
        move x:(r5+$3e),r6
        move x:(r4+$0),a
        move a1,x:(r4+$1e)
        move x:(r4+$1),a
        move a1,x:(r4+$1f)
        move x:(r4+$1f),a
        move x:(r4+$1e),b
        lsl #$8,b
        move b1,a0
        move a1,x1
        move a0,y1
        move x:(r4+$1d),a
        move x:(r4+$1c),b
        lsl #$8,b
        move b1,a0
        move x1,b
        move y1,b0
        add b,a
        move a1,b
        and #>$00ffff,b
        move b1,x:(r4+$21)
        move a0,b
        lsr #$8,b
        and #>$00ffff,b
        move b1,x:(r4+$20)
        move #>$0,a
        move a1,x:(r5+$36)
        move #>$0,a
        move a1,x:(r5+$37)
        move r6,a
        add #>$36,a
        move a1,r6
        jsrl pk_resonant_decay
        move x:(r5+$3e),r6
        move x:(r4+$0),a
        move a1,x:(r4+$22)
        move x:(r4+$1),a
        move a1,x:(r4+$23)
        move x:(r6+$1d),a
        move a1,x:(r4+$24)
        clr a
        move a1,x:(r4+$25)
        move #>$000000,a
        move #>$000000,a0
        move a1,x1
        move a0,y1
        move x:(r6+$39),a
        asl #$8,a,a
        move a1,a
        asr #$8,a,a
        move x:(r6+$38),b
        lsl #$8,b
        move b1,a0
        move x1,b
        move y1,b0
        cmp b,a
        beq pk3b_pkr_label_00003
        move #>$000000,a
        move #>$088000,a0
        move a1,x1
        move a0,y1
        move x:(r4+$25),a
        move x:(r4+$24),b
        lsl #$8,b
        move b1,a0
        move x1,b
        move y1,b0
        add b,a
        move a1,b
        and #>$00ffff,b
        move b1,x:(r4+$25)
        move a0,b
        lsr #$8,b
        and #>$00ffff,b
        move b1,x:(r4+$24)
pk3b_pkr_label_00003:
        clr a
        move a1,x:(r4+$25)
        move x:(r4+$25),a
        asl #$8,a,a
        move a1,a
        asr #$8,a,a
        move x:(r4+$24),b
        lsl #$8,b
        move b1,a0
        move a1,x1
        move a0,y1
        clr a
        move x:(r6+$10),b
        lsl #$8,b
        move b1,a0
        move x1,b
        move y1,b0
        cmp b,a
        beq pk3b_pkr_label_00004
        move x:(r4+$24),a
        move a1,x:(r6+$10)
        move x:(r4+$25),a
        move a1,x:(r5-$2d)
        move #>$000001,a
        move a1,x:(r6+$f)
        move #>$000000,a
        move a1,x:(r5-$2d)
pk3b_pkr_label_00004:
        move x:(r4+$20),a
        move a1,x:(r4+$18)
        move x:(r4+$21),a
        move a1,x:(r4+$19)
        move r6,a
        add #>$f,a
        move a1,r6
        jsrl pk_resonant_core
        move x:(r5+$3e),r6
        move x:(r4+$21),a
        asl #$8,a,a
        move a1,a
        asr #$8,a,a
        move x:(r4+$20),b
        lsl #$8,b
        move b1,a0
        asr #>$4,a,a
        move a1,b
        and #>$00ffff,b
        move b1,x:(r4+$27)
        move a0,b
        lsr #$8,b
        and #>$00ffff,b
        move b1,x:(r4+$26)
        move x:(r4+$27),a
        move x:(r4+$26),b
        lsl #$8,b
        move b1,a0
        move a1,x1
        move a0,y1
        move x:(r6+$1c),a
        move x:(r6+$1b),b
        lsl #$8,b
        move b1,a0
        move x1,b
        move y1,b0
        add b,a
        move a1,b
        and #>$00ffff,b
        move b1,x:(r4+$29)
        move a0,b
        lsr #$8,b
        and #>$00ffff,b
        move b1,x:(r4+$28)
        move x:(r6+$1f),a
        move x:(r6+$1e),b
        lsl #$8,b
        move b1,a0
        move a1,x1
        move a0,y1
        move x:(r4+$29),a
        move x:(r4+$28),b
        lsl #$8,b
        move b1,a0
        move x1,b
        move y1,b0
        sub b,a
        move a1,b
        and #>$00ffff,b
        move b1,x:(r4+$2b)
        move a0,b
        lsr #$8,b
        and #>$00ffff,b
        move b1,x:(r4+$2a)
        move #>$1,a
        move a1,x:(r5+$36)
        move #>$0,a
        move a1,x:(r5+$37)
        move r6,a
        add #>$40,a
        move a1,r6
        jsrl pk_resonant_decay
        move x:(r5+$3e),r6
        move x:(r4+$0),a
        move a1,x:(r4+$2c)
        move x:(r4+$1),a
        move a1,x:(r4+$2d)
        move x:(r6+$20),a
        move a1,x:(r5-$40)
        move x:(r6+$21),a
        move a1,x:(r5-$3f)
        move x:(r4+$2a),a
        move a1,x:(r5-$3e)
        move x:(r4+$2b),a
        move a1,x:(r5-$3d)
        jsrl pk_u32_mul_low
        move x:(r5-$38),a
        move a1,x:(r4+$30)
        move x:(r5-$37),a
        move a1,x:(r4+$31)
        move x:(r4+$31),a
        asl #$8,a,a
        move a1,a
        asr #$8,a,a
        move x:(r4+$30),b
        lsl #$8,b
        move b1,a0
        asr #>$f,a,a
        move a1,b
        and #>$00ffff,b
        move b1,x:(r4+$31)
        move a0,b
        lsr #$8,b
        and #>$00ffff,b
        move b1,x:(r4+$30)
        move x:(r4+$31),a
        move x:(r4+$30),b
        lsl #$8,b
        move b1,a0
        move a1,x1
        move a0,y1
        move x:(r6+$1f),a
        move x:(r6+$1e),b
        lsl #$8,b
        move b1,a0
        move x1,b
        move y1,b0
        add b,a
        move a1,b
        and #>$00ffff,b
        move b1,x:(r4+$33)
        move a0,b
        lsr #$8,b
        and #>$00ffff,b
        move b1,x:(r4+$32)
        move x:(r4+$32),a
        move a1,x:(r6+$1e)
        move x:(r4+$33),a
        move a1,x:(r6+$1f)
        jsrl pk_resonant_noise
        asl #$8,a,a
        move a1,a
        asr #$8,a,a
        asr #$10,a,a
        move a1,b
        and #>$00ffff,b
        move b1,x:(r4+$2f)
        move a0,b
        lsr #$8,b
        and #>$00ffff,b
        move b1,x:(r4+$2e)
        move x:(r4+$2e),a
        move a1,x:(r4+$18)
        move x:(r4+$2f),a
        move a1,x:(r4+$19)
        move r6,a
        add #>$4a,a
        move a1,r6
        jsrl pk_resonant_core
        move x:(r5+$3e),r6
        move x:(r6+$56),a
        move a1,x:(r5-$40)
        move x:(r6+$57),a
        move a1,x:(r5-$3f)
        move x:(r4+$2c),a
        move a1,x:(r5-$3e)
        move x:(r4+$2d),a
        move a1,x:(r5-$3d)
        jsrl pk_u32_mul_low
        move x:(r5-$38),a
        move a1,x:(r4+$30)
        move x:(r5-$37),a
        move a1,x:(r4+$31)
        move x:(r4+$31),a
        asl #$8,a,a
        move a1,a
        asr #$8,a,a
        move x:(r4+$30),b
        lsl #$8,b
        move b1,a0
        asr #>$10,a,a
        move a1,b
        and #>$00ffff,b
        move b1,x:(r4+$31)
        move a0,b
        lsr #$8,b
        and #>$00ffff,b
        move b1,x:(r4+$30)
        move x:(r4+$31),a
        move x:(r4+$30),b
        lsl #$8,b
        move b1,a0
        move a1,x1
        move a0,y1
        move x:(r4+$33),a
        move x:(r4+$32),b
        lsl #$8,b
        move b1,a0
        move x1,b
        move y1,b0
        add b,a
        move a1,b
        and #>$00ffff,b
        move b1,x:(r4+$33)
        move a0,b
        lsr #$8,b
        and #>$00ffff,b
        move b1,x:(r4+$32)
        move x:(r4+$33),a
        move x:(r4+$32),b
        lsl #$8,b
        move b1,a0
        move a1,x1
        move a0,y1
        move x:(r4+$33),a
        move x:(r4+$32),b
        lsl #$8,b
        move b1,a0
        move x1,b
        move y1,b0
        add b,a
        move a1,b
        and #>$00ffff,b
        move b1,x:(r4+$31)
        move a0,b
        lsr #$8,b
        and #>$00ffff,b
        move b1,x:(r4+$30)
        move x:(r4+$31),a
        move x:(r4+$30),b
        lsl #$8,b
        move b1,a0
        move a1,x1
        move a0,y1
        move x:(r4+$33),a
        move x:(r4+$32),b
        lsl #$8,b
        move b1,a0
        move x1,b
        move y1,b0
        add b,a
        move a1,b
        and #>$00ffff,b
        move b1,x:(r4+$33)
        move a0,b
        lsr #$8,b
        and #>$00ffff,b
        move b1,x:(r4+$32)
        move x:(r4+$32),a
        move a1,x:(r5-$40)
        move x:(r4+$33),a
        move a1,x:(r5-$3f)
        move x:(r6+$0),a
        move a1,x:(r5-$3e)
        clr a
        move a1,x:(r5-$3d)
        jsrl pk_u32_mul_low
        move x:(r5-$38),a
        move a1,x:(r4+$1c)
        move x:(r5-$37),a
        move a1,x:(r4+$1d)
        move x:(r4+$1d),a
        asl #$8,a,a
        move a1,a
        asr #$8,a,a
        move x:(r4+$1c),b
        lsl #$8,b
        move b1,a0
        asr #>$8,a,a
        move a1,b
        and #>$00ffff,b
        move b1,x:(r4+$1d)
        move a0,b
        lsr #$8,b
        and #>$00ffff,b
        move b1,x:(r4+$1c)
        move #>$ffffff,a
        move #>$800000,a0
        move a1,x1
        move a0,y1
        move x:(r4+$1d),a
        asl #$8,a,a
        move a1,a
        asr #$8,a,a
        move x:(r4+$1c),b
        lsl #$8,b
        move b1,a0
        move x1,b
        move y1,b0
        cmp b,a
        bge pk3b_pkr_label_00005
        move #>$008000,a
        move a1,x:(r4+$1c)
        move #>$00ffff,a
        move a1,x:(r4+$1d)
pk3b_pkr_label_00005:
        move #>$000000,a
        move #>$7fff00,a0
        move a1,x1
        move a0,y1
        move x:(r4+$1d),a
        asl #$8,a,a
        move a1,a
        asr #$8,a,a
        move x:(r4+$1c),b
        lsl #$8,b
        move b1,a0
        move x1,b
        move y1,b0
        cmp b,a
        ble pk3b_pkr_label_00006
        move #>$007fff,a
        move a1,x:(r4+$1c)
        move #>$000000,a
        move a1,x:(r4+$1d)
pk3b_pkr_label_00006:
        move x:(r4+$1d),a
        asl #$8,a,a
        move a1,a
        asr #$8,a,a
        move x:(r4+$1c),b
        lsl #$8,b
        move b1,a0
        asl #$10,a,a
        move a1,x:(r0)+
        move a1,x:(r0)+
pk3b_pkr_samples_done:
        nop
        rts
; ===== END resonant_bass.asm =====

; ===== BEGIN resonant_snare.asm =====

pk3d_snare_voice:
        move r5,a
        add #>$40,a
        move a1,r4
        move r6,a
        move a1,x:(r5+$3e)
        do n7,pk3s_pkr_samples_done
        move x:(r5+$3e),r6
        lua (r6+$1),r6
        jsrl pk_noise_hat_envelope
        move x:(r5+$3e),r6
        move #>$1,a
        move a1,x:(r5+$36)
        move #>$0,a
        move a1,x:(r5+$37)
        move r6,a
        add #>$39,a
        move a1,r6
        jsrl pk_resonant_decay
        move x:(r5+$3e),r6
        move x:(r4+$0),a
        move a1,x:(r4+$1e)
        move x:(r4+$1),a
        move a1,x:(r4+$1f)
        move #>$1,a
        move a1,x:(r5+$36)
        move #>$a3d,a
        move a1,x:(r5+$37)
        move r6,a
        add #>$43,a
        move a1,r6
        jsrl pk_resonant_decay
        move x:(r5+$3e),r6
        move x:(r4+$0),a
        move a1,x:(r4+$20)
        move x:(r4+$1),a
        move a1,x:(r4+$21)
        move x:(r4+$21),a
        move x:(r4+$20),b
        lsl #$8,b
        move b1,a0
        move a1,x1
        move a0,y1
        move x:(r4+$1f),a
        move x:(r4+$1e),b
        lsl #$8,b
        move b1,a0
        move x1,b
        move y1,b0
        add b,a
        move a1,b
        and #>$00ffff,b
        move b1,x:(r4+$1d)
        move a0,b
        lsr #$8,b
        and #>$00ffff,b
        move b1,x:(r4+$1c)
        move x:(r4+$1c),a
        move a1,x:(r4+$18)
        move x:(r4+$1d),a
        move a1,x:(r4+$19)
        move r6,a
        add #>$f,a
        move a1,r6
        jsrl pk_resonant_core
        move x:(r5+$3e),r6
        move x:(r4+$1d),a
        asl #$8,a,a
        move a1,a
        asr #$8,a,a
        move x:(r4+$1c),b
        lsl #$8,b
        move b1,a0
        asr #>$4,a,a
        move a1,b
        and #>$00ffff,b
        move b1,x:(r4+$25)
        move a0,b
        lsr #$8,b
        and #>$00ffff,b
        move b1,x:(r4+$24)
        move x:(r4+$25),a
        move x:(r4+$24),b
        lsl #$8,b
        move b1,a0
        move a1,x1
        move a0,y1
        move x:(r6+$1c),a
        move x:(r6+$1b),b
        lsl #$8,b
        move b1,a0
        move x1,b
        move y1,b0
        add b,a
        move a1,b
        and #>$00ffff,b
        move b1,x:(r4+$25)
        move a0,b
        lsr #$8,b
        and #>$00ffff,b
        move b1,x:(r4+$24)
        move #>$1,a
        move a1,x:(r5+$36)
        move #>$3333,a
        move a1,x:(r5+$37)
        move r6,a
        add #>$4d,a
        move a1,r6
        jsrl pk_resonant_decay
        move x:(r5+$3e),r6
        move x:(r4+$0),a
        move a1,x:(r4+$22)
        move x:(r4+$1),a
        move a1,x:(r4+$23)
        move x:(r4+$22),a
        move a1,x:(r4+$18)
        move x:(r4+$23),a
        move a1,x:(r4+$19)
        move r6,a
        add #>$1d,a
        move a1,r6
        jsrl pk_resonant_core
        move x:(r5+$3e),r6
        move x:(r4+$23),a
        asl #$8,a,a
        move a1,a
        asr #$8,a,a
        move x:(r4+$22),b
        lsl #$8,b
        move b1,a0
        asr #>$4,a,a
        move a1,b
        and #>$00ffff,b
        move b1,x:(r4+$27)
        move a0,b
        lsr #$8,b
        and #>$00ffff,b
        move b1,x:(r4+$26)
        move x:(r4+$27),a
        move x:(r4+$26),b
        lsl #$8,b
        move b1,a0
        move a1,x1
        move a0,y1
        move x:(r6+$2a),a
        move x:(r6+$29),b
        lsl #$8,b
        move b1,a0
        move x1,b
        move y1,b0
        add b,a
        move a1,b
        and #>$00ffff,b
        move b1,x:(r4+$27)
        move a0,b
        lsr #$8,b
        and #>$00ffff,b
        move b1,x:(r4+$26)
        move #>$1,a
        move a1,x:(r5+$36)
        move #>$0,a
        move a1,x:(r5+$37)
        move r6,a
        add #>$57,a
        move a1,r6
        jsrl pk_resonant_decay
        move x:(r5+$3e),r6
        move x:(r4+$0),a
        move a1,x:(r4+$28)
        move x:(r4+$1),a
        move a1,x:(r4+$29)
        jsrl pk_resonant_noise
        asl #$8,a,a
        move a1,a
        asr #$8,a,a
        asr #$10,a,a
        move a1,b
        and #>$00ffff,b
        move b1,x:(r4+$2b)
        move a0,b
        lsr #$8,b
        and #>$00ffff,b
        move b1,x:(r4+$2a)
        move x:(r4+$2a),a
        move a1,x:(r4+$18)
        move x:(r4+$2b),a
        move a1,x:(r4+$19)
        move r6,a
        add #>$2b,a
        move a1,r6
        jsrl pk_resonant_core
        move x:(r5+$3e),r6
        move x:(r4+$26),a
        move a1,x:(r5-$40)
        move x:(r4+$27),a
        move a1,x:(r5-$3f)
        move x:(r6+$61),a
        move a1,x:(r5-$3e)
        move x:(r6+$62),a
        move a1,x:(r5-$3d)
        jsrl pk_u32_mul_low
        move x:(r5-$38),a
        move a1,x:(r4+$2e)
        move x:(r5-$37),a
        move a1,x:(r4+$2f)
        move x:(r4+$2f),a
        asl #$8,a,a
        move a1,a
        asr #$8,a,a
        move x:(r4+$2e),b
        lsl #$8,b
        move b1,a0
        asr #>$f,a,a
        move a1,b
        and #>$00ffff,b
        move b1,x:(r4+$2f)
        move a0,b
        lsr #$8,b
        and #>$00ffff,b
        move b1,x:(r4+$2e)
        move x:(r6+$63),a
        move a1,x:(r5-$40)
        move x:(r6+$64),a
        move a1,x:(r5-$3f)
        move x:(r4+$24),a
        move a1,x:(r5-$3e)
        move x:(r4+$25),a
        move a1,x:(r5-$3d)
        jsrl pk_u32_mul_low
        move x:(r5-$38),a
        move a1,x:(r4+$2c)
        move x:(r5-$37),a
        move a1,x:(r4+$2d)
        move x:(r4+$2d),a
        asl #$8,a,a
        move a1,a
        asr #$8,a,a
        move x:(r4+$2c),b
        lsl #$8,b
        move b1,a0
        asr #>$f,a,a
        move a1,b
        and #>$00ffff,b
        move b1,x:(r4+$2d)
        move a0,b
        lsr #$8,b
        and #>$00ffff,b
        move b1,x:(r4+$2c)
        move x:(r4+$2d),a
        move x:(r4+$2c),b
        lsl #$8,b
        move b1,a0
        move a1,x1
        move a0,y1
        move x:(r4+$2f),a
        move x:(r4+$2e),b
        lsl #$8,b
        move b1,a0
        move x1,b
        move y1,b0
        add b,a
        move a1,b
        and #>$00ffff,b
        move b1,x:(r4+$2f)
        move a0,b
        lsr #$8,b
        and #>$00ffff,b
        move b1,x:(r4+$2e)
        move x:(r6+$37),a
        move a1,x:(r5-$40)
        move x:(r6+$38),a
        move a1,x:(r5-$3f)
        move x:(r4+$28),a
        move a1,x:(r5-$3e)
        move x:(r4+$29),a
        move a1,x:(r5-$3d)
        jsrl pk_u32_mul_low
        move x:(r5-$38),a
        move a1,x:(r4+$2c)
        move x:(r5-$37),a
        move a1,x:(r4+$2d)
        move x:(r4+$2d),a
        asl #$8,a,a
        move a1,a
        asr #$8,a,a
        move x:(r4+$2c),b
        lsl #$8,b
        move b1,a0
        asr #>$f,a,a
        move a1,b
        and #>$00ffff,b
        move b1,x:(r4+$2d)
        move a0,b
        lsr #$8,b
        and #>$00ffff,b
        move b1,x:(r4+$2c)
        move x:(r4+$2d),a
        move x:(r4+$2c),b
        lsl #$8,b
        move b1,a0
        move a1,x1
        move a0,y1
        move x:(r4+$2f),a
        move x:(r4+$2e),b
        lsl #$8,b
        move b1,a0
        move x1,b
        move y1,b0
        add b,a
        move a1,b
        and #>$00ffff,b
        move b1,x:(r4+$2f)
        move a0,b
        lsr #$8,b
        and #>$00ffff,b
        move b1,x:(r4+$2e)
        move x:(r4+$2f),a
        move x:(r4+$2e),b
        lsl #$8,b
        move b1,a0
        move a1,x1
        move a0,y1
        move x:(r4+$2f),a
        move x:(r4+$2e),b
        lsl #$8,b
        move b1,a0
        move x1,b
        move y1,b0
        add b,a
        move a1,b
        and #>$00ffff,b
        move b1,x:(r4+$2f)
        move a0,b
        lsr #$8,b
        and #>$00ffff,b
        move b1,x:(r4+$2e)
        move x:(r4+$2e),a
        move a1,x:(r5-$40)
        move x:(r4+$2f),a
        move a1,x:(r5-$3f)
        move x:(r6+$0),a
        move a1,x:(r5-$3e)
        clr a
        move a1,x:(r5-$3d)
        jsrl pk_u32_mul_low
        move x:(r5-$38),a
        move a1,x:(r4+$1c)
        move x:(r5-$37),a
        move a1,x:(r4+$1d)
        move x:(r4+$1d),a
        asl #$8,a,a
        move a1,a
        asr #$8,a,a
        move x:(r4+$1c),b
        lsl #$8,b
        move b1,a0
        asr #>$8,a,a
        move a1,b
        and #>$00ffff,b
        move b1,x:(r4+$1d)
        move a0,b
        lsr #$8,b
        and #>$00ffff,b
        move b1,x:(r4+$1c)
        move #>$ffffff,a
        move #>$800000,a0
        move a1,x1
        move a0,y1
        move x:(r4+$1d),a
        asl #$8,a,a
        move a1,a
        asr #$8,a,a
        move x:(r4+$1c),b
        lsl #$8,b
        move b1,a0
        move x1,b
        move y1,b0
        cmp b,a
        bge pk3s_pkr_label_00001
        move #>$008000,a
        move a1,x:(r4+$1c)
        move #>$00ffff,a
        move a1,x:(r4+$1d)
pk3s_pkr_label_00001:
        move #>$000000,a
        move #>$7fff00,a0
        move a1,x1
        move a0,y1
        move x:(r4+$1d),a
        asl #$8,a,a
        move a1,a
        asr #$8,a,a
        move x:(r4+$1c),b
        lsl #$8,b
        move b1,a0
        move x1,b
        move y1,b0
        cmp b,a
        ble pk3s_pkr_label_00002
        move #>$007fff,a
        move a1,x:(r4+$1c)
        move #>$000000,a
        move a1,x:(r4+$1d)
pk3s_pkr_label_00002:
        move x:(r4+$1d),a
        asl #$8,a,a
        move a1,a
        asr #$8,a,a
        move x:(r4+$1c),b
        lsl #$8,b
        move b1,a0
        asl #$10,a,a
        move a1,x:(r0)+
        move a1,x:(r0)+
pk3s_pkr_samples_done:
        nop
        rts
; ===== END resonant_snare.asm =====

; ===== BEGIN resident_cores.asm =====

pk_resonant_decay:
        move x:(r6+$1),a
        cmp #>$7f,a
        bgt pkr_label_00007
        move x:(r6+$5),a
        cmp #>$7f,a
        bgt pkr_label_00007
        move x:(r6+$9),a
        tst a
        bne pkr_label_00007
        move x:(r6+$7),a
        add #>$40,a
        and #>$00ffff,a
        cmp #>$7f,a
        bgt pkr_label_00007
        move x:(r6+$3),a
        tst a
        bne pkr_label_00008
        move x:(r6+$2),r2
        bra pkr_label_00009
pkr_label_00008:
        cmp #>$00ffff,a
        bne pkr_label_00007
        move #>$ffffff,r2
pkr_label_00009:
        move x:(r6+$7),a
        lsl #$10,a
        move x:(r6+$6),x0
        or x0,a
        move a1,r1
        move x:(r6+$1),a
        lsl #$10,a
        move x:(r6),x0
        or x0,a
        move a1,x0
        move x:(r6+$5),a
        lsl #$10,a
        move x:(r6+$4),y0
        or y0,a
        move a1,y0
        mpyuu x0,y0,a
        asr #$1,a,a
        asl #$18,a,a
        asr #$c,a,a
        move a1,a
        and #>$0fffff,a
        move a1,a
        move x:(r6+$8),x0
        cmp x0,a
        bge pkrd_min_done
        move x0,a
pkrd_min_done:
        move a1,r3
        move r2,a
        tst a
        ble pkrd_count_done
        sub #>$1,a
        move a1,r2
        move a1,x:(r6+$2)
        tst a
        bne pkrd_count_done
        move r1,a
        abs a
        move r3,x0
        add x0,a
        move a1,r3
pkrd_count_done:
        move r3,a
        move a1,b
        and #>$00ffff,b
        move b1,x:(r6+$4)
        lsr #$10,a
        move a1,x:(r6+$5)
        move r3,a
        move a1,x0
        move x:(r5+$36),a
        tst a
        beq pkrd_sign_done
        move r1,a
        tst a
        bge pkrd_sign_done
        move x0,a
        neg a
        move a1,x0
pkrd_sign_done:
        move r2,a
        tst a
        beq pkrd_constant_done
        move x:(r5+$37),a
        add x0,a
        move a1,x0
pkrd_constant_done:
        move x0,a
        asr #$10,a,a
        move a1,b
        and #>$00ffff,b
        move b1,x:(r4+$1)
        move a0,b
        lsr #$8,b
        and #>$00ffff,b
        move b1,x:(r4+$0)
        rts
pkr_label_00007:
        move x:(r6+$0),a
        move a1,x:(r5-$40)
        move x:(r6+$1),a
        move a1,x:(r5-$3f)
        move x:(r6+$4),a
        move a1,x:(r5-$3e)
        move x:(r6+$5),a
        move a1,x:(r5-$3d)
        jsrl pk_u32_mul_low
        move x:(r5-$38),a
        move a1,x:(r4+$0)
        move x:(r5-$37),a
        move a1,x:(r4+$1)
        move x:(r4+$1),a
        move x:(r4+$0),b
        lsl #$8,b
        move b1,a0
        asr #>$c,a,a
        move a1,b
        and #>$00ffff,b
        move b1,x:(r4+$1)
        move a0,b
        lsr #$8,b
        and #>$00ffff,b
        move b1,x:(r4+$0)
        move x:(r6+$9),a
        asl #$8,a,a
        move a1,a
        asr #$8,a,a
        move x:(r6+$8),b
        lsl #$8,b
        move b1,a0
        move a1,x1
        move a0,y1
        move x:(r4+$1),a
        asl #$8,a,a
        move a1,a
        asr #$8,a,a
        move x:(r4+$0),b
        lsl #$8,b
        move b1,a0
        move x1,b
        move y1,b0
        cmp b,a
        bge pkr_label_00010
        move x:(r6+$8),a
        move a1,x:(r4+$0)
        move x:(r6+$9),a
        move a1,x:(r4+$1)
pkr_label_00010:
        move x:(r4+$0),a
        move a1,x:(r6+$4)
        move x:(r4+$1),a
        move a1,x:(r6+$5)
        move x:(r6+$2),a
        move a1,x:(r4+$2)
        move x:(r6+$3),a
        move a1,x:(r4+$3)
        move x:(r6+$6),a
        move a1,x:(r4+$4)
        move x:(r6+$7),a
        move a1,x:(r4+$5)
        move #>$000000,a
        move #>$000000,a0
        move a1,x1
        move a0,y1
        move x:(r4+$3),a
        asl #$8,a,a
        move a1,a
        asr #$8,a,a
        move x:(r4+$2),b
        lsl #$8,b
        move b1,a0
        move x1,b
        move y1,b0
        cmp b,a
        ble pkr_label_00011
        move #>$000000,a
        move #>$000100,a0
        move a1,x1
        move a0,y1
        move x:(r4+$3),a
        move x:(r4+$2),b
        lsl #$8,b
        move b1,a0
        move x1,b
        move y1,b0
        sub b,a
        move a1,b
        and #>$00ffff,b
        move b1,x:(r4+$3)
        move a0,b
        lsr #$8,b
        and #>$00ffff,b
        move b1,x:(r4+$2)
        move x:(r4+$2),a
        move a1,x:(r6+$2)
        move x:(r4+$3),a
        move a1,x:(r6+$3)
        move #>$000000,a
        move #>$000000,a0
        move a1,x1
        move a0,y1
        move x:(r4+$3),a
        asl #$8,a,a
        move a1,a
        asr #$8,a,a
        move x:(r4+$2),b
        lsl #$8,b
        move b1,a0
        move x1,b
        move y1,b0
        cmp b,a
        bne pkr_label_00011
        move x:(r4+$4),a
        move a1,x:(r4+$6)
        move x:(r4+$5),a
        move a1,x:(r4+$7)
        move #>$000000,a
        move #>$000000,a0
        move a1,x1
        move a0,y1
        move x:(r4+$7),a
        asl #$8,a,a
        move a1,a
        asr #$8,a,a
        move x:(r4+$6),b
        lsl #$8,b
        move b1,a0
        move x1,b
        move y1,b0
        cmp b,a
        bge pkr_label_00012
        move x:(r4+$7),a
        move x:(r4+$6),b
        lsl #$8,b
        move b1,a0
        move a1,x1
        move a0,y1
        move #>$000000,a
        move #>$000000,a0
        move x1,b
        move y1,b0
        sub b,a
        move a1,b
        and #>$00ffff,b
        move b1,x:(r4+$7)
        move a0,b
        lsr #$8,b
        and #>$00ffff,b
        move b1,x:(r4+$6)
pkr_label_00012:
        move x:(r4+$7),a
        move x:(r4+$6),b
        lsl #$8,b
        move b1,a0
        move a1,x1
        move a0,y1
        move x:(r4+$1),a
        move x:(r4+$0),b
        lsl #$8,b
        move b1,a0
        move x1,b
        move y1,b0
        add b,a
        move a1,b
        and #>$00ffff,b
        move b1,x:(r4+$1)
        move a0,b
        lsr #$8,b
        and #>$00ffff,b
        move b1,x:(r4+$0)
        move x:(r4+$0),a
        move a1,x:(r6+$4)
        move x:(r4+$1),a
        move a1,x:(r6+$5)
pkr_label_00011:
        move #>$000000,a
        move #>$000000,a0
        move a1,x1
        move a0,y1
        clr a
        move x:(r5+$36),b
        lsl #$8,b
        move b1,a0
        move x1,b
        move y1,b0
        cmp b,a
        beq pkr_label_00013
        move #>$000000,a
        move #>$000000,a0
        move a1,x1
        move a0,y1
        move x:(r4+$5),a
        asl #$8,a,a
        move a1,a
        asr #$8,a,a
        move x:(r4+$4),b
        lsl #$8,b
        move b1,a0
        move x1,b
        move y1,b0
        cmp b,a
        bge pkr_label_00013
        move x:(r4+$1),a
        move x:(r4+$0),b
        lsl #$8,b
        move b1,a0
        move a1,x1
        move a0,y1
        move #>$000000,a
        move #>$000000,a0
        move x1,b
        move y1,b0
        sub b,a
        move a1,b
        and #>$00ffff,b
        move b1,x:(r4+$1)
        move a0,b
        lsr #$8,b
        and #>$00ffff,b
        move b1,x:(r4+$0)
pkr_label_00013:
        move #>$000000,a
        move #>$000000,a0
        move a1,x1
        move a0,y1
        move x:(r4+$3),a
        asl #$8,a,a
        move a1,a
        asr #$8,a,a
        move x:(r4+$2),b
        lsl #$8,b
        move b1,a0
        move x1,b
        move y1,b0
        cmp b,a
        beq pkr_label_00014
        clr a
        move x:(r5+$37),b
        lsl #$8,b
        move b1,a0
        move a1,x1
        move a0,y1
        move x:(r4+$1),a
        move x:(r4+$0),b
        lsl #$8,b
        move b1,a0
        move x1,b
        move y1,b0
        add b,a
        move a1,b
        and #>$00ffff,b
        move b1,x:(r4+$1)
        move a0,b
        lsr #$8,b
        and #>$00ffff,b
        move b1,x:(r4+$0)
pkr_label_00014:
        rts
pk_resonant_core:
        move #>$000000,a
        move #>$000000,a0
        move a1,x1
        move a0,y1
        clr a
        move x:(r6+$0),b
        lsl #$8,b
        move b1,a0
        move x1,b
        move y1,b0
        cmp b,a
        beq pkr_label_00015
        move x:(r6+$1),a
        lsr #$7,a
        and #>$0000ff,a
        move a1,n1
        move #>$002500,r1
        lua (r1+n1),r2
        move y:(r2),a
        move a1,x:(r5+$3a)
        move y:(r2+$1),b
        sub a,b
        move b1,x0
        move x:(r6+$1),a
        lsl #$9,a
        and #>$00ffff,a
        move a1,y0
        mpy y0,x0,a
        asr #$11,a,a
        move a0,a
        and #>$00ffff,a
        move x:(r5+$3a),x0
        add x0,a
        and #>$00ffff,a
        move a1,x:(r6+$3)
        clr a
        move a1,x:(r6+$4)
        move x:(r6+$2),a
        lsr #$7,a
        and #>$0000ff,a
        move a1,n1
        move #>$002600,r1
        lua (r1+n1),r2
        move y:(r2),a
        move a1,x:(r5+$3a)
        move y:(r2+$1),b
        sub a,b
        move b1,x0
        move x:(r6+$2),a
        lsl #$9,a
        and #>$00ffff,a
        move a1,y0
        mpy y0,x0,a
        asr #$11,a,a
        move a0,a
        and #>$00ffff,a
        move x:(r5+$3a),x0
        add x0,a
        and #>$00ffff,a
        move a1,x:(r6+$5)
        clr a
        move a1,x:(r6+$6)
        move #>$000000,a
        move a1,x:(r6+$0)
        move #>$000000,a
        move a1,x:(r5-$2d)
pkr_label_00015:
        move x:(r4+$19),a
        add #>$40,a
        and #>$00ffff,a
        cmp #>$7f,a
        bgt pkr_label_00016
        move x:(r6+$4),a
        tst a
        bne pkr_label_00016
        move x:(r6+$6),a
        tst a
        bne pkr_label_00016
        move x:(r6+$8),a
        tst a
        bne pkr_label_00016
        move x:(r6+$a),a
        asl #$8,a,a
        move a1,a
        asr #$8,a,a
        move a1,x:(r5+$36)
        asr #$10,a,a
        and #>$00ffff,a
        move a1,a
        move x:(r6+$b),x0
        cmp x0,a
        bne pkr_label_00016
        move x:(r6+$c),a
        asl #$8,a,a
        move a1,a
        asr #$8,a,a
        move a1,x:(r5+$37)
        asr #$10,a,a
        and #>$00ffff,a
        move a1,a
        move x:(r6+$d),x0
        cmp x0,a
        bne pkr_label_00016
        move x:(r4+$19),a
        lsl #$10,a
        move x:(r4+$18),x0
        or x0,a
        move a1,r1
        move x:(r5+$36),r2
        move x:(r5+$37),x1
        move x:(r6+$5),y0
        move x:(r6+$3),y1
        move x:(r6+$7),x0
        move x0,a
        tst a
        beq pkrf_mod_done
        move #>$80,a
        move a1,x:(r5+$38)
        move r2,a
        cmp #>$1000,a
        ble pkrf_mod_small
        sub #>$800,a
        asr #$3,a,a
        add y0,a
        move a1,y0
        move r2,a
        asr #$4,a,a
        move a1,x:(r5+$38)
pkrf_mod_small:
        move y0,n1
        move x:(r5+$38),y0
        mpyuu x0,y0,a
        asr #$a,a,a
        move a0,a
        add y1,a
        move a1,y1
        move n1,y0
pkrf_mod_done:
        move r1,r7
        move x:(r6+$9),a
        tst a
        bne pkrf_bypass_done
        move x1,x0
        mpy y0,x0,a
        asr #$1,a,a
        asl #$18,a,a
        asr #$f,a,a
        move a1,a
        move r1,b
        sub a,b
        move b1,r7
pkrf_bypass_done:
        move x1,x0
        move y1,y0
        mpy y0,x0,a
        asr #$1,a,a
        asl #$18,a,a
        asr #$f,a,a
        move a1,a
        move r2,x0
        add x0,a
        cmp #>$007fff,a
        ble pkrf_pos_hi
        move #>$007fff,a
pkrf_pos_hi:
        cmp #>$ff8001,a
        bge pkrf_pos_lo
        move #>$ff8001,a
pkrf_pos_lo:
        move a1,r2
        move a1,b
        and #>$00ffff,b
        move b1,x:(r6+$a)
        move a1,b
        asr #$10,b,b
        and #>$00ffff,b
        move b1,x:(r6+$b)
        move r7,a
        move r2,x0
        sub x0,a
        move a1,x0
        move y1,y0
        mpy y0,x0,a
        asr #$1,a,a
        asl #$18,a,a
        asr #$f,a,a
        move a1,a
        add x1,a
        cmp #>$007fff,a
        ble pkrf_vel_hi
        move #>$007fff,a
pkrf_vel_hi:
        cmp #>$ff8001,a
        bge pkrf_vel_lo
        move #>$ff8001,a
pkrf_vel_lo:
        move a1,b
        and #>$00ffff,b
        move b1,x:(r6+$c)
        move a1,b
        asr #$10,b,b
        and #>$00ffff,b
        move b1,x:(r6+$d)
        rts
pkr_label_00016:
        move x:(r6+$5),a
        move a1,x:(r4+$8)
        move x:(r6+$6),a
        move a1,x:(r4+$9)
        move x:(r6+$3),a
        move a1,x:(r4+$a)
        move x:(r6+$4),a
        move a1,x:(r4+$b)
        move x:(r6+$a),a
        move a1,x:(r4+$c)
        move x:(r6+$b),a
        move a1,x:(r4+$d)
        move x:(r6+$c),a
        move a1,x:(r4+$e)
        move x:(r6+$d),a
        move a1,x:(r4+$f)
        move x:(r6+$7),a
        move a1,x:(r4+$10)
        move x:(r6+$8),a
        move a1,x:(r4+$11)
        move #>$000000,a
        move #>$000000,a0
        move a1,x1
        move a0,y1
        move x:(r4+$11),a
        asl #$8,a,a
        move a1,a
        asr #$8,a,a
        move x:(r4+$10),b
        lsl #$8,b
        move b1,a0
        move x1,b
        move y1,b0
        cmp b,a
        beq pkr_label_00017
        move #>$000080,a
        move a1,x:(r4+$12)
        move #>$000000,a
        move a1,x:(r4+$13)
        move #>$000000,a
        move #>$100000,a0
        move a1,x1
        move a0,y1
        move x:(r4+$d),a
        asl #$8,a,a
        move a1,a
        asr #$8,a,a
        move x:(r4+$c),b
        lsl #$8,b
        move b1,a0
        move x1,b
        move y1,b0
        cmp b,a
        ble pkr_label_00018
        move #>$000000,a
        move #>$080000,a0
        move a1,x1
        move a0,y1
        move x:(r4+$d),a
        move x:(r4+$c),b
        lsl #$8,b
        move b1,a0
        move x1,b
        move y1,b0
        sub b,a
        move a1,b
        and #>$00ffff,b
        move b1,x:(r4+$15)
        move a0,b
        lsr #$8,b
        and #>$00ffff,b
        move b1,x:(r4+$14)
        move x:(r4+$15),a
        asl #$8,a,a
        move a1,a
        asr #$8,a,a
        move x:(r4+$14),b
        lsl #$8,b
        move b1,a0
        asr #>$3,a,a
        move a1,b
        and #>$00ffff,b
        move b1,x:(r4+$15)
        move a0,b
        lsr #$8,b
        and #>$00ffff,b
        move b1,x:(r4+$14)
        move x:(r4+$15),a
        move x:(r4+$14),b
        lsl #$8,b
        move b1,a0
        move a1,x1
        move a0,y1
        move x:(r4+$9),a
        move x:(r4+$8),b
        lsl #$8,b
        move b1,a0
        move x1,b
        move y1,b0
        add b,a
        move a1,b
        and #>$00ffff,b
        move b1,x:(r4+$9)
        move a0,b
        lsr #$8,b
        and #>$00ffff,b
        move b1,x:(r4+$8)
        move x:(r4+$d),a
        asl #$8,a,a
        move a1,a
        asr #$8,a,a
        move x:(r4+$c),b
        lsl #$8,b
        move b1,a0
        asr #>$4,a,a
        move a1,b
        and #>$00ffff,b
        move b1,x:(r4+$13)
        move a0,b
        lsr #$8,b
        and #>$00ffff,b
        move b1,x:(r4+$12)
pkr_label_00018:
        move x:(r4+$12),a
        move a1,x:(r5-$40)
        move x:(r4+$13),a
        move a1,x:(r5-$3f)
        move x:(r4+$10),a
        move a1,x:(r5-$3e)
        move x:(r4+$11),a
        move a1,x:(r5-$3d)
        jsrl pk_u32_mul_low
        move x:(r5-$38),a
        move a1,x:(r4+$14)
        move x:(r5-$37),a
        move a1,x:(r4+$15)
        move x:(r4+$15),a
        asl #$8,a,a
        move a1,a
        asr #$8,a,a
        move x:(r4+$14),b
        lsl #$8,b
        move b1,a0
        asr #>$9,a,a
        move a1,b
        and #>$00ffff,b
        move b1,x:(r4+$15)
        move a0,b
        lsr #$8,b
        and #>$00ffff,b
        move b1,x:(r4+$14)
        move x:(r4+$15),a
        move x:(r4+$14),b
        lsl #$8,b
        move b1,a0
        move a1,x1
        move a0,y1
        move x:(r4+$b),a
        move x:(r4+$a),b
        lsl #$8,b
        move b1,a0
        move x1,b
        move y1,b0
        add b,a
        move a1,b
        and #>$00ffff,b
        move b1,x:(r4+$b)
        move a0,b
        lsr #$8,b
        and #>$00ffff,b
        move b1,x:(r4+$a)
pkr_label_00017:
        move x:(r4+$18),a
        move a1,x:(r4+$16)
        move x:(r4+$19),a
        move a1,x:(r4+$17)
        move #>$000000,a
        move #>$000000,a0
        move a1,x1
        move a0,y1
        clr a
        move x:(r6+$9),b
        lsl #$8,b
        move b1,a0
        move x1,b
        move y1,b0
        cmp b,a
        bne pkr_label_00019
        move x:(r4+$e),a
        move a1,x:(r5-$40)
        move x:(r4+$f),a
        move a1,x:(r5-$3f)
        move x:(r4+$8),a
        move a1,x:(r5-$3e)
        move x:(r4+$9),a
        move a1,x:(r5-$3d)
        jsrl pk_u32_mul_low
        move x:(r5-$38),a
        move a1,x:(r4+$14)
        move x:(r5-$37),a
        move a1,x:(r4+$15)
        move x:(r4+$15),a
        asl #$8,a,a
        move a1,a
        asr #$8,a,a
        move x:(r4+$14),b
        lsl #$8,b
        move b1,a0
        asr #>$f,a,a
        move a1,b
        and #>$00ffff,b
        move b1,x:(r4+$15)
        move a0,b
        lsr #$8,b
        and #>$00ffff,b
        move b1,x:(r4+$14)
        move x:(r4+$15),a
        move x:(r4+$14),b
        lsl #$8,b
        move b1,a0
        move a1,x1
        move a0,y1
        move x:(r4+$17),a
        move x:(r4+$16),b
        lsl #$8,b
        move b1,a0
        move x1,b
        move y1,b0
        sub b,a
        move a1,b
        and #>$00ffff,b
        move b1,x:(r4+$17)
        move a0,b
        lsr #$8,b
        and #>$00ffff,b
        move b1,x:(r4+$16)
pkr_label_00019:
        move x:(r4+$e),a
        move a1,x:(r5-$40)
        move x:(r4+$f),a
        move a1,x:(r5-$3f)
        move x:(r4+$a),a
        move a1,x:(r5-$3e)
        move x:(r4+$b),a
        move a1,x:(r5-$3d)
        jsrl pk_u32_mul_low
        move x:(r5-$38),a
        move a1,x:(r4+$14)
        move x:(r5-$37),a
        move a1,x:(r4+$15)
        move x:(r4+$15),a
        asl #$8,a,a
        move a1,a
        asr #$8,a,a
        move x:(r4+$14),b
        lsl #$8,b
        move b1,a0
        asr #>$f,a,a
        move a1,b
        and #>$00ffff,b
        move b1,x:(r4+$15)
        move a0,b
        lsr #$8,b
        and #>$00ffff,b
        move b1,x:(r4+$14)
        move x:(r4+$15),a
        move x:(r4+$14),b
        lsl #$8,b
        move b1,a0
        move a1,x1
        move a0,y1
        move x:(r4+$d),a
        move x:(r4+$c),b
        lsl #$8,b
        move b1,a0
        move x1,b
        move y1,b0
        add b,a
        move a1,b
        and #>$00ffff,b
        move b1,x:(r4+$d)
        move a0,b
        lsr #$8,b
        and #>$00ffff,b
        move b1,x:(r4+$c)
        move #>$ffffff,a
        move #>$800100,a0
        move a1,x1
        move a0,y1
        move x:(r4+$d),a
        asl #$8,a,a
        move a1,a
        asr #$8,a,a
        move x:(r4+$c),b
        lsl #$8,b
        move b1,a0
        move x1,b
        move y1,b0
        cmp b,a
        bge pkr_label_00020
        move #>$008001,a
        move a1,x:(r4+$c)
        move #>$00ffff,a
        move a1,x:(r4+$d)
pkr_label_00020:
        move #>$000000,a
        move #>$7fff00,a0
        move a1,x1
        move a0,y1
        move x:(r4+$d),a
        asl #$8,a,a
        move a1,a
        asr #$8,a,a
        move x:(r4+$c),b
        lsl #$8,b
        move b1,a0
        move x1,b
        move y1,b0
        cmp b,a
        ble pkr_label_00021
        move #>$007fff,a
        move a1,x:(r4+$c)
        move #>$000000,a
        move a1,x:(r4+$d)
pkr_label_00021:
        move x:(r4+$c),a
        move a1,x:(r6+$a)
        move x:(r4+$d),a
        move a1,x:(r6+$b)
        move x:(r4+$d),a
        move x:(r4+$c),b
        lsl #$8,b
        move b1,a0
        move a1,x1
        move a0,y1
        move x:(r4+$17),a
        move x:(r4+$16),b
        lsl #$8,b
        move b1,a0
        move x1,b
        move y1,b0
        sub b,a
        move a1,b
        and #>$00ffff,b
        move b1,x:(r4+$17)
        move a0,b
        lsr #$8,b
        and #>$00ffff,b
        move b1,x:(r4+$16)
        move x:(r4+$a),a
        move a1,x:(r5-$40)
        move x:(r4+$b),a
        move a1,x:(r5-$3f)
        move x:(r4+$16),a
        move a1,x:(r5-$3e)
        move x:(r4+$17),a
        move a1,x:(r5-$3d)
        jsrl pk_u32_mul_low
        move x:(r5-$38),a
        move a1,x:(r4+$14)
        move x:(r5-$37),a
        move a1,x:(r4+$15)
        move x:(r4+$15),a
        asl #$8,a,a
        move a1,a
        asr #$8,a,a
        move x:(r4+$14),b
        lsl #$8,b
        move b1,a0
        asr #>$f,a,a
        move a1,b
        and #>$00ffff,b
        move b1,x:(r4+$15)
        move a0,b
        lsr #$8,b
        and #>$00ffff,b
        move b1,x:(r4+$14)
        move x:(r4+$15),a
        move x:(r4+$14),b
        lsl #$8,b
        move b1,a0
        move a1,x1
        move a0,y1
        move x:(r4+$f),a
        move x:(r4+$e),b
        lsl #$8,b
        move b1,a0
        move x1,b
        move y1,b0
        add b,a
        move a1,b
        and #>$00ffff,b
        move b1,x:(r4+$f)
        move a0,b
        lsr #$8,b
        and #>$00ffff,b
        move b1,x:(r4+$e)
        move #>$ffffff,a
        move #>$800100,a0
        move a1,x1
        move a0,y1
        move x:(r4+$f),a
        asl #$8,a,a
        move a1,a
        asr #$8,a,a
        move x:(r4+$e),b
        lsl #$8,b
        move b1,a0
        move x1,b
        move y1,b0
        cmp b,a
        bge pkr_label_00022
        move #>$008001,a
        move a1,x:(r4+$e)
        move #>$00ffff,a
        move a1,x:(r4+$f)
pkr_label_00022:
        move #>$000000,a
        move #>$7fff00,a0
        move a1,x1
        move a0,y1
        move x:(r4+$f),a
        asl #$8,a,a
        move a1,a
        asr #$8,a,a
        move x:(r4+$e),b
        lsl #$8,b
        move b1,a0
        move x1,b
        move y1,b0
        cmp b,a
        ble pkr_label_00023
        move #>$007fff,a
        move a1,x:(r4+$e)
        move #>$000000,a
        move a1,x:(r4+$f)
pkr_label_00023:
        move x:(r4+$e),a
        move a1,x:(r6+$c)
        move x:(r4+$f),a
        move a1,x:(r6+$d)
        rts
; ===== END resident_cores.asm =====

; ===== BEGIN resident_tail.asm =====

pk_resonant_noise:
        move    x:(r6+$c),a
        tst     a
        beq     pkr_noise_refresh
        sub     #>$1,a
        and     #>$00ffff,a
        move    a1,x:(r6+$c)
        move    x:(r6+$e),a
        rts
pkr_noise_refresh:
        move    x:(r6+$d),a
        move    a1,x:(r6+$c)
        move    x:(r5+$32),a
        move    a1,x:(r5-$40)
        move    x:(r5+$33),a
        move    a1,x:(r5-$3f)
        move    x:(r5+$34),a
        move    a1,x:(r5-$3e)
        move    x:(r5+$35),a
        move    a1,x:(r5-$3d)
        jsrl     pk_rng_step
        move    x:(r5-$40),a
        move    a1,x:(r5+$32)
        move    x:(r5-$3f),a
        move    a1,x:(r5+$33)
        move    x:(r5-$3e),a
        move    a1,x:(r5+$34)
        move    x:(r5-$3d),a
        move    a1,x:(r5+$35)
        move    x:(r5-$30),a
        and     #>$00ffff,a
        move    a1,x:(r6+$e)
        rts
; PĒRKONS v1.2.1 Noise Hat common-envelope renderer.
;
; Compact envelope state at r6 (11 words), identical to simple_drum_envelope:
;   +0 state, +1 shape, +2 flag4, +3 flag6, +4 trigger/gate
;   +5/+6 value u32 lo/hi, +7/+8 hold u32 lo/hi, +9 attack, +a decay
;
; Output A1 = unsigned u16 amplitude.
;
; Candidate packed-Y layout (1025 u16 points per curve; index 1024 is needed
; as the interpolation neighbour when the clamped accumulator reaches 1023.x):
;   shape 1 / envelope1: Y:$09a5
;   shape 2 / envelope2: Y:$0c51
; Each table uses the existing 3-u16-in-2-DSP-word direct packing.  These are
; candidate addresses, not final all-family shipping placement.

pk_noise_hat_envelope:
        move    x:(r6+$0),a
        tst     a
        beq     pknhe_idle
        cmp     #>$1,a
        beq     pknhe_attack
        cmp     #>$3,a
        beq     pknhe_hold
        cmp     #>$4,a
        beq     pknhe_release
        bra     pknhe_output

pknhe_idle:
        move    x:(r6+$4),a
        move    x:(r6+$2),x0
        or      x0,a
        tst     a
        beq     pknhe_output
        move    #>$1,a
        move    a1,x:(r6+$0)
        bra     pknhe_output

pknhe_attack:
        move    x:(r6+$6),a
        asl     #$10,a,a
        move    x:(r6+$5),x0
        add     x0,a
        move    x:(r6+$9),x0
        add     x0,a
        cmp     #>$0ffffe,a
        ble     pknhe_commit
        move    a1,x1
        move    x:(r6+$2),b
        move    x:(r6+$3),x0
        or      x0,b
        tst     b
        beq     pknhe_choose_hold
        move    #>$4,b
        bra     pknhe_choose_done
pknhe_choose_hold:
        move    #>$3,b
pknhe_choose_done:
        move    b1,x:(r6+$0)
        move    x1,a
        cmp     #>$100000,a
        blt     pknhe_commit
        move    #>$0fffff,a
        bra     pknhe_commit

pknhe_hold:
        move    x:(r6+$4),a
        tst     a
        bne     pknhe_output
        move    x:(r6+$2),a
        tst     a
        bne     pknhe_begin_release
        move    x:(r6+$7),a
        and     #>$0000ff,a
        tst     a
        bne     pknhe_output
pknhe_begin_release:
        move    #>$4,a
        move    a1,x:(r6+$0)
        bra     pknhe_output

pknhe_release:
        move    x:(r6+$4),a
        tst     a
        bne     pknhe_restart
        move    x:(r6+$6),a
        asl     #$10,a,a
        move    x:(r6+$5),x0
        add     x0,a
        move    x:(r6+$a),x0
        sub     x0,a
        tst     a
        bgt     pknhe_commit
        clr     a
        move    a1,x:(r6+$5)
        move    a1,x:(r6+$6)
        move    x:(r6+$2),a
        tst     a
        beq     pknhe_stop
pknhe_restart:
        move    #>$1,a
        move    a1,x:(r6+$0)
        bra     pknhe_output
pknhe_stop:
        clr     a
        move    a1,x:(r6+$0)
        bra     pknhe_output

pknhe_commit:
        move    a1,b
        and     #>$00ffff,b
        move    b1,x:(r6+$5)
        lsr     #$10,a
        and     #>$00ffff,a
        move    a1,x:(r6+$6)

pknhe_output:
        ; Reconstruct bounded raw u32 value in A for the analytic path.
        move    x:(r6+$6),a
        asl     #$10,a,a
        move    x:(r6+$5),x0
        add     x0,a

        move    x:(r6+$1),b
        cmp     #>$1,b
        beq     pknhe_shape1
        cmp     #>$2,b
        beq     pknhe_shape2

        ; Any other shape is the firmware's analytic linear path.
        lsr     #$4,a
        and     #>$00ffff,a
        rts

pknhe_shape1:
        clr     b
        move    b1,x:(r5+$19)           ; curve id 0
        bra     pknhe_shaped
pknhe_shape2:
        move    #>$1,b
        move    b1,x:(r5+$19)           ; curve id 1

pknhe_shaped:
        ; raw is clamped to $0fffff, hence index 0..1023 and next 1..1024.
        move    x:(r6+$5),a
        move    a1,b
        and     #>$00fc00,b
        lsr     #$a,b
        move    b1,x0
        move    x:(r6+$6),a
        and     #>$00000f,a
        asl     #$6,a,a
        add     x0,a
        and     #>$0003ff,a
        move    a1,x:(r5+$12)

        move    x:(r6+$5),a
        and     #>$0003ff,a
        move    a1,x:(r5+$13)

        move    x:(r5+$12),x0
        jsrl     pknhe_read_u16
        move    a1,x:(r5+$14)

        move    x:(r5+$12),a
        add     #>$1,a
        move    a1,x0
        jsrl     pknhe_read_u16
        move    a1,x:(r5+$15)

        ; unsigned endpoints produce a signed17 delta; exact arithmetic >>10.
        move    x:(r5+$15),a
        move    x:(r5+$14),x0
        sub     x0,a
        move    a1,x0
        move    x:(r5+$13),y0
        mpy     y0,x0,a
        asr     #$b,a,a                 ; fractional MPY alignment + >>10
        move    a0,a
        move    x:(r5+$14),x0
        add     x0,a
        and     #>$00ffff,a
        rts

; input x0 = table index 0..1024
; input X:r5+$59 = curve id 0/1
; output A1 = unsigned u16 from direct packed Y
pknhe_read_u16:
        move    x0,x:(r5+$18)
        move    #>$00aaab,y0
        mpyuu   x0,y0,a
        asr     #$1,a,a
        asr     #$10,a,a
        move    a0,x1
        move    x1,b
        and     #>$00ffff,b
        lsr     b
        move    b1,x1                   ; q=floor(index/3)

        move    x1,b
        asl     b
        add     x1,b
        move    b1,y0
        move    x:(r5+$18),a
        sub     y0,a
        move    a1,y1                   ; remainder 0..2

        move    x1,b
        asl     b
        move    b1,n1
        move    x:(r5+$19),a
        tst     a
        beq     pknhe_env1_base
        move    #>$002280,r1
        bra     pknhe_base_ready
pknhe_env1_base:
        move    #>$002000,r1
pknhe_base_ready:
        lua     (r1+n1),r2

        move    y1,a
        tst     a
        beq     pknhe_read_r0
        cmp     #>$1,a
        beq     pknhe_read_r1
pknhe_read_r2:
        move    y:(r2+$1),a
        lsr     #$8,a
        and     #>$00ffff,a
        rts
pknhe_read_r1:
        move    y:(r2),a
        lsr     #$10,a
        and     #>$0000ff,a
        move    a1,x1
        move    y:(r2+$1),b
        and     #>$0000ff,b
        asl     #$8,b,b
        add     x1,b
        and     #>$00ffff,b
        move    b1,a
        rts
pknhe_read_r0:
        move    y:(r2),a
        and     #>$00ffff,a
        rts
; PERKY Noise/Tone DSP56300 32-bit arithmetic/state kernel / standalone probe.
; Not in the audio hook yet. Firmware u32 values are two 16-bit limbs.
; Normal 24-bit DSP mode only: do not use SA; Octabam's emulator does not
; implement SA semantics, so explicit limbs keep the off-hardware oracle valid.
;
; bd909_host-compatible probe ABI:
;   r5 = X state base, r6 = X parameter block, x:(r6+$0) = op
; State: +0 a.lo, +1 a.hi, +2 b.lo, +3 b.hi, +4 shift,
;        +8 result.low32.lo, +9 result.low32.hi,
;       +10 result.high32.lo,+11 result.high32.hi,
;       +12 primitive result word,
;       +40 noise countdown, +41 noise reload, +42 held noise sample.
; Ops: 1 add32, 2 sub32, 3 signed ASR32, 4 low32 multiply,
;      5 full64 multiply, 6 PERKONS two-word RNG step,
;      7 Noise/Tone sample-and-hold noise step.
;
; RNG op 6 uses input a=oldLow, b=oldHigh. It mutates +0..+3 to
; newLow/newHigh and mirrors them to +8..+11 for the generic probe harness.
; Scratch +20..+36 is private to the RNG probe path.
;
; Noise op 7 uses the same RNG input/state plus +40/+41/+42. It writes the
; 16-bit result bit-pattern to +12. When countdown is non-zero no RNG step is
; performed; when it reaches zero the reload is copied to countdown and the
; held sample becomes low16(nextRandom()).

; Exact modulo-2^32 add. Low sum <= 0x1fffe, so A1 bit16 is carry.
pk_u32_add:
        move    x:(r5-$40),a
        move    x:(r5-$3e),x0
        add     x0,a
        move    #>$0,y0
        btst    #16,a1
        bcc     pk_add_no_carry
        move    #>$1,y0
pk_add_no_carry:
        and     #>$00ffff,a
        move    a1,x:(r5-$38)
        move    x:(r5-$3f),b
        move    x:(r5-$3d),x0
        add     x0,b
        add     y0,b
        and     #>$00ffff,b
        move    b1,x:(r5-$37)
        rts

; Exact modulo-2^32 subtract. For 16-bit inputs N on low diff means borrow.
pk_u32_sub:
        move    x:(r5-$40),a
        move    x:(r5-$3e),x0
        sub     x0,a
        move    #>$0,y0
        bpl     pk_sub_no_borrow
        move    #>$1,y0
pk_sub_no_borrow:
        and     #>$00ffff,a
        move    a1,x:(r5-$38)
        move    x:(r5-$3f),b
        move    x:(r5-$3d),x0
        sub     x0,b
        sub     y0,b
        and     #>$00ffff,b
        move    b1,x:(r5-$37)
        rts

; Signed 32-bit arithmetic right shift by 0..31. y0 is a sign-extended high
; limb. Each iteration shifts low logically, high arithmetically, then uses
; the high shift's carry to inject old high bit0 into low bit15.
pk_u32_asr:
        move    x:(r5-$3f),a
        btst    #15,a1
        bcc     pk_u32_shift_sign_ready
        sub     #>$010000,a
pk_u32_shift_sign_ready:
        move    x:(r5-$40),b
        lsl     #$8,b
        move    b1,a0
        move    x:(r5-$3c),x0
        asr     x0,a,a
        move    a1,b
        and     #>$00ffff,b
        move    b1,x:(r5-$37)
        move    a0,b
        lsr     #$8,b
        and     #>$00ffff,b
        move    b1,x:(r5-$38)
        rts

; Low 32 bits of unsigned 32x32 multiply using three 16x16 products:
; lo=low16(al*bl), hi=low16(high16(al*bl)+al*bh+ah*bl).
pk_u32_mul_low:
        move    x:(r5-$40),x0
        move    x:(r5-$3e),y0
        mpyuu   x0,y0,a
        asr     #$1,a,a                 ; remove fractional multiply alignment
        move    a0,x1
        move    x1,b
        and     #>$00ffff,b
        move    b1,x:(r5-$38)
        asr     #$10,a,a
        move    a0,x1
        move    x1,b
        and     #>$00ffff,b
        move    b1,y1

        move    x:(r5-$40),x0
        move    x:(r5-$3d),y0
        mpyuu   x0,y0,a
        asr     #$1,a,a                 ; remove fractional multiply alignment
        move    a0,a
        and     #>$00ffff,a
        move    a1,x1
        move    y1,b
        add     x1,b

        move    x:(r5-$3f),x0
        move    x:(r5-$3e),y0
        mpyuu   x0,y0,a
        asr     #$1,a,a                 ; remove fractional multiply alignment
        move    a0,a
        and     #>$00ffff,a
        move    a1,x1
        add     x1,b
        and     #>$00ffff,b
        move    b1,x:(r5-$37)
        rts

; Helper: unsigned 16x16 -> x1=low16, y1=high16. Remove MPYUU
; fractional alignment first; A0 then holds product bits 0..23, and
; a full-accumulator ASR #16 exposes bits 16..31 in A0.
pk_mul16:
        mpyuu   x0,y0,a
        asr     #$1,a,a                 ; remove fractional multiply alignment
        move    a0,x1
        move    x1,b
        and     #>$00ffff,b
        move    b1,x1
        asr     #$10,a,a
        move    a0,y1
        move    y1,b
        and     #>$00ffff,b
        move    b1,y1
        rts

; Exact unsigned 32x32 -> 64 bits. Four 16x16 partial products are staged at
; X:(r5+$10)..+$16, then two base-2^16 carry folds produce r0..r3.
; Output low32 is +8/+9; high32 is +10/+11.
pk_u32_mul_full:
        ; p0 = al*bl: r0 plus p0.high
        move    x:(r5-$40),x0
        move    x:(r5-$3e),y0
        jsrl     pk_mul16
        move    x1,x:(r5-$38)
        move    y1,x:(r5-$30)

        ; p1 = al*bh
        move    x:(r5-$40),x0
        move    x:(r5-$3d),y0
        jsrl     pk_mul16
        move    x1,x:(r5-$2f)
        move    y1,x:(r5-$2e)

        ; p2 = ah*bl
        move    x:(r5-$3f),x0
        move    x:(r5-$3e),y0
        jsrl     pk_mul16
        move    x1,x:(r5-$2d)
        move    y1,x:(r5-$2c)

        ; p3 = ah*bh
        move    x:(r5-$3f),x0
        move    x:(r5-$3d),y0
        jsrl     pk_mul16
        move    x1,x:(r5-$2b)
        move    y1,x:(r5-$2a)

        ; t1 = p0.high + p1.low + p2.low; r1=low16(t1), carry1=t1>>16.
        move    x:(r5-$30),a
        move    x:(r5-$2f),x0
        add     x0,a
        move    x:(r5-$2d),x0
        add     x0,a
        move    a1,b
        and     #>$00ffff,b
        move    b1,x:(r5-$37)
        lsr     #$10,a
        move    a1,x1                   ; carry1 (0..2)

        ; t2 = p1.high + p2.high + p3.low + carry1.
        move    x:(r5-$2e),a
        move    x:(r5-$2c),x0
        add     x0,a
        move    x:(r5-$2b),x0
        add     x0,a
        add     x1,a
        move    a1,b
        and     #>$00ffff,b
        move    b1,x:(r5-$30)           ; r2
        lsr     #$10,a
        move    a1,x1                   ; carry2 (0..2)

        ; r3 = low16(p3.high + carry2)
        move    x:(r5-$2a),b
        add     x1,b
        and     #>$00ffff,b
        move    b1,x:(r5-$2f)
        rts

; Exact PĒRKONS two-word RNG step used by the Noise/Tone renderer:
;   accumulator = low32(oldLow*A) + low32(oldHigh*B)
;   product     = full64(oldLow*B)
;   newLow      = low32(product) + 1
;   newHigh     = accumulator + high32(product) + carry(newLow)
;   return      = newHigh & 0x7fffffff
; Constants: A=$5851f42d, B=$4c957f2d.
;
; Input oldLow is +0/+1 and oldHigh is +2/+3. The routine stores newLow and
; newHigh back to +0..+3 and mirrors them to +8..+11. The caller can obtain
; the firmware return value by clearing bit 15 of the high limb at +11.
pk_rng_step:
        ; Preserve original RNG words in private scratch.
        move    x:(r5-$40),a
        move    a1,x:(r5-$20)
        move    x:(r5-$3f),a
        move    a1,x:(r5-$1f)
        move    x:(r5-$3e),a
        move    a1,x:(r5-$1e)
        move    x:(r5-$3d),a
        move    a1,x:(r5-$1d)

        ; accumulator = low32(oldLow * A)
        move    x:(r5-$20),a
        move    a1,x:(r5-$40)
        move    x:(r5-$1f),a
        move    a1,x:(r5-$3f)
        move    #>$00f42d,a
        move    a1,x:(r5-$3e)
        move    #>$005851,a
        move    a1,x:(r5-$3d)
        jsrl     pk_u32_mul_low
        move    x:(r5-$38),a
        move    a1,x:(r5-$1c)
        move    x:(r5-$37),a
        move    a1,x:(r5-$1b)

        ; accumulator += low32(oldHigh * B)
        move    x:(r5-$1e),a
        move    a1,x:(r5-$40)
        move    x:(r5-$1d),a
        move    a1,x:(r5-$3f)
        move    #>$007f2d,a
        move    a1,x:(r5-$3e)
        move    #>$004c95,a
        move    a1,x:(r5-$3d)
        jsrl     pk_u32_mul_low
        move    x:(r5-$1c),a
        move    a1,x:(r5-$40)
        move    x:(r5-$1b),a
        move    a1,x:(r5-$3f)
        move    x:(r5-$38),a
        move    a1,x:(r5-$3e)
        move    x:(r5-$37),a
        move    a1,x:(r5-$3d)
        jsrl     pk_u32_add
        move    x:(r5-$38),a
        move    a1,x:(r5-$1c)
        move    x:(r5-$37),a
        move    a1,x:(r5-$1b)

        ; product = full64(oldLow * B)
        move    x:(r5-$20),a
        move    a1,x:(r5-$40)
        move    x:(r5-$1f),a
        move    a1,x:(r5-$3f)
        move    #>$007f2d,a
        move    a1,x:(r5-$3e)
        move    #>$004c95,a
        move    a1,x:(r5-$3d)
        jsrl     pk_u32_mul_full
        move    x:(r5-$38),a
        move    a1,x:(r5-$1a)
        move    x:(r5-$37),a
        move    a1,x:(r5-$19)
        move    x:(r5-$30),a
        move    a1,x:(r5-$18)
        move    x:(r5-$2f),a
        move    a1,x:(r5-$17)

        ; newLow = productLow + 1
        move    x:(r5-$1a),a
        move    a1,x:(r5-$40)
        move    x:(r5-$19),a
        move    a1,x:(r5-$3f)
        move    #>$1,a
        move    a1,x:(r5-$3e)
        clr     a
        move    a1,x:(r5-$3d)
        jsrl     pk_u32_add
        move    x:(r5-$38),a
        move    a1,x:(r5-$10)
        move    x:(r5-$37),a
        move    a1,x:(r5-$f)

        ; carry = 1 iff productLow was $ffffffff.
        clr     a
        move    a1,x:(r5-$a)
        move    x:(r5-$1a),a
        cmp     #>$00ffff,a
        bne     pk_rng_no_carry
        move    x:(r5-$19),a
        cmp     #>$00ffff,a
        bne     pk_rng_no_carry
        move    #>$1,a
        move    a1,x:(r5-$a)
pk_rng_no_carry:

        ; newHigh = accumulator + productHigh
        move    x:(r5-$1c),a
        move    a1,x:(r5-$40)
        move    x:(r5-$1b),a
        move    a1,x:(r5-$3f)
        move    x:(r5-$18),a
        move    a1,x:(r5-$3e)
        move    x:(r5-$17),a
        move    a1,x:(r5-$3d)
        jsrl     pk_u32_add
        move    x:(r5-$38),a
        move    a1,x:(r5-$e)
        move    x:(r5-$37),a
        move    a1,x:(r5-$d)

        ; Add carry from newLow wrap.
        move    x:(r5-$e),a
        move    a1,x:(r5-$40)
        move    x:(r5-$d),a
        move    a1,x:(r5-$3f)
        move    x:(r5-$a),a
        move    a1,x:(r5-$3e)
        clr     a
        move    a1,x:(r5-$3d)
        jsrl     pk_u32_add
        move    x:(r5-$38),a
        move    a1,x:(r5-$e)
        move    x:(r5-$37),a
        move    a1,x:(r5-$d)

        ; Publish/mutate RNG state and generic probe outputs.
        move    x:(r5-$10),a
        move    a1,x:(r5-$40)
        move    a1,x:(r5-$38)
        move    x:(r5-$f),a
        move    a1,x:(r5-$3f)
        move    a1,x:(r5-$37)
        move    x:(r5-$e),a
        move    a1,x:(r5-$3e)
        move    a1,x:(r5-$30)
        move    x:(r5-$d),a
        move    a1,x:(r5-$3d)
        move    a1,x:(r5-$2f)
        rts

; Noise/Tone sample-and-hold source primitive. This is the renderer's
; renderNoise() reduced to its exact state transition. +40/+41/+42 are direct
; 16-bit probe words corresponding to firmware count/reload/held-sample u16s.
; +12 receives the returned sample bit-pattern.
pk_noise_step:
        move    x:(r5+$0),a
        tst     a
        beq     pk_noise_refresh

        sub     #>$1,a
        and     #>$00ffff,a
        move    a1,x:(r5+$0)
        move    x:(r5+$2),a
        and     #>$00ffff,a
        move    a1,x:(r5-$2e)
        rts

pk_noise_refresh:
        move    x:(r5+$1),a
        and     #>$00ffff,a
        move    a1,x:(r5+$0)
        jsrl     pk_rng_step

        ; renderNoise casts low16(nextRandom()) to int16. nextRandom() is
        ; newHigh & $7fffffff, so its low16 is exactly newHigh.low at +10.
        move    x:(r5-$30),a
        and     #>$00ffff,a
        move    a1,x:(r5+$2)
        move    a1,x:(r5-$2e)
        rts

; ===== END resident_tail.asm =====

; ===== BEGIN fold_drum_1.asm =====
; Fold Drum 1 candidate renderer: shared exact Simple Drum primitives.
; 40 live words, prepared base at +$34/$35. Private scratch as Simple Drum.
; Not dispatched by PERKY3 until controls/trigger/integration gates qualify it.
pk_fold_voice:
        move r6,a
        move a1,x:(r5+$20)
        do n7,pkfd_samples_done
        move x:(r5+$20),r6
        lua (r6+$a),r6
        jsrl pk_simple_envelope
        move a1,x:(r5+$1d)
        move x:(r5+$20),r6
        lua (r6+$15),r6
        jsrl pk_simple_envelope
        move x:(r5+$20),r6
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
        jsrl pk_simple_frequency
        move a1,b
        and #>$ffff,b
        move b1,x:(r6+$4)
        asr #$10,a,a
        and #>$ffff,a
        move a1,x:(r6+$5)
        lua (r6+$2),r7
        jsrl pk_simple_oscillator
        move a1,x:(r5+$1e)
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
        move a1,x:(r5+$1f)
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
        jsrl pknv_noise
        move x:(r5+$20),r6
        move x:(r5+$21),a
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
        move x:(r5+$1f),x0
        add x0,a
        move a1,x:(r5+$1f)
        bra pkfd_counter_step
pkfd_pulse:
        move x:(r5+$1f),a
        add #>$3fff,a
        move a1,x:(r5+$1f)
pkfd_counter_step:
        move x:(r6+$23),a
        add #>$1,a
        move a1,x:(r6+$23)
pkfd_transient_done:
        move x:(r6+$1),a
        tst a
        bne pkfd_muted
        move x:(r5+$1f),a
        move x:(r5+$1e),x0
        add x0,a
        asr #$1,a,a
        move a1,x0
        move x:(r5+$1d),y0
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
        move x:(r5+$20),r6
        rts


pk_simple_envelope:
        move    x:(r6+$0),a
        tst     a
        beq     pksde_idle
        cmp     #>$1,a
        beq     pksde_attack
        cmp     #>$3,a
        beq     pksde_hold
        cmp     #>$4,a
        beq     pksde_release
        bra     pksde_output

pksde_idle:
        move    x:(r6+$4),a
        move    x:(r6+$2),x0
        or      x0,a
        tst     a
        beq     pksde_output
        move    #>$1,a
        move    a1,x:(r6+$0)
        bra     pksde_output

pksde_attack:
        move    x:(r6+$6),a
        asl     #$10,a,a
        move    x:(r6+$5),x0
        add     x0,a
        move    x:(r6+$9),x0
        add     x0,a
        cmp     #>$0ffffe,a
        ble     pksde_commit
        move    a1,x1
        move    x:(r6+$2),b
        move    x:(r6+$3),x0
        or      x0,b
        tst     b
        beq     pksde_choose_hold
        move    #>$4,b
        bra     pksde_choose_done
pksde_choose_hold:
        move    #>$3,b
pksde_choose_done:
        move    b1,x:(r6+$0)
        move    x1,a
        cmp     #>$100000,a
        blt     pksde_commit
        move    #>$0fffff,a
        bra     pksde_commit

pksde_hold:
        move    x:(r6+$4),a
        tst     a
        bne     pksde_output
        move    x:(r6+$2),a
        tst     a
        bne     pksde_begin_release
        ; Native checks the low byte of hold at +0x10, which is compact hold.lo.
        move    x:(r6+$7),a
        and     #>$0000ff,a
        tst     a
        bne     pksde_output
pksde_begin_release:
        move    #>$4,a
        move    a1,x:(r6+$0)
        bra     pksde_output

pksde_release:
        move    x:(r6+$4),a
        tst     a
        bne     pksde_restart
        move    x:(r6+$6),a
        asl     #$10,a,a
        move    x:(r6+$5),x0
        add     x0,a
        move    x:(r6+$a),x0
        sub     x0,a
        tst     a
        bgt     pksde_commit
        clr     a
        move    a1,x:(r6+$5)
        move    a1,x:(r6+$6)
        move    x:(r6+$2),a
        tst     a
        beq     pksde_stop
pksde_restart:
        move    #>$1,a
        move    a1,x:(r6+$0)
        bra     pksde_output
pksde_stop:
        clr     a
        move    a1,x:(r6+$0)
        bra     pksde_output

pksde_commit:
        move    a1,b
        and     #>$00ffff,b
        move    b1,x:(r6+$5)
        lsr     #$10,a
        and     #>$00ffff,a
        move    a1,x:(r6+$6)

pksde_output:
        ; Reconstruct bounded raw u32 value in A for the analytic linear path.
        move    x:(r6+$6),a
        asl     #$10,a,a
        move    x:(r6+$5),x0
        add     x0,a

        move    x:(r6+$1),b
        cmp     #>$1,b
        beq     pksde_shape1

        ; shape 0: (raw >> 4) & $ffff.
        lsr     #$4,a
        and     #>$00ffff,a
        rts

pksde_shape1:
        ; index = raw >> 10 (0..1023), fraction = raw.low & $3ff.
        ; Use the compact limbs directly so this does not depend on accumulator
        ; subregister placement after reconstructing the u32 value above.
        move    x:(r6+$5),a
        move    a1,b
        and     #>$00fc00,b
        lsr     #$a,b
        move    b1,x0
        move    x:(r6+$6),a
        and     #>$00000f,a
        asl     #$6,a,a
        add     x0,a
        and     #>$0003ff,a
        move    a1,x:(r5+$12)

        move    x:(r6+$5),a
        and     #>$0003ff,a
        move    a1,x:(r5+$13)

        move    x:(r5+$12),x0
        jsrl     pksde_read_u16
        move    a1,x:(r5+$14)

        move    x:(r5+$12),a
        add     #>$1,a
        cmp     #>$400,a
        blt     pksde_next_ready
        move    #>$3ff,a                ; authentic endpoint duplicates 1023
pksde_next_ready:
        move    a1,x0
        jsrl     pksde_read_u16
        move    a1,x:(r5+$15)

        ; unsigned endpoints produce signed17 delta; exact arithmetic >>10.
        move    x:(r5+$15),a
        move    x:(r5+$14),x0
        sub     x0,a
        move    a1,x0
        move    x:(r5+$13),y0
        mpy     y0,x0,a
        asr     #$b,a,a                 ; fractional MPY alignment + >>10
        move    a0,a
        move    x:(r5+$14),x0
        add     x0,a
        and     #>$00ffff,a
        rts

; input x0 = envelope index 0..1023
; output A1 = unsigned u16 at direct-packed Y:$09a5
pksde_read_u16:
        move    x0,x:(r5+$18)
        move    #>$00aaab,y0
        mpyuu   x0,y0,a
        asr     #$1,a,a
        asr     #$10,a,a
        move    a0,x1
        move    x1,b
        and     #>$00ffff,b
        lsr     b
        move    b1,x1                   ; q=floor(index/3)

        move    x1,b
        asl     b
        add     x1,b
        move    b1,y0
        move    x:(r5+$18),a
        sub     y0,a
        move    a1,y1                   ; remainder 0..2

        move    x1,b
        asl     b
        move    b1,n1
        move    #>$000c50,r1
        lua     (r1+n1),r2

        move    y1,a
        tst     a
        beq     pksde_read_r0
        cmp     #>$1,a
        beq     pksde_read_r1
pksde_read_r2:
        move    y:(r2+$1),a
        lsr     #$8,a
        and     #>$00ffff,a
        rts
pksde_read_r1:
        move    y:(r2),a
        lsr     #$10,a
        and     #>$0000ff,a
        move    a1,x1
        move    y:(r2+$1),b
        and     #>$0000ff,b
        asl     #$8,b,b
        add     x1,b
        and     #>$00ffff,b
        move    b1,a
        rts
pksde_read_r0:
        move    y:(r2),a
        and     #>$00ffff,a
        rts


pk_simple_frequency:
        ; z = sign_extend_12(x0 & $fff).
        move    x0,a
        and     #>$000fff,a
        btst    #11,a1
        bcc     pksf_z_ready
        sub     #>$001000,a
pksf_z_ready:
        move    a1,x1                   ; x1 = signed z

        ; integer part = 21*z = (16 + 4 + 1)*z; keep it in scratch y1.
        move    x1,b
        asl     #$4,b,b
        move    b1,y1                   ; 16*z
        move    x1,b
        asl     #$2,b,b                 ; 4*z
        add     y1,b
        add     x1,b
        move    b1,y1                   ; y1 = 21*z

        ; fractional part = trunc0(z * $3619f1 / 2^22).
        move    x1,x0
        move    #>$3619f1,y0
        mpysu   x0,y0,a
        asr     #$17,a,a                ; product<<1 / 2^23 = floor(product/2^22)
        move    a0,a

        ; Signed ASR floors negative non-integral values. No nonzero z in this
        ; 12-bit domain makes z*$3619f1 divisible by 2^22 (constant is odd),
        ; so add one exactly when z < 0 to obtain truncation toward zero.
        move    x1,b
        tst     b
        bpl     pksf_fraction_ready
        add     #>$1,a
pksf_fraction_ready:
        add     y1,a
        rts


pk_simple_oscillator:
        ; Exact modulo-2^32 phase += increment using two 16-bit limbs.
        move    x:(r7+$0),a
        move    x:(r7+$2),x0
        add     x0,a
        move    #>$0,y0
        btst    #16,a1
        bcc     pksdo_add_no_carry
        move    #>$1,y0
pksdo_add_no_carry:
        move    a1,b
        and     #>$00ffff,b
        move    b1,x:(r7+$0)
        move    x:(r7+$1),a
        move    x:(r7+$3),x0
        add     x0,a
        add     y0,a
        and     #>$00ffff,a
        move    a1,x:(r7+$1)

        ; Native condition is signed32(phase) > $00100000, strictly greater.
        move    x:(r7+$1),a
        btst    #15,a1
        bcs     pksdo_phase_ready        ; negative signed phase never wraps
        cmp     #>$0010,a
        bgt     pksdo_phase_wrap
        blt     pksdo_phase_ready
        move    x:(r7+$0),a
        tst     a
        bgt     pksdo_phase_wrap
        bra     pksdo_phase_ready

pksdo_phase_wrap:
        move    x:(r7+$1),a
        sub     #>$0010,a
        and     #>$00ffff,a
        move    a1,x:(r7+$1)

        ; Deferred table switch occurs only on phase wrap.
        move    x:(r7+$4),a
        move    x:(r7+$6),x0
        cmp     x0,a
        bne     pksdo_switch_wave
        move    x:(r7+$5),a
        move    x:(r7+$7),x0
        cmp     x0,a
        beq     pksdo_phase_ready
pksdo_switch_wave:
        move    x:(r7+$6),a
        move    a1,x:(r7+$4)
        move    x:(r7+$7),a
        move    a1,x:(r7+$5)

pksdo_phase_ready:
        ; Resolve authentic current wave identity to packed global base.
        move    x:(r7+$5),a
        cmp     #>$0802,a
        bne     pksdo_unknown_wave
        move    x:(r7+$4),a
        cmp     #>$22a0,a
        beq     pksdo_wave0
        cmp     #>$26a0,a
        beq     pksdo_wave1
        cmp     #>$28a0,a
        beq     pksdo_wave2
        cmp     #>$24a0,a
        beq     pksdo_wave3
        bra     pksdo_unknown_wave
pksdo_wave0:
        clr     a
        move    a1,x:(r5+$19)
        bra     pksdo_have_wave
pksdo_wave1:
        move    #>$000100,a
        move    a1,x:(r5+$19)
        bra     pksdo_have_wave
pksdo_wave2:
        move    #>$000200,a
        move    a1,x:(r5+$19)
        bra     pksdo_have_wave
pksdo_wave3:
        ; Complex Drum V2 also selects the neighboring 0x24a0 table. The
        ; ordinary Simple Drum bank remains three tables; Complex's payload
        ; appends this fourth table at ordinal 3.
        move    #>$000300,a
        move    a1,x:(r5+$19)
        bra     pksdo_have_wave
pksdo_unknown_wave:
        clr     a
        rts

pksdo_have_wave:
        ; local index = (phase >> 12) & $ff.
        move    x:(r7+$0),a
        move    a1,b
        and     #>$00f000,b
        lsr     #$c,b
        move    b1,x0
        move    x:(r7+$1),a
        and     #>$00000f,a
        asl     #$4,a,a
        add     x0,a
        and     #>$0000ff,a
        move    a1,x:(r5+$12)

        ; fraction = phase & $fff.
        move    x:(r7+$0),a
        and     #>$000fff,a
        move    a1,x:(r5+$13)

        ; first = wave[local], second = wave[(local+1)&255].
        move    x:(r5+$12),a
        move    x:(r5+$19),x0
        add     x0,a
        move    a1,x0
        jsrl     pksdo_read_s16
        move    a1,x:(r5+$14)

        move    x:(r5+$12),a
        add     #>$1,a
        and     #>$0000ff,a
        move    x:(r5+$19),x0
        add     x0,a
        move    a1,x0
        jsrl     pksdo_read_s16
        move    a1,x:(r5+$15)

        ; signed17 delta * unsigned12 fraction, arithmetic >>12.
        move    x:(r5+$15),a
        move    x:(r5+$14),x0
        sub     x0,a
        move    a1,x0
        move    x:(r5+$13),y0
        mpy     y0,x0,a
        asr     #$d,a,a                 ; fractional MPY alignment + >>12
        move    a0,a
        move    x:(r5+$14),x0
        add     x0,a
        and     #>$00ffff,a
        ; Sign-extend returned signed16 to signed24.
        btst    #15,a1
        bcc     pksdo_sample_ready
        sub     #>$010000,a
pksdo_sample_ready:
        rts

; input x0 = global packed-u16 index 0..767
; output A1 = sign-extended signed16 sample
pksdo_read_s16:
        move    x0,x:(r5+$18)
        ; q=floor(index/3) using exact reciprocal over this range.
        move    #>$00aaab,y0
        mpyuu   x0,y0,a
        asr     #$1,a,a
        asr     #$10,a,a
        move    a0,x1
        move    x1,b
        and     #>$00ffff,b
        lsr     b
        move    b1,x1

        ; remainder = index - 3*q.
        move    x1,b
        asl     b
        add     x1,b
        move    b1,y0
        move    x:(r5+$18),a
        sub     y0,a
        move    a1,y1

        ; pair pointer = Y:$07a5 + 2*q.
        move    x1,b
        asl     b
        move    b1,n1
        move    #>$0007a5,r1
        lua     (r1+n1),r2

        move    y1,a
        tst     a
        beq     pksdo_read_r0
        cmp     #>$1,a
        beq     pksdo_read_r1
pksdo_read_r2:
        move    y:(r2+$1),a
        lsr     #$8,a
        and     #>$00ffff,a
        bra     pksdo_read_sign
pksdo_read_r1:
        move    y:(r2),a
        lsr     #$10,a
        and     #>$0000ff,a
        move    a1,x1
        move    y:(r2+$1),b
        and     #>$0000ff,b
        asl     #$8,b,b
        add     x1,b
        and     #>$00ffff,b
        move    b1,a
        bra     pksdo_read_sign
pksdo_read_r0:
        move    y:(r2),a
        and     #>$00ffff,a
pksdo_read_sign:
        btst    #15,a1
        bcc     pksdo_read_done
        sub     #>$010000,a
pksdo_read_done:
        rts

; Exact second-difference block decoder. One persistent 17-word cache at r4.
; x0=sample index, r1=packed table base, y0=bits/block, y1=first delta width.
; n3=second difference width (signed). Cursor reads two packed Y words; the
; payload builder must reserve a zero padding word past the final stream.
pk_simple_delta_at:
        move    x0,a
        and     #>$f,a
        move    a1,x:(r5+$d)
        move    x0,a
        lsr     #$4,a
        move    a1,x0
        move    x:(r4),b
        cmp     x0,b
        beq     pksdd_hit
        move    x0,x:(r4)
        move    y1,x:(r5+$e)
        move    n3,x:(r5+$f)
        mpyuu   x0,y0,a
        asr     #$1,a,a
        move    a0,x:(r5+$c)
        move    a0,x0
        move    #>$2aaaab,y0
        mpyuu   x0,y0,a
        asr     #$1b,a,a
        move    a0,x0
        move    x0,n1
        lua     (r1+n1),r2
        move    x0,b
        asl     #$4,b,b
        move    b1,y0
        move    x0,b
        asl     #$3,b,b
        add     y0,b
        move    x:(r5+$c),a
        sub     b,a
        move    a1,x1
        lua     (r4+$1),r3
        move    #>$10,n2
        jsrl     pksdd_unsigned
        move    a1,x:(r5+$10)
        move    a1,x:(r3)+
        move    x:(r5+$e),n2
        jsrl     pksdd_unsigned
        move    a1,x:(r5+$11)
        move    x:(r5+$10),x0
        add     x0,a
        move    a1,x:(r5+$10)
        move    a1,x:(r3)+
        do      #$e,pksdd_decoded
        move    x:(r5+$f),n2
        clr     a
        move    y:(r2),a0
        move    y:(r2+$1),a1
        move    n2,b
        asl     #$c,b,b
        add     x1,b
        move    b1,y0
        extract y0,a,b
        move    b0,a
        move    x:(r5+$11),x0
        add     x0,a
        move    a1,x:(r5+$11)
        move    x:(r5+$10),x0
        add     x0,a
        move    a1,x:(r5+$10)
        move    a1,x:(r3)+
        jsrl     pksdd_advance
pksdd_decoded:
        nop
pksdd_hit:
        move    x:(r5+$d),n1
        lua     (r4+$1),r1
        move    x:(r1+n1),a
        rts
pksdd_unsigned:
        clr     a
        move    y:(r2),a0
        move    y:(r2+$1),a1
        move    n2,b
        asl     #$c,b,b
        add     x1,b
        move    b1,y0
        extractu y0,a,b
        move    b0,y1
        jsrl     pksdd_advance
        move    y1,a
        rts
pksdd_advance:
        move    x1,a
        move    n2,x0
        add     x0,a
        cmp     #>$18,a
        blt     pksdd_cursor_ok
        sub     #>$18,a
        move    #>$1,n2
        lua     (r2+n2),r2
pksdd_cursor_ok:
        move    a1,x1
        rts
; Control-rate base frequency, prepared pitch is restricted to 0..4095.
; Uses a separate global pitch cache after the shared scratch block.
pk_simple_base:
        move    r6,a
        move    a1,x:(r5+$20)
        move    x:(r6+$20),a
        move    a1,x:(r5+$8)
        lsr     #$9,a
        move    a1,x:(r5+$9)
        move    x:(r6+$20),a
        and     #>$1ff,a
        move    a1,x0
        move    #>$003964,r4
        move    #>$000efb,r1
        move    #>$32,y0
        move    #>$6,y1
        move    #>$2,n3
        jsrl     pk_simple_delta_at
        move    #>$7,b
        move    x:(r5+$9),x0
        sub     x0,b
        move    b1,x0
        asr     x0,a,a
        move    a1,x0
        move    #>$00bb80,y0
        mpyuu   x0,y0,a
        asr     #$15,a,a
        move    a0,a
        move    x:(r5+$20),r6
        move    a1,x:(r6+$34)
        clr     a
        move    a1,x:(r6+$35)
        rts

; ===== END fold_drum_1.asm =====

; ===== BEGIN resident_primitives.asm =====

pknv_noise:
        move x:(r6+$c),a
        tst a
        beq pknv_refresh
        sub #>$1,a
        and #>$00ffff,a
        move a1,x:(r6+$c)
        move x:(r6+$e),a
        move a1,x:(r5+$21)
        rts
pknv_refresh:
        move x:(r6+$d),a
        move a1,x:(r6+$c)
        move x:>$38e8,a
        move a1,x:(r5-$40)
        move x:>$38e9,a
        move a1,x:(r5-$3f)
        move x:>$38ea,a
        move a1,x:(r5-$3e)
        move x:>$38eb,a
        move a1,x:(r5-$3d)
        jsrl pk_rng_step
        move x:(r5-$40),a
        move a1,x:>$38e8
        move x:(r5-$3f),a
        move a1,x:>$38e9
        move x:(r5-$3e),a
        move a1,x:>$38ea
        move x:(r5-$3d),a
        move a1,x:>$38eb
        move x:(r5-$30),a
        and #>$00ffff,a
        move a1,x:(r6+$e)
        move a1,x:(r5+$21)
        rts

; ===== END resident_primitives.asm =====

; PERKY Noise/Tone envelope standalone DSP56300 probe.
;
; Exact transition/interpolation model from NativeV121NoiseToneShared's
; renderEnvelope(). No firmware curve bytes are embedded: the executable gate
; supplies two synthetic 2048-entry u16 curves at X:$3200 and X:$3a00.
;
; bd909_host probe state at r5:
;   +40 envelope state byte
;   +41 shape (0 linear, 1 curve A, 2 curve B)
;   +42 firmware flag base+4
;   +43 firmware flag base+6
;   +44 firmware flag base+7
;   +45/+46 envelope value u32 lo/hi
;   +47/+48 base+0x10 u32 (state-3 zero test)
;   +49 attack increment u16 (base+0x20)
;   +50 decay decrement u16 (base+0x22)
;   +51 returned envelope u16
; Scratch +0..+19 and +52..+59.

pk_envelope_probe:
        move    x:(r5+$40),a
        tst     a
        beq     pke_state0
        cmp     #>$1,a
        beq     pke_state1
        cmp     #>$2,a
        beq     pke_output
        cmp     #>$3,a
        beq     pke_state3
        cmp     #>$4,a
        beq     pke_state4
        bra     pke_output

pke_state0:
        move    x:(r5+$44),a
        tst     a
        bne     pke_start_state0
        move    x:(r5+$42),a
        tst     a
        beq     pke_output
pke_start_state0:
        move    #>$1,a
        move    a1,x:(r5+$40)
        bra     pke_output

pke_state1:
        ; value += attack increment, modulo 2^32.
        move    x:(r5+$45),a
        move    a1,x:(r5+$0)
        move    x:(r5+$46),a
        move    a1,x:(r5+$1)
        move    x:(r5+$49),a
        and     #>$00ffff,a
        move    a1,x:(r5+$2)
        clr     a
        move    a1,x:(r5+$3)
        jsr     pke_add
        move    x:(r5+$8),a
        move    a1,x:(r5+$45)
        move    x:(r5+$9),a
        move    a1,x:(r5+$46)

        jsr     pke_value_gt_peak
        move    x:(r5+$59),a
        tst     a
        beq     pke_output

        ; Above $000ffffe: flag4 chooses release state 4; otherwise flag6
        ; selects 3 (zero) or 4 (non-zero).
        move    x:(r5+$42),a
        tst     a
        bne     pke_release_state1
        move    x:(r5+$43),a
        tst     a
        bne     pke_release_state1
        move    #>$3,a
        move    a1,x:(r5+$40)
        bra     pke_clamp_state1
pke_release_state1:
        move    #>$4,a
        move    a1,x:(r5+$40)

pke_clamp_state1:
        ; Clamp only when value >= $00100000; $000fffff remains untouched.
        jsr     pke_value_ge_one
        move    x:(r5+$59),a
        tst     a
        beq     pke_output
        move    #>$00ffff,a
        move    a1,x:(r5+$45)
        move    #>$00000f,a
        move    a1,x:(r5+$46)
        bra     pke_output

pke_state3:
        ; if flag7==0 && (flag4!=0 || base+0x10==0), enter release state 4.
        move    x:(r5+$44),a
        tst     a
        bne     pke_output
        move    x:(r5+$42),a
        tst     a
        bne     pke_release_state3
        move    x:(r5+$47),a
        move    x:(r5+$48),x0
        or      x0,a
        tst     a
        bne     pke_output
pke_release_state3:
        move    #>$4,a
        move    a1,x:(r5+$40)
        bra     pke_output

pke_state4:
        move    x:(r5+$44),a
        tst     a
        beq     pke_decay_state4
        move    #>$1,a
        move    a1,x:(r5+$40)
        bra     pke_output

pke_decay_state4:
        ; value -= decay decrement, modulo 2^32.
        move    x:(r5+$45),a
        move    a1,x:(r5+$0)
        move    x:(r5+$46),a
        move    a1,x:(r5+$1)
        move    x:(r5+$50),a
        and     #>$00ffff,a
        move    a1,x:(r5+$2)
        clr     a
        move    a1,x:(r5+$3)
        jsr     pke_sub
        move    x:(r5+$8),a
        move    a1,x:(r5+$45)
        move    x:(r5+$9),a
        move    a1,x:(r5+$46)

        jsr     pke_value_le_zero
        move    x:(r5+$59),a
        tst     a
        beq     pke_output
        clr     a
        move    a1,x:(r5+$45)
        move    a1,x:(r5+$46)
        move    x:(r5+$42),a
        tst     a
        beq     pke_idle_state4
        move    #>$1,a
        move    a1,x:(r5+$40)
        bra     pke_output
pke_idle_state4:
        clr     a
        move    a1,x:(r5+$40)

pke_output:
        move    x:(r5+$41),a
        cmp     #>$1,a
        beq     pke_first_curve
        cmp     #>$2,a
        beq     pke_second_curve

        ; Linear/default shape: (unsigned32(value) >> 4) & $ffff.
        move    x:(r5+$45),a
        move    a1,b
        and     #>$00fff0,b
        lsr     #$4,b
        move    b1,x0
        move    x:(r5+$46),a
        and     #>$00000f,a
        asl     #$c,a,a
        add     x0,a
        and     #>$00ffff,a
        move    a1,x:(r5+$51)
        rts

pke_first_curve:
        move    #>$003200,r1
        bra     pke_curve
pke_second_curve:
        move    #>$003a00,r1

pke_curve:
        ; index = (raw >> 10) & $7ff.
        move    x:(r5+$45),a
        move    a1,b
        and     #>$00fc00,b
        lsr     #$a,b
        move    b1,x0
        move    x:(r5+$46),a
        and     #>$00001f,a
        asl     #$6,a,a
        add     x0,a
        and     #>$0007ff,a
        move    a1,x:(r5+$52)

        ; fraction = raw & $3ff.
        move    x:(r5+$45),a
        and     #>$0003ff,a
        move    a1,x:(r5+$53)

        ; first/second are unsigned 16-bit curve values.
        move    x:(r5+$52),a
        move    a1,n1
        move    x:(r1+n1),a
        and     #>$00ffff,a
        move    a1,x:(r5+$54)
        move    x:(r5+$52),a
        add     #>$1,a
        and     #>$0007ff,a
        move    a1,n1
        move    x:(r1+n1),a
        and     #>$00ffff,a
        move    a1,x:(r5+$55)

        ; delta = signed32(second-first), represented as two 16-bit limbs.
        move    x:(r5+$55),a
        move    x:(r5+$54),x0
        sub     x0,a
        move    a1,x:(r5+$56)
        move    a1,b
        and     #>$00ffff,b
        move    b1,x:(r5+$0)
        move    #>$0,x0
        tst     a
        jpl     pke_delta_sign_ready
        move    #>$00ffff,x0
pke_delta_sign_ready:
        move    x0,x:(r5+$1)
        move    x:(r5+$53),a
        move    a1,x:(r5+$2)
        clr     a
        move    a1,x:(r5+$3)
        jsr     pke_mul_low

        ; interp = ASR32(low32(delta*fraction), 10).
        move    x:(r5+$8),a
        move    a1,x:(r5+$0)
        move    x:(r5+$9),a
        move    a1,x:(r5+$1)
        move    #>$a,a
        move    a1,x:(r5+$4)
        jsr     pke_asr

        ; output = low16(first + interp).
        move    x:(r5+$54),a
        move    a1,x:(r5+$0)
        clr     a
        move    a1,x:(r5+$1)
        move    x:(r5+$8),a
        move    a1,x:(r5+$2)
        move    x:(r5+$9),a
        move    a1,x:(r5+$3)
        jsr     pke_add
        move    x:(r5+$8),a
        and     #>$00ffff,a
        move    a1,x:(r5+$51)
        rts

; ---- exact condition helpers ---------------------------------------------

; +59 = 1 iff signed32(value) > $000ffffe.
pke_value_gt_peak:
        clr     b
        move    b1,x:(r5+$59)
        move    x:(r5+$46),a
        btst    #15,a1
        jcc     pke_gt_peak_positive
        rts
pke_gt_peak_positive:
        cmp     #>$00000f,a
        bgt     pke_bool_true
        blt     pke_bool_false
        move    x:(r5+$45),a
        cmp     #>$00fffe,a
        bgt     pke_bool_true
pke_bool_false:
        rts

; +59 = 1 iff signed32(value) >= $00100000.
pke_value_ge_one:
        clr     b
        move    b1,x:(r5+$59)
        move    x:(r5+$46),a
        btst    #15,a1
        jcc     pke_ge_one_positive
        rts
pke_ge_one_positive:
        cmp     #>$000010,a
        bge     pke_bool_true
        rts

; +59 = 1 iff signed32(value) <= 0.
pke_value_le_zero:
        clr     b
        move    b1,x:(r5+$59)
        move    x:(r5+$46),a
        btst    #15,a1
        jcc     pke_le_zero_nonnegative
        bra     pke_bool_true
pke_le_zero_nonnegative:
        tst     a
        bne     pke_return_le_zero
        move    x:(r5+$45),a
        tst     a
        bne     pke_return_le_zero
pke_bool_true:
        move    #>$1,b
        move    b1,x:(r5+$59)
pke_return_le_zero:
        rts

; ---- exact two-limb helpers ------------------------------------------------

pke_add:
        move    x:(r5+$0),a
        move    x:(r5+$2),x0
        add     x0,a
        move    #>$0,y0
        btst    #16,a1
        jcc     pke_branch_add_no_carry
        move    #>$1,y0
pke_branch_add_no_carry:
        and     #>$00ffff,a
        move    a1,x:(r5+$8)
        move    x:(r5+$1),b
        move    x:(r5+$3),x0
        add     x0,b
        add     y0,b
        and     #>$00ffff,b
        move    b1,x:(r5+$9)
        rts

pke_sub:
        move    x:(r5+$0),a
        move    x:(r5+$2),x0
        sub     x0,a
        move    #>$0,y0
        jpl     pke_branch_sub_no_borrow
        move    #>$1,y0
pke_branch_sub_no_borrow:
        and     #>$00ffff,a
        move    a1,x:(r5+$8)
        move    x:(r5+$1),b
        move    x:(r5+$3),x0
        sub     x0,b
        sub     y0,b
        and     #>$00ffff,b
        move    b1,x:(r5+$9)
        rts

pke_asr:
        move    x:(r5+$1),a
        btst    #15,a1
        jcc     pke_shift_sign_ready
        sub     #>$010000,a
pke_shift_sign_ready:
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

pke_mul_low:
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

; PERKY Noise/Tone oscillator/interpolator standalone DSP56300 probe.
;
; No PĒRKONS waveform data lives here. The executable gate supplies two
; synthetic 256-sample signed-16 tables at X:$3000 and X:$3100 and maps two
; synthetic 32-bit firmware-style table identities onto them. This proves the
; phase, strict wrap threshold, deferred table switch, index wrap and linear
; interpolation independently of any copyrighted firmware table blob.
;
; bd909_host probe state at r5:
;   +40/+41 phase      u32 lo/hi
;   +42/+43 increment  u32 lo/hi
;   +44/+45 current table identity u32 lo/hi
;   +46/+47 next table identity    u32 lo/hi
;   +48       returned sample bit-pattern (u16)
; Scratch +0..+19 and +52..+59.
;
; Synthetic identities used only by this probe:
;   $11112222 -> X:$3000
;   $33334444 -> X:$3100

pk_osc_probe:
        ; phase = phase + increment, modulo 2^32
        move    x:(r5+$40),a
        move    a1,x:(r5+$0)
        move    x:(r5+$41),a
        move    a1,x:(r5+$1)
        move    x:(r5+$42),a
        move    a1,x:(r5+$2)
        move    x:(r5+$43),a
        move    a1,x:(r5+$3)
        jsr     pko_add
        move    x:(r5+$8),a
        move    a1,x:(r5+$40)
        move    x:(r5+$9),a
        move    a1,x:(r5+$41)

        ; Native code uses signed32(phase) > $00100000 -- strictly greater.
        move    x:(r5+$41),a
        btst    #15,a1
        jcc     pko_phase_positive
        bra     pko_phase_ready
pko_phase_positive:
        cmp     #>$0010,a
        bgt     pko_phase_wrap
        blt     pko_phase_ready
        move    x:(r5+$40),a
        tst     a
        bgt     pko_phase_wrap
        bra     pko_phase_ready

pko_phase_wrap:
        ; phase -= $00100000. Low limb is zero, so only high changes.
        move    x:(r5+$41),a
        sub     #>$0010,a
        and     #>$00ffff,a
        move    a1,x:(r5+$41)

        ; If next != current, publish next as current at the wrap.
        move    x:(r5+$44),a
        move    x:(r5+$46),x0
        cmp     x0,a
        bne     pko_switch_table
        move    x:(r5+$45),a
        move    x:(r5+$47),x0
        cmp     x0,a
        beq     pko_phase_ready
pko_switch_table:
        move    x:(r5+$46),a
        move    a1,x:(r5+$44)
        move    x:(r5+$47),a
        move    a1,x:(r5+$45)

pko_phase_ready:
        ; Resolve current synthetic identity to one of the two supplied tables.
        move    x:(r5+$44),a
        cmp     #>$002222,a
        bne     pko_try_table1
        move    x:(r5+$45),a
        cmp     #>$001111,a
        bne     pko_try_table1
        move    #>$003000,r1
        bra     pko_have_table
pko_try_table1:
        move    x:(r5+$44),a
        cmp     #>$004444,a
        bne     pko_missing_table
        move    x:(r5+$45),a
        cmp     #>$003333,a
        bne     pko_missing_table
        move    #>$003100,r1
        bra     pko_have_table
pko_missing_table:
        clr     a
        move    a1,x:(r5+$48)
        rts

pko_have_table:
        ; index = (phase >> 12) & $ff.
        move    x:(r5+$40),a
        move    a1,b
        and     #>$00f000,b
        lsr     #$c,b
        move    b1,x0
        move    x:(r5+$41),a
        and     #>$00000f,a
        asl     #$4,a,a
        add     x0,a
        and     #>$0000ff,a
        move    a1,x:(r5+$52)           ; index

        ; fraction = phase & $fff.
        move    x:(r5+$40),a
        and     #>$000fff,a
        move    a1,x:(r5+$53)

        ; first = signed16(table[index]).
        move    x:(r5+$52),a
        move    a1,n1
        move    x:(r1+n1),a
        and     #>$00ffff,a
        btst    #15,a1
        jcc     pko_first_ready
        sub     #>$010000,a
pko_first_ready:
        move    a1,x:(r5+$54)

        ; second = signed16(table[(index+1)&$ff]).
        move    x:(r5+$52),a
        add     #>$1,a
        and     #>$0000ff,a
        move    a1,n1
        move    x:(r1+n1),a
        and     #>$00ffff,a
        btst    #15,a1
        jcc     pko_second_ready
        sub     #>$010000,a
pko_second_ready:
        move    a1,x:(r5+$55)

        ; delta = second - first, then sign-extend the 24-bit temporary into
        ; the two 16-bit limbs expected by the exact low32 multiplier.
        move    x:(r5+$55),a
        move    x:(r5+$54),x0
        sub     x0,a
        move    a1,x:(r5+$56)
        move    a1,b
        and     #>$00ffff,b
        move    b1,x:(r5+$0)
        move    #>$0,x0
        tst     a
        jpl     pko_delta_sign_ready
        move    #>$00ffff,x0
pko_delta_sign_ready:
        move    x0,x:(r5+$1)
        move    x:(r5+$53),a
        move    a1,x:(r5+$2)
        clr     a
        move    a1,x:(r5+$3)
        jsr     pko_mul_low

        ; interp = arithmeticShiftRight(low32(delta*fraction), 12).
        move    x:(r5+$8),a
        move    a1,x:(r5+$0)
        move    x:(r5+$9),a
        move    a1,x:(r5+$1)
        move    #>$c,a
        move    a1,x:(r5+$4)
        jsr     pko_asr
        move    x:(r5+$8),a
        move    a1,x:(r5+$57)
        move    x:(r5+$9),a
        move    a1,x:(r5+$58)

        ; result = signed16(first + interp): add as u32 and keep low16.
        move    x:(r5+$54),a
        move    a1,b
        and     #>$00ffff,b
        move    b1,x:(r5+$0)
        move    #>$0,x0
        tst     a
        jpl     pko_first_sign_ready
        move    #>$00ffff,x0
pko_first_sign_ready:
        move    x0,x:(r5+$1)
        move    x:(r5+$57),a
        move    a1,x:(r5+$2)
        move    x:(r5+$58),a
        move    a1,x:(r5+$3)
        jsr     pko_add
        move    x:(r5+$8),a
        and     #>$00ffff,a
        move    a1,x:(r5+$48)
        rts

; ---- exact two-limb helpers ------------------------------------------------

pko_add:
        move    x:(r5+$0),a
        move    x:(r5+$2),x0
        add     x0,a
        move    #>$0,y0
        btst    #16,a1
        jcc     pko_branch_add_no_carry
        move    #>$1,y0
pko_branch_add_no_carry:
        and     #>$00ffff,a
        move    a1,x:(r5+$8)
        move    x:(r5+$1),b
        move    x:(r5+$3),x0
        add     x0,b
        add     y0,b
        and     #>$00ffff,b
        move    b1,x:(r5+$9)
        rts

pko_asr:
        move    x:(r5+$1),a
        btst    #15,a1
        jcc     pko_shift_sign_ready
        sub     #>$010000,a
pko_shift_sign_ready:
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

pko_mul_low:
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

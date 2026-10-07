; PĒRKONS v1.2.1 Noise Hat classic wrapper delay.
;
; ABI: r6 = 121-word X state, r5 = scratch, r4 = external 4,805-word Y ring.
; X:(r5+$60) = signed16 input bits; result A1 = narrowed signed16 output.
; State +$6d..+$71 = offsets, +$72..+$76 = gains, +$77 = index, +$78 = mix.
;
; Integer MPY products live in A0/A1 after removing fractional alignment.
; Tap sums wrap to signed32 BEFORE the >>4 and [-32767,32767] clamp.
; The final >>12 is followed by int16 narrowing, so its low16 is identical
; whether the preceding sum is kept wide or wraps to signed32 (the discarded
; difference after shifting is a multiple of 2^20). No final saturation.
; Only established signed MPY y0,x0 is used, even for positive coefficients.

pk_noise_hat_classic_delay:
        ; Rebase hot scratch so raw A0 stores use the stock one-word X form.
        move    r5,a
        add     #>$40,a
        move    a1,r7
        move    x:(r7+$20),a
        and     #>$00ffff,a
        move    a1,x:(r7+$24)           ; original input bits
        move    a1,x:(r7+$22)           ; current stage bits
        move    x:(r6+$77),a
        move    a1,x:(r7+$25)           ; pre-write index
        add     #>$1,a
        cmp     #>$12c4,a
        ble     pknhcd_next_ready
        clr     a
pknhcd_next_ready:
        move    a1,x:(r7+$26)

        move    r6,r1
        move    #>$6d,n1
        move    (r1)+n1
        move    r6,r2
        move    #>$72,n2
        move    (r2)+n2
        jsr     pknhcd_tap
        jsr     pknhcd_tap
        jsr     pknhcd_tap
        jsr     pknhcd_tap
        jsr     pknhcd_tap

        move    x:(r7+$26),n3
        move    r4,r3
        move    (r3)+n3
        move    x:(r7+$22),a
        move    a1,y:(r3)
        move    x:(r7+$26),a
        move    a1,x:(r6+$77)

        ; wet = (signed16(stage) * 5) >>1, bounded to signed18.
        move    x:(r7+$22),a
        asl     #$8,a,a
        move    a1,a
        asr     #$8,a,a
        move    a1,x0
        move    #>$5,y0
        mpy     y0,x0,a
        asr     #$2,a,a
        move    a0,x1

        move    x:(r6+$78),a
        asl     #$8,a,a
        move    a1,a
        asr     #$8,a,a
        move    a1,y0                   ; signed16 mix
        move    x1,x0
        mpy     y0,x0,a
        asr     #$1,a,a
        move    a0,x:(r7+$3)           ; raw low24, never a limiting move
        move    a1,x:(r7+$4)           ; signed upper product

        move    #>$000fff,a
        sub     y0,a
        move    a1,y0                   ; signed17 dry factor
        move    x:(r7+$24),a
        asl     #$8,a,a
        move    a1,a
        asr     #$8,a,a
        move    a1,x0
        mpy     y0,x0,a
        asr     #$1,a,a
        ; Reconstruct the first product without accumulator-to-accumulator
        ; limiting: B1 is signed upper24, B0 is the raw lower24.
        move    x:(r7+$4),b
        move    x:(r7+$3),b0
        add     b,a
        asr     #$c,a,a
        move    a0,a
        asl     #$8,a,a
        move    a1,a
        asr     #$8,a,a
        rts

; One serial tap; preserve r1/r2 array cursors, r4 ring base and r6 state.
pknhcd_tap:
        move    x:(r1)+,a
        move    a1,x:(r7+$27)
        move    x:(r2)+,a
        move    a1,x:(r7+$28)
        sub     #>$10,a
        move    a1,y0                   ; gain-16, signed17
        move    x:(r7+$22),a
        asl     #$8,a,a
        move    a1,a
        asr     #$8,a,a
        move    a1,x0
        mpy     y0,x0,a
        asr     #$1,a,a
        move    a0,x:(r7+$3)
        move    a1,x:(r7+$4)

        move    x:(r7+$25),a
        move    x:(r7+$27),x0
        cmp     x0,a
        bge     pknhcd_read_subtract
        add     #>$12c5,a
pknhcd_read_subtract:
        sub     x0,a
        move    a1,n3
        move    r4,r3
        move    (r3)+n3
        move    y:(r3),a
        asl     #$8,a,a
        move    a1,a
        asr     #$8,a,a
        move    a1,x0
        move    x:(r7+$28),y0
        mpy     y0,x0,a
        asr     #$1,a,a
        move    x:(r7+$4),b
        move    x:(r7+$3),b0
        add     b,a

        ; Shift the raw sum left24: the 56-bit accumulator now contains
        ; exactly sign-extended low32 aligned for the data ALU. Arithmetic
        ; >>4 keeps all signed28 bits for the clamp (including its remainder).
        asl     #$18,a,a
        asr     #$4,a,a
        cmp     #>$007fff,a
        ble     pknhcd_clamp_low
        move    #>$007fff,a
pknhcd_clamp_low:
        cmp     #>$ff8001,a
        bge     pknhcd_store
        move    #>$ff8001,a
pknhcd_store:
        and     #>$00ffff,a
        move    a1,x:(r7+$22)
        rts

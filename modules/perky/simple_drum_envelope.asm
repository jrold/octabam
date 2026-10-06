; PERKY Simple Drum v1.2.1 common-envelope renderer.
;
; Compact envelope state at r6 (11 words):
;   +0 state, +1 shape, +2 flag4, +3 flag6, +4 trigger/gate
;   +5/+6 value u32 lo/hi, +7/+8 hold u32 lo/hi, +9 attack, +a decay
;
; shape 0 is the analytic linear AMP envelope. Shape 1 uses the authentic
; pitch-envelope curve, direct packed-u16 at Y:$09a5. The reachable envelope
; accumulator is clamped to 0..$0fffff, so shaped indices are 0..1023.
;
; Shipping entry:
;   pk_simple_envelope: r6=11-word envelope, r5=scratch; returns u16 in A1.
;
; Standalone probe:
;   X:r5+$40..+$4a envelope state; renders n7 outputs to stereo X:(r0)+.

pk_simple_envelope_probe:
        lua     (r5+$40),r6
        do      n7,pksde_probe_done
        jsr     pk_simple_envelope
        move    a1,x:(r0)+
        move    a1,x:(r0)+
pksde_probe_done:
        nop
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
        ; Reconstruct bounded raw u32 value in A.
        move    x:(r6+$6),a
        asl     #$10,a,a
        move    x:(r6+$5),x0
        add     x0,a
        move    a1,x:(r5+$50)           ; low 24 bits of raw for shaped path

        move    x:(r6+$1),b
        cmp     #>$1,b
        beq     pksde_shape1

        ; shape 0: (raw >> 4) & $ffff.
        lsr     #$4,a
        and     #>$00ffff,a
        rts

pksde_shape1:
        ; index = raw >> 10 (0..1023), fraction = raw & $3ff.
        move    x:(r5+$50),a
        move    a1,b
        and     #>$00fc00,b
        lsr     #$a,b
        move    b1,x0
        move    x:(r6+$6),a
        and     #>$00000f,a
        asl     #$6,a,a
        add     x0,a
        and     #>$0003ff,a
        move    a1,x:(r5+$52)

        move    x:(r5+$50),a
        and     #>$0003ff,a
        move    a1,x:(r5+$53)

        move    x:(r5+$52),x0
        jsr     pksde_read_u16
        move    a1,x:(r5+$54)

        move    x:(r5+$52),a
        add     #>$1,a
        cmp     #>$400,a
        blt     pksde_next_ready
        move    #>$3ff,a                ; authentic endpoint duplicates 1023
pksde_next_ready:
        move    a1,x0
        jsr     pksde_read_u16
        move    a1,x:(r5+$55)

        ; unsigned endpoints produce signed17 delta; exact arithmetic >>10.
        move    x:(r5+$55),a
        move    x:(r5+$54),x0
        sub     x0,a
        move    a1,x0
        move    x:(r5+$53),y0
        mpy     y0,x0,a
        asr     #$b,a,a                 ; fractional MPY alignment + >>10
        move    a0,a
        move    x:(r5+$54),x0
        add     x0,a
        and     #>$00ffff,a
        rts

; input x0 = envelope index 0..1023
; output A1 = unsigned u16 at direct-packed Y:$09a5
pksde_read_u16:
        move    x0,x:(r5+$58)
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
        move    x:(r5+$58),a
        sub     y0,a
        move    a1,y1                   ; remainder 0..2

        move    x1,b
        asl     b
        move    b1,n1
        move    #>$0009a5,r1
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

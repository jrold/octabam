; Shipping envelope state machine. Live value is bounded to 0..0xfffff:
; attack/decay are u16, so transitions fit a signed24 accumulator exactly.
; The packed wrapper supplies curve interpolation; this entry returns linear.
pk_envelope_probe:
        move x:(r6+$1),a
        tst a
        beq pkne_idle
        cmp #>$1,a
        beq pkne_attack
        cmp #>$3,a
        beq pkne_hold
        cmp #>$4,a
        beq pkne_release
        bra pkne_output
pkne_idle:
        move x:(r6+$5),a
        move x:(r6+$3),x0
        or x0,a
        tst a
        beq pkne_output
pkne_start:
        move #>$1,a
        move a1,x:(r6+$1)
        bra pkne_output
pkne_attack:
        move x:(r6+$7),a
        asl #$10,a,a
        move x:(r6+$6),x0
        add x0,a
        move x:(r6+$a),x0
        add x0,a
        cmp #>$0ffffe,a
        ble pkne_commit
        move a1,x1
        move x:(r6+$3),b
        move x:(r6+$4),x0
        or x0,b
        tst b
        beq pkne_choose_hold
        move #>$4,b
        bra pkne_choose_done
pkne_choose_hold:
        move #>$3,b
pkne_choose_done:
        move b1,x:(r6+$1)
        move x1,a
        cmp #>$100000,a
        blt pkne_commit
        move #>$0fffff,a
        bra pkne_commit
pkne_hold:
        move x:(r6+$5),a
        tst a
        bne pkne_output
        move x:(r6+$3),a
        tst a
        bne pkne_begin_release
        move x:(r6+$8),a
        move x:(r6+$9),x0
        or x0,a
        tst a
        bne pkne_output
pkne_begin_release:
        move #>$4,a
        move a1,x:(r6+$1)
        bra pkne_output
pkne_release:
        move x:(r6+$5),a
        tst a
        bne pkne_restart
        move x:(r6+$7),a
        asl #$10,a,a
        move x:(r6+$6),x0
        add x0,a
        move x:(r6+$b),x0
        sub x0,a
        tst a
        bgt pkne_commit
        clr a
        move a1,x:(r6+$6)
        move a1,x:(r6+$7)
        move x:(r6+$3),a
        tst a
        beq pkne_stop
        bra pkne_restart
pkne_stop:
        clr a
        move a1,x:(r6+$1)
        bra pkne_output
pkne_commit:
        move a1,b
        and #>$00ffff,b
        move b1,x:(r6+$6)
        lsr #$10,a
        move a1,x:(r6+$7)
        bra pkne_output
pkne_restart:
        move #>$1,a
        move a1,x:(r6+$1)
        bra pkne_output
pkne_output:
        move x:(r6+$7),a
        asl #$10,a,a
        move x:(r6+$6),x0
        add x0,a
        lsr #$4,a
        and #>$00ffff,a
        move a1,x:(r5+$51)
        rts

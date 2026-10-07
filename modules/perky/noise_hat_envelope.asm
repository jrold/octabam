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
        move    b1,x:(r5+$59)           ; curve id 0
        bra     pknhe_shaped
pknhe_shape2:
        move    #>$1,b
        move    b1,x:(r5+$59)           ; curve id 1

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
        move    a1,x:(r5+$52)

        move    x:(r6+$5),a
        and     #>$0003ff,a
        move    a1,x:(r5+$53)

        move    x:(r5+$52),x0
        jsr     pknhe_read_u16
        move    a1,x:(r5+$54)

        move    x:(r5+$52),a
        add     #>$1,a
        move    a1,x0
        jsr     pknhe_read_u16
        move    a1,x:(r5+$55)

        ; unsigned endpoints produce a signed17 delta; exact arithmetic >>10.
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

; input x0 = table index 0..1024
; input X:r5+$59 = curve id 0/1
; output A1 = unsigned u16 from direct packed Y
pknhe_read_u16:
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
        move    x:(r5+$59),a
        tst     a
        beq     pknhe_env1_base
        move    #>$000c51,r1
        bra     pknhe_base_ready
pknhe_env1_base:
        move    #>$0009a5,r1
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

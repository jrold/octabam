; Exact second-difference block decoder. One persistent 17-word cache at r4.
; x0=sample index, r1=packed table base, y0=bits/block, y1=first delta width.
; n3=second difference width (signed). Cursor reads two packed Y words; the
; payload builder must reserve a zero padding word past the final stream.
pk_simple_delta_at:
        move    x0,a
        and     #>$f,a
        move    a1,x:(r5+$4d)
        move    x0,a
        lsr     #$4,a
        move    a1,x0
        move    x:(r4),b
        cmp     x0,b
        beq     pksdd_hit
        move    x0,x:(r4)
        move    y1,x:(r5+$4e)
        move    n3,x:(r5+$4f)
        mpyuu   x0,y0,a
        asr     #$1,a,a
        move    a0,x:(r5+$4c)
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
        move    x:(r5+$4c),a
        sub     b,a
        move    a1,x1
        lua     (r4+$1),r3
        move    #>$10,n2
        jsr     pksdd_unsigned
        move    a1,x:(r5+$50)
        move    a1,x:(r3)+
        move    x:(r5+$4e),n2
        jsr     pksdd_unsigned
        move    a1,x:(r5+$51)
        move    x:(r5+$50),x0
        add     x0,a
        move    a1,x:(r5+$50)
        move    a1,x:(r3)+
        do      #$e,pksdd_decoded
        move    x:(r5+$4f),n2
        clr     a
        move    y:(r2),a0
        move    y:(r2+$1),a1
        move    n2,b
        asl     #$c,b,b
        add     x1,b
        move    b1,y0
        extract y0,a,b
        move    b0,a
        move    x:(r5+$51),x0
        add     x0,a
        move    a1,x:(r5+$51)
        move    x:(r5+$50),x0
        add     x0,a
        move    a1,x:(r5+$50)
        move    a1,x:(r3)+
        jsr     pksdd_advance
pksdd_decoded:
        nop
pksdd_hit:
        move    x:(r5+$4d),n1
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
        jsr     pksdd_advance
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
        move    a1,x:(r5+$60)
        move    x:(r6+$20),a
        move    a1,x:(r5+$48)
        lsr     #$9,a
        move    a1,x:(r5+$49)
        move    x:(r6+$20),a
        and     #>$1ff,a
        move    a1,x0
        move    #>$003964,r4
        move    #>$000efb,r1
        move    #>$32,y0
        move    #>$6,y1
        move    #>$2,n3
        jsr     pk_simple_delta_at
        move    #>$7,b
        move    x:(r5+$49),x0
        sub     x0,b
        move    b1,x0
        asr     x0,a,a
        move    a1,x0
        move    #>$00bb80,y0
        mpyuu   x0,y0,a
        asr     #$15,a,a
        move    a0,a
        move    x:(r5+$60),r6
        move    a1,x:(r6+$34)
        clr     a
        move    a1,x:(r6+$35)
        rts

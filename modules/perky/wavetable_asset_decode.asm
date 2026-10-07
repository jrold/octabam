; Lossless second-difference32 block decoder. Candidate storage backend.
; x0 sample index 0..2047; r1 asset header (first delta width, 64 descriptors);
; n4 absolute packed-data base; r4 33-word X cache; r5 100-word scratch.
; Cache tag = (header_address << 6) + block; invalidate to $ffffff at init.
; Returns signed16 sample in a1. Clobbers r1/r2/r3,x0/x1,y0/y1,n1/n2.
; Single-word Y addresses used here are logical; placement is gated separately.
pk_wavetable_asset_at:
        move x0,a
        and #>$1f,a
        move a1,x:(r5+$4d)
        move x0,a
        lsr #$5,a
        move a1,n1
        move r1,b
        asl #$6,b,b
        add a,b
        move x:(r4),x0
        cmp x0,b
        beq pkwd_hit
        move b1,x:(r4)
        move y:(r1),a
        move a1,x:(r5+$4e)
        lua (r1+$1),r1
        move y:(r1+n1),a
        move a1,b
        lsr #$13,b
        move b1,x:(r5+$4f)
        and #>$7ffff,a
        move n4,x0
        add x0,a
        move a1,r2
        move #>$0,x1
        lua (r4+$1),r3
        move #>$10,n2
        jsr pkwd_signed
        move a1,x:(r5+$50)
        move a1,x:(r3)+
        move x:(r5+$4e),n2
        jsr pkwd_signed
        move a1,x:(r5+$51)
        move x:(r5+$50),x0
        add x0,a
        move a1,x:(r5+$50)
        move a1,x:(r3)+
        do #$1e,pkwd_decoded
        move x:(r5+$4f),n2
        jsr pkwd_signed
        move x:(r5+$51),x0
        add x0,a
        move a1,x:(r5+$51)
        move x:(r5+$50),x0
        add x0,a
        move a1,x:(r5+$50)
        move a1,x:(r3)+
pkwd_decoded:
        nop
pkwd_hit:
        move x:(r5+$4d),n1
        lua (r4+$1),r1
        move x:(r1+n1),a
        rts
pkwd_signed:
        clr a
        move y:(r2),a0
        move y:(r2+$1),a1
        move n2,b
        asl #$c,b,b
        add x1,b
        move b1,y0
        extract y0,a,b
        move b0,y1
        move x1,a
        move n2,x0
        add x0,a
        cmp #>$18,a
        blt pkwd_cursor_ok
        sub #>$18,a
        lua (r2+$1),r2
pkwd_cursor_ok:
        move a1,x1
        move y1,a
        rts

; PERKY Noise/Tone DSP56300 32-bit arithmetic kernel / standalone probe.
; Not in the audio hook yet. Firmware u32 values are two 16-bit limbs.
; Normal 24-bit DSP mode only: do not use SA; Octabam's emulator does not
; implement SA semantics, so explicit limbs keep the off-hardware oracle valid.
;
; bd909_host-compatible probe ABI:
;   r5 = X state base, r6 = X parameter block, x:(r6+$0) = op
; State: +0 a.lo, +1 a.hi, +2 b.lo, +3 b.hi, +4 shift,
;        +8 result.lo, +9 result.hi
; Ops: 1 add32, 2 sub32, 3 signed ASR32, 4 low32 multiply.

pk_math_probe:
        move    x:(r6+$0),a
        move    #>$1,x0
        cmp     x0,a
        beq     pk_math_do_add
        move    #>$2,x0
        cmp     x0,a
        beq     pk_math_do_sub
        move    #>$3,x0
        cmp     x0,a
        beq     pk_math_do_asr
        move    #>$4,x0
        cmp     x0,a
        beq     pk_math_do_mul
        rts

pk_math_do_add:
        jsr     pk_u32_add
        rts
pk_math_do_sub:
        jsr     pk_u32_sub
        rts
pk_math_do_asr:
        jsr     pk_u32_asr
        rts
pk_math_do_mul:
        jsr     pk_u32_mul_low
        rts

; Exact modulo-2^32 add. Low sum <= 0x1fffe, so A1 bit16 is carry.
pk_u32_add:
        move    x:(r5+$0),a
        move    x:(r5+$2),x0
        add     x0,a
        move    #>$0,y0
        btst    #16,a1
        jcc     pk_add_no_carry
        move    #>$1,y0
pk_add_no_carry:
        and     #>$00ffff,a
        move    a1,x:(r5+$8)
        move    x:(r5+$1),b
        move    x:(r5+$3),x0
        add     x0,b
        add     y0,b
        and     #>$00ffff,b
        move    b1,x:(r5+$9)
        rts

; Exact modulo-2^32 subtract. For 16-bit inputs N on low diff means borrow.
pk_u32_sub:
        move    x:(r5+$0),a
        move    x:(r5+$2),x0
        sub     x0,a
        move    #>$0,y0
        jpl     pk_sub_no_borrow
        move    #>$1,y0
pk_sub_no_borrow:
        and     #>$00ffff,a
        move    a1,x:(r5+$8)
        move    x:(r5+$1),b
        move    x:(r5+$3),x0
        sub     x0,b
        sub     y0,b
        and     #>$00ffff,b
        move    b1,x:(r5+$9)
        rts

; Signed 32-bit arithmetic right shift by 0..31. y0 is a sign-extended high
; limb. Each iteration shifts low logically, high arithmetically, then uses
; the high shift's carry to inject old high bit0 into low bit15.
pk_u32_asr:
        move    x:(r5+$0),x1
        move    x:(r5+$1),y0
        move    y0,a
        btst    #15,a1
        jcc     pk_asr_sign_done
        move    #>$010000,x0
        sub     x0,a
pk_asr_sign_done:
        move    a1,y0
        move    x:(r5+$4),x0
        move    #>$008000,y1
        do      x0,pk_asr_loop_done
        move    x1,b
        lsr     b
        move    b1,x1
        move    y0,a
        asr     a
        add     y1,b ifcs
        move    b1,x1
        move    a1,y0
pk_asr_loop_done:
        nop
        move    x1,a
        and     #>$00ffff,a
        move    a1,x:(r5+$8)
        move    y0,b
        and     #>$00ffff,b
        move    b1,x:(r5+$9)
        rts

; Low 32 bits of unsigned 32x32 multiply using three 16x16 products:
; lo=low16(al*bl), hi=low16(high16(al*bl)+al*bh+ah*bl).
; MPYUU is right-justified in A2:A1:A0; with 16-bit operands the product is
; <=32 bits, so LSR #16 exposes product bits 16..31 in A0.
pk_u32_mul_low:
        move    x:(r5+$0),x0
        move    x:(r5+$2),y0
        mpyuu   x0,y0,a
        move    a0,x1
        move    x1,b
        and     #>$00ffff,b
        move    b1,x:(r5+$8)
        lsr     #$10,a,a
        move    a0,x1
        move    x1,b
        and     #>$00ffff,b
        move    b1,y1

        move    x:(r5+$0),x0
        move    x:(r5+$3),y0
        mpyuu   x0,y0,a
        and     #>$00ffff,a
        move    a1,x1
        move    y1,b
        add     x1,b

        move    x:(r5+$1),x0
        move    x:(r5+$2),y0
        mpyuu   x0,y0,a
        and     #>$00ffff,a
        move    a1,x1
        add     x1,b
        and     #>$00ffff,b
        move    b1,x:(r5+$9)
        rts

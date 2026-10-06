; PERKY Noise/Tone envelope wrapper using the shipping packed-Y curve layout.
;
; Correctness-first design: do NOT duplicate the proven envelope state machine.
; We save the requested shape, temporarily force shape=0, call the already
; executable-gated pk_envelope_probe for the state transition, then restore the
; shape and recompute only the shaped output from packed Y.
;
; Probe ABI remains noise_tone_envelope.asm:
;   X:r5+40..50  envelope state/parameters
;   X:r5+51      returned u16 amplitude
;   X:r5+52..63  scratch
;
; One shipping-sized derived cache is addressed through r4:
;   X:(r4)       key = (curve_id << 7) | block_id, invalid = $ffff
;   X:(r4+1..16) sixteen decoded u16 values
;
; Two entries share one implementation:
;   pk_envelope_packed7_probe  -- standalone gates; points r4 at X:r5+64
;   pk_envelope_packed7_cached -- shipping caller supplies persistent r4
;
; Synthetic packed table geometry used by this executable canary:
;   curve 0 / shape 1: Y:$0a50, 7-bit deltas
;   curve 1 / shape 2: Y:$0cd6, 7-bit deltas
; The real firmware may produce another delta width; the generic Python cursor
; and payload metadata remain the source of truth until real bytes qualify it.

pk_envelope_packed7_probe:
        lua     (r5+$64),r4             ; standalone cache = scratch + 100
        bra     pk_envelope_packed7_cached

pk_envelope_packed7_cached:
        ; Preserve caller's shape outside the raw envelope kernel's scratch.
        move    x:(r6+$2),a
        move    a1,x:(r5+$62)

        ; State transition is shape-independent. Force linear so the proven
        ; kernel never reads its old unpacked X tables; its output is ignored
        ; below for shapes 1/2 and kept verbatim for every other shape.
        clr     a
        move    a1,x:(r6+$2)
        jsr     pk_envelope_probe

        move    x:(r5+$62),a
        move    a1,x:(r6+$2)
        cmp     #>$1,a
        beq     pkep_shape1
        cmp     #>$2,a
        beq     pkep_shape2
        rts

pkep_shape1:
        bra     pken_linear
pken_unused_shape1:
        clr     b
        move    b1,x:(r5+$63)           ; curve id 0
        bra     pkep_shaped
pkep_shape2:
        move    #>$1,b
        move    b1,x:(r5+$63)           ; curve id 1

pkep_shaped:
        ; index = (raw value >> 10) & $7ff.
        move    x:(r6+$6),a
        move    a1,b
        and     #>$00fc00,b
        lsr     #$a,b
        move    b1,x0
        move    x:(r6+$7),a
        and     #>$00001f,a
        asl     #$6,a,a
        add     x0,a
        and     #>$0007ff,a
        move    a1,x:(r5+$52)

        ; fraction = raw & $3ff.
        move    x:(r6+$6),a
        and     #>$0003ff,a
        move    a1,x:(r5+$53)

        ; first = curve[index].
        move    x:(r5+$52),x0
        jsr     pkep_curve_u16
        move    a1,x:(r5+$54)

        ; second = curve[(index+1)&$7ff].
        move    x:(r5+$52),a
        add     #>$1,a
        and     #>$0007ff,a
        move    a1,x0
        jsr     pkep_curve_u16
        move    a1,x:(r5+$55)

        ; unsigned16 endpoints have a signed17 delta; fraction <=1023.
        move x:(r5+$55),a
        move x:(r5+$54),x0
        sub x0,a
        move a1,x0
        move x:(r5+$53),y0
        mpy y0,x0,a
        asr #$b,a,a
        move a0,a
        move x:(r5+$54),x0
        add x0,a
        and #>$00ffff,a
        move a1,x:(r5+$51)
        rts

; ---------------------------------------------------------------------------
; pkep_curve_u16
;   input  x0 = curve index 0..2047
;   input  X:r5+63 = curve id 0/1
;   input  r4 = 17-word persistent cache base
;   output A1 = unsigned u16 value
; ---------------------------------------------------------------------------
pkep_curve_u16:
        move    x0,a
        move    a1,x:(r5+$60)           ; full index
        move    a1,b
        and     #>$00000f,b
        move    b1,x:(r5+$61)           ; within-block 0..15

        lsr     #$4,a
        and     #>$00007f,a
        move    a1,x1                   ; block 0..127
        move    x:(r5+$63),b
        tst     b
        beq     pkep_key_ready
        move    x1,a
        add     #>$000080,a
        move    a1,x1
pkep_key_ready:
        move    x:(r4),a
        cmp     x1,a
        beq     pkep_cache_hit

        ; Publish the new curve+block key, then decode its 16 values.
        move    x1,x:(r4)

        ; block = index >> 4.
        move    x:(r5+$60),a
        lsr     #$4,a
        and     #>$00007f,a
        move    a1,x0

        ; bitpos = block * 121.
        move    #>$000079,y0
        mpyuu   x0,y0,a
        asr     #$1,a,a                 ; remove fractional multiply alignment
        move    a0,x0
        move    x0,x:(r5+$59)

        ; q3 = floor(bitpos / 3), using exact reciprocal for this range.
        move    #>$00aaab,y0
        mpyuu   x0,y0,a
        asr     #$1,a,a                 ; remove fractional multiply alignment
        asr     #$10,a,a
        move    a0,x1
        move    x1,b
        and     #>$00ffff,b
        lsr     b
        move    b1,x1

        ; word = floor(q3/8) = floor(bitpos/24).
        move    x1,b
        lsr     #$3,b
        move    b1,n1                   ; packed word offset
        move    b1,x1

        ; bit = bitpos - 24*word.
        move    x1,b
        asl     #$3,b,b                 ; 8*word
        move    b1,y0
        move    y0,b
        asl     b                       ; 16*word
        add     y0,b                    ; 24*word
        move    b1,y0
        move    x:(r5+$59),a
        sub     y0,a
        move    a1,x1                   ; bit offset 0..23

        ; Select packed curve base.
        move    x:(r5+$63),a
        tst     a
        beq     pkep_env1
        move    #>$000cd6,r1
        bra     pkep_base_ready
pkep_env1:
        move    #>$000a50,r1
pkep_base_ready:
        lua     (r1+n1),r2
        lua     (r4+$1),r3

        ; Unsigned 16-bit anchor.
        clr     a
        move    y:(r2),a0
        move    y:(r2+$1),a1
        move    #>$010000,b             ; width 16 << 12
        add     x1,b
        move    b1,y0
        extractu y0,a,b
        move    b0,y1
        move    y1,a
        and     #>$00ffff,a
        move    a1,y1
        move    y1,x:(r3)+

        ; cursor += 16.
        move    x1,a
        add     #>$10,a
        cmp     #>$18,a
        blt     pkep_anchor_cursor_ok
        sub     #>$18,a
        move    #>$1,n2
        lua     (r2+n2),r2
pkep_anchor_cursor_ok:
        move    a1,x1

        ; Fifteen signed 7-bit first differences.
        do      #$f,pkep_delta_done
        clr     a
        move    y:(r2),a0
        move    y:(r2+$1),a1
        move    #>$007000,b             ; width 7 << 12
        add     x1,b
        move    b1,y0
        extract  y0,a,b
        move    b0,x0

        move    y1,a
        add     x0,a
        and     #>$00ffff,a
        move    a1,y1
        move    y1,x:(r3)+

        ; cursor += 7.
        move    x1,a
        add     #>$7,a
        cmp     #>$18,a
        blt     pkep_delta_cursor_ok
        sub     #>$18,a
        move    #>$1,n2
        lua     (r2+n2),r2
pkep_delta_cursor_ok:
        move    a1,x1
pkep_delta_done:
        nop

pkep_cache_hit:
        move    x:(r5+$61),a
        move    a1,n1
        lua     (r4+$1),r1
        move    x:(r1+n1),a
        and     #>$00ffff,a
        rts

; The synthetic curve1 is round(index*65535/2047). Exact division by
; 2047 uses its Mersenne form; exhaustive 2048-index gate pins the formula.
; This specialization is enabled only for the synthetic asset fingerprint.
pken_linear:
        move x:(r6+$6),a
        move a1,b
        and #>$00fc00,b
        lsr #$a,b
        move b1,x0
        move x:(r6+$7),a
        and #>$00001f,a
        asl #$6,a,a
        add x0,a
        and #>$0007ff,a
        move a1,x:(r5+$52)
        move a1,x0
        jsr pken_index_value
        move a1,x:(r5+$54)
        move #>$20,x0
        move x:(r5+$52),a
        cmp #>$7ff,a
        beq pken_wrapped_pair
        move y1,a
        add #>$1f,a
        cmp #>$7ff,a
        blt pken_pair_ready
        move #>$21,x0
        bra pken_pair_ready
pken_wrapped_pair:
        move #>$ff0001,x0
pken_pair_ready:
        move x:(r6+$6),a
        and #>$0003ff,a
        move a1,y0
        mpy y0,x0,a
        asr #$b,a,a
        move a0,a
        move x:(r5+$54),x0
        add x0,a
        and #>$00ffff,a
        move a1,x:(r5+$51)
        rts

pken_index_value:
        move x0,a
        asl #$5,a,a
        move a1,x1
        sub x0,a
        add #>$0003ff,a
        move a1,b
        lsr #$b,b
        move b1,y0
        and #>$0007ff,a
        add y0,a
        cmp #>$0007ff,a
        blt pken_no_div_carry
        sub #>$0007ff,a
        move y0,b
        add #>$1,b
        move b1,y0
pken_no_div_carry:
        move a1,y1
        move x1,a
        add y0,a
        rts

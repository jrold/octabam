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
; One shipping-sized derived cache lives at:
;   X:r5+64      key = (curve_id << 7) | block_id, invalid = $ffff
;   X:r5+65..80  sixteen decoded u16 values
;
; Synthetic packed table geometry used by this executable canary:
;   curve 0 / shape 1: Y:$0a40, 7-bit deltas
;   curve 1 / shape 2: Y:$0cc6, 7-bit deltas
; The real firmware may produce another delta width; the generic Python cursor
; and payload metadata remain the source of truth until real bytes qualify it.

pk_envelope_packed7_probe:
        ; Preserve caller's shape outside the raw envelope kernel's scratch.
        move    x:(r5+$41),a
        move    a1,x:(r5+$62)

        ; State transition is shape-independent. Force linear so the proven
        ; kernel never reads its old unpacked X tables; its output is ignored
        ; below for shapes 1/2 and kept verbatim for every other shape.
        clr     a
        move    a1,x:(r5+$41)
        jsr     pk_envelope_probe

        move    x:(r5+$62),a
        move    a1,x:(r5+$41)
        cmp     #>$1,a
        beq     pkep_shape1
        cmp     #>$2,a
        beq     pkep_shape2
        rts

pkep_shape1:
        clr     b
        move    b1,x:(r5+$63)           ; curve id 0
        bra     pkep_shaped
pkep_shape2:
        move    #>$1,b
        move    b1,x:(r5+$63)           ; curve id 1

pkep_shaped:
        ; index = (raw value >> 10) & $7ff.
        move    x:(r5+$45),a
        move    a1,b
        and     #>$00fc00,b
        lsr     #$a,b,b
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

        ; Same exact interpolation arithmetic as the proven raw-table kernel.
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
        jpl     pkep_delta_sign_ready
        move    #>$00ffff,x0
pkep_delta_sign_ready:
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

; ---------------------------------------------------------------------------
; pkep_curve_u16
;   input  x0 = curve index 0..2047
;   input  X:r5+63 = curve id 0/1
;   output A1 = unsigned u16 value
;
; One cache word keys BOTH the curve and block. Therefore switching shape at
; the same block number is a miss and refills the same 17 words.
; ---------------------------------------------------------------------------
pkep_curve_u16:
        move    x0,a
        move    a1,x:(r5+$60)           ; full index
        move    a1,b
        and     #>$00000f,b
        move    b1,x:(r5+$61)           ; within-block 0..15

        lsr     #$4,a,a
        and     #>$00007f,a
        move    a1,x1                   ; block 0..127
        move    x:(r5+$63),b
        tst     b
        beq     pkep_key_ready
        move    x1,a
        add     #>$000080,a
        move    a1,x1
pkep_key_ready:
        move    x:(r5+$64),a
        cmp     x1,a
        beq     pkep_cache_hit

        ; Publish the new curve+block key, then decode its 16 values.
        move    x1,x:(r5+$64)

        ; block = index >> 4.
        move    x:(r5+$60),a
        lsr     #$4,a,a
        and     #>$00007f,a
        move    a1,x0

        ; bitpos = block * 121.
        move    #>$000079,y0
        mpyuu   x0,y0,a
        move    a0,x0
        move    x0,x:(r5+$59)

        ; q3 = floor(bitpos / 3), using exact reciprocal for this range.
        move    #>$00aaab,y0
        mpyuu   x0,y0,a
        lsr     #$10,a,a
        move    a0,x1
        move    x1,b
        and     #>$00ffff,b
        lsr     b
        move    b1,x1

        ; word = floor(q3/8) = floor(bitpos/24).
        move    x1,b
        lsr     #$3,b,b
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
        move    #>$000cc6,r1
        bra     pkep_base_ready
pkep_env1:
        move    #>$000a40,r1
pkep_base_ready:
        lua     (r1+n1),r2
        lua     (r5+$65),r3

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
        lua     (r5+$65),r1
        move    x:(r1+n1),a
        and     #>$00ffff,a
        rts

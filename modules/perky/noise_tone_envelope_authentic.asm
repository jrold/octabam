; Authentic v1.2.1 Noise/Tone envelope wrapper for HW4 T6.
;
; Reuses the already qualified pk_envelope_probe state-transition kernel, then
; recomputes shaped output from the exact losslessly packed v1.2.1 curves.
; Unlike noise_tone_envelope_packed7.asm this file makes NO assumption that the
; real curves use seven-bit first differences.
;
; Caller/scratch ABI (same as the existing envelope probes):
;   r5+$40..$50  envelope state/parameters
;   r5+$51       returned u16 amplitude
;   r5+$52..$5f  private scratch
;   r4           17-word persistent decoded-block cache
;                +0 key=(curve_id<<7)|block, $ffff invalid
;                +1..+16 decoded u16 values
;
; Build substitutions supplied from noise-tone-authentic/manifest.json:
;   @NT_ENV1_BASE@       packed Y base for curve 1
;   @NT_ENV2_BASE@       packed Y base for curve 2
;   @NT_ENV1_DELTA_BITS@ signed first-difference width for curve 1
;   @NT_ENV2_DELTA_BITS@ signed first-difference width for curve 2
;   @NT_ENV1_BLOCK_BITS@ 16 + 15*delta_bits for curve 1
;   @NT_ENV2_BLOCK_BITS@ 16 + 15*delta_bits for curve 2
;
; Every curve block is exactly 16 samples: one unsigned u16 anchor followed by
; fifteen signed fixed-width deltas, bit-packed LSB-first into 24-bit Y words.

pk_nt_auth_envelope_cached:
        ; Preserve requested shape while the proven transition kernel runs in
        ; linear mode. The transition itself is shape-independent.
        move    x:(r5+$41),a
        move    a1,x:(r5+$5e)
        clr     a
        move    a1,x:(r5+$41)
        jsrl    pk_envelope_probe
        move    x:(r5+$5e),a
        move    a1,x:(r5+$41)

        cmp     #>$1,a
        beq     pknta_shape1
        cmp     #>$2,a
        beq     pknta_shape2
        rts

pknta_shape1:
        clr     b
        move    b1,x:(r5+$5f)           ; curve id 0
        move    #>@NT_ENV1_BASE@,r1
        move    #>@NT_ENV1_DELTA_BITS@,x1
        move    #>@NT_ENV1_BLOCK_BITS@,y1
        bra     pknta_shape_ready

pknta_shape2:
        move    #>$1,b
        move    b1,x:(r5+$5f)           ; curve id 1
        move    #>@NT_ENV2_BASE@,r1
        move    #>@NT_ENV2_DELTA_BITS@,x1
        move    #>@NT_ENV2_BLOCK_BITS@,y1

pknta_shape_ready:
        ; Persist curve-specific decode constants across the two lookups below.
        move    r1,x:(r5+$58)           ; packed Y base
        move    x1,x:(r5+$59)           ; delta width
        move    y1,x:(r5+$5a)           ; bits per 16-sample block

        ; index=(raw envelope value >> 10) & $7ff.
        move    x:(r5+$45),a
        move    a1,b
        and     #>$00fc00,b
        lsr     #$a,b
        move    b1,x0
        move    x:(r5+$46),a
        and     #>$00001f,a
        asl     #$6,a,a
        add     x0,a
        and     #>$0007ff,a
        move    a1,x:(r5+$52)

        ; fraction=raw & $3ff.
        move    x:(r5+$45),a
        and     #>$0003ff,a
        move    a1,x:(r5+$53)

        ; first=curve[index].
        move    x:(r5+$52),x0
        jsrl    pk_nt_auth_curve_u16
        move    a1,x:(r5+$54)

        ; second=curve[(index+1)&$7ff].
        move    x:(r5+$52),a
        add     #>$1,a
        and     #>$0007ff,a
        move    a1,x0
        jsrl    pk_nt_auth_curve_u16
        move    a1,x:(r5+$55)

        ; Exact original interpolation:
        ; output=first+ASR32(low32((second-first)*fraction),10).
        move    x:(r5+$55),a
        move    x:(r5+$54),x0
        sub     x0,a
        move    a1,b
        and     #>$00ffff,b
        move    b1,x:(r5+$0)
        move    #>$0,x0
        tst     a
        jpl     pknta_delta_positive
        move    #>$00ffff,x0
pknta_delta_positive:
        move    x0,x:(r5+$1)
        move    x:(r5+$53),a
        move    a1,x:(r5+$2)
        clr     a
        move    a1,x:(r5+$3)
        jsrl    pk_u32_mul_low

        move    x:(r5+$8),a
        move    a1,x:(r5+$0)
        move    x:(r5+$9),a
        move    a1,x:(r5+$1)
        move    #>$a,a
        move    a1,x:(r5+$4)
        jsrl    pk_u32_asr

        move    x:(r5+$54),a
        move    a1,x:(r5+$0)
        clr     a
        move    a1,x:(r5+$1)
        move    x:(r5+$8),a
        move    a1,x:(r5+$2)
        move    x:(r5+$9),a
        move    a1,x:(r5+$3)
        jsrl    pk_u32_add
        move    x:(r5+$8),a
        and     #>$00ffff,a
        move    a1,x:(r5+$51)
        rts

; ---------------------------------------------------------------------------
; pk_nt_auth_curve_u16
;   x0 = curve sample index 0..2047
;   X:r5+$58 = packed Y base
;   X:r5+$59 = signed delta width
;   X:r5+$5a = block bit count (16+15*width)
;   X:r5+$5f = curve id 0/1
;   r4 = 17-word persistent block cache
; returns A1 = exact unsigned u16 curve sample
; ---------------------------------------------------------------------------
pk_nt_auth_curve_u16:
        move    x0,a
        move    a1,x:(r5+$5b)           ; full index
        move    a1,b
        and     #>$00000f,b
        move    b1,x:(r5+$5c)           ; within block 0..15

        lsr     #$4,a
        and     #>$00007f,a
        move    a1,x1                   ; block 0..127
        move    x:(r5+$5f),b
        tst     b
        beq     pknta_key_ready
        move    x1,a
        add     #>$000080,a
        move    a1,x1
pknta_key_ready:
        move    x:(r4),a
        cmp     x1,a
        beq     pknta_cache_hit
        move    x1,x:(r4)

        ; bitpos=block*block_bits. Values are <=127*271, safely inside 16 bits.
        move    x:(r5+$5b),a
        lsr     #$4,a
        and     #>$00007f,a
        move    a1,x0
        move    x:(r5+$5a),y0
        mpyuu   x0,y0,a
        asr     #$1,a,a                 ; remove fractional multiply alignment
        move    a0,x0
        move    x0,x:(r5+$5d)           ; bitpos

        ; word=floor(bitpos/24). q3=floor(bitpos/3), word=floor(q3/8).
        move    #>$00aaab,y0
        mpyuu   x0,y0,a
        asr     #$1,a,a
        asr     #$10,a,a
        move    a0,x1
        move    x1,b
        and     #>$00ffff,b
        lsr     b
        move    b1,x1                   ; q3
        move    x1,b
        lsr     #$3,b
        move    b1,n1                   ; packed word offset

        ; bit=bitpos-24*word.
        move    b1,x1
        move    x1,b
        asl     #$3,b,b
        move    b1,y0                   ; 8*word
        move    y0,b
        asl     b                       ; 16*word
        add     y0,b                    ; 24*word
        move    b1,y0
        move    x:(r5+$5d),a
        sub     y0,a
        move    a1,x1                   ; cursor 0..23

        move    x:(r5+$58),r1
        lua     (r1+n1),r2
        lua     (r4+$1),r3

        ; Anchor: unsigned 16 bits at current cursor.
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

        ; cursor += 16, carrying into next Y word as needed.
        move    x1,a
        add     #>$10,a
pknta_anchor_carry:
        cmp     #>$18,a
        blt     pknta_anchor_ready
        sub     #>$18,a
        move    #>$1,n2
        lua     (r2+n2),r2
        bra     pknta_anchor_carry
pknta_anchor_ready:
        move    a1,x1

        ; Decode fifteen signed fixed-width first differences.
        do      #$f,pknta_delta_done
        clr     a
        move    y:(r2),a0
        move    y:(r2+$1),a1
        move    x:(r5+$59),b
        asl     #$c,b,b                 ; width << 12
        add     x1,b                    ; plus bit offset
        move    b1,y0
        extract y0,a,b
        move    b0,x0                   ; sign-extended delta

        move    y1,a
        add     x0,a
        and     #>$00ffff,a
        move    a1,y1
        move    y1,x:(r3)+

        ; cursor += delta width; width <=17, so at most one 24-bit carry.
        move    x1,a
        move    x:(r5+$59),x0
        add     x0,a
        cmp     #>$18,a
        blt     pknta_delta_cursor_ready
        sub     #>$18,a
        move    #>$1,n2
        lua     (r2+n2),r2
pknta_delta_cursor_ready:
        move    a1,x1
pknta_delta_done:
        nop

pknta_cache_hit:
        move    x:(r5+$5c),a
        move    a1,n1
        lua     (r4+$1),r1
        move    x:(r1+n1),a
        and     #>$00ffff,a
        rts

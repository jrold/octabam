; PERKY packed-envelope block decoder -- synthetic 7-bit executable canary.
;
; This exercises the SHIPPING memory/bitstream shape at the actual synthetic
; payload addresses. The real v1.2.1 curves may use another delta width; the
; generic geometry/oracle lives in noise_tone_envelope_cursor.py and the final
; renderer will substitute the measured width/constants at build time.
;
; Input / state (bd909_host probe ABI, X relative to r5):
;   +39  curve selector: 0 = env1 at Y:$0a50, nonzero = env2 at Y:$0cd6
;   +40  block id 0..127 (incremented after each call)
;   +41..+56  decoded 16-value u16 cache
;   +60  scratch absolute block bit position
;
; Each call decodes exactly one 16-sample block, writes its 16 u16 values to
; the cache, then mirrors them as positive 24-bit words to both X:0 channels.
; The executable gate calls this 128 times/curve and reconstructs all 2048
; entries.
;
; Synthetic packed block geometry:
;   anchor             16 bits unsigned
;   15 deltas x 7      105 bits signed
;   block              121 bits
;
; Bit field extraction uses the DSP56300 BFU. Two adjacent 24-bit table words
; are loaded into accumulator A as A1:A0; EXTRACTU/EXTRACT then select a field
; beginning at the cursor's 0..23 bit offset. Field width <= 16/7, so two words
; always suffice.
;
; floor(bitpos/24) = floor(floor(bitpos/3)/8). /3 uses the exact unsigned
; reciprocal already used by the packed-wave decoder:
;   floor(n/3) = (n * $aaab) >> 17 for this bounded nonnegative domain.

pk_env_unpack7_probe:
        ; bitpos = block_id * 121. Values are <= 15367, so low24 is complete.
        move    x:(r5+$40),x0
        move    #>$000079,y0
        mpyuu   x0,y0,a
        asr     #$1,a,a                 ; remove fractional multiply alignment
        move    a0,x0
        move    x0,x:(r5+$60)

        ; q3 = floor(bitpos / 3).
        move    #>$00aaab,y0
        mpyuu   x0,y0,a
        asr     #$1,a,a                 ; remove fractional multiply alignment
        asr     #$10,a,a
        move    a0,x1
        move    x1,b
        and     #>$00ffff,b
        lsr     b
        move    b1,x1                   ; q3

        ; word = floor(q3 / 8) = floor(bitpos / 24).
        move    x1,b
        lsr     #$3,b
        move    b1,n1                   ; word offset
        move    b1,x1                   ; keep word quotient for remainder

        ; bit = bitpos - 24*word.
        move    x1,b
        asl     #$3,b,b                 ; 8*word
        move    b1,y0
        move    y0,b
        asl     b                       ; 16*word
        add     y0,b                    ; 24*word
        move    b1,y0
        move    x:(r5+$60),a
        sub     y0,a
        move    a1,x1                   ; bit offset 0..23

        ; Choose the packed curve base, then add the word offset.
        move    x:(r5+$39),a
        tst     a
        beq     pke7_env1
        move    #>$000cd6,r1
        bra     pke7_base_ready
pke7_env1:
        move    #>$000a50,r1
pke7_base_ready:
        lua     (r1+n1),r2
        lua     (r5+$41),r3             ; cache write cursor

        ; ---- unsigned 16-bit anchor ---------------------------------------
        clr     a
        move    y:(r2),a0
        move    y:(r2+$1),a1
        move    #>$010000,b             ; width 16 << 12
        add     x1,b                    ; + bit offset
        move    b1,y0
        extractu y0,a,b
        move    b0,y1                   ; current u16 value
        move    y1,a
        and     #>$00ffff,a
        move    a1,y1
        move    y1,x:(r3)+

        ; cursor += 16.
        move    x1,a
        add     #>$10,a
        cmp     #>$18,a
        blt     pke7_anchor_cursor_ok
        sub     #>$18,a
        move    #>$1,n2
        lua     (r2+n2),r2
pke7_anchor_cursor_ok:
        move    a1,x1

        ; ---- fifteen signed 7-bit first differences -----------------------
        do      #$f,pke7_delta_done
        clr     a
        move    y:(r2),a0
        move    y:(r2+$1),a1
        move    #>$007000,b             ; width 7 << 12
        add     x1,b
        move    b1,y0
        extract  y0,a,b                 ; signed field -> sign-extended B
        move    b0,x0                   ; signed 24-bit delta

        move    y1,a
        add     x0,a
        and     #>$00ffff,a
        move    a1,y1
        move    y1,x:(r3)+

        ; cursor += 7.
        move    x1,a
        add     #>$7,a
        cmp     #>$18,a
        blt     pke7_delta_cursor_ok
        sub     #>$18,a
        move    #>$1,n2
        lua     (r2+n2),r2
pke7_delta_cursor_ok:
        move    a1,x1
pke7_delta_done:
        nop

        ; Mirror the cache to the stereo source buffer for a simple external
        ; oracle comparison. Envelope u16 values are kept positive 0..65535.
        lua     (r5+$41),r3
        move    #$0,r0
        do      #$10,pke7_output_done
        move    x:(r3)+,a
        and     #>$00ffff,a
        move    a1,x:(r0)+
        move    a1,x:(r0)+
pke7_output_done:
        nop

        ; Next invocation decodes the next block.
        move    x:(r5+$40),a
        add     #>$1,a
        move    a1,x:(r5+$40)
        rts

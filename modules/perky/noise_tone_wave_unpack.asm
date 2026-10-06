; PERKY packed u16 wave-stream decoder / executable probe.
;
; Shipping packing ABI (noise_tone_tables.py): three 16-bit samples occupy
; two 24-bit DSP words, LSB-first.  For a global sample index n:
;
;   q = floor(n/3), r = n%3, pair = TABLE + 2*q
;   r=0: sample = pair[0] & $ffff
;   r=1: sample = (pair[0] >> 16) | ((pair[1] & $ff) << 8)
;   r=2: sample = (pair[1] >> 8) & $ffff
;
; The probe decodes n7 consecutive samples beginning at X:(r5+$40), writes
; the current u16 bit-pattern to X:(r5+$41), increments the index, and writes
; the sign-extended sample to both channels at X:(r0)+.
;
; Shipping table base: Y:$07a5. The synthetic payload uses the identical
; layout: its four concatenated 256-sample waves occupy Y:$07a5..$0a4f.
;
; Division by 3 is exact for this range using
;   floor(n/3) = (n * $aaab) >> 17.
; MPYUU is right-justified; after >>16, one more LSR yields q.

pk_wave_unpack_probe:
        do      n7,pkw_block_done

        move    x:(r5+$40),x0           ; n, 0..1023
        move    #>$00aaab,y0
        mpyuu   x0,y0,a
        asr     #$1,a,a                 ; remove fractional multiply alignment
        asr     #$10,a,a
        move    a0,x1
        move    x1,b
        and     #>$00ffff,b
        lsr     b
        move    b1,x1                   ; q = floor(n/3)

        ; r = n - 3*q.
        move    x1,b
        asl     b
        add     x1,b
        move    b1,y0                   ; 3*q
        move    x:(r5+$40),a
        sub     y0,a
        move    a1,y1                   ; remainder 0..2

        ; pair pointer = Y:$07a5 + 2*q.
        move    x1,b
        asl     b
        move    b1,n1
        move    #>$0007a5,r1
        lua     (r1+n1),r2

        move    y1,a
        tst     a
        beq     pkw_r0
        cmp     #>$1,a
        beq     pkw_r1

pkw_r2:
        move    y:(r2+$1),a
        lsr     #$8,a
        and     #>$00ffff,a
        move    a1,x:(r5+$41)
        bra     pkw_got

pkw_r1:
        move    y:(r2),a
        lsr     #$10,a
        and     #>$0000ff,a
        move    a1,x1
        move    y:(r2+$1),b
        and     #>$0000ff,b
        asl     #$8,b,b
        add     x1,b
        and     #>$00ffff,b
        move    b1,x:(r5+$41)
        bra     pkw_got

pkw_r0:
        move    y:(r2),a
        and     #>$00ffff,a
        move    a1,x:(r5+$41)

pkw_got:
        ; Advance the global sample index for the next iteration.
        move    x:(r5+$40),a
        add     #>$1,a
        move    a1,x:(r5+$40)

        ; Sign-extend u16 to the 24-bit audio word and duplicate to stereo.
        move    x:(r5+$41),a
        and     #>$00ffff,a
        btst    #15,a1
        jcc     pkw_sample_ready
        sub     #>$010000,a
pkw_sample_ready:
        move    a1,x:(r0)+
        move    a1,x:(r0)+

pkw_block_done:
        nop
        rts

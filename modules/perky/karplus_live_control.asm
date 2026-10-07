; Exact live Karplus control application for the HW4 audition.
;
; Inputs:
;   r4 = prepared PK/Y1 record
;        +08/+09 TUNE   prepared u16 (0..4095, double-smoothed on ColdFire)
;        +0a/+0b DECAY  prepared u16
;        +0c/+0d EDGE   prepared u16
;        +0e/+0f TWANG  prepared u16
;        +10      MODE  physical panel 0/1/2
;   r6 = 32-word compact Karplus state (58-word track overlay is available)
;
; Proven control-owned compact words:
;   +$07 amplitude-envelope trigger/gate
;   +$0c amplitude-envelope attack
;   +$0d amplitude-envelope decay
;   +$12 resonant-filter coefficient
;   +$19 excitation target
;   +$1b/$1c 32-bit delay (high word is zero for the qualified 2K ring)
;
; The three 4096-entry functions are generated from the user's pinned v1.2.1
; image and packed 3*u16 -> 2*DSP-word, exactly like the existing PERKY wave
; payload.  Placeholders are replaced by build_hw4_audition_candidate.py.
;
; MODE is not part of the seven update() words: it is the wrapper-owned byte and
; is applied separately at compact +$02 with physical M1/M2/M3 -> firmware 1/0/2.

pk_karplus_apply_controls:
        ; TUNE -> exact ring delay table.
        move    x:(r4+$8),a
        and     #>$ff,a
        asl     #$8,a,a
        move    x:(r4+$9),b
        and     #>$ff,b
        move    b1,x0
        add     x0,a
        and     #>$0fff,a
        move    a1,x0
        move    #>@KARPLUS_TUNE_DELAY_BASE@,r1
        jsr     pk_karplus_lut_u16
        move    a1,x:(r6+$1b)
        clr     a
        move    a1,x:(r6+$1c)

        ; DECAY -> exact original envelope-rate table.
        move    x:(r4+$a),a
        and     #>$ff,a
        asl     #$8,a,a
        move    x:(r4+$b),b
        and     #>$ff,b
        move    b1,x0
        add     x0,a
        and     #>$0fff,a
        move    a1,x0
        move    #>@KARPLUS_DECAY_RATE_BASE@,r1
        jsr     pk_karplus_lut_u16
        move    a1,x:(r6+$d)

        ; The original attack path is independent of the four live knobs for
        ; this initialized Karplus configuration; update() rewrites the same
        ; authenticated value each time.
        move    #>@KARPLUS_ATTACK_RATE@,a
        move    a1,x:(r6+$c)

        ; Original gate law: prepared DECAY > object u16 at +$08.
        move    x:(r4+$a),a
        and     #>$ff,a
        asl     #$8,a,a
        move    x:(r4+$b),b
        and     #>$ff,b
        move    b1,x0
        add     x0,a
        and     #>$0fff,a
        cmp     #>@KARPLUS_GATE_THRESHOLD@,a
        ble     pkk_live_gate_zero
        move    #>$1,a
        bra     pkk_live_gate_ready
pkk_live_gate_zero:
        clr     a
pkk_live_gate_ready:
        move    a1,x:(r6+$7)

        ; EDGE -> exact original filter coefficient table.
        move    x:(r4+$c),a
        and     #>$ff,a
        asl     #$8,a,a
        move    x:(r4+$d),b
        and     #>$ff,b
        move    b1,x0
        add     x0,a
        and     #>$0fff,a
        move    a1,x0
        move    #>@KARPLUS_EDGE_COEFF_BASE@,r1
        jsr     pk_karplus_lut_u16
        move    a1,x:(r6+$12)

        ; TWANG -> original excitation target = prepared P2 >> 1.
        move    x:(r4+$e),a
        and     #>$ff,a
        asl     #$8,a,a
        move    x:(r4+$f),b
        and     #>$ff,b
        move    b1,x0
        add     x0,a
        and     #>$0fff,a
        lsr     a
        move    a1,x:(r6+$19)

        ; Physical panel M1/M2/M3 (0/1/2) -> firmware mode 1/0/2.
        move    x:(r4+$10),a
        and     #>$ff,a
        tst     a
        beq     pkk_live_mode0
        cmp     #>$1,a
        beq     pkk_live_mode1
        move    #>$2,a
        bra     pkk_live_mode_ready
pkk_live_mode0:
        move    #>$1,a
        bra     pkk_live_mode_ready
pkk_live_mode1:
        clr     a
pkk_live_mode_ready:
        move    a1,x:(r6+$2)
        rts

; Packed u16 random-access lookup.
;   x0 = index 0..4095
;   r1 = packed Y base
; returns a1 = exact u16
; clobbers a/b, x1, y0/y1, r2, n1
;
; q=floor(index/3) uses the same exact $aaab multiply as the shipping PERKY
; wave unpacker.  Two Y words hold three u16 values LSB-first.
pk_karplus_lut_u16:
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
        move    b1,y0                   ; 3*q
        move    x0,a
        sub     y0,a
        move    a1,y1                   ; remainder 0..2

        move    x1,b
        asl     b
        move    b1,n1
        lua     (r1+n1),r2              ; packed pair

        move    y1,a
        tst     a
        beq     pkk_lut_r0
        cmp     #>$1,a
        beq     pkk_lut_r1

pkk_lut_r2:
        move    y:(r2+$1),a
        lsr     #$8,a
        and     #>$00ffff,a
        rts

pkk_lut_r1:
        move    y:(r2),a
        lsr     #$10,a
        and     #>$0000ff,a
        move    a1,x1
        move    y:(r2+$1),b
        and     #>$0000ff,b
        asl     #$8,b,b
        add     x1,b
        move    b1,a
        and     #>$00ffff,a
        rts

pkk_lut_r0:
        move    y:(r2),a
        and     #>$00ffff,a
        rts

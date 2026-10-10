; ---------------------------------------------------------------------------
; TESTGEN -- a measurement source: the track's audio is replaced by a known
; signal (modules/testgen/README.md, float reference testgen_ref.py, which
; holds every law below as the module computes it).
;
; Insert contract: frames in place at x:(r0)/x:(r0+n0), knobs from r6,
; state in this instance's r7 block. No bus, no buffers, no shared window.
;
; ---- SINE ---------------------------------------------------------------------
;   p  += inc                      24-bit phase, a cycle is 2^24 (wraps by
;                                  storing a1 unlimited)
;   r   = wrap(p - 1/2)            sin(pi p) = cos(pi r) = sin(pi (1/2 - |r|))
;   u   = 2 (1/2 - |r|)            in [-1, 1], +1 held at $7fffff
;   s   = u (c1 + w (c3 + w (c5 + w (c7 + w c9)))),  w = u^2
;         sin(pi u / 2) on Chebyshev nodes, max error 3.4e-9 (-169 dB);
;         the coefficients are stored halved and the product doubled
; ---- SWEEP: the same sine, its increment growing by r each sample --------------
;   inc is 48 bits ($03 integer, $04 fraction); p += inc_hi;
;   inc += (inc_hi * d) >> 12, d = (r - 1) * 2^35 from SWD: 20.0007 Hz to
;   20 kHz in N = (t + 1) s, then 1 s of silence with p and inc held at
;   their start, repeating.
; ---- WHITE: x' = 0x5DEECE66D x + 11 mod 2^46, the sample its top 23 bits -------
;   (drand48's multiplier; a period of 2^46 samples, 50 years). x is held as two
;   23-bit halves, so every product is of non-negative operands. L and R each
;   have their own generator, R's started 0x3243f6a8885 steps ahead of L's.
; ---- PINK: Kellet's three poles on WHITE, scaled by 0.11 (-14.4 dBFS RMS) ------
;   one filter per channel.
; With CHAN L+R the noise channels are independent; with MONO, L-R, L or R
; both channels take L's generator (R = L, R = -L, or one side).
; ---- IMPULSE: one full-scale sample every (t + 1) / 4 s, from sample 0 ---------
; ---- NEEDLE: one full-scale sample every P samples, from sample 0, ---------------
;   P = round(2^24 / inc), the whole period nearest FREQ and FINE: a strictly
;   periodic train at FS / P (1 kHz is P = 44, 1002.27 Hz), its spectrum lines
;   at FS / P and its multiples
; ---- DC: full scale on every sample (IMPULSE with a period of one) ---------------
;
; Every signal is full scale, then L = s * gL, R = s * gR, from LEVL and CHAN
; per block. A change of MODE, FREQ or LEN restarts every generator, so a
; capture lines up with the reference from the change on.
;
; ---- the P table (the manifest's ptable, 192 words) -------------------------
;   +0   LEVEL  10^(-(127 - k)/40), k = 0..127 (0.5 dB steps, 127 = $7fffff)
;   +128 FINC   the phase increment of FREQ step k, k = 0..31 (the ISO
;               third-octave centres, and A 440 between 400 and 500)
;   +160 SWD    the sweep's growth, (r - 1) * 2^35, LEN step t = LEN >> 3
; (the sweep's length, (t + 1) 44100 samples, is computed)
; The module (396 words) and its table fill PLATE REV's 594 words but for 6.
;
; ---- r7 slots ---------------------------------------------------------------
; persistent, set at init and on a restart:
;   $00 phase   $03 sweep inc (integer)   $04 sweep inc (fraction)
;   $05 sweep sample count   $0a impulse countdown
;   $20.. L's noise: $20 x high, $21 x low, $22 $23 $24 pink's poles
;   $28.. R's noise, the same
;   $30 the FX2 flag, set at init (non-zero: an FX2 slot, a dry pass)
; (a restart zeroes $00..$2f, then sets the sweep's start and the seeds)
; persistent, the knobs last block (0 after a restart):
;   $01 FREQ index   $02 MODE   $0b LEN step
; per block (FINE is applied here, without a restart, so tuning by ear is smooth):
;   $10 gL   $11 gR   $12 the sine's inc   $13 the sweep's N   $14 d
;   $15 the impulse period less one   $16 N + the gap
;   $17 non-zero: independent noise channels (CHAN L+R)   $18 non-zero: PINK
;
; Every multiply is x0,x0, x1,x0 or x0,y1 (the signed encodings). The sine
; rounds (mpyr, macr, rnd): truncation left the peak 5 LSB short of full
; scale. Every Tcc reads the compare directly above it with only moves
; between. One branch per block picks the mode's loop; the loops are
; branch-free.
; ---------------------------------------------------------------------------

init:
; FX1 ONLY (Spectrum's idiom, modules/spectrum/spectrum.asm): X:0x213 points
; at this instance's entry in the base table, valid here and nowhere else.
; FX1 slots are below 0x4000, FX2 slots at or above it. An FX2 instance runs
; as a dry pass: proc returns before it touches a frame, so a part that names
; this id on FX2 (a 0.1 project) costs its core nothing and passes audio.
        move    x:>$213,r4
        move    x:(r4),a
        and     #>$ffc000,a             ; non-zero: the base is 0x4000 or above
        move    a1,x:(r7+$30)           ; the FX2 flag, above the restart's clear
        move    #>$ffffff,m5
        bra     tg_rst                  ; every slot; the first block restarts
                                        ; again (its knob memories read 0), to
                                        ; the same state

proc:
        move    x:(r7+$30),a            ; an FX2 slot: dry, nothing written
        tst     a
        bne     tg_xnse
; ---- per block: MODE (slot 6), FREQ, LEN; any change restarts -----------------
        move    #>$ffffff,m5
        move    #>$ffffff,m4            ; the tables are read at (r4+n4)
        move    #0,y0
        clr     b                       ; the change flag
        move    x:(r6+$c),a             ; MODE, slot 6: the value in bits 22..16
        and     #>$7f0000,a
        asr     #$10,a,a
        move    #>$000006,x0
        cmp     x0,a
        tgt     y0,a                    ; an invalid saved byte -> SINE
        move    a1,x1                   ; mode
        move    x:(r7+$02),a
        cmp     x1,a
        tne     x0,b                    ; changed (x0 is non-zero)
        move    x:(r6+$1),a             ; FREQ: the step in bits 22..16
        and     #>$7f0000,a
        asr     #$10,a,a
        move    #>$00001f,x0            ; 31, the last step (20 kHz)
        cmp     x0,a
        tgt     x0,a
        move    a1,y1                   ; FREQ
        move    x:(r7+$01),a
        cmp     y1,a
        tne     x0,b
        move    x:(r6+$2),a             ; LEN: the step t in bits 22..19
        and     #>$780000,a
        asr     #$13,a,a
        move    a1,y0                   ; LEN
        move    x:(r7+$0b),a
        cmp     y0,a
        tne     x0,b
        tst     b
        beq     tg_keep
        bsr     tg_rst                  ; keeps x1, y1, y0
tg_keep:
        move    x1,x:(r7+$02)
        move    y1,x:(r7+$01)
        move    y0,x:(r7+$0b)
        clr     b                       ; PINK?
        move    #>$000002,x0
        move    x1,a
        cmp     x0,a
        teq     x0,b
        move    b,x:(r7+$18)
; ---- the tables -------------------------------------------------------------------
        move    #>$fab1e0,r4            ; the table base, read at (r4+n4)
        move    x:(r7+$01),a
        add     #>$000080,a             ; + 128, FINC
        move    a1,n4
        move    p:(r4+n4),x1            ; FINC[k]
; FINE: inc = FINC[k] * 2^(y/3), y = value/128 - 1/2: +-200 cents, 3.125 a step.
; m/2 = 1/2 + y (a/2 + y (a^2/4 + y (a^3/12 + y a^4/48))), a = ln 2 / 3:
; within 1.9e-7 of 2^(y/3) (0.0002 Hz at 1 kHz); FINE 0 gives m/2 = 1/2
; exactly, so the tone is FINC[k]'s, bit for bit.
        move    x:(r6+$3),a
        and     #>$7fffff,a
        sub     #>$400000,a
        move    a,y1                    ; y
        move    #>$0001f2,x0            ; a^4/48
        move    #>$0021ae,a             ; a^3/12
        mac     x0,y1,a
        move    a,x0
        move    #>$01b552,a             ; a^2/4
        mac     x0,y1,a
        move    a,x0
        move    #>$0ec982,a             ; a/2
        mac     x0,y1,a
        move    a,x0
        move    #>$400000,a             ; 1/2
        mac     x0,y1,a
        move    a,x0                    ; m/2
        mpy     x1,x0,a
        asl     #$1,a,a                 ; FINC[k] m
        rnd     a
        move    #>$74198b,x0            ; 20 kHz (FINC[31]): FINE does not go above it (near
        cmp     x0,a                    ; 22.05 kHz a sine is a few samples a cycle)
        tgt     x0,a
        move    a,x:(r7+$12)            ; the sine's inc
        move    x:(r7+$0b),a
        add     #>$0000a0,a             ; + 160, SWD
        move    a1,n4
        move    p:(r4+n4),x0
        move    x0,x:(r7+$14)           ; d
        move    x:(r7+$0b),a            ; N = (t + 1) 44100
        add     #1,a
        move    a1,x0
        move    #>$00ac44,y1
        mpy     x0,y1,a                 ; 2 N, an integer in a1:a0
        asr     a
        move    a0,a
        move    a,x:(r7+$13)            ; N
        add     #>$00ac44,a             ; + 44100, the gap
        move    a,x:(r7+$16)
        move    x:(r7+$13),a            ; IMPULSE's period, N/4 = (t + 1) 11025,
        asr     #$2,a,a                 ; less one
        sub     #1,a
        move    a,y0
; NEEDLE: a period of P = round(2^24 / inc) samples, the whole period nearest
; FREQ and FINE: (2^25 + inc) / (2 inc), a 48-by-24 division. Undoubled, the
; dividend a1:a0 = 2^25 + inc gives a0 = floor(a / (2 inc)).
        move    x:(r7+$12),x0           ; inc, 0 < inc < 2^23
        clr     a
        move    x0,a0
        move    #$2,a1                  ; a short immediate to a1 is an integer; a2 stays 0
        andi    #$fe,ccr               ; C = 0, the first quotient bit's carry in
        rep     #24
        div     x0,a
        move    a0,b                    ; P
        sub     #1,b
        move    x:(r7+$02),a            ; mode
        cmp     #5,a
        tne     y0,b                    ; not NEEDLE: IMPULSE's
        move    #0,y0
        cmp     #6,a
        teq     y0,b                    ; DC: a period of one, every sample
        move    b,x:(r7+$15)            ; the period less one
        move    x:(r6+$0),a             ; LEVL: value/128 in bits 22..16
        and     #>$7f0000,a
        asr     #$10,a,a
        move    a1,n4
        move    p:(r4+n4),b             ; g
        move    b,y1
; ---- CHAN (slot 8): L+R, L, R, L and inverted R, MONO -------------------------
        move    #0,y0
        neg     b
        move    b,x1                    ; -g
        move    x:(r6+$d),a
        and     #>$7f0000,a
        asr     #$10,a,a                ; chan
        move    y1,b                    ; gL = g
        cmp     #2,a
        teq     y0,b                    ; R only -> 0
        move    b,x:(r7+$10)
        move    y1,b                    ; gR = g
        cmp     #1,a
        teq     y0,b                    ; L only -> 0
        cmp     #3,a
        teq     x1,b                    ; L and inverted R -> -g
        move    b,x:(r7+$11)
        clr     b                       ; independent noise channels: L+R only
        move    #>$000001,x0
        tst     a
        teq     x0,b
        move    b,x:(r7+$17)
; ---- the mode's loop ---------------------------------------------------------------
        move    x:(r7+$02),a            ; mode
        tst     a
        beq     tg_sin
        cmp     #1,a
        beq     tg_swp
        cmp     #3,a
        bgt     tg_imp                  ; IMPULSE, NEEDLE, DC
; ---- PINK and WHITE: one generator per channel ---------------------------------
        lua     (r7+$20),r5             ; L's block; R's is 8 on
        move    #>$000008,n5
        do      n7,>tg_xnse
        bsr     tg_gen
        move    x0,y0                   ; L
        move    (r5)+n5
        bsr     tg_gen
        move    (r5)-n5
        move    x0,b                    ; R, its own
        move    x:(r7+$17),a
        tst     a
        teq     y0,b                    ; not L+R: R takes L's sample
        move    y0,x0
        move    b,y0
        move    x:(r7+$10),y1           ; gL
        mpyr    x0,y1,a
        move    a,x:(r0)+
        move    y0,x0
        move    x:(r7+$11),y1           ; gR
        mpyr    x0,y1,a
        move    a,x:(r0)+
tg_xnse:
        nop
        rts

; ---- SINE ---------------------------------------------------------------------------
tg_sin:
        do      n7,>tg_xsin
        move    x:(r7+$00),b            ; p
        move    x:(r7+$12),x0
        move    b,a
        add     x0,a
        move    a1,x:(r7+$00)           ; p + inc, wrapped (a1 is not limited)
        bsr     tg_core                 ; x0 = sin(pi b)
        move    x:(r7+$10),y1           ; gL
        mpyr    x0,y1,a
        move    a,x:(r0)+
        move    x:(r7+$11),y1           ; gR
        mpyr    x0,y1,a
        move    a,x:(r0)+
tg_xsin:
        nop
        rts

; ---- SWEEP --------------------------------------------------------------------------
tg_swp:
        do      n7,>tg_xswp
        move    x:(r7+$00),b            ; p
        bsr     tg_core
        move    x0,y0                   ; s
; p += inc_hi; inc += (inc_hi * d) >> 12
        move    x:(r7+$03),x0           ; inc_hi
        move    x:(r7+$00),a
        add     x0,a
        move    a1,x:(r7+$00)
        move    x:(r7+$14),y1           ; d
        mpy     x0,y1,a                 ; 2 inc_hi d, in units of 2^-47
        asr     #$c,a,a
        move    x:(r7+$03),b
        move    x:(r7+$04),b0
        add     a,b
        move    b1,x:(r7+$03)
        move    b0,x:(r7+$04)
; past the sweep (count >= N): silence, and p and inc held at their start
        move    #0,x0
        move    #>$001db9,x1            ; 7609
        move    x:(r7+$13),y1           ; N
        move    x:(r7+$05),a            ; count
        move    y0,b
        cmp     y1,a
        tge     x0,b                    ; s -> 0
        move    b,y0
        move    x:(r7+$00),b
        cmp     y1,a
        tge     x0,b                    ; p -> 0
        move    b1,x:(r7+$00)
        move    x:(r7+$03),b
        move    x:(r7+$04),b0
        cmp     y1,a
        tge     x1,b                    ; inc -> 7609.0 (b0 cleared)
        move    b1,x:(r7+$03)
        move    b0,x:(r7+$04)
        add     #1,a                    ; count + 1, back to 0 after the gap
        move    x:(r7+$16),y1
        cmp     y1,a
        teq     x0,a
        move    a1,x:(r7+$05)
        move    y0,x0
        move    x:(r7+$10),y1           ; gL
        mpyr    x0,y1,a
        move    a,x:(r0)+
        move    x:(r7+$11),y1           ; gR
        mpyr    x0,y1,a
        move    a,x:(r0)+
tg_xswp:
        nop
        rts

; ---- IMPULSE, NEEDLE and DC: one full-scale sample every period ($15 + 1) ----------
tg_imp:
        do      n7,>tg_ximp
        clr     b
        move    #>$7fffff,x0
        move    x:(r7+$0a),a            ; countdown
        tst     a
        teq     x0,b                    ; 0 -> full scale
        move    b,y0                    ; s
        sub     #1,a
        move    x:(r7+$15),x0           ; the period less one
        tmi     x0,a
        move    a1,x:(r7+$0a)
        move    y0,x0
        move    x:(r7+$10),y1           ; gL
        mpyr    x0,y1,a
        move    a,x:(r0)+
        move    x:(r7+$11),y1           ; gR
        mpyr    x0,y1,a
        move    a,x:(r0)+
tg_ximp:
        nop
        rts

; ---- the sine core: x0 = sin(pi b), b the phase (a cycle is 2^24) ------------------
; Uses a, b, x0, x1, y1.
tg_core:
        sub     #>$400000,b             ; the quarter wave: u = 2 (1/2 - |wrap(p - 1/2)|)
        move    b1,x0                   ; wrapped
        move    x0,b
        abs     b
        neg     b
        add     #>$400000,b
        asl     #$1,b,b
        move    b,y1                    ; u (+1 limited to $7fffff)
        move    y1,x0
        mpyr    x0,x0,a
        move    a,x1                    ; w = u^2
        move    #>$000279,x0            ;  c9/2 =  0.000150817160/2
        move    #>$ffb373,a             ;  c7/2 = -0.00467222026/2
        macr    x1,x0,a
        move    a,x0
        move    #>$05199e,a             ;  c5/2 =  0.0796884748/2
        macr    x1,x0,a
        move    a,x0
        move    #>$d6a889,a             ;  c3/2 = -0.645963358/2
        macr    x1,x0,a
        move    a,x0
        move    #>$6487ed,a             ;  c1/2 =  1.57079629/2
        macr    x1,x0,a
        move    a,x0                    ; P/2
        mpy     x0,y1,a                 ; s/2 = u P/2, 48 bits
        asl     #$1,a,a                 ; s
        rnd     a
        move    a,x0                    ; (limited)
        rts

; ---- one noise sample from the block at r5: x0 = WHITE, or PINK if $18 -------------
; Straight-line: the pink filter runs in WHITE too, and a Tcc picks the sample.
; x' = a x + c mod 2^46, x = xh 2^23 + xl, a = ah 2^23 + al:
;   a x + c = (al xl + c) + 2^23 (ah xl + al xh)  mod 2^46
; Fractional products are doubled: a1:a0 = 2 (al xl + c) leaves its top part
; (>> 23) in a1 and twice its low 23 bits in a0.
; Uses a, b, x0, x1, y1.
tg_gen:
        move    x:(r5+$1),x0            ; xl
        move    #>$000bbd,y1            ; ah
        mpy     x0,y1,b                 ; 2 ah xl
        move    #>$6ce66d,y1            ; al
        clr     a
        move    #>$000016,a0            ; 2c
        mac     x0,y1,a                 ; 2 (al xl + c)
        move    x:(r5),x0               ; xh
        mac     x0,y1,b                 ; 2 (ah xl + al xh)
        asr     #$1,b,b                 ; its low word, mod 2^24
        move    b0,x0
        add     x0,a                    ; the high half, before mod 2^23
        move    a0,b
        lsr     #$1,b                   ; xl'
        move    b1,x:(r5+$1)
        and     #>$7fffff,a             ; xh'
        move    a1,x:(r5)
        lsl     #$1,a                   ; the sample: 2 xh' - 2^23
        eor     #>$800000,a
        move    a1,x1                   ; w (a1 is not limited)
        move    #>$7fb2ff,x0            ; 0.99765
        move    x:(r5+$2),y1
        mpy     x0,y1,a
        move    #>$016502,x0            ; 0.0990460 * 0.11
        macr    x1,x0,a
        move    a,x:(r5+$2)
        move    a,b                     ; the sum of the poles
        move    #>$7b4396,x0            ; 0.963
        move    x:(r5+$3),y1
        mpy     x0,y1,a
        move    #>$042cca,x0            ; 0.2965164 * 0.11
        macr    x1,x0,a
        move    a,x:(r5+$3)
        add     a,b
        move    #>$48f5c3,x0            ; 0.57
        move    x:(r5+$4),y1
        mpy     x0,y1,a
        move    #>$0ed268,x0            ; 1.0526913 * 0.11
        macr    x1,x0,a
        move    a,x:(r5+$4)
        add     b,a
        move    #>$029a1c,x0            ; 0.1848 * 0.11
        macr    x1,x0,a
        move    a,x0                    ; pink (limited)
        move    x1,b                    ; white
        move    x:(r7+$18),a
        tst     a
        tne     x0,b                    ; PINK -> the filtered sample
        move    b,x0
        rts

; ---- restart every generator: zero $00..$2f, then the sweep's start and the seeds --
; Uses a, x0, r5.
tg_rst:
        move    r7,r5
        clr     a
        rep     #$30
        move    a,x:(r5)+
        move    #>$001db9,x0            ; 7609: the sweep starts at 20.0007 Hz
        move    x0,x:(r7+$03)
        move    #>$2a5f31,x0            ; L's seed, x = $2a5f31 2^23
        move    x0,x:(r7+$20)
        move    #>$343f62,x0            ; R's: L's advanced 0x3243f6a8885 steps
        move    x0,x:(r7+$28)
        move    #>$66953f,x0
        move    x0,x:(r7+$29)
        rts

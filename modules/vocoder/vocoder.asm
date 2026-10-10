; ---------------------------------------------------------------------------
; VOCODER -- a ten-band channel vocoder after the Roland VP-330
; (modules/vocoder/DESIGN.md; float reference vocoder_ref.py, which holds the
; law in this form).
;
; Insert contract: frames in place at x:(r0)/x:(r0+n0), knobs from r6,
; state in this instance's r7 block. No bus, no buffers, no shared window.
; Uses r4, r5 (m5 linear); r1 is left alone.
; Runs on FX2 of tracks 2, 3, 6 and 7 only (r7 0x6500 or 0x6800): at most two
; per DSP core, which the MKII carries; a dry pass on every other slot.
;
; ---- the law ------------------------------------------------------------------
;   m = (L + R)/2 (INT) or L (EXT);  c = 0.3 saw(NOTE) + 0.2 saw(NOTE + 12) (INT)
;       or R/2 (EXT); the two sawtooths share one 24-bit phase (the 4' is the
;       phase doubled), polyBLEP, branch-free
;   each band k: two Chamberlin band-pass sections (f1, then f2, Q 7), each
;       input scaled by q = 1/7 so a section peaks at its input's level; the
;       same pair on m and on c
;   v = (W_k/2) |band_k(m)|;  e = max(v, e (1 - 0.00227)): a peak detector,
;       instant attack and 10 ms release, as the VP-330's diodes; e in 48 bits
;       (in 24 it stuck above zero in a pause)
;   out = LEVL limit(2^8 sum_k e_k band_k(c) + 4 CONS hp6(m/2) + DRY m)
;   hp6: three Chamberlin high-pass sections at 4 kHz (Q 0.518, 0.707, 1.932),
;       q/2 stored and applied twice (q is above 1)
;
; ---- the P table (the manifest's ptable, 172 words) -------------------------
;   +0   BAND[10] x {f1, f2, W/2, f1, f2}: in the order the band loop reads them
;   +50  NINC[61] the phase increment of NOTE step k (C1 + k), a cycle 2^24
;   +111 NIDT[61] 1/(du 2^11), du = NINC / 2^24
;
; ---- r7 slots ---------------------------------------------------------------
; per sample: $00 q m   $01 q c   $02 the band sum   $04 m
;             $17 this band's envelope
; persistent: $05 the carrier phase   $06..$0b hp6: three sections of (low, band)
;             $1b..$7e ten band blocks of 10, band k at $1b + 10k:
;               +0 +1 m section 1 (low, band)   +2 +3 m section 2
;               +4 +5 the envelope (high, low)  +6 +7 c section 1   +8 +9 c section 2
; per block:  $0c NINC   $0d NIDT   $0e CONS   $0f DRY   $10 LEVL   $11 MODE
;             $12 the table base   $13 NIDT/2   $14 0.00227   $16 q
;             $18 $19 $1a hp6's q/2
; Scratch sits low so its moves take one word; the band blocks are walked
; with (r5)+, so the section arithmetic carries its loads and stores as
; parallel moves.
;
; Every multiply is one of the valid signed pairs (x0,y1  y0,x0  x1,x0  y1,x1
; x1,y0  x0,x0). Every Tcc reads the arithmetic directly above it, with only
; moves between.
; ---------------------------------------------------------------------------

init:
        move    #>$ffffff,m5
        move    r7,r5
        clr     a
        rep     #$7f                    ; every slot, $00..$7e
        move    a,x:(r5)+
        rts

proc:
; ---- TWO PER CORE, BUILT IN: FX2 positions 1 and 2 only --------------------------
; Three VOCODERs on one DSP core overran Ignorato's MKII (a glitch, then a stall
; until a reboot; two ran safely), so it runs at two positions per core and is an
; exact dry pass everywhere else. Not position 0 (T1, T5). Measured: on Ignorato's
; MKII VOCODER on T1 put left-only click bursts into the main out at one phase of
; the pattern, worst at trigs; on T2 and T3 it ran clean (5 Oct 2026). Inferred:
; at position 0 the ColdFire's pull of the previous frame's read-back must finish
; before T1's FX2 output is copied over it (docs/contributing/FAILURE_MODES.md,
; "Junk on main R ... T1 with BusDelay"; that was main R, 16-24 samples). T5 is
; excluded by analogy, unmeasured.
; So it runs at r7 = 0x6500 and 0x6800 (T2, T3 on core 1; T6, T7 on core 0). r7 per
; slot measured under the port: modules/send/README.md, "An FX1 slot is not a client".
        move    r7,a
        move    #>$6500,x0
        cmp     x0,a
        beq     vc_run
        move    #>$6800,x0
        cmp     x0,a
        bne     vc_end                  ; not T2/T3/T6/T7's FX2: dry, nothing written
vc_run:
; ---- per block: the knobs ---------------------------------------------------------
        move    #>$ffffff,m5
        move    #>$ffffff,m4            ; the (r4)+ table walk: linear, whatever ran before
        move    #>$fab1e0,r4            ; the table base
        move    r4,x:(r7+$12)
        move    x:(r6+$0),a             ; NOTE: the step in bits 16 and up
        and     #>$7f0000,a
        asr     #$10,a,a
        move    #>$00003c,x0            ; 60, C6
        cmp     x0,a
        tgt     x0,a
        add     #>$000032,a             ; + 50, NINC
        move    a1,n5
        move    r4,r5
        move    (r5)+n5
        move    p:(r5),x0
        move    x0,x:(r7+$c)
        move    #>$00003d,n5            ; + 61, NIDT
        move    (r5)+n5
        move    p:(r5),a
        move    a,x:(r7+$d)
        asr     #$1,a,a
        move    a,x:(r7+$13)
        move    x:(r6+$1),a             ; CONS: value/128
        and     #>$7f0000,a
        move    a,x:(r7+$e)
        move    x:(r6+$2),a             ; DRY: value/128
        and     #>$7f0000,a
        move    a,x:(r7+$f)
        move    x:(r6+$3),a             ; LEVL: value/128, 127 pinned to full
        and     #>$7f0000,a
        move    #>$7f0000,x0
        cmp     x0,a
        move    #>$7fffff,x0
        teq     x0,a
        move    a,x:(r7+$10)
        move    x:(r6+$c),a             ; MODE, slot 6: 0 INT, 1 EXT
        and     #>$7f0000,a
        asr     #$10,a,a
        move    a1,x:(r7+$11)
        move    #>$004a38,x0            ; 0.00227: the 10 ms release
        move    x0,x:(r7+$14)
        move    #>$124925,x0            ; q = 1/7
        move    x0,x:(r7+$16)
        move    #>$7ba5c9,x0            ; hp6's q/2: Q 0.518, 0.707, 1.932
        move    x0,x:(r7+$18)
        move    #>$5a82b2,x0
        move    x0,x:(r7+$19)
        move    #>$2120c5,x0
        move    x0,x:(r7+$1a)
        move    #$1,n0

        do      n7,>vc_end
; ---- the modulator: (L + R)/2, or L with MODE EXT -----------------------------------
        move    x:(r0),a                ; L
        move    x:(r0+n0),b             ; R
        add     a,b       a,x1          ; L + R;  x1 = L
        asr     b                       ; (L + R)/2
        move    x:(r7+$11),a
        tst     a
        tne     x1,b                    ; EXT -> L
        move    b,x:(r7+$4)             ; m
        move    b,y0
        move    x:(r7+$16),x1           ; q
        mpyr    x1,y0,a
        move    a,x:(r7)                ; q m
; ---- the carrier: two polyBLEP sawtooths on one phase, or R/2 ----------------------
        move    #>$001000,y0            ; 2^-11, the cap, for both calls
        move    x:(r7+$5),b             ; s, the 8' phase
        move    x:(r7+$d),y1            ; 1/(du 2^11)
        bsr     vc_blep                 ; x0 = the 8' sawtooth
        move    #>$266666,y1            ; 0.3
        mpy     x0,y1,a
        move    a,x:(r7+$1)             ; (the 8' part, for a moment)
        move    x:(r7+$5),b
        asl     #$1,b,b
        move    b1,x0                   ; the 4' phase: doubled, wrapped
        move    x0,b
        move    x:(r7+$13),y1           ; du is twice as large: 1/(du 2^11) halved
        bsr     vc_blep                 ; x0 = the 4' sawtooth
        move    #>$19999a,y1            ; 0.2
        move    x:(r7+$1),a
        mac     x0,y1,a                 ; 0.3 saw8 + 0.2 saw4
        move    x:(r0+n0),b             ; R
        asr     #$1,b,b
        move    b,x1                    ; R/2
        move    x:(r7+$11),b
        tst     b
        tne     x1,a                    ; EXT -> R/2
        move    a,y0
        move    x:(r7+$16),x1           ; q
        mpyr    x1,y0,a
        move    a,x:(r7+$1)             ; q c
        move    x:(r7+$5),a             ; the phase advances
        move    x:(r7+$c),x0
        add     x0,a
        move    a1,x:(r7+$5)            ; (a1 is not limited: it wraps)
; ---- the ten bands ---------------------------------------------------------------------
        clr     a
        move    a,x:(r7+$2)
        move    x:(r7+$12),r4           ; BAND
        move    r7,b
        add     #27,b                   ; $1b, band 0
        move    b1,r5
        do      #10,>vc_bend
; m, section 1 (f1); x1 = q in every section
        move    p:(r4)+,x0              ; f1
        move    x:(r5)+,a               ; low
        move    x:(r5)-,y1              ; band
        macr    x0,y1,a   x:(r7),b      ; low += f band;  b = q m
        sub     a,b       a,x:(r5)+     ; q m - low
        macr    -y1,x1,b                ; hp = q m - low - q band
        tfr     y1,a      b,y0
        macr    y0,x0,a                 ; band += f hp
        move    a,y0
        mpy     x1,y0,b   a,x:(r5)+     ; section 2's input, q band
; m, section 2 (f2)
        move    p:(r4)+,x0              ; f2
        move    x:(r5)+,a
        move    x:(r5)-,y1
        macr    x0,y1,a
        sub     a,b       a,x:(r5)+
        macr    -y1,x1,b
        tfr     y1,a      b,y0
        macr    y0,x0,a                 ; the m band
        abs     a         a,x:(r5)+     ; |m band| (the signed band is stored)
; the envelope: e = max((W/2) |m band|, e (1 - 0.00227)), 48 bits
        move    a,y0
        move    p:(r4)+,x0              ; W/2
        mpy     y0,x0,b                 ; v
        move    x:(r5)+,a               ; e, high word
        move    x:(r5)-,a0              ; e, low word
        move    a1,x0
        move    x:(r7+$14),y1           ; 0.00227
        mac     -x0,y1,a                ; e (1 - 0.00227)
        cmp     b,a
        tlt     b,a                     ; below v -> v (the instant attack)
        move    a1,x:(r5)+
        move    a0,x:(r5)+
        move    a,x:(r7+$17)            ; e, for the VCA
; c, section 1 (f1)
        move    p:(r4)+,x0              ; f1
        move    x:(r5)+,a
        move    x:(r5)-,y1
        move    x:(r7+$1),b             ; q c
        macr    x0,y1,a
        sub     a,b       a,x:(r5)+
        macr    -y1,x1,b
        tfr     y1,a      b,y0
        macr    y0,x0,a
        move    a,y0
        mpy     x1,y0,b   a,x:(r5)+
; c, section 2 (f2)
        move    p:(r4)+,x0              ; f2
        move    x:(r5)+,a
        move    x:(r5)-,y1
        macr    x0,y1,a
        sub     a,b       a,x:(r5)+
        macr    -y1,x1,b
        tfr     y1,a      b,y0
        macr    y0,x0,a                 ; the c band
        move    a,x:(r5)+               ; (r5 -> the next band)
; the VCA: the band sum += e (c band), rounded to 24 bits (about 62 dB under
; the vocoded signal, README and DESIGN; two moves a band fewer than 48)
        move    a,y0
        move    x:(r7+$17),x0           ; e
        move    x:(r7+$2),b
        macr    y0,x0,b
        move    b,x:(r7+$2)
vc_bend:
; ---- hp6: m/2 through three high-pass sections at 4 kHz, states walked by r5 -------------
        move    x:(r7+$4),b
        asr     #$1,b,b                 ; m/2
        move    #>$47f6e6,x0            ; f, 4 kHz
        move    r7,a
        add     #6,a
        move    a1,r5                   ; $06
        move    x:(r5)+,a               ; section 1: low
        move    x:(r5)-,y1              ; band
        macr    x0,y1,a
        sub     a,b       a,x:(r5)+
        move    x:(r7+$18),x1           ; q/2, Q 0.518
        macr    -y1,x1,b
        macr    -y1,x1,b
        tfr     y1,a      b,y0
        macr    y0,x0,a
        move    a,x:(r5)+
        move    x:(r5)+,a               ; section 2
        move    x:(r5)-,y1
        macr    x0,y1,a
        sub     a,b       a,x:(r5)+
        move    x:(r7+$19),x1           ; q/2, Q 0.707
        macr    -y1,x1,b
        macr    -y1,x1,b
        tfr     y1,a      b,y0
        macr    y0,x0,a
        move    a,x:(r5)+
        move    x:(r5)+,a               ; section 3
        move    x:(r5)-,y1
        macr    x0,y1,a
        sub     a,b       a,x:(r5)+
        move    x:(r7+$1a),x1           ; q/2, Q 1.932
        macr    -y1,x1,b
        macr    -y1,x1,b
        tfr     y1,a      b,y0
        macr    y0,x0,a
        move    a,x:(r5)+
; ---- out = LEVL limit(2^8 sum + 4 CONS hp + DRY m) -------------------------------------
        move    x:(r7+$e),x0            ; CONS
        mpy     y0,x0,b                 ; hp CONS
        asl     #$2,b,b
        move    x:(r7+$4),x0            ; m
        move    x:(r7+$f),y1            ; DRY
        mac     x0,y1,b
        move    x:(r7+$2),a
        asl     #$8,a,a                 ; 2^8, the make-up gain
        add     a,b
        move    b,x0                    ; (limited)
        move    x:(r7+$10),y1           ; LEVL
        mpyr    x0,y1,a
        move    a,x:(r0)+
        move    a,x:(r0)+
vc_end:
        nop
        rts

; ---- x0 = the polyBLEP sawtooth at phase b; y1 = 1/(du 2^11), y0 = 2^-11; uses a, b, x0, x1 --
; corr = (1 - min(u/du, 1))^2 - (1 - min((1 - u)/du, 1))^2, u = s/2 + 1/2
vc_blep:
        move    b,x1                    ; s
        asr     #$1,b,b
        add     #>$400000,b             ; u
        move    #>$7fffff,a
        sub     b,a                     ; 1 - u
        move    a,x0
        mpy     x0,y1,a                 ; (1 - u)/(du 2^11)
        cmp     y0,a
        tgt     y0,a                    ; min(., 2^-11)
        asl     #$b,a,a
        move    a,x0                    ; t_b (1.0 limited)
        move    #>$7fffff,a
        sub     x0,a
        move    a,x0
        mpyr    x0,x0,a                 ; (1 - t_b)^2
        move    a,x0
        move    x1,a
        sub     x0,a                    ; s - (1 - t_b)^2
        move    a,x1
        move    b,x0                    ; u
        mpy     x0,y1,a                 ; u/(du 2^11)
        cmp     y0,a
        tgt     y0,a
        asl     #$b,a,a
        move    a,x0                    ; t_a
        move    #>$7fffff,a
        sub     x0,a
        move    a,x0
        mpyr    x0,x0,a                 ; (1 - t_a)^2
        add     x1,a
        move    a,x0                    ; (limited)
        rts

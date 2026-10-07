; PĒRKONS v1.2.1 Noise Hat Pulse Stack phase/LCG kernel.
;
; Input:
;   r6 -> compact Pulse Stack phase substate (NoiseHatPulseStack words +28)
;   r5 -> shared scratch base
;
; Substate layout, 16-bit limbs:
;   +00..+0b  six phase u32 values (lo,hi)
;   +0c..+17  six phase increment u32 values (lo,hi)
;   +18/+19   local-LCG clock phase u32
;   +1a/+1b   local-LCG clock increment u32
;   +1c/+1d   local LCG state u32
;
; Output:
;   state mutated in place
;   X:(r5+$62) = number of the six updated phases with bit31 set (0..6)
;
; Dependencies: pk_u32_add, pk_u32_mul_low from noise_tone_math.asm.
; The local LCG is the ARM renderer's:
;   random = random * $0019660d + $3c6ef35f  (mod 2^32)
; and advances only when clockPhase + clockIncrement wraps modulo 2^32.

pk_noise_hat_phase_step:
        ; ---- local-LCG clock phase, preserving the carry out of bit 31 -----
        move    x:(r6+$18),a
        move    x:(r6+$1a),x0
        add     x0,a
        move    #>$0,y0
        btst    #16,a1
        jcc     pknhp_clock_low_no_carry
        move    #>$1,y0
pknhp_clock_low_no_carry:
        and     #>$00ffff,a
        move    a1,x:(r6+$18)

        move    x:(r6+$19),b
        move    x:(r6+$1b),x0
        add     x0,b
        add     y0,b
        move    #>$0,y1
        btst    #16,b1
        jcc     pknhp_clock_no_wrap
        move    #>$1,y1
pknhp_clock_no_wrap:
        and     #>$00ffff,b
        move    b1,x:(r6+$19)

        ; On wrap, perform the exact modulo-2^32 LCG update.  Use the already
        ; execution-qualified generic two-limb helpers so the 25-bit multiply
        ; is not approximated by the DSP's fractional multiply semantics.
        move    y1,a
        tst     a
        jeq     pknhp_lcg_done

        move    x:(r6+$1c),a
        move    a1,x:(r5+$0)
        move    x:(r6+$1d),a
        move    a1,x:(r5+$1)
        move    #>$00660d,a
        move    a1,x:(r5+$2)
        move    #>$000019,a
        move    a1,x:(r5+$3)
        jsr     pk_u32_mul_low

        move    x:(r5+$8),a
        move    a1,x:(r5+$0)
        move    x:(r5+$9),a
        move    a1,x:(r5+$1)
        move    #>$00f35f,a
        move    a1,x:(r5+$2)
        move    #>$003c6e,a
        move    a1,x:(r5+$3)
        jsr     pk_u32_add
        move    x:(r5+$8),a
        move    a1,x:(r6+$1c)
        move    x:(r5+$9),a
        move    a1,x:(r6+$1d)
pknhp_lcg_done:

        ; y1 accumulates the number of updated oscillator phases whose bit31
        ; is set.  Each phase add is exact modulo 2^32 via pk_u32_add.
        move    #>$0,y1

        ; phase 0: +0/+1 += +c/+d
        move    x:(r6+$0),a
        move    a1,x:(r5+$0)
        move    x:(r6+$1),a
        move    a1,x:(r5+$1)
        move    x:(r6+$c),a
        move    a1,x:(r5+$2)
        move    x:(r6+$d),a
        move    a1,x:(r5+$3)
        jsr     pk_u32_add
        move    x:(r5+$8),a
        move    a1,x:(r6+$0)
        move    x:(r5+$9),a
        move    a1,x:(r6+$1)
        btst    #15,a1
        jcc     pknhp_phase0_positive
        move    y1,b
        move    #>$1,x0
        add     x0,b
        move    b1,y1
pknhp_phase0_positive:

        ; phase 1: +2/+3 += +e/+f
        move    x:(r6+$2),a
        move    a1,x:(r5+$0)
        move    x:(r6+$3),a
        move    a1,x:(r5+$1)
        move    x:(r6+$e),a
        move    a1,x:(r5+$2)
        move    x:(r6+$f),a
        move    a1,x:(r5+$3)
        jsr     pk_u32_add
        move    x:(r5+$8),a
        move    a1,x:(r6+$2)
        move    x:(r5+$9),a
        move    a1,x:(r6+$3)
        btst    #15,a1
        jcc     pknhp_phase1_positive
        move    y1,b
        move    #>$1,x0
        add     x0,b
        move    b1,y1
pknhp_phase1_positive:

        ; phase 2: +4/+5 += +10/+11
        move    x:(r6+$4),a
        move    a1,x:(r5+$0)
        move    x:(r6+$5),a
        move    a1,x:(r5+$1)
        move    x:(r6+$10),a
        move    a1,x:(r5+$2)
        move    x:(r6+$11),a
        move    a1,x:(r5+$3)
        jsr     pk_u32_add
        move    x:(r5+$8),a
        move    a1,x:(r6+$4)
        move    x:(r5+$9),a
        move    a1,x:(r6+$5)
        btst    #15,a1
        jcc     pknhp_phase2_positive
        move    y1,b
        move    #>$1,x0
        add     x0,b
        move    b1,y1
pknhp_phase2_positive:

        ; phase 3: +6/+7 += +12/+13
        move    x:(r6+$6),a
        move    a1,x:(r5+$0)
        move    x:(r6+$7),a
        move    a1,x:(r5+$1)
        move    x:(r6+$12),a
        move    a1,x:(r5+$2)
        move    x:(r6+$13),a
        move    a1,x:(r5+$3)
        jsr     pk_u32_add
        move    x:(r5+$8),a
        move    a1,x:(r6+$6)
        move    x:(r5+$9),a
        move    a1,x:(r6+$7)
        btst    #15,a1
        jcc     pknhp_phase3_positive
        move    y1,b
        move    #>$1,x0
        add     x0,b
        move    b1,y1
pknhp_phase3_positive:

        ; phase 4: +8/+9 += +14/+15
        move    x:(r6+$8),a
        move    a1,x:(r5+$0)
        move    x:(r6+$9),a
        move    a1,x:(r5+$1)
        move    x:(r6+$14),a
        move    a1,x:(r5+$2)
        move    x:(r6+$15),a
        move    a1,x:(r5+$3)
        jsr     pk_u32_add
        move    x:(r5+$8),a
        move    a1,x:(r6+$8)
        move    x:(r5+$9),a
        move    a1,x:(r6+$9)
        btst    #15,a1
        jcc     pknhp_phase4_positive
        move    y1,b
        move    #>$1,x0
        add     x0,b
        move    b1,y1
pknhp_phase4_positive:

        ; phase 5: +a/+b += +16/+17
        move    x:(r6+$a),a
        move    a1,x:(r5+$0)
        move    x:(r6+$b),a
        move    a1,x:(r5+$1)
        move    x:(r6+$16),a
        move    a1,x:(r5+$2)
        move    x:(r6+$17),a
        move    a1,x:(r5+$3)
        jsr     pk_u32_add
        move    x:(r5+$8),a
        move    a1,x:(r6+$a)
        move    x:(r5+$9),a
        move    a1,x:(r6+$b)
        btst    #15,a1
        jcc     pknhp_phase5_positive
        move    y1,b
        move    #>$1,x0
        add     x0,b
        move    b1,y1
pknhp_phase5_positive:

        move    y1,x:(r5+$62)
        rts

; PERKY Noise/Tone DSP56300 32-bit arithmetic/state kernel / standalone probe.
; Not in the audio hook yet. Firmware u32 values are two 16-bit limbs.
; Normal 24-bit DSP mode only: do not use SA; Octabam's emulator does not
; implement SA semantics, so explicit limbs keep the off-hardware oracle valid.
;
; bd909_host-compatible probe ABI:
;   r5 = X state base, r6 = X parameter block, x:(r6+$0) = op
; State: +0 a.lo, +1 a.hi, +2 b.lo, +3 b.hi, +4 shift,
;        +8 result.low32.lo, +9 result.low32.hi,
;       +10 result.high32.lo,+11 result.high32.hi,
;       +12 primitive result word,
;       +40 noise countdown, +41 noise reload, +42 held noise sample.
; Ops: 1 add32, 2 sub32, 3 signed ASR32, 4 low32 multiply,
;      5 full64 multiply, 6 PERKONS two-word RNG step,
;      7 Noise/Tone sample-and-hold noise step.
;
; RNG op 6 uses input a=oldLow, b=oldHigh. It mutates +0..+3 to
; newLow/newHigh and mirrors them to +8..+11 for the generic probe harness.
; Scratch +20..+36 is private to the RNG probe path.
;
; Noise op 7 uses the same RNG input/state plus +40/+41/+42. It writes the
; 16-bit result bit-pattern to +12. When countdown is non-zero no RNG step is
; performed; when it reaches zero the reload is copied to countdown and the
; held sample becomes low16(nextRandom()).

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
        move    #>$5,x0
        cmp     x0,a
        beq     pk_math_wide_mul
        move    #>$6,x0
        cmp     x0,a
        beq     pk_math_do_rng
        move    #>$7,x0
        cmp     x0,a
        beq     pk_math_do_noise
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
pk_math_wide_mul:
        jsr     pk_u32_mul_full
        rts
pk_math_do_rng:
        jsr     pk_rng_step
        rts
pk_math_do_noise:
        jsr     pk_noise_step
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
        move    x:(r5+$1),a
        btst    #15,a1
        jcc     pk_u32_shift_sign_ready
        sub     #>$010000,a
pk_u32_shift_sign_ready:
        move    x:(r5+$0),b
        lsl     #$8,b
        move    b1,a0
        move    x:(r5+$4),x0
        asr     x0,a,a
        move    a1,b
        and     #>$00ffff,b
        move    b1,x:(r5+$9)
        move    a0,b
        lsr     #$8,b
        and     #>$00ffff,b
        move    b1,x:(r5+$8)
        rts

; Low 32 bits of unsigned 32x32 multiply using three 16x16 products:
; lo=low16(al*bl), hi=low16(high16(al*bl)+al*bh+ah*bl).
pk_u32_mul_low:
        move    x:(r5+$0),x0
        move    x:(r5+$2),y0
        mpyuu   x0,y0,a
        asr     #$1,a,a                 ; remove fractional multiply alignment
        move    a0,x1
        move    x1,b
        and     #>$00ffff,b
        move    b1,x:(r5+$8)
        asr     #$10,a,a
        move    a0,x1
        move    x1,b
        and     #>$00ffff,b
        move    b1,y1

        move    x:(r5+$0),x0
        move    x:(r5+$3),y0
        mpyuu   x0,y0,a
        asr     #$1,a,a                 ; remove fractional multiply alignment
        move    a0,a
        and     #>$00ffff,a
        move    a1,x1
        move    y1,b
        add     x1,b

        move    x:(r5+$1),x0
        move    x:(r5+$2),y0
        mpyuu   x0,y0,a
        asr     #$1,a,a                 ; remove fractional multiply alignment
        move    a0,a
        and     #>$00ffff,a
        move    a1,x1
        add     x1,b
        and     #>$00ffff,b
        move    b1,x:(r5+$9)
        rts

; Helper: unsigned 16x16 -> x1=low16, y1=high16. Remove MPYUU
; fractional alignment first; A0 then holds product bits 0..23, and
; a full-accumulator ASR #16 exposes bits 16..31 in A0.
pk_mul16:
        mpyuu   x0,y0,a
        asr     #$1,a,a                 ; remove fractional multiply alignment
        move    a0,x1
        move    x1,b
        and     #>$00ffff,b
        move    b1,x1
        asr     #$10,a,a
        move    a0,y1
        move    y1,b
        and     #>$00ffff,b
        move    b1,y1
        rts

; Exact unsigned 32x32 -> 64 bits. Four 16x16 partial products are staged at
; X:(r5+$10)..+$16, then two base-2^16 carry folds produce r0..r3.
; Output low32 is +8/+9; high32 is +10/+11.
pk_u32_mul_full:
        ; p0 = al*bl: r0 plus p0.high
        move    x:(r5+$0),x0
        move    x:(r5+$2),y0
        jsr     pk_mul16
        move    x1,x:(r5+$8)
        move    y1,x:(r5+$10)

        ; p1 = al*bh
        move    x:(r5+$0),x0
        move    x:(r5+$3),y0
        jsr     pk_mul16
        move    x1,x:(r5+$11)
        move    y1,x:(r5+$12)

        ; p2 = ah*bl
        move    x:(r5+$1),x0
        move    x:(r5+$2),y0
        jsr     pk_mul16
        move    x1,x:(r5+$13)
        move    y1,x:(r5+$14)

        ; p3 = ah*bh
        move    x:(r5+$1),x0
        move    x:(r5+$3),y0
        jsr     pk_mul16
        move    x1,x:(r5+$15)
        move    y1,x:(r5+$16)

        ; t1 = p0.high + p1.low + p2.low; r1=low16(t1), carry1=t1>>16.
        move    x:(r5+$10),a
        move    x:(r5+$11),x0
        add     x0,a
        move    x:(r5+$13),x0
        add     x0,a
        move    a1,b
        and     #>$00ffff,b
        move    b1,x:(r5+$9)
        lsr     #$10,a
        move    a1,x1                   ; carry1 (0..2)

        ; t2 = p1.high + p2.high + p3.low + carry1.
        move    x:(r5+$12),a
        move    x:(r5+$14),x0
        add     x0,a
        move    x:(r5+$15),x0
        add     x0,a
        add     x1,a
        move    a1,b
        and     #>$00ffff,b
        move    b1,x:(r5+$10)           ; r2
        lsr     #$10,a
        move    a1,x1                   ; carry2 (0..2)

        ; r3 = low16(p3.high + carry2)
        move    x:(r5+$16),b
        add     x1,b
        and     #>$00ffff,b
        move    b1,x:(r5+$11)
        rts

; Exact PĒRKONS two-word RNG step used by the Noise/Tone renderer:
;   accumulator = low32(oldLow*A) + low32(oldHigh*B)
;   product     = full64(oldLow*B)
;   newLow      = low32(product) + 1
;   newHigh     = accumulator + high32(product) + carry(newLow)
;   return      = newHigh & 0x7fffffff
; Constants: A=$5851f42d, B=$4c957f2d.
;
; Input oldLow is +0/+1 and oldHigh is +2/+3. The routine stores newLow and
; newHigh back to +0..+3 and mirrors them to +8..+11. The caller can obtain
; the firmware return value by clearing bit 15 of the high limb at +11.
pk_rng_step:
        ; Preserve original RNG words in private scratch.
        move    x:(r5+$0),a
        move    a1,x:(r5+$20)
        move    x:(r5+$1),a
        move    a1,x:(r5+$21)
        move    x:(r5+$2),a
        move    a1,x:(r5+$22)
        move    x:(r5+$3),a
        move    a1,x:(r5+$23)

        ; accumulator = low32(oldLow * A)
        move    x:(r5+$20),a
        move    a1,x:(r5+$0)
        move    x:(r5+$21),a
        move    a1,x:(r5+$1)
        move    #>$00f42d,a
        move    a1,x:(r5+$2)
        move    #>$005851,a
        move    a1,x:(r5+$3)
        jsr     pk_u32_mul_low
        move    x:(r5+$8),a
        move    a1,x:(r5+$24)
        move    x:(r5+$9),a
        move    a1,x:(r5+$25)

        ; accumulator += low32(oldHigh * B)
        move    x:(r5+$22),a
        move    a1,x:(r5+$0)
        move    x:(r5+$23),a
        move    a1,x:(r5+$1)
        move    #>$007f2d,a
        move    a1,x:(r5+$2)
        move    #>$004c95,a
        move    a1,x:(r5+$3)
        jsr     pk_u32_mul_low
        move    x:(r5+$24),a
        move    a1,x:(r5+$0)
        move    x:(r5+$25),a
        move    a1,x:(r5+$1)
        move    x:(r5+$8),a
        move    a1,x:(r5+$2)
        move    x:(r5+$9),a
        move    a1,x:(r5+$3)
        jsr     pk_u32_add
        move    x:(r5+$8),a
        move    a1,x:(r5+$24)
        move    x:(r5+$9),a
        move    a1,x:(r5+$25)

        ; product = full64(oldLow * B)
        move    x:(r5+$20),a
        move    a1,x:(r5+$0)
        move    x:(r5+$21),a
        move    a1,x:(r5+$1)
        move    #>$007f2d,a
        move    a1,x:(r5+$2)
        move    #>$004c95,a
        move    a1,x:(r5+$3)
        jsr     pk_u32_mul_full
        move    x:(r5+$8),a
        move    a1,x:(r5+$26)
        move    x:(r5+$9),a
        move    a1,x:(r5+$27)
        move    x:(r5+$10),a
        move    a1,x:(r5+$28)
        move    x:(r5+$11),a
        move    a1,x:(r5+$29)

        ; newLow = productLow + 1
        move    x:(r5+$26),a
        move    a1,x:(r5+$0)
        move    x:(r5+$27),a
        move    a1,x:(r5+$1)
        move    #>$1,a
        move    a1,x:(r5+$2)
        clr     a
        move    a1,x:(r5+$3)
        jsr     pk_u32_add
        move    x:(r5+$8),a
        move    a1,x:(r5+$30)
        move    x:(r5+$9),a
        move    a1,x:(r5+$31)

        ; carry = 1 iff productLow was $ffffffff.
        clr     a
        move    a1,x:(r5+$36)
        move    x:(r5+$26),a
        cmp     #>$00ffff,a
        bne     pk_rng_no_carry
        move    x:(r5+$27),a
        cmp     #>$00ffff,a
        bne     pk_rng_no_carry
        move    #>$1,a
        move    a1,x:(r5+$36)
pk_rng_no_carry:

        ; newHigh = accumulator + productHigh
        move    x:(r5+$24),a
        move    a1,x:(r5+$0)
        move    x:(r5+$25),a
        move    a1,x:(r5+$1)
        move    x:(r5+$28),a
        move    a1,x:(r5+$2)
        move    x:(r5+$29),a
        move    a1,x:(r5+$3)
        jsr     pk_u32_add
        move    x:(r5+$8),a
        move    a1,x:(r5+$32)
        move    x:(r5+$9),a
        move    a1,x:(r5+$33)

        ; Add carry from newLow wrap.
        move    x:(r5+$32),a
        move    a1,x:(r5+$0)
        move    x:(r5+$33),a
        move    a1,x:(r5+$1)
        move    x:(r5+$36),a
        move    a1,x:(r5+$2)
        clr     a
        move    a1,x:(r5+$3)
        jsr     pk_u32_add
        move    x:(r5+$8),a
        move    a1,x:(r5+$32)
        move    x:(r5+$9),a
        move    a1,x:(r5+$33)

        ; Publish/mutate RNG state and generic probe outputs.
        move    x:(r5+$30),a
        move    a1,x:(r5+$0)
        move    a1,x:(r5+$8)
        move    x:(r5+$31),a
        move    a1,x:(r5+$1)
        move    a1,x:(r5+$9)
        move    x:(r5+$32),a
        move    a1,x:(r5+$2)
        move    a1,x:(r5+$10)
        move    x:(r5+$33),a
        move    a1,x:(r5+$3)
        move    a1,x:(r5+$11)
        rts

; Noise/Tone sample-and-hold source primitive. This is the renderer's
; renderNoise() reduced to its exact state transition. +40/+41/+42 are direct
; 16-bit probe words corresponding to firmware count/reload/held-sample u16s.
; +12 receives the returned sample bit-pattern.
pk_noise_step:
        move    x:(r5+$40),a
        tst     a
        beq     pk_noise_refresh

        sub     #>$1,a
        and     #>$00ffff,a
        move    a1,x:(r5+$40)
        move    x:(r5+$42),a
        and     #>$00ffff,a
        move    a1,x:(r5+$12)
        rts

pk_noise_refresh:
        move    x:(r5+$41),a
        and     #>$00ffff,a
        move    a1,x:(r5+$40)
        jsr     pk_rng_step

        ; renderNoise casts low16(nextRandom()) to int16. nextRandom() is
        ; newHigh & $7fffffff, so its low16 is exactly newHigh.low at +10.
        move    x:(r5+$10),a
        and     #>$00ffff,a
        move    a1,x:(r5+$42)
        move    a1,x:(r5+$12)
        rts

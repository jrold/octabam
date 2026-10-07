; PĒRKONS v1.2.1 Noise Hat / Pulse Stack DSP candidate.
;
; Compact state is exactly 59 X words, matching noise_hat_pulse_compact.py:
;   +00        velocity u8
;   +01..+0b  common amplitude envelope (11 words)
;   +0c..+13  filter A (8 words)
;   +14..+1b  filter B (8 words)
;   +1c..+27  six phase u32 values
;   +28..+33  six phase increment u32 values
;   +34/+35   local-LCG clock phase u32
;   +36/+37   local-LCG clock increment u32
;   +38/+39   local LCG state u32
;   +39        second filter input u16 (aliases RNG high word, ARM +0x136)
;   +3a        signed interpolation mix u16
;
; Voice ABI: r6=state, r5=scratch, n7=sample count, r0=stereo output.
; Dependencies:
;   pk_noise_hat_phase_step
;   pk_noise_hat_filter
;   pk_noise_hat_envelope
;   pk_u32_add / pk_u32_mul_low via noise_tone_math.asm
;
; This candidate is deliberately not in the shipping dispatcher yet.  Its
; executable gate must establish exact PCM/state parity and timing first.

pk_noise_hat_pulse_voice:
        move    r6,a
        move    a1,x:(r5+$60)

        do      n7,pknhv_done
        ; Advance all seven u32 phase accumulators and conditionally update the
        ; local LCG. signCount (0..6) is returned at scratch +$62.
        move    x:(r5+$60),r6
        lua     (r6+$1c),r6
        jsr     pk_noise_hat_phase_step

        ; pulseStack = signed32(signCount - 3) * $1555.
        move    x:(r5+$62),a
        sub     #>$3,a
        move    a1,x0
        move    #>$001555,y0
        mpy     y0,x0,a
        asr     #$1,a,a                 ; remove fractional MPY alignment
        move    a0,a
        move    a1,x:(r5+$61)

        ; First state-variable filter pass.
        move    x:(r5+$60),r6
        lua     (r6+$c),r6
        jsr     pk_noise_hat_filter

        ; Native captures filter A velocity *before* running filter B.
        move    x:(r5+$60),r6
        move    x:(r6+$12),a            ; filterA +6 velocity low limb
        asl     #$8,a,a
        move    a1,a
        asr     #$8,a,a
        move    a1,x:(r5+$63)

        ; ARM +0x136 is the high half of the local u32 RNG at +0x134.
        ; Therefore an LCG update performed above changes this input on the
        ; same sample; there is deliberately no independent compact word.
        move    x:(r6+$39),a
        and     #>$00ffff,a
        sub     #>$008000,a
        move    a1,x:(r5+$61)

        ; Second state-variable filter pass.
        lua     (r6+$14),r6
        jsr     pk_noise_hat_filter

        ; target = signed filterB.second.
        move    x:(r5+$60),r6
        move    x:(r6+$18),a            ; filterB +4 second low limb
        asl     #$8,a,a
        move    a1,a
        asr     #$8,a,a
        move    a1,x1

        ; mix is a signed16. filtered = previous + ((mix * delta) >> 15).
        move    x:(r6+$3a),a
        asl     #$8,a,a
        move    a1,a
        asr     #$8,a,a
        move    a1,y0                   ; signed mix
        move    x:(r5+$63),a
        move    a1,y1                   ; previous
        move    x1,a
        sub     y1,a
        move    a1,x0                   ; delta
        mpy     y0,x0,a
        asr     #$10,a,a                ; fractional MPY alignment + >>15
        move    a0,a
        add     y1,a
        move    a1,x:(r5+$63)           ; filtered

        ; Common amplitude envelope, including both authentic curve selectors.
        move    x:(r5+$60),r6
        lua     (r6+$1),r6
        jsr     pk_noise_hat_envelope
        move    a1,y0                   ; unsigned u16 amplitude

        ; value = (filtered * amplitude) >> 16.
        move    x:(r5+$63),x0
        mpysu   x0,y0,a
        asr     #$11,a,a                ; fractional MPY alignment + >>16
        ; Native narrows the product to signed32 before shifting. Thus its
        ; >>16 result is signed16 even when filtered * amplitude overflows.
        move    a0,a
        asl     #$8,a,a
        move    a1,a
        asr     #$8,a,a
        move    a1,x0

        ; output = (value * velocity) >> 8.
        move    x:(r5+$60),r6
        move    x:(r6+$0),a
        and     #>$0000ff,a
        move    a1,y0
        mpysu   x0,y0,a
        asr     #$9,a,a                 ; fractional MPY alignment + >>8
        move    a0,a

        ; Native C++ saturates this final path to the full int16 range.
        cmp     #>$007fff,a
        ble     pknhv_sat_low
        move    #>$007fff,a
pknhv_sat_low:
        cmp     #>$ff8000,a
        bge     pknhv_sat_done
        move    #>$ff8000,a
pknhv_sat_done:
        move    a1,x:(r0)+
        move    a1,x:(r0)+
        move    x:(r5+$60),r6
pknhv_done:
        nop
        rts

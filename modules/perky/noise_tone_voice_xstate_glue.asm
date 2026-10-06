; PERKY Noise/Tone complete renderer using the shipping X-state ABI.
;
; This is the source-seam-ready form of noise_tone_voice_glue.asm.  The five
; previously gated kernels still operate on one reusable X scratch block, but
; the live 41-word voice and 17-word envelope cache are persistent in X rather
; than the standalone harness's Y state.
;
; Caller ABI:
;   r0  = X stereo output buffer
;   r5  = 100-word X scratch base (shipping: X:$3900..$3963)
;   r6  = 58-word persistent voice base (41 state + 17 envelope cache)
;   n7  = sample count (normally 16)
;
; Persistent global RNG is fixed at X:$38e8..$38eb:
;   low.lo, low.hi, high.lo, high.hi
;
; Per-voice layout below is DECIMAL. DSP displacement literals are hexadecimal,
; so e.g. decimal word 25 is addressed as r6+$19.
;    0 velocity
;    1 env state, 2 shape, 3 flag4, 4 flag6, 5 trigger
;    6/7 env value, 8/9 env hold, 10 attack, 11 decay
;   12 noise count, 13 reload, 14 held
;   15 filter damping, 16 coefficient, 17/18 first, 19/20 second, 21/22 velocity
;   23/24 osc1 phase, 25/26 inc, 27/28 current, 29/30 next
;   31/32 osc2 phase, 33/34 inc, 35/36 current, 37/38 next
;   39/40 mix
;   41 cache key, 42..57 sixteen decoded envelope values
;
; The standalone primitive scratch ABI is intentionally sparse and hexadecimal:
; it reaches X:r5+$63, therefore the shared block is 0x64 = 100 words.
; Scratch temporaries used by this composer are X:r5+$60..$63:
;   +$60 amplitude, +$61 noise, +$62 oscillator1, +$63 oscillator2
;
; Required linked kernels in the same assembled image:
;   pk_noise_step              (noise_tone_math.asm)
;   pk_filter_probe            (noise_tone_filter.asm)
;   pk_osc_packed_probe        (noise_tone_oscillator_packed.asm)
;   pk_envelope_packed7_cached (noise_tone_envelope_packed7.asm)
;   pk_envelope_probe          (noise_tone_envelope.asm, state transition oracle)
;   pk_mix_probe               (noise_tone_mix.asm)

pk_voice_xstate:
        do      n7,pkvx_block_done

        ; ---- amplitude envelope -------------------------------------------
        move    x:(r6+$1),a
        move    a1,x:(r5+$40)
        move    x:(r6+$2),a
        move    a1,x:(r5+$41)
        move    x:(r6+$3),a
        move    a1,x:(r5+$42)
        move    x:(r6+$4),a
        move    a1,x:(r5+$43)
        move    x:(r6+$5),a
        move    a1,x:(r5+$44)
        move    x:(r6+$6),a
        move    a1,x:(r5+$45)
        move    x:(r6+$7),a
        move    a1,x:(r5+$46)
        move    x:(r6+$8),a
        move    a1,x:(r5+$47)
        move    x:(r6+$9),a
        move    a1,x:(r5+$48)
        move    x:(r6+$a),a             ; compact word 10
        move    a1,x:(r5+$49)
        move    x:(r6+$b),a             ; compact word 11
        move    a1,x:(r5+$50)
        lua     (r6+$29),r4             ; compact word 41: persistent cache key
        jsr     pk_envelope_packed7_cached
        move    x:(r5+$40),a
        move    a1,x:(r6+$1)
        move    x:(r5+$45),a
        move    a1,x:(r6+$6)
        move    x:(r5+$46),a
        move    a1,x:(r6+$7)
        move    x:(r5+$51),a
        move    a1,x:(r5+$60)          ; amplitude

        ; ---- sample/hold noise + shared RNG -------------------------------
        move    x:>$38e8,a
        move    a1,x:(r5+$0)
        move    x:>$38e9,a
        move    a1,x:(r5+$1)
        move    x:>$38ea,a
        move    a1,x:(r5+$2)
        move    x:>$38eb,a
        move    a1,x:(r5+$3)
        move    x:(r6+$c),a             ; compact word 12
        move    a1,x:(r5+$40)
        move    x:(r6+$d),a             ; compact word 13
        move    a1,x:(r5+$41)
        move    x:(r6+$e),a             ; compact word 14
        move    a1,x:(r5+$42)
        jsr     pk_noise_step
        move    x:(r5+$0),a
        move    a1,x:>$38e8
        move    x:(r5+$1),a
        move    a1,x:>$38e9
        move    x:(r5+$2),a
        move    a1,x:>$38ea
        move    x:(r5+$3),a
        move    a1,x:>$38eb
        move    x:(r5+$40),a
        move    a1,x:(r6+$c)
        move    x:(r5+$42),a
        move    a1,x:(r6+$e)
        move    x:(r5+$12),a
        move    a1,x:(r5+$61)          ; noise sample

        ; ---- resonant noise filter, two passes ----------------------------
        move    x:(r6+$10),a            ; compact word 16
        move    a1,x:(r5+$44)
        move    x:(r6+$f),a             ; compact word 15
        move    a1,x:(r5+$45)
        move    x:(r6+$11),a            ; compact word 17
        move    a1,x:(r5+$46)
        move    x:(r6+$12),a            ; compact word 18
        move    a1,x:(r5+$47)
        move    x:(r6+$13),a            ; compact word 19
        move    a1,x:(r5+$48)
        move    x:(r6+$14),a            ; compact word 20
        move    a1,x:(r5+$49)
        move    x:(r6+$15),a            ; compact word 21
        move    a1,x:(r5+$50)
        move    x:(r6+$16),a            ; compact word 22
        move    a1,x:(r5+$51)
        move    x:(r5+$61),a
        move    a1,x:(r5+$52)
        jsr     pk_filter_probe
        jsr     pk_filter_probe
        move    x:(r5+$46),a
        move    a1,x:(r6+$11)
        move    x:(r5+$47),a
        move    a1,x:(r6+$12)
        move    x:(r5+$48),a
        move    a1,x:(r6+$13)
        move    x:(r5+$49),a
        move    a1,x:(r6+$14)
        move    x:(r5+$50),a
        move    a1,x:(r6+$15)
        move    x:(r5+$51),a
        move    a1,x:(r6+$16)

        ; ---- oscillator 1 --------------------------------------------------
        move    x:(r6+$17),a            ; compact word 23
        move    a1,x:(r5+$40)
        move    x:(r6+$18),a            ; compact word 24
        move    a1,x:(r5+$41)
        move    x:(r6+$19),a            ; compact word 25
        move    a1,x:(r5+$42)
        move    x:(r6+$1a),a            ; compact word 26
        move    a1,x:(r5+$43)
        move    x:(r6+$1b),a            ; compact word 27
        move    a1,x:(r5+$44)
        move    x:(r6+$1c),a            ; compact word 28
        move    a1,x:(r5+$45)
        move    x:(r6+$1d),a            ; compact word 29
        move    a1,x:(r5+$46)
        move    x:(r6+$1e),a            ; compact word 30
        move    a1,x:(r5+$47)
        jsr     pk_osc_packed_probe
        move    x:(r5+$40),a
        move    a1,x:(r6+$17)
        move    x:(r5+$41),a
        move    a1,x:(r6+$18)
        move    x:(r5+$44),a
        move    a1,x:(r6+$1b)
        move    x:(r5+$45),a
        move    a1,x:(r6+$1c)
        move    x:(r5+$48),a
        move    a1,x:(r5+$62)

        ; ---- oscillator 2 --------------------------------------------------
        move    x:(r6+$1f),a            ; compact word 31
        move    a1,x:(r5+$40)
        move    x:(r6+$20),a            ; compact word 32
        move    a1,x:(r5+$41)
        move    x:(r6+$21),a            ; compact word 33
        move    a1,x:(r5+$42)
        move    x:(r6+$22),a            ; compact word 34
        move    a1,x:(r5+$43)
        move    x:(r6+$23),a            ; compact word 35
        move    a1,x:(r5+$44)
        move    x:(r6+$24),a            ; compact word 36
        move    a1,x:(r5+$45)
        move    x:(r6+$25),a            ; compact word 37
        move    a1,x:(r5+$46)
        move    x:(r6+$26),a            ; compact word 38
        move    a1,x:(r5+$47)
        jsr     pk_osc_packed_probe
        move    x:(r5+$40),a
        move    a1,x:(r6+$1f)
        move    x:(r5+$41),a
        move    a1,x:(r6+$20)
        move    x:(r5+$44),a
        move    a1,x:(r6+$23)
        move    x:(r5+$45),a
        move    a1,x:(r6+$24)
        move    x:(r5+$48),a
        move    a1,x:(r5+$63)

        ; ---- final mixer ---------------------------------------------------
        move    x:(r6+$27),a            ; compact word 39
        move    a1,x:(r5+$40)
        move    x:(r6+$28),a            ; compact word 40
        move    a1,x:(r5+$41)
        move    x:(r5+$61),a
        move    a1,x:(r5+$42)
        move    x:(r5+$62),a
        move    a1,x:(r5+$43)
        move    x:(r5+$63),a
        move    a1,x:(r5+$44)
        move    x:(r5+$60),a
        move    a1,x:(r5+$45)
        move    x:(r6+$0),a
        move    a1,x:(r5+$46)
        jsr     pk_mix_probe

        ; Mixer returns signed16 bit-pattern. Sign-extend to OT 24-bit source
        ; and duplicate mono to both channels.
        move    x:(r5+$47),a
        and     #>$00ffff,a
        btst    #15,a1
        jcc     pkvx_sample_ready
        sub     #>$010000,a
pkvx_sample_ready:
        move    a1,x:(r0)+
        move    a1,x:(r0)+

pkvx_block_done:
        nop
        rts

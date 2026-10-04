; PERKY Noise/Tone combined-render correctness glue.
;
; This is the first COMPLETE DSP56300 voice path. It deliberately composes the
; already executable-gated primitive probes instead of duplicating their math.
; It is not the final optimized shipping renderer yet.
;
; Standalone composition ABI used by verify_perky_voice_exec.py:
;   r0      X stereo output buffer (same bd909_host ABI as Analog BD)
;   r5      common base
;   n7      sample count (normally 16)
;   Y:r5+0..40   compact 41-word voice ABI (noise_tone_compact.py)
;   Y:r5+41..44  global RNG: low.lo, low.hi, high.lo, high.hi
;   Y:r5+45      temporary amplitude
;   Y:r5+46      temporary noise sample
;   Y:r5+47      temporary oscillator 1 sample
;   Y:r5+48      temporary oscillator 2 sample
;   X:r5+0..63   reusable primitive scratch/probe workspace
;
; The primitive sources are concatenated behind this file by the executable
; gate. Their established table geometry is retained for this correctness
; canary: oscillator tables X:$3000/$3100; envelope curves X:$3200/$3a00.
; Packing those tables is a separate optimization after complete-render parity.
;
; Compact Y-word offsets (must match noise_tone_compact.py):
;    0 velocity
;    1 env state, 2 shape, 3 flag4, 4 flag6, 5 trigger
;    6/7 env value, 8/9 env hold, 10 attack, 11 decay
;   12 noise count, 13 reload, 14 held
;   15 filter damping, 16 coefficient, 17/18 first, 19/20 second, 21/22 velocity
;   23/24 osc1 phase, 25/26 inc, 27/28 current, 29/30 next
;   31/32 osc2 phase, 33/34 inc, 35/36 current, 37/38 next
;   39/40 mix
;
; Clobbers the primitive kernels' documented registers. Stock integration will
; wrap/preserve what the source seam requires; this standalone gate cares only
; about bit-exact renderer behaviour and instruction count.

pk_voice_probe:
        do      n7,pkv_block_done

        ; ---- amplitude envelope: compact Y:1..11 -> probe X:40..50 --------
        move    y:(r5+$1),a
        move    a1,x:(r5+$40)
        move    y:(r5+$2),a
        move    a1,x:(r5+$41)
        move    y:(r5+$3),a
        move    a1,x:(r5+$42)
        move    y:(r5+$4),a
        move    a1,x:(r5+$43)
        move    y:(r5+$5),a
        move    a1,x:(r5+$44)
        move    y:(r5+$6),a
        move    a1,x:(r5+$45)
        move    y:(r5+$7),a
        move    a1,x:(r5+$46)
        move    y:(r5+$8),a
        move    a1,x:(r5+$47)
        move    y:(r5+$9),a
        move    a1,x:(r5+$48)
        move    y:(r5+$10),a
        move    a1,x:(r5+$49)
        move    y:(r5+$11),a
        move    a1,x:(r5+$50)
        jsr     pk_envelope_probe
        move    x:(r5+$40),a
        move    a1,y:(r5+$1)
        move    x:(r5+$45),a
        move    a1,y:(r5+$6)
        move    x:(r5+$46),a
        move    a1,y:(r5+$7)
        move    x:(r5+$51),a
        move    a1,y:(r5+$45)           ; amplitude

        ; ---- sample/hold noise + shared RNG -------------------------------
        move    y:(r5+$41),a
        move    a1,x:(r5+$0)
        move    y:(r5+$42),a
        move    a1,x:(r5+$1)
        move    y:(r5+$43),a
        move    a1,x:(r5+$2)
        move    y:(r5+$44),a
        move    a1,x:(r5+$3)
        move    y:(r5+$12),a
        move    a1,x:(r5+$40)
        move    y:(r5+$13),a
        move    a1,x:(r5+$41)
        move    y:(r5+$14),a
        move    a1,x:(r5+$42)
        jsr     pk_noise_step
        move    x:(r5+$0),a
        move    a1,y:(r5+$41)
        move    x:(r5+$1),a
        move    a1,y:(r5+$42)
        move    x:(r5+$2),a
        move    a1,y:(r5+$43)
        move    x:(r5+$3),a
        move    a1,y:(r5+$44)
        move    x:(r5+$40),a
        move    a1,y:(r5+$12)
        move    x:(r5+$42),a
        move    a1,y:(r5+$14)
        move    x:(r5+$12),a
        move    a1,y:(r5+$46)           ; noise sample

        ; ---- resonant noise filter, first pass ----------------------------
        move    y:(r5+$16),a            ; coefficient
        move    a1,x:(r5+$44)
        move    y:(r5+$15),a            ; damping
        move    a1,x:(r5+$45)
        move    y:(r5+$17),a
        move    a1,x:(r5+$46)
        move    y:(r5+$18),a
        move    a1,x:(r5+$47)
        move    y:(r5+$19),a
        move    a1,x:(r5+$48)
        move    y:(r5+$20),a
        move    a1,x:(r5+$49)
        move    y:(r5+$21),a
        move    a1,x:(r5+$50)
        move    y:(r5+$22),a
        move    a1,x:(r5+$51)
        move    y:(r5+$46),a
        move    a1,x:(r5+$52)
        jsr     pk_filter_probe
        ; Firmware calls the exact same filter transition twice per sample.
        jsr     pk_filter_probe
        move    x:(r5+$46),a
        move    a1,y:(r5+$17)
        move    x:(r5+$47),a
        move    a1,y:(r5+$18)
        move    x:(r5+$48),a
        move    a1,y:(r5+$19)
        move    x:(r5+$49),a
        move    a1,y:(r5+$20)
        move    x:(r5+$50),a
        move    a1,y:(r5+$21)
        move    x:(r5+$51),a
        move    a1,y:(r5+$22)

        ; ---- oscillator 1: compact Y:23..30 -> probe X:40..47 -------------
        move    y:(r5+$23),a
        move    a1,x:(r5+$40)
        move    y:(r5+$24),a
        move    a1,x:(r5+$41)
        move    y:(r5+$25),a
        move    a1,x:(r5+$42)
        move    y:(r5+$26),a
        move    a1,x:(r5+$43)
        move    y:(r5+$27),a
        move    a1,x:(r5+$44)
        move    y:(r5+$28),a
        move    a1,x:(r5+$45)
        move    y:(r5+$29),a
        move    a1,x:(r5+$46)
        move    y:(r5+$30),a
        move    a1,x:(r5+$47)
        jsr     pk_osc_probe
        move    x:(r5+$40),a
        move    a1,y:(r5+$23)
        move    x:(r5+$41),a
        move    a1,y:(r5+$24)
        move    x:(r5+$44),a
        move    a1,y:(r5+$27)
        move    x:(r5+$45),a
        move    a1,y:(r5+$28)
        move    x:(r5+$48),a
        move    a1,y:(r5+$47)

        ; ---- oscillator 2 --------------------------------------------------
        move    y:(r5+$31),a
        move    a1,x:(r5+$40)
        move    y:(r5+$32),a
        move    a1,x:(r5+$41)
        move    y:(r5+$33),a
        move    a1,x:(r5+$42)
        move    y:(r5+$34),a
        move    a1,x:(r5+$43)
        move    y:(r5+$35),a
        move    a1,x:(r5+$44)
        move    y:(r5+$36),a
        move    a1,x:(r5+$45)
        move    y:(r5+$37),a
        move    a1,x:(r5+$46)
        move    y:(r5+$38),a
        move    a1,x:(r5+$47)
        jsr     pk_osc_probe
        move    x:(r5+$40),a
        move    a1,y:(r5+$31)
        move    x:(r5+$41),a
        move    a1,y:(r5+$32)
        move    x:(r5+$44),a
        move    a1,y:(r5+$35)
        move    x:(r5+$45),a
        move    a1,y:(r5+$36)
        move    x:(r5+$48),a
        move    a1,y:(r5+$48)

        ; ---- final mixer ---------------------------------------------------
        move    y:(r5+$39),a
        move    a1,x:(r5+$40)
        move    y:(r5+$40),a
        move    a1,x:(r5+$41)
        move    y:(r5+$46),a
        move    a1,x:(r5+$42)
        move    y:(r5+$47),a
        move    a1,x:(r5+$43)
        move    y:(r5+$48),a
        move    a1,x:(r5+$44)
        move    y:(r5+$45),a
        move    a1,x:(r5+$45)
        move    y:(r5+$0),a
        move    a1,x:(r5+$46)
        jsr     pk_mix_probe

        ; Probe mixer returns a signed16 bit-pattern. Sign-extend to the OT's
        ; 24-bit source buffer and write mono to both channels.
        move    x:(r5+$47),a
        and     #>$00ffff,a
        btst    #15,a1
        jcc     pkv_sample_ready
        sub     #>$010000,a
pkv_sample_ready:
        move    a1,x:(r0)+
        move    a1,x:(r0)+

pkv_block_done:
        nop
        rts

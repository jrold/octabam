; PĒRKONS v1.2.1 Noise Hat classic firmware mode 1 full DSP candidate.
;
; ABI:
;   r6 = 121-word classic compact state base
;   r5 = scratch base (includes hold/RNG sideband used by mode1 inner)
;   r4 = Y base of 4,805-word wrapper delay ring
;   r0 = interleaved stereo output
;   n7 = sample count
;
; Dependencies:
;   pk_noise_hat_classic_inner1
;   pk_noise_hat_classic_delay
;
; This preserves the native wrapper's outer mute semantics: X:(state+0) skips
; the inner renderer AND the wrapper delay, so hold/RNG/ring/index all freeze.

pk_noise_hat_classic_mode1_voice:
        move    r6,a
        move    a1,x:(r5+$76)           ; persistent classic state base

        do      n7,pknhc1v_done
        move    x:(r5+$76),r6
        move    x:(r6+$0),a             ; wrapper overall mute byte
        tst     a
        bne     pknhc1v_muted

        jsr     pk_noise_hat_classic_inner1
        and     #>$00ffff,a
        move    a1,x:(r5+$60)           ; delay input bit-pattern
        move    x:(r5+$76),r6
        jsr     pk_noise_hat_classic_delay
        move    a1,x:(r0)+
        move    a1,x:(r0)+
        bra     pknhc1v_next

pknhc1v_muted:
        clr     a
        move    a1,x:(r0)+
        move    a1,x:(r0)+

pknhc1v_next:
        move    x:(r5+$76),r6
pknhc1v_done:
        nop
        rts

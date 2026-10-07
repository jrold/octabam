; PĒRKONS v1.2.1 Noise Hat classic firmware mode 0 full DSP candidate.
;
; ABI:
;   r6 = 121-word classic compact state base
;   r5 = scratch base
;   r4 = Y base of 4,805-word wrapper delay ring
;   r0 = interleaved stereo output
;   n7 = sample count
;
; Dependencies: pk_noise_hat_classic_mode0, pk_noise_hat_classic_delay.

pk_noise_hat_classic_mode0_voice:
        move    r6,a
        move    a1,x:(r5+$76)

        do      n7,pknhc0v_done
        move    x:(r5+$76),r6
        move    x:(r6+$0),a
        tst     a
        bne     pknhc0v_muted

        jsr     pk_noise_hat_classic_mode0
        and     #>$00ffff,a
        move    a1,x:(r5+$60)
        move    x:(r5+$76),r6
        jsr     pk_noise_hat_classic_delay
        move    a1,x:(r0)+
        move    a1,x:(r0)+
        bra     pknhc0v_next

pknhc0v_muted:
        clr     a
        move    a1,x:(r0)+
        move    a1,x:(r0)+

pknhc0v_next:
        move    x:(r5+$76),r6
pknhc0v_done:
        nop
        rts

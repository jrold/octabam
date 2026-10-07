; PĒRKONS v1.2.1 Noise Hat classic firmware mode 0 (panel M2 / metallic noise).
;
; One-sample inner renderer. The wrapper delay is composed separately.
;
; ABI:
;   r6 = 121-word classic compact state base
;   r5 = scratch base
;   result A1 = signed int16 inner sample before wrapper delay
;
; Compact offsets:
;   +$01 velocity u8
;   +$02..+$0c envelope
;   +$0d..+$30 six 6-word pulse objects
;   +$31..+$50 four 8-word filters
;
; Dependencies: pk_noise_hat_filter, pk_noise_hat_envelope.

pk_noise_hat_classic_mode0:
        ; Sum six pulse contributions. Native pulse output is +/-32767, then
        ; uint32>>5 narrowed to int16: +1023 or -1024 respectively.
        clr     a
        move    a1,x:(r5+$60)

        lua     (r6+$0d),r7
        jsr     pknhc0_pulse
        move    x:(r5+$60),b
        add     b,a
        move    a1,x:(r5+$60)

        lua     (r6+$13),r7
        jsr     pknhc0_pulse
        move    x:(r5+$60),b
        add     b,a
        move    a1,x:(r5+$60)

        lua     (r6+$19),r7
        jsr     pknhc0_pulse
        move    x:(r5+$60),b
        add     b,a
        move    a1,x:(r5+$60)

        lua     (r6+$1f),r7
        jsr     pknhc0_pulse
        move    x:(r5+$60),b
        add     b,a
        move    a1,x:(r5+$60)

        lua     (r6+$25),r7
        jsr     pknhc0_pulse
        move    x:(r5+$60),b
        add     b,a
        move    a1,x:(r5+$60)

        lua     (r6+$2b),r7
        jsr     pknhc0_pulse
        move    x:(r5+$60),b
        add     b,a
        move    a1,x:(r5+$60)

        ; Four serial state-variable filters. The native chain feeds first from
        ; filter0, then second from filter1 and filter2 into the next stage.
        move    x:(r5+$60),a
        and     #>$00ffff,a
        move    a1,x:(r5+$61)
        lua     (r6+$31),r7
        move    r7,r6
        jsr     pk_noise_hat_filter

        move    x:(r6+$2),a             ; filter0 first low
        move    a1,x:(r5+$61)
        lua     (r6+$8),r6              ; filter1
        jsr     pk_noise_hat_filter

        move    x:(r6+$4),a             ; filter1 second low
        move    a1,x:(r5+$61)
        lua     (r6+$8),r6              ; filter2
        jsr     pk_noise_hat_filter

        move    x:(r6+$4),a             ; filter2 second low
        move    a1,x:(r5+$61)
        lua     (r6+$8),r6              ; filter3
        jsr     pk_noise_hat_filter

        ; Save filter3 velocity before restoring the classic base. It is
        ; signed16-bounded despite its signed32 compact representation.
        move    x:(r6+$6),a
        and     #>$00ffff,a
        move    a1,x:(r5+$63)

        ; filter3 base is classic+$49, so restore classic r6 by subtracting $49.
        move    r6,a
        sub     #>$49,a
        move    a1,r6

        ; Common envelope.
        lua     (r6+$02),r7
        move    r7,r6
        jsr     pk_noise_hat_envelope
        move    a1,y0                   ; amplitude u16
        move    r6,a
        sub     #>$02,a
        move    a1,r6

        ; x = asr(low32(filter3.velocity * amplitude), 11).
        move    x:(r5+$63),a
        asl     #$8,a,a
        move    a1,a
        asr     #$8,a,a
        move    a1,x0
        mpysu   x0,y0,a
        asr     #$c,a,a                 ; fractional alignment + >>11
        move    a0,x0

        ; Native velocity helper: asr(x * velocity_u8, 8), then sat16.
        move    x:(r6+$01),y0
        and     #>$0000ff,y0
        mpysu   x0,y0,a
        asr     #$9,a,a                 ; fractional alignment + >>8
        move    a0,a
        cmp     #>$007fff,a
        ble     pknhc0_sat_low
        move    #>$007fff,a
pknhc0_sat_low:
        cmp     #>$ff8000,a
        bge     pknhc0_done
        move    #>$ff8000,a
pknhc0_done:
        rts

; ---------------------------------------------------------------------------
; Six-word pulse object at X:r7:
;   +0/+1 phase u32, +2/+3 increment u32, +4 width u16, +5 reload u16.
; Returns the exact contribution consumed by mode0: +1023 or -1024.
; ---------------------------------------------------------------------------
pknhc0_pulse:
        ; phase += increment modulo 2^32.
        move    x:(r7+$0),a
        move    x:(r7+$2),x0
        add     x0,a
        clr     y0
        btst    #16,a1
        jcc     pknhc0_pulse_no_carry
        move    #>$1,y0
pknhc0_pulse_no_carry:
        and     #>$00ffff,a
        move    a1,x:(r7+$0)

        move    x:(r7+$1),b
        move    x:(r7+$3),x0
        add     x0,b
        add     y0,b
        and     #>$00ffff,b
        move    b1,x:(r7+$1)

        ; if signed32(phase) > $00100000: phase -= $00100000; width=reload.
        btst    #15,b1
        jcs     pknhc0_pulse_compare_width
        cmp     #>$0010,b
        bgt     pknhc0_pulse_wrap
        blt     pknhc0_pulse_compare_width
        move    x:(r7+$0),a
        tst     a
        beq     pknhc0_pulse_compare_width
pknhc0_pulse_wrap:
        move    x:(r7+$1),a
        sub     #>$0010,a
        and     #>$00ffff,a
        move    a1,x:(r7+$1)
        move    x:(r7+$5),a
        and     #>$00ffff,a
        move    a1,x:(r7+$4)

pknhc0_pulse_compare_width:
        ; Negative phase => arithmetic phase>>8 is negative, so any u16 width
        ; is greater. Positive phase with high>=0x100 has >>8 >=65536, so no
        ; u16 width can be greater. Otherwise compare the exact 0..65535 value.
        move    x:(r7+$1),a
        and     #>$00ffff,a
        btst    #15,a1
        jcs     pknhc0_pulse_positive_contribution
        cmp     #>$0100,a
        bge     pknhc0_pulse_negative_contribution

        asl     #$8,a,a
        move    a1,b
        move    x:(r7+$0),a
        lsr     #$8,a
        add     a,b                      ; B = phase >> 8
        move    b1,x0
        move    x:(r7+$4),a
        and     #>$00ffff,a
        cmp     x0,a
        bgt     pknhc0_pulse_positive_contribution

pknhc0_pulse_negative_contribution:
        move    #>$fffc00,a             ; -1024
        rts
pknhc0_pulse_positive_contribution:
        move    #>$0003ff,a             ; +1023
        rts

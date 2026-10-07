; PERKY Simple Drum v1.2.1 oscillator/interpolator.
;
; Compact oscillator state (r7):
;   +0/+1 phase u32 lo/hi
;   +2/+3 increment u32 lo/hi
;   +4/+5 current wave identity u32 lo/hi
;   +6/+7 next wave identity u32 lo/hi
;
; Authentic Simple Drum wave identities map to one direct-packed u16 stream:
;   $080222a0 -> ordinal 0 -> samples   0..255
;   $080226a0 -> ordinal 1 -> samples 256..511
;   $080228a0 -> ordinal 2 -> samples 512..767
; Packed stream begins at Y:$07a5 (three u16 samples in two DSP words).
;
; Shipping entry:
;   pk_simple_oscillator: r7=osc state, r5=100-word scratch, result A1 signed16
;
; Standalone executable entry:
;   state is X:r5+$40..+$47; n7 samples are rendered to stereo X:(r0)+.

pk_simple_oscillator_probe:
        move    #>$40,n5
        lua     (r5+n5),r7
        do      n7,pksdo_probe_done
        jsr     pk_simple_oscillator
        move    a1,x:(r0)+
        move    a1,x:(r0)+
pksdo_probe_done:
        nop
        rts

pk_simple_oscillator:
        ; Exact modulo-2^32 phase += increment using two 16-bit limbs.
        move    x:(r7+$0),a
        move    x:(r7+$2),x0
        add     x0,a
        move    #>$0,y0
        btst    #16,a1
        bcc     pksdo_add_no_carry
        move    #>$1,y0
pksdo_add_no_carry:
        move    a1,b
        and     #>$00ffff,b
        move    b1,x:(r7+$0)
        move    x:(r7+$1),a
        move    x:(r7+$3),x0
        add     x0,a
        add     y0,a
        and     #>$00ffff,a
        move    a1,x:(r7+$1)

        ; Native condition is signed32(phase) > $00100000, strictly greater.
        move    x:(r7+$1),a
        btst    #15,a1
        bcs     pksdo_phase_ready        ; negative signed phase never wraps
        cmp     #>$0010,a
        bgt     pksdo_phase_wrap
        blt     pksdo_phase_ready
        move    x:(r7+$0),a
        tst     a
        bgt     pksdo_phase_wrap
        bra     pksdo_phase_ready

pksdo_phase_wrap:
        move    x:(r7+$1),a
        sub     #>$0010,a
        and     #>$00ffff,a
        move    a1,x:(r7+$1)

        ; Deferred table switch occurs only on phase wrap.
        move    x:(r7+$4),a
        move    x:(r7+$6),x0
        cmp     x0,a
        bne     pksdo_switch_wave
        move    x:(r7+$5),a
        move    x:(r7+$7),x0
        cmp     x0,a
        beq     pksdo_phase_ready
pksdo_switch_wave:
        move    x:(r7+$6),a
        move    a1,x:(r7+$4)
        move    x:(r7+$7),a
        move    a1,x:(r7+$5)

pksdo_phase_ready:
        ; Resolve authentic current wave identity to packed global base.
        move    x:(r7+$5),a
        cmp     #>$0802,a
        bne     pksdo_unknown_wave
        move    x:(r7+$4),a
        cmp     #>$22a0,a
        beq     pksdo_wave0
        cmp     #>$26a0,a
        beq     pksdo_wave1
        cmp     #>$28a0,a
        beq     pksdo_wave2
        cmp     #>$24a0,a
        beq     pksdo_wave3
        bra     pksdo_unknown_wave
pksdo_wave0:
        clr     a
        move    a1,x:(r5+$59)
        bra     pksdo_have_wave
pksdo_wave1:
        move    #>$000100,a
        move    a1,x:(r5+$59)
        bra     pksdo_have_wave
pksdo_wave2:
        move    #>$000200,a
        move    a1,x:(r5+$59)
        bra     pksdo_have_wave
pksdo_wave3:
        ; Complex Drum V2 also selects the neighboring 0x24a0 table. The
        ; ordinary Simple Drum bank remains three tables; Complex's payload
        ; appends this fourth table at ordinal 3.
        move    #>$000300,a
        move    a1,x:(r5+$59)
        bra     pksdo_have_wave
pksdo_unknown_wave:
        clr     a
        rts

pksdo_have_wave:
        ; local index = (phase >> 12) & $ff.
        move    x:(r7+$0),a
        move    a1,b
        and     #>$00f000,b
        lsr     #$c,b
        move    b1,x0
        move    x:(r7+$1),a
        and     #>$00000f,a
        asl     #$4,a,a
        add     x0,a
        and     #>$0000ff,a
        move    a1,x:(r5+$52)

        ; fraction = phase & $fff.
        move    x:(r7+$0),a
        and     #>$000fff,a
        move    a1,x:(r5+$53)

        ; first = wave[local], second = wave[(local+1)&255].
        move    x:(r5+$52),a
        move    x:(r5+$59),x0
        add     x0,a
        move    a1,x0
        jsr     pksdo_read_s16
        move    a1,x:(r5+$54)

        move    x:(r5+$52),a
        add     #>$1,a
        and     #>$0000ff,a
        move    x:(r5+$59),x0
        add     x0,a
        move    a1,x0
        jsr     pksdo_read_s16
        move    a1,x:(r5+$55)

        ; signed17 delta * unsigned12 fraction, arithmetic >>12.
        move    x:(r5+$55),a
        move    x:(r5+$54),x0
        sub     x0,a
        move    a1,x0
        move    x:(r5+$53),y0
        mpy     y0,x0,a
        asr     #$d,a,a                 ; fractional MPY alignment + >>12
        move    a0,a
        move    x:(r5+$54),x0
        add     x0,a
        and     #>$00ffff,a
        ; Sign-extend returned signed16 to signed24.
        btst    #15,a1
        bcc     pksdo_sample_ready
        sub     #>$010000,a
pksdo_sample_ready:
        rts

; input x0 = global packed-u16 index 0..767
; output A1 = sign-extended signed16 sample
pksdo_read_s16:
        move    x0,x:(r5+$58)
        ; q=floor(index/3) using exact reciprocal over this range.
        move    #>$00aaab,y0
        mpyuu   x0,y0,a
        asr     #$1,a,a
        asr     #$10,a,a
        move    a0,x1
        move    x1,b
        and     #>$00ffff,b
        lsr     b
        move    b1,x1

        ; remainder = index - 3*q.
        move    x1,b
        asl     b
        add     x1,b
        move    b1,y0
        move    x:(r5+$58),a
        sub     y0,a
        move    a1,y1

        ; pair pointer = Y:$07a5 + 2*q.
        move    x1,b
        asl     b
        move    b1,n1
        move    #>$0007a5,r1
        lua     (r1+n1),r2

        move    y1,a
        tst     a
        beq     pksdo_read_r0
        cmp     #>$1,a
        beq     pksdo_read_r1
pksdo_read_r2:
        move    y:(r2+$1),a
        lsr     #$8,a
        and     #>$00ffff,a
        bra     pksdo_read_sign
pksdo_read_r1:
        move    y:(r2),a
        lsr     #$10,a
        and     #>$0000ff,a
        move    a1,x1
        move    y:(r2+$1),b
        and     #>$0000ff,b
        asl     #$8,b,b
        add     x1,b
        and     #>$00ffff,b
        move    b1,a
        bra     pksdo_read_sign
pksdo_read_r0:
        move    y:(r2),a
        and     #>$00ffff,a
pksdo_read_sign:
        btst    #15,a1
        bcc     pksdo_read_done
        sub     #>$010000,a
pksdo_read_done:
        rts

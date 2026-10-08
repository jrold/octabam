; Authentic PĒRKONS v1.2.1 Noise/Tone physical M1 / Waveform2 renderer.
;
; Exact compact ABI is modules/perky/noise_tone_wave2_compact.py:
;   r6+$00 velocity u8
;   r6+$01 mute/bypass u8
;   r6+$02..$0c linear envelope (resonator_compact ENV layout)
;   r6+$0d/$0e phase u32 lo/hi
;   r6+$0f/$10 increment u32 lo/hi
;   r6+$11/$12 phase offset u32 lo/hi
;   r6+$13/$14 current 32-bit original wave identity
;   r6+$15/$16 next    32-bit original wave identity
;   r6+$17/$18 phase reduction u32 lo/hi
;
; Caller:
;   r0 = X stereo output
;   r5 = common 100-word X scratch
;   r6 = persistent 25-word M1 compact voice
;   n7 = sample count
;
; Required linked routines:
;   pk_envelope_probe
;   pk_u32_add / pk_u32_sub / pk_u32_mul_low / pk_u32_asr
;
; Build substitutions from the authentic Noise/Tone asset manifest:
;   @NT_W2_BASE@  packed Y base of concatenated 2048-sample waves
;   @NT_W2_W0L@/@NT_W2_W0H@ original identity for ordinal 0
;   @NT_W2_W1L@/@NT_W2_W1H@ original identity for ordinal 1
;
; Values are kept in the same two-u16-limb representation as the qualified
; Python compact oracle. No floating point, approximation or resampling.

pk_nt_wave2_voice:
        do      n7,pkntw_block_done

        ; ---- linear amplitude envelope ------------------------------------
        ; M1's original Waveform2 envelope shape is linear (shape=0). Copy the
        ; 11-word compact envelope to the already qualified scratch ABI.
        move    x:(r6+$2),a
        move    a1,x:(r5+$40)
        move    x:(r6+$3),a
        move    a1,x:(r5+$41)
        move    x:(r6+$4),a
        move    a1,x:(r5+$42)
        move    x:(r6+$5),a
        move    a1,x:(r5+$43)
        move    x:(r6+$6),a
        move    a1,x:(r5+$44)
        move    x:(r6+$7),a
        move    a1,x:(r5+$45)
        move    x:(r6+$8),a
        move    a1,x:(r5+$46)
        move    x:(r6+$9),a
        move    a1,x:(r5+$47)
        move    x:(r6+$a),a
        move    a1,x:(r5+$48)
        move    x:(r6+$b),a
        move    a1,x:(r5+$49)
        move    x:(r6+$c),a
        move    a1,x:(r5+$50)
        jsrl    pk_envelope_probe
        move    x:(r5+$40),a
        move    a1,x:(r6+$2)
        move    x:(r5+$45),a
        move    a1,x:(r6+$7)
        move    x:(r5+$46),a
        move    a1,x:(r6+$8)
        move    x:(r5+$51),a
        move    a1,x:(r5+$60)           ; amp u16

        ; ---- phase reduction ----------------------------------------------
        ; if unsigned phase > unsigned reduction: phase -= reduction.
        move    x:(r6+$e),a             ; phase high
        move    x:(r6+$18),x0           ; reduction high
        cmp     x0,a
        bgt     pkntw_reduce
        blt     pkntw_after_reduce
        move    x:(r6+$d),a             ; equal highs: compare low limbs
        move    x:(r6+$17),x0
        cmp     x0,a
        ble     pkntw_after_reduce
pkntw_reduce:
        move    x:(r6+$d),a
        move    a1,x:(r5+$0)
        move    x:(r6+$e),a
        move    a1,x:(r5+$1)
        move    x:(r6+$17),a
        move    a1,x:(r5+$2)
        move    x:(r6+$18),a
        move    a1,x:(r5+$3)
        jsrl    pk_u32_sub
        move    x:(r5+$8),a
        move    a1,x:(r6+$d)
        move    x:(r5+$9),a
        move    a1,x:(r6+$e)
pkntw_after_reduce:

        ; phase += increment modulo 2^32.
        move    x:(r6+$d),a
        move    a1,x:(r5+$0)
        move    x:(r6+$e),a
        move    a1,x:(r5+$1)
        move    x:(r6+$f),a
        move    a1,x:(r5+$2)
        move    x:(r6+$10),a
        move    a1,x:(r5+$3)
        jsrl    pk_u32_add
        move    x:(r5+$8),a
        move    a1,x:(r6+$d)
        move    x:(r5+$9),a
        move    a1,x:(r6+$e)

        ; signed32(phase) > $00100000: subtract period and commit deferred wave.
        move    x:(r6+$e),a
        btst    #15,a1
        bcs     pkntw_phase_ready
        cmp     #>$0010,a
        bgt     pkntw_wrap
        blt     pkntw_phase_ready
        move    x:(r6+$d),a
        tst     a
        ble     pkntw_phase_ready
pkntw_wrap:
        move    x:(r6+$d),a
        move    a1,x:(r5+$0)
        move    x:(r6+$e),a
        move    a1,x:(r5+$1)
        clr     a
        move    a1,x:(r5+$2)
        move    #>$0010,a
        move    a1,x:(r5+$3)
        jsrl    pk_u32_sub
        move    x:(r5+$8),a
        move    a1,x:(r6+$d)
        move    x:(r5+$9),a
        move    a1,x:(r6+$e)
        move    x:(r6+$15),a
        move    a1,x:(r6+$13)
        move    x:(r6+$16),a
        move    a1,x:(r6+$14)
pkntw_phase_ready:

        ; lookup = phase; if offset != 0, lookup += offset and wrap signed > period.
        move    x:(r6+$d),a
        move    a1,x:(r5+$62)           ; lookup lo
        move    x:(r6+$e),a
        move    a1,x:(r5+$63)           ; lookup hi
        move    x:(r6+$11),a
        move    x:(r6+$12),x0
        or      x0,a
        tst     a
        beq     pkntw_lookup_ready

        move    x:(r5+$62),a
        move    a1,x:(r5+$0)
        move    x:(r5+$63),a
        move    a1,x:(r5+$1)
        move    x:(r6+$11),a
        move    a1,x:(r5+$2)
        move    x:(r6+$12),a
        move    a1,x:(r5+$3)
        jsrl    pk_u32_add
        move    x:(r5+$8),a
        move    a1,x:(r5+$62)
        move    x:(r5+$9),a
        move    a1,x:(r5+$63)

        ; signed32(lookup) > $00100000.
        move    x:(r5+$63),a
        btst    #15,a1
        bcs     pkntw_lookup_ready
        cmp     #>$0010,a
        bgt     pkntw_lookup_wrap
        blt     pkntw_lookup_ready
        move    x:(r5+$62),a
        tst     a
        ble     pkntw_lookup_ready
pkntw_lookup_wrap:
        move    x:(r5+$62),a
        move    a1,x:(r5+$0)
        move    x:(r5+$63),a
        move    a1,x:(r5+$1)
        clr     a
        move    a1,x:(r5+$2)
        move    #>$0010,a
        move    a1,x:(r5+$3)
        jsrl    pk_u32_sub
        move    x:(r5+$8),a
        move    a1,x:(r5+$62)
        move    x:(r5+$9),a
        move    a1,x:(r5+$63)
pkntw_lookup_ready:

        ; Resolve current original 32-bit identity to packed-wave ordinal.
        move    x:(r6+$13),a
        cmp     #>@NT_W2_W0L@,a
        bne     pkntw_try_wave1
        move    x:(r6+$14),a
        cmp     #>@NT_W2_W0H@,a
        bne     pkntw_try_wave1
        clr     a
        move    a1,x:(r5+$61)           ; global sample base 0
        bra     pkntw_wave_ready
pkntw_try_wave1:
        move    x:(r6+$13),a
        cmp     #>@NT_W2_W1L@,a
        bne     pkntw_missing_wave
        move    x:(r6+$14),a
        cmp     #>@NT_W2_W1H@,a
        bne     pkntw_missing_wave
        move    #>$000800,a
        move    a1,x:(r5+$61)           ; global sample base 2048
        bra     pkntw_wave_ready
pkntw_missing_wave:
        clr     a
        move    a1,x:(r5+$57)           ; oscillator=0
        bra     pkntw_have_osc

pkntw_wave_ready:
        ; local index=(lookup>>9)&$7ff, fraction=lookup&$1ff.
        move    x:(r5+$62),a
        move    a1,b
        and     #>$00fe00,b
        lsr     #$9,b
        move    b1,x0
        move    x:(r5+$63),a
        and     #>$00000f,a
        asl     #$7,a,a
        add     x0,a
        and     #>$0007ff,a
        move    a1,x:(r5+$52)           ; local index
        move    x:(r5+$62),a
        and     #>$0001ff,a
        move    a1,x:(r5+$53)           ; fraction

        ; first packed signed16 sample.
        move    x:(r5+$52),a
        move    x:(r5+$61),x0
        add     x0,a
        move    a1,x0
        jsrl    pk_nt_wave2_read_s16
        move    a1,x:(r5+$54)

        ; second uses (local+1)&$7ff in the SAME wave ordinal.
        move    x:(r5+$52),a
        add     #>$1,a
        and     #>$0007ff,a
        move    x:(r5+$61),x0
        add     x0,a
        move    a1,x0
        jsrl    pk_nt_wave2_read_s16
        move    a1,x:(r5+$55)

        ; osc=signed16(first + ASR32(low32((second-first)*fraction),9)).
        move    x:(r5+$55),a
        move    x:(r5+$54),x0
        sub     x0,a
        move    a1,b
        and     #>$00ffff,b
        move    b1,x:(r5+$0)
        move    #>$0,x0
        tst     a
        jpl     pkntw_delta_positive
        move    #>$00ffff,x0
pkntw_delta_positive:
        move    x0,x:(r5+$1)
        move    x:(r5+$53),a
        move    a1,x:(r5+$2)
        clr     a
        move    a1,x:(r5+$3)
        jsrl    pk_u32_mul_low
        move    x:(r5+$8),a
        move    a1,x:(r5+$0)
        move    x:(r5+$9),a
        move    a1,x:(r5+$1)
        move    #>$9,a
        move    a1,x:(r5+$4)
        jsrl    pk_u32_asr

        move    x:(r5+$54),a
        move    a1,b
        and     #>$00ffff,b
        move    b1,x:(r5+$0)
        move    #>$0,x0
        tst     a
        jpl     pkntw_first_positive
        move    #>$00ffff,x0
pkntw_first_positive:
        move    x0,x:(r5+$1)
        move    x:(r5+$8),a
        move    a1,x:(r5+$2)
        move    x:(r5+$9),a
        move    a1,x:(r5+$3)
        jsrl    pk_u32_add
        move    x:(r5+$8),a
        and     #>$00ffff,a
        move    a1,x:(r5+$57)
pkntw_have_osc:

        ; value=ASR32(low32(signed16(osc)*amp),17).
        move    x:(r5+$57),a
        move    a1,b
        and     #>$00ffff,b
        move    b1,x:(r5+$0)
        move    #>$0,x0
        tst     a
        jpl     pkntw_osc_positive
        move    #>$00ffff,x0
pkntw_osc_positive:
        move    x0,x:(r5+$1)
        move    x:(r5+$60),a
        and     #>$00ffff,a
        move    a1,x:(r5+$2)
        clr     a
        move    a1,x:(r5+$3)
        jsrl    pk_u32_mul_low
        move    x:(r5+$8),a
        move    a1,x:(r5+$0)
        move    x:(r5+$9),a
        move    a1,x:(r5+$1)
        move    #>$11,a
        move    a1,x:(r5+$4)
        jsrl    pk_u32_asr

        ; velocity_scale(value,velocity)=ASR32(low32(value*(velocity&$ff)),8).
        move    x:(r5+$8),a
        move    a1,x:(r5+$0)
        move    x:(r5+$9),a
        move    a1,x:(r5+$1)
        move    x:(r6+$0),a
        and     #>$0000ff,a
        move    a1,x:(r5+$2)
        clr     a
        move    a1,x:(r5+$3)
        jsrl    pk_u32_mul_low
        move    x:(r5+$8),a
        move    a1,x:(r5+$0)
        move    x:(r5+$9),a
        move    a1,x:(r5+$1)
        move    #>$8,a
        move    a1,x:(r5+$4)
        jsrl    pk_u32_asr

        ; Exact Python/original clamp: -32768 .. +32767.
        move    x:(r5+$9),a
        btst    #15,a1
        bcs     pkntw_clamp_negative
        tst     a
        bne     pkntw_clamp_high
        move    x:(r5+$8),a
        cmp     #>$007fff,a
        bgt     pkntw_clamp_high
        bra     pkntw_clamp_copy
pkntw_clamp_negative:
        cmp     #>$00ffff,a
        bne     pkntw_clamp_low
        move    x:(r5+$8),a
        cmp     #>$008000,a
        blt     pkntw_clamp_low
        bra     pkntw_clamp_copy
pkntw_clamp_high:
        move    #>$007fff,a
        bra     pkntw_output_ready
pkntw_clamp_low:
        move    #>$008000,a
        sub     #>$010000,a             ; sign-extended -32768 in 24-bit A
        bra     pkntw_output_ready
pkntw_clamp_copy:
        move    x:(r5+$8),a
        and     #>$00ffff,a
        btst    #15,a1
        bcc     pkntw_output_ready
        sub     #>$010000,a
pkntw_output_ready:
        ; Mute/bypass field returns exact zero after state still advances.
        move    x:(r6+$1),x0
        tst     x0
        beq     pkntw_write
        clr     a
pkntw_write:
        move    a1,x:(r0)+
        move    a1,x:(r0)+

pkntw_block_done:
        nop
        rts

; Packed u16 random access for concatenated Waveform2 2048-sample waves.
;   x0 = global sample index 0..4095
; returns A1 as sign-extended signed16 sample.
pk_nt_wave2_read_s16:
        move    x0,a
        move    a1,x:(r5+$56)           ; preserve global index
        move    #>$00aaab,y0
        mpyuu   x0,y0,a
        asr     #$1,a,a
        asr     #$10,a,a
        move    a0,x1
        move    x1,b
        and     #>$00ffff,b
        lsr     b
        move    b1,x1                   ; q=floor(n/3)

        move    x1,b
        asl     b
        add     x1,b
        move    b1,y0                   ; 3*q
        move    x:(r5+$56),a
        sub     y0,a
        move    a1,y1                   ; remainder 0..2

        move    x1,b
        asl     b
        move    b1,n1
        move    #>@NT_W2_BASE@,r1
        lua     (r1+n1),r2

        move    y1,a
        tst     a
        beq     pkntw_read_r0
        cmp     #>$1,a
        beq     pkntw_read_r1
pkntw_read_r2:
        move    y:(r2+$1),a
        lsr     #$8,a
        and     #>$00ffff,a
        bra     pkntw_read_sign
pkntw_read_r1:
        move    y:(r2),a
        lsr     #$10,a
        and     #>$0000ff,a
        move    a1,x1
        move    y:(r2+$1),b
        and     #>$0000ff,b
        asl     #$8,b,b
        add     x1,b
        move    b1,a
        and     #>$00ffff,a
        bra     pkntw_read_sign
pkntw_read_r0:
        move    y:(r2),a
        and     #>$00ffff,a
pkntw_read_sign:
        btst    #15,a1
        bcc     pkntw_read_done
        sub     #>$010000,a
pkntw_read_done:
        rts

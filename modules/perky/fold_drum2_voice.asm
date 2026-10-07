; PĒRKONS v1.2.1 Fold Drum 2 DSP56300 renderer candidate.
;
; Compact X state (51 words):
;   +$00 velocity, +$01 mute
;   +$02..+$09 oscillator A (ARM object +$2c)
;   +$0a..+$14 amplitude envelope
;   +$15..+$1f pitch envelope
;   +$20 raw pitch, +$21 pitch amount
;   +$22..+$29 oscillator B (ARM object +$f4)
;   +$2a mode, +$2b transient counter, +$2c fold
;   +$2d noise count, +$2e noise rate, +$2f noise sample
;   +$30 last faded amplitude, +$31 crossfade counter
;   +$32 primary selector (0=A, 1=B)
;   +$34/+35 prepared base frequency
;
; Uses the already-qualified Simple/Fold1 envelope, oscillator, frequency,
; packed-wave, pitch-cache and RNG helpers.  The absolute ARM oscillator
; pointers at +$128/+12c are normalized to +$32 so the DSP state is relocatable.

pk_fold2_voice:
        move    r6,a
        move    a1,x:(r5+$60)

        do      n7,pkf2_samples_done

        ; amplitude envelope
        move    x:(r5+$60),r6
        lua     (r6+$a),r6
        jsr     pk_simple_envelope
        move    a1,x:(r5+$5d)

        ; pitch envelope
        move    x:(r5+$60),r6
        lua     (r6+$15),r6
        jsr     pk_simple_envelope
        move    a1,x:(r5+$62)

        ; factor = ((pitchEnv & $1fff) + $2000) >> (13-(pitchEnv>>13)) - 1
        move    x:(r5+$60),r6
        move    x:(r5+$62),a
        move    a1,b
        lsr     #$d,b
        move    b1,x0
        move    #>$d,b
        sub     x0,b
        move    b1,x0
        and     #>$1fff,a
        add     #>$2000,a
        asr     x0,a,a
        sub     #>$1,a

        ; frequency = preparedBase + (pitchAmount * factor >> 9)
        move    a1,x0
        move    x:(r6+$21),y0
        mpyuu   x0,y0,a
        asr     #$a,a,a
        move    a0,a
        move    x:(r6+$34),x0
        add     x0,a
        move    a1,x0
        jsr     pk_simple_frequency

        ; Keep the returned 32-bit oscillator increment while choosing p1.
        move    a1,b
        and     #>$ffff,b
        move    b1,x:(r5+$63)
        asr     #$10,a,a
        and     #>$ffff,a
        move    a1,x:(r5+$64)

        move    x:(r6+$32),a
        tst     a
        bne     pkf2_primary_b
pkf2_primary_a:
        lua     (r6+$2),r7
        bra     pkf2_primary_ready
pkf2_primary_b:
        lua     (r6+$22),r7
pkf2_primary_ready:
        move    x:(r5+$63),a
        move    a1,x:(r7+$2)
        move    x:(r5+$64),a
        move    a1,x:(r7+$3)

        ; Render p1.
        jsr     pk_simple_oscillator
        move    a1,x:(r5+$5e)

        ; Render p2 (the other fixed oscillator).
        move    x:(r5+$60),r6
        move    x:(r6+$32),a
        tst     a
        bne     pkf2_secondary_a
pkf2_secondary_b:
        lua     (r6+$22),r7
        bra     pkf2_secondary_ready
pkf2_secondary_a:
        lua     (r6+$2),r7
pkf2_secondary_ready:
        jsr     pk_simple_oscillator
        move    a1,x:(r5+$5f)

        ; amplitude -= fade only when fade < amplitude (unsigned values live
        ; in positive 24-bit DSP words, so ordinary compare is sufficient).
        move    x:(r5+$60),r6
        move    x:(r5+$5d),a
        move    x:(r6+$31),x0
        cmp     x0,a
        bgt     pkf2_amp_sub
        bra     pkf2_amp_ready
pkf2_amp_sub:
        sub     x0,a
pkf2_amp_ready:
        move    a1,x:(r5+$5d)
        move    a1,x:(r6+$30)

        ; firstProduct = (amplitude * firstOsc) >> 16
        move    x:(r5+$5e),x0
        move    x:(r5+$5d),y0
        mpysu   x0,y0,a
        asr     #$11,a,a
        move    a0,a
        move    a1,x:(r5+$63)

        ; secondProduct = (fade * secondOsc) >> 16
        move    x:(r5+$5f),x0
        move    x:(r6+$31),y0
        mpysu   x0,y0,a
        asr     #$11,a,a
        move    a0,a
        move    x:(r5+$63),x0
        add     x0,a
        asr     #$1,a,a
        move    a1,x:(r5+$5e)          ; original crossfaded sample

        ; fade = max(fade, $88) - $88.
        move    x:(r6+$31),a
        cmp     #>$88,a
        blt     pkf2_fade_zero
        sub     #>$88,a
        bra     pkf2_fade_store
pkf2_fade_zero:
        clr     a
        bra     pkf2_fade_store
pkf2_fade_store:
        move    a1,x:(r6+$31)

        ; Fold original exactly as Fold Drum 1.
        move    x:(r5+$5e),x0
        move    x:(r6+$2c),a
        asl     #$8,a,a
        move    a1,a
        asr     #$8,a,a
        add     #>$100,a
        move    a1,y0
        mpy     y0,x0,a
        asr     #$9,a,a
        move    a0,a
        add     #>$8000,a
        and     #>$1ffff,a
        move    a1,a
        cmp     #>$10000,a
        blt     pkf2_rising
        move    a1,x0
        move    #>$18000,a
        sub     x0,a
        bra     pkf2_folded
pkf2_rising:
        sub     #>$8000,a
pkf2_folded:
        move    a1,x:(r5+$5f)

        ; Shared transient law, with Fold2's compact offsets.
        move    x:(r6+$2b),a
        cmp     #>$210,a
        bgt     pkf2_transient_done
        move    x:(r6+$2a),a
        tst     a
        beq     pkf2_pulse
        cmp     #>$2,a
        bne     pkf2_counter_step

        ; pknv_noise reads +$c/+d/+e relative to r6.  Rebase so those are
        ; Fold2 +$2d/+2e/+2f.
        lua     (r6+$21),r6
        jsr     pknv_noise
        move    x:(r5+$60),r6
        move    x:(r5+$61),a
        asl     #$8,a,a
        move    a1,a
        asr     #$8,a,a
        move    a1,x0
        move    x:(r6+$2b),a
        cmp     #>$110,a
        bgt     pkf2_counter_step
        cmp     #>$8f,a
        bgt     pkf2_noise_tail
        move    #>$b,y0
        mpysu   x0,y0,a
        asr     #$5,a,a
        move    a0,a
        bra     pkf2_add_noise
pkf2_noise_tail:
        move    a1,y0
        move    #>$110,a
        sub     y0,a
        move    a1,y0
        mpysu   x0,y0,a
        asr     #$9,a,a
        move    a0,x0
        move    #>$2c,y0
        mpysu   x0,y0,a
        asr     #$7,a,a
        move    a0,a
pkf2_add_noise:
        move    x:(r5+$5f),x0
        add     x0,a
        move    a1,x:(r5+$5f)
        bra     pkf2_counter_step
pkf2_pulse:
        move    x:(r5+$5f),a
        add     #>$3fff,a
        move    a1,x:(r5+$5f)
pkf2_counter_step:
        move    x:(r6+$2b),a
        add     #>$1,a
        move    a1,x:(r6+$2b)
pkf2_transient_done:

        move    x:(r6+$1),a
        tst     a
        bne     pkf2_muted

        ; mixed = (folded + original) >> 1; then velocityScale(mixed).
        move    x:(r5+$5f),a
        move    x:(r5+$5e),x0
        add     x0,a
        asr     #$1,a,a
        move    a1,x0
        move    x:(r6),y0
        mpysu   x0,y0,a
        asr     #$9,a,a
        move    a0,a
        bra     pkf2_store

pkf2_muted:
        clr     a
pkf2_store:
        move    a1,x:(r0)+
        move    a1,x:(r0)+

pkf2_samples_done:
        nop
        move    x:(r5+$60),r6
        rts

; Fold Drum 2 production PK/Y1 control seam.
;
; Inputs:
;   r4 = prepared PK/Y1 byte record
;   r6 = 51-word Fold Drum 2 compact state (58-word overlay is allowed)
;
; Clobbers a, b, x0.
;
; This routine intentionally applies ONLY the control/update fields already
; proven common to the original v1.2.1 Fold-family control law.  It does not
; implement a trigger and must not touch OSC_A/B, transient/noise state,
; FADE_SAVED, FADE, or PRIMARY.  Fold Drum 2 active retrigger behavior stays
; gated by the original-ARM retrigger corpus before browser exposure.
;
; PK/Y1 bytes:
;   +08/+09 TUNE   -> raw pitch           state +$20
;   +0a/+0b DECAY  -> amp envelope decay  state +$14
;   +0c/+0d P1     -> fold                state +$2c
;   +0e/+0f P2     -> pitch-env amount    state +$21
;   +10      mode  -> firmware mode 1/2/0 state +$2a
;   +11      gate  -> amp envelope gate   state +$0e
;
; The pitch-envelope decay is fixed at 43 by the original Fold-family update.
;
pk_fold2_apply_controls:
        ; TUNE: big-endian prepared u16.
        move    x:(r4+$8),a
        and     #>$ff,a
        asl     #$8,a,a
        move    x:(r4+$9),b
        and     #>$ff,b
        move    b1,x0
        add     x0,a
        move    a1,x:(r6+$20)

        ; DECAY: prepared amp-envelope decay.
        move    x:(r4+$a),a
        and     #>$ff,a
        asl     #$8,a,a
        move    x:(r4+$b),b
        and     #>$ff,b
        move    b1,x0
        add     x0,a
        move    a1,x:(r6+$14)

        ; P1: Fold amount.
        move    x:(r4+$c),a
        and     #>$ff,a
        asl     #$8,a,a
        move    x:(r4+$d),b
        and     #>$ff,b
        move    b1,x0
        add     x0,a
        move    a1,x:(r6+$2c)

        ; P2: pitch-envelope amount.
        move    x:(r4+$e),a
        and     #>$ff,a
        asl     #$8,a,a
        move    x:(r4+$f),b
        and     #>$ff,b
        move    b1,x0
        add     x0,a
        move    a1,x:(r6+$21)

        ; Original Fold-family pitch-envelope decay is fixed at 43.
        move    #>$2b,a
        move    a1,x:(r6+$1f)

        ; Original physical mode order is panel 0/1/2 -> firmware 1/2/0.
        move    x:(r4+$10),a
        and     #>$ff,a
        tst     a
        beq     pkf2_mode0
        cmp     #>$1,a
        beq     pkf2_mode1
        clr     a
        bra     pkf2_mode_ready
pkf2_mode0:
        move    #>$1,a
        bra     pkf2_mode_ready
pkf2_mode1:
        move    #>$2,a
pkf2_mode_ready:
        move    a1,x:(r6+$2a)

        ; Amp-envelope gate/hold bit prepared by the transport.
        move    x:(r4+$11),a
        and     #>$1,a
        move    a1,x:(r6+$e)
        rts

; Common update writes the direct u16 pitch-table entry to oscillator A's
; 32-bit increment, even when B is primary. The renderer's frequency
; conversion is a separate operation. r5 supplies shared decoder scratch;
; this routine clobbers r1..r4, n1..n3, a/b and x/y data registers.
pk_fold2_apply_pitch:
        jsr     pk_simple_pitch_at
        move    a1,x:(r6+$4)
        clr     a
        move    a1,x:(r6+$5)
        rts

; PĒRKONS v1.2.1 Karplus live-control application for the HW4 audition.
;
; Input:
;   r4 = prepared PK/Y1 record from control_hw4_candidate.c
;   r6 = 58-word track overlay; first 32 words are compact Karplus state
;
; PK/Y1 control bytes:
;   +08/+09 TUNE   prepared 0..4095, big-endian
;   +0a/+0b DECAY  prepared 0..4095, big-endian
;   +0c/+0d EDGE   prepared 0..4095, big-endian
;   +0e/+0f TWANG  prepared 0..4095, big-endian
;   +10      MODE  physical panel index 0/1/2
;
; Exact steady-state v1.2.1 update ownership:
;   compact +$07  amp-envelope gate
;   compact +$0c  amp-envelope attack (constant authentic init; untouched here)
;   compact +$0d  amp-envelope decay rate
;   compact +$12  resonant-filter coefficient
;   compact +$19  excitation/TWANG target
;   compact +$1b/+1c  32-bit delay distance
;   compact +$02  MODE (separate from ARM common-update ownership)
;
; Overlay +$20 is the Karplus has-triggered bit. +$21..+$27 are private to
; this HW4 profile and shadow the seven live words that a generated original
; trigger plan is allowed to disturb. The seam snapshots them after applying
; the current OT controls and restores them immediately after first/active
; trigger, matching the original firmware's trigger -> update -> render order.
;
; The three nonlinear functions are complete 4096-entry u16 tables generated
; locally from the pinned original v1.2.1 update arithmetic. They use the same
; 3-u16-in-2-DSP-word packing already qualified for PERKY wave/table assets.
;
; Placeholders are resolved by build_hw4_audition_candidate.py:
;   @K_TUNE_LUT@       Y base, TUNE prepared -> delay
;   @K_DECAY_LUT@      Y base, DECAY prepared -> envelope decrement
;   @K_EDGE_LUT@       Y base, EDGE prepared -> filter coefficient
;   @K_GATE_THRESHOLD@ authentic prepared DECAY gate threshold
;
; This first hardware live-control path is deliberately endpoint-exact and
; immediate. It does not emulate the ARM UI-rate transition smoother, so an OT
; p-lock reaches its exact final PĒRKONS control state without a hidden ramp.

pk_karplus_apply_controls:
        ; TUNE -> exact 2K delay-ring distance.
        move    x:(r4+$8),a
        and     #>$ff,a
        asl     #$8,a,a
        move    x:(r4+$9),b
        and     #>$ff,b
        move    b1,x0
        add     x0,a
        move    a1,n1
        move    #>@K_TUNE_LUT@,r1
        jsrl    pk_karplus_lut_u16
        move    a1,x:(r6+$1b)
        clr     a
        move    a1,x:(r6+$1c)

        ; DECAY controls both the amplitude-envelope decrement and the original
        ; gate/hold condition (threshold <= prepared DECAY).
        move    x:(r4+$a),a
        and     #>$ff,a
        asl     #$8,a,a
        move    x:(r4+$b),b
        and     #>$ff,b
        move    b1,x0
        add     x0,a
        move    a1,n1
        cmp     #>@K_GATE_THRESHOLD@,a
        blt     pkk_control_gate_off
        move    #>$1,a
        move    a1,x:(r6+$7)
        bra     pkk_control_gate_ready
pkk_control_gate_off:
        clr     a
        move    a1,x:(r6+$7)
pkk_control_gate_ready:
        move    #>@K_DECAY_LUT@,r1
        jsrl    pk_karplus_lut_u16
        move    a1,x:(r6+$d)

        ; EDGE -> exact resonant-filter coefficient.
        move    x:(r4+$c),a
        and     #>$ff,a
        asl     #$8,a,a
        move    x:(r4+$d),b
        and     #>$ff,b
        move    b1,x0
        add     x0,a
        move    a1,n1
        move    #>@K_EDGE_LUT@,r1
        jsrl    pk_karplus_lut_u16
        move    a1,x:(r6+$12)

        ; TWANG -> original excitation target: prepared control >> 1.
        move    x:(r4+$e),a
        and     #>$ff,a
        asl     #$8,a,a
        move    x:(r4+$f),b
        and     #>$ff,b
        move    b1,x0
        add     x0,a
        lsr     #$1,a,a
        move    a1,x:(r6+$19)

        ; Physical panel M1/M2/M3 -> Karplus firmware mode 1/0/2.
        move    x:(r4+$10),a
        and     #>$ff,a
        tst     a
        beq     pkk_control_mode0
        cmp     #>$1,a
        beq     pkk_control_mode1
        move    #>$2,a
        bra     pkk_control_mode_ready
pkk_control_mode0:
        move    #>$1,a
        bra     pkk_control_mode_ready
pkk_control_mode1:
        clr     a
pkk_control_mode_ready:
        move    a1,x:(r6+$2)
        rts

; Save the exact post-update control surface in spare words of this track's
; 58-word HW4 overlay. Generated original trigger plans operate on the compact
; first 32 words only, so +$21..+$27 survive the trigger.
pk_karplus_shadow_controls:
        move    x:(r6+$2),a
        move    a1,x:(r6+$21)
        move    x:(r6+$7),a
        move    a1,x:(r6+$22)
        move    x:(r6+$d),a
        move    a1,x:(r6+$23)
        move    x:(r6+$12),a
        move    a1,x:(r6+$24)
        move    x:(r6+$19),a
        move    a1,x:(r6+$25)
        move    x:(r6+$1b),a
        move    a1,x:(r6+$26)
        move    x:(r6+$1c),a
        move    a1,x:(r6+$27)
        rts

; Original v1.2.1 runs update() after trigger/retrigger. Restore the exact
; current OT-derived control surface after the generated trigger mutation and
; before rendering the triggered suffix.
pk_karplus_restore_controls:
        move    x:(r6+$21),a
        move    a1,x:(r6+$2)
        move    x:(r6+$22),a
        move    a1,x:(r6+$7)
        move    x:(r6+$23),a
        move    a1,x:(r6+$d)
        move    x:(r6+$24),a
        move    a1,x:(r6+$12)
        move    x:(r6+$25),a
        move    a1,x:(r6+$19)
        move    x:(r6+$26),a
        move    a1,x:(r6+$1b)
        move    x:(r6+$27),a
        move    a1,x:(r6+$1c)
        rts

; Decode one packed u16 table entry.
;
; Input:
;   n1 = entry index 0..4095
;   r1 = Y-memory packed table base
; Output:
;   a1 = decoded unsigned 16-bit value
; Clobbers a,b,x0,x1,y0,y1,r2,n2.
;
; Packing geometry for index n:
;   q = floor(n/3), r = n%3, pair = base + 2*q
;   r=0: pair[0] & $ffff
;   r=1: (pair[0] >> 16) | ((pair[1] & $ff) << 8)
;   r=2: (pair[1] >> 8) & $ffff
pk_karplus_lut_u16:
        move    n1,x0
        move    #>$00aaab,y0
        mpyuu   x0,y0,a
        asr     #$1,a,a
        asr     #$10,a,a
        move    a0,x1
        move    x1,b
        and     #>$00ffff,b
        lsr     b
        move    b1,x1                   ; q = floor(n/3)

        move    x1,b
        asl     b
        add     x1,b
        move    b1,y0                   ; 3*q
        move    x0,a
        sub     y0,a
        move    a1,y1                   ; remainder 0..2

        move    x1,b
        asl     b
        move    b1,n2
        lua     (r1+n2),r2              ; pair pointer

        move    y1,a
        tst     a
        beq     pkk_lut_r0
        cmp     #>$1,a
        beq     pkk_lut_r1

pkk_lut_r2:
        move    y:(r2+$1),a
        lsr     #$8,a
        and     #>$00ffff,a
        rts

pkk_lut_r1:
        move    y:(r2),a
        lsr     #$10,a
        and     #>$0000ff,a
        move    a1,x1
        move    y:(r2+$1),b
        and     #>$0000ff,b
        asl     #$8,b,b
        add     x1,b
        and     #>$00ffff,b
        move    b1,x0
        move    x0,a
        rts

pkk_lut_r0:
        move    y:(r2),a
        and     #>$00ffff,a
        rts

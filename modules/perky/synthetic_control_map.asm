; PERKY synthetic Noise/Tone control mapper -- DEVELOPMENT CANARY ONLY.
;
; This routine makes the five Octatrack source controls audibly functional
; before the real PĒRKONS v1.2.1 update/control law is ported.  It is kept as
; one isolated routine so the final firmware can replace this mapping without
; touching the already-qualified sample renderer.
;
; Caller:
;   r4 = PK/Y1 source record (DSP words)
;   r6 = 58-word persistent compact voice
;
; PK/Y1 parameter words begin at record word 8:
;   r4+$08 TUNE   0..127
;   r4+$09 DECAY  0..127
;   r4+$0a ENV    0..127
;   r4+$0b MIX    0..127
;   r4+$0e MODE   0..2
;
; Compact-voice fields changed here (ABI indices are decimal; assembler
; displacements below are hex):
;   +10/+11         attack/decay       -> $0a/$0b
;   +25/+26         osc1 increment     -> $19/$1a
;   +27..+30        osc1 wave IDs      -> $1b..$1e
;   +33/+34         osc2 increment     -> $21/$22
;   +35..+38        osc2 wave IDs      -> $23..$26
;   +39/+40         noise/tone mix     -> $27/$28
;
; Mapping is deliberately simple and deterministic, not a claim of PĒRKONS
; sonic equivalence. Wave identities are build-time substitutions shared with
; noise_tone_oscillator_packed.asm.

pk_synth_apply_controls:
        ; TUNE: two related musical-rate increments.  Keep high limbs zero.
        move    x:(r4+$8),a
        and     #>$00007f,a
        asl     #$8,a,a
        add     #>$001000,a
        move    a1,x:(r6+$19)
        clr     a
        move    a1,x:(r6+$1a)

        move    x:(r4+$8),a
        and     #>$00007f,a
        asl     #$7,a,a
        add     #>$000c00,a
        move    a1,x:(r6+$21)
        clr     a
        move    a1,x:(r6+$22)

        ; DECAY: larger panel values -> smaller decrement -> longer tail.
        move    x:(r4+$9),b
        and     #>$00007f,b
        move    b1,x0
        move    #>$00007f,a
        sub     x0,a
        asl     #$5,a,a
        add     #>$000200,a
        move    a1,x:(r6+$0b)

        ; ENV: synthetic envelope attack strength/rate control.
        move    x:(r4+$a),a
        and     #>$00007f,a
        asl     #$7,a,a
        add     #>$000800,a
        move    a1,x:(r6+$0a)

        ; MIX: exact 7-bit -> near-full 12-bit noise/tone balance.
        move    x:(r4+$b),a
        and     #>$00007f,a
        asl     #$5,a,a
        move    a1,x:(r6+$27)
        clr     a
        move    a1,x:(r6+$28)

        ; MODE: three visibly/audibly distinct wave pairs.
        move    x:(r4+$e),a
        and     #>$0000ff,a
        tst     a
        beq     pksc_mode0
        cmp     #>$1,a
        beq     pksc_mode1
        bra     pksc_mode2

pksc_mode0:
        move    #>@W0L@,a
        move    a1,x:(r6+$1b)
        move    a1,x:(r6+$1d)
        move    #>@W0H@,a
        move    a1,x:(r6+$1c)
        move    a1,x:(r6+$1e)
        move    #>@W1L@,a
        move    a1,x:(r6+$23)
        move    a1,x:(r6+$25)
        move    #>@W1H@,a
        move    a1,x:(r6+$24)
        move    a1,x:(r6+$26)
        rts

pksc_mode1:
        move    #>@W1L@,a
        move    a1,x:(r6+$1b)
        move    a1,x:(r6+$1d)
        move    #>@W1H@,a
        move    a1,x:(r6+$1c)
        move    a1,x:(r6+$1e)
        move    #>@W2L@,a
        move    a1,x:(r6+$23)
        move    a1,x:(r6+$25)
        move    #>@W2H@,a
        move    a1,x:(r6+$24)
        move    a1,x:(r6+$26)
        rts

pksc_mode2:
        move    #>@W2L@,a
        move    a1,x:(r6+$1b)
        move    a1,x:(r6+$1d)
        move    #>@W2H@,a
        move    a1,x:(r6+$1c)
        move    a1,x:(r6+$1e)
        move    #>@W3L@,a
        move    a1,x:(r6+$23)
        move    a1,x:(r6+$25)
        move    #>@W3H@,a
        move    a1,x:(r6+$24)
        move    a1,x:(r6+$26)
        rts

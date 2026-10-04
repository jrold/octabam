; PERKY Noise/Tone source-seam glue -- development synth canary.
;
; This is intentionally separate from probe_glue.asm. The impulse canary stays
; untouched as the minimal CF->DSP transport diagnostic; this file is the next
; layer and calls the complete X-state packed renderer.
;
; It mirrors Analog BD's hardware-qualified seam:
;   A P:$0039c / B P:$001a2 replaces `move a,x:>$20e`
;   stock continuation: @CONT@ (A $426 / B $221)
;
; PK/Y1 record:
;   w0 low16 $504b ('PK')
;   w2 low16 $5931 ('Y1')
;   w3 low16 1 iff this frame carries a trig
;
; Persistent memory per core:
;   X:$3800 + 58*voice   41 compact state + 17 envelope-cache words
;   X:$38e8..$38eb       shared RNG
;   X:$3900..$393f       one shared 64-word scratch block
;   Y:$0795..            packed wave/envelope tables
;
; x:$418 is stock's per-core track position: $00/$20/$40/$60. We map those
; directly to four 58-word voice blocks. A signed PERKY source consumes the
; same FLEX ring slot advance as Analog BD and resumes at stock AMP/FX.
;
; Sample-accurate trigger policy for this development canary:
;   render [0,event) with trigger word low;
;   render exactly one sample at event with trigger word high;
;   render (event,16) with trigger word low.
; The renderer itself stays ignorant of stock block/event bookkeeping.

pk_synth_source:
        move    a,x:>$20e               ; replay displaced stock instruction
        move    x:>$209,r4              ; current track's source record

        move    #>$00504b,x0
        move    x:(r4),b
        and     #>$ffff,b
        cmp     x0,b
        bne     pks_stock
        move    #>$005931,x0
        move    x:(r4+$2),b
        and     #>$ffff,b
        cmp     x0,b
        beq     pks_hit
pks_stock:
        rts

pks_hit:
        ; Keep the later track record boundary identical to stock/Analog BD.
        move    x:>$20b,a
        add     #>$80,a
        move    a,x:>$20b

        ; Resolve this core's track slot to one 58-word voice base.
        move    x:>$418,a
        tst     a
        beq     pks_voice0
        cmp     #>$20,a
        beq     pks_voice1
        cmp     #>$40,a
        beq     pks_voice2
        cmp     #>$60,a
        beq     pks_voice3
        ; Unknown slot is safer as silence than writing outside claimed X.
        bra     pks_silence
pks_voice0:
        move    #>$003800,r6
        bra     pks_voice_ready
pks_voice1:
        move    #>$00383a,r6
        bra     pks_voice_ready
pks_voice2:
        move    #>$003874,r6
        bra     pks_voice_ready
pks_voice3:
        move    #>$0038ae,r6
pks_voice_ready:
        move    #>$003900,r5            ; shared 64-word scratch
        move    #>$ffffff,m0
        move    #>$ffffff,m1
        move    #>$ffffff,m2
        move    #>$ffffff,m3
        move    #>$ffffff,m4
        move    #>$ffffff,m5
        move    #>$ffffff,m6
        move    #$0,r0                  ; stock source buffer X:0

        ; Default: no trigger pulse this frame.
        clr     a
        move    a1,x:(r6+$5)

        ; The CF record flag prevents a stale x:$20c from manufacturing a hit.
        move    x:(r4+$3),b
        and     #>$ffff,b
        tst     b
        beq     pks_render_full

        move    x:>$20c,a               ; stock event sample offset
        tst     a
        blt     pks_render_full
        cmp     #>$10,a
        bge     pks_render_full
        move    a1,x:(r5+$3f)           ; preserve event 0..15 in last scratch word

        ; Prefix [0,event). Do not issue a zero-count DO loop.
        tst     a
        beq     pks_trigger_sample
        move    a1,n7
        jsr     pk_voice_xstate

pks_trigger_sample:
        move    #>$1,a
        move    a1,x:(r6+$5)
        move    #>$1,n7
        jsr     pk_voice_xstate
        clr     a
        move    a1,x:(r6+$5)

        ; Suffix after the one trigger sample: 15-event samples.
        move    #>$f,a
        move    x:(r5+$3f),x0
        sub     x0,a
        tst     a
        beq     pks_continue
        move    a1,n7
        jsr     pk_voice_xstate
        bra     pks_continue

pks_render_full:
        move    #>$10,n7
        jsr     pk_voice_xstate
        bra     pks_continue

pks_silence:
        move    #$0,r0
        clr     a
        do      #$20,pks_silence_done
        move    a1,x:(r0)+
pks_silence_done:
        nop

pks_continue:
        move    #>$10,n7                ; stock AMP/FX source-stage contract
        move    ssh,x0                  ; discard seam JSR return
        jmp     @CONT@                  ; stock AMP -> FX1 -> FX2 -> packer

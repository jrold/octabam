; ---------------------------------------------------------------------------
; PERKY source-seam probe -- DEVELOPMENT CANARY, not the final engine.
;
; This mirrors ANALOG BD's measured source hook.  A stock/non-PERKY record
; returns immediately and lets the original source renderer run.  A PERKY
; record writes sixteen zero samples to the stock source buffer and, on a trig,
; places one +0.5 impulse at the exact stock event offset.  It then skips the
; stock source and resumes at @CONT@ so AMP, FX1 and FX2 still run.
;
; The point of this file is to prove machine selection, record packing and
; sample-accurate trig placement on both DSP payloads BEFORE Noise / Tone DSP
; is involved.  It is not registered or assembled into an image yet.
;
; ColdFire record words (32-bit CF words arrive as hi/lo DSP words):
;   w0 low16 = $504b  ('PK')
;   w2 low16 = $5931  ('Y1')
;   w3 low16 = 1 when this frame carries the track trig
;   w8..w19  = future twelve source-control bytes
;
; Build-time substitution:
;   @CONT@ = stock continuation after the source renderer for this payload
; ---------------------------------------------------------------------------

        .global pk_probe_source
pk_probe_source:
        move    a,x:>$20e               ; replay displaced stock instruction
        move    x:>$209,r4              ; current track's source record

        move    #>$00504b,x0             ; 'PK'
        move    x:(r4),b
        and     #>$ffff,b
        cmp     x0,b
        bne     pk_probe_stock

        move    #>$005931,x0             ; 'Y1'
        move    x:(r4+$2),b
        and     #>$ffff,b
        cmp     x0,b
        bne     pk_probe_stock
        bra     pk_probe_hit

pk_probe_stock:
        rts                             ; unsigned source: run stock path

pk_probe_hit:
        ; A synthesized source consumes the same FLEX ring slot advance as the
        ; measured Analog BD seam, keeping every later track's record boundary.
        move    x:>$20b,a
        add     #>$80,a
        move    a,x:>$20b

        ; Clear the sixteen-sample mono source block at X:0.
        move    #>$ffffff,m0
        move    #$0,r0
        clr     a
        do      #$10,pk_probe_zero_done
        move    a,x:(r0)+
pk_probe_zero_done:

        ; The stock source builder already publishes this frame's event sample
        ; offset in X:$20c.  Analog BD uses the same value.  The record flag is
        ; still checked so a stale/non-event offset cannot manufacture a hit.
        move    x:(r4+$3),b
        and     #>$ffff,b
        tst     b
        beq     pk_probe_continue

        move    x:>$20c,a
        tst     a
        blt     pk_probe_continue
        cmp     #>$10,a
        bge     pk_probe_continue

        move    a1,n1
        move    #$0,r1
        move    #>$400000,a              ; +0.5 Q1.23 integration impulse
        move    a,x:(r1+n1)

pk_probe_continue:
        move    ssh,x0                  ; discard seam JSR return
        jmp     @CONT@                  ; stock AMP -> FX1 -> FX2 -> packer

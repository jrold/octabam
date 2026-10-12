; ===========================================================================
; MINIMAL HARDWARE-DEBUG SOURCE HOOK -- no renderer, no state, no audio.
;
; WHY THIS EXISTS. On the physical Octatrack, with a Perky machine assigned,
; pressing PLAY stopped the sequencer advancing. The production hook ended its
; not-admitted path with `rts`, but the hook site is STRAIGHT-LINE stock code
; reached by fall-through -- nothing called it -- so that `rts` popped a return
; address that was never ours and the DSP left for hyperspace. The frame never
; completed, the ColdFire waited for a handshake that never came, and the
; sequencer stopped. Every track that was not the admitted one took that path.
;
; This image isolates the QUESTION from the ANSWER. It keeps the hook, the site,
; the admission test and BOTH continuations, and throws away everything else:
;
;   ADMITTED      -> jmp @CONT@   (take the track over; render nothing at all)
;   NOT ADMITTED  -> jmp @NEXT@   (continue stock at the instruction after the
;                                  hook, with the displaced op already replayed)
;
; WHAT EACH OUTCOME MEANS when this is flashed:
;   * sequencer runs normally, Perky track silent  -> the hook mechanism, the
;     continuation addresses and the admission test are all sound, and the
;     wedge is inside the RENDERER (the sample loop, the state load, register
;     or buffer use). Next debug target: the hook plus a renderer that writes
;     nothing.
;   * sequencer STILL stops -> the fault is in the hook MECHANISM itself: the
;     patch at the site, the placement, the displaced-instruction replay, or an
;     address the build bound. The renderer is not implicated and must not be
;     touched until this is understood.
;
; Either outcome is a result. Neither is a shipping image.
; ===========================================================================
pk3d_source:
        ; The instruction this hook displaced. Stock expects it to have run, and
        ; the ADMITTED continuation reads x:$20e back.
        move    a,x:>$20e

        move    x:>$418,b               ; this core's admitted track slot
        tst     b
        bne     pk3d_not_admitted

        move    x:>$209,r4              ; the source record for this event
        move    #>$00504b,x0            ; 'PK'
        move    x:(r4),b
        and     #>$ffff,b
        cmp     x0,b
        bne     pk3d_not_admitted
        move    #>$005931,x0            ; 'Y1'
        move    x:(r4+$2),b
        and     #>$ffff,b
        cmp     x0,b
        bne     pk3d_not_admitted

        jmp     @CONT@                  ; ours: take over, render nothing

pk3d_not_admitted:
        jmp     @NEXT@                  ; not ours: continue stock, do not return

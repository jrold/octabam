; ===========================================================================
; MINIMAL HARDWARE-DEBUG SOURCE HOOK -- no renderer, no state, no audio.
;
; WHY THIS EXISTS. On the physical Octatrack, with a Perky machine assigned,
; pressing PLAY stopped the sequencer advancing. The production hook is the
; suspect, and this image isolates it from every other part of the machine.
;
; THE STACK IS THE THING TO GET RIGHT, and both exits balance it differently on
; purpose. The seam is planted as a `jsr`, so one return address is pushed:
;
;   NOT ADMITTED -> `rts`, which POPS that return and resumes stock at the
;                   instruction after the hook. The displaced instruction has
;                   been replayed, so the stock source renderer runs normally.
;   ADMITTED     -> `move ssh,x0` DISCARDS the return -- measured on this
;                   emulator: with it, a following `rts` does not return;
;                   without it, it does -- and then `jmp @CONT@` skips the
;                   stock source and resumes after it.
;
; NEITHER PATH MAY SIMPLY `jmp`. That leaks one stack level per track per frame,
; wraps the 15-deep hardware stack, and destroys stock's return addresses. An
; earlier attempt to "fix" the not-admitted path by jumping to the next
; instruction was exactly that mistake and has been reverted.
;
; WHAT EACH OUTCOME MEANS when this is flashed:
;   * sequencer runs normally -> the hook, its stack balance, its site and its
;     continuations are all sound, and the wedge is inside the RENDERER or the
;     state the dispatcher loads. Next target: the hook plus a renderer that
;     renders but writes nothing.
;   * sequencer STILL stops -> the fault is in the hook MECHANISM or in how the
;     seam is planted, and the renderer is not implicated.
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

        move    ssh,x0                  ; discard the seam's JSR return
        jmp     @CONT@                  ; ours: take over, render nothing

pk3d_not_admitted:
        rts                             ; not ours: pop and run the stock source

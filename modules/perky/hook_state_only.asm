; ===========================================================================
; DEBUG RUNG 2 -- hook + admission + state load + silence, NO RENDERER.
;
; Rung 1 (modules/perky/hook_only.asm) is the bare hook: admission test and the
; two stack-balanced exits, nothing else. This rung adds everything the
; production dispatcher does EXCEPT the per-sample synthesis:
;
;   * the admission test, the 'PK'/'Y1' record check and the engine ledger
;   * the engine's compact state copied out of the record into X:0x3800
;     (the same ~100-word copy loop, with the same `do n1` zero guard)
;   * n7 set to 16, X:0 filled with 32 zero words (the silence path)
;   * the same exit: `move ssh,x0` then `jmp @CONT@`
;
; WHAT IT SEPARATES. Rung 1 and rung 3 (the full machine) bracket this:
;
;   rung 1 clean, rung 2 clean  -> the hook AND the dispatcher/state load are
;                                  sound; the wedge is the per-sample renderer
;                                  and nothing else. That is the strong result:
;                                  it attributes the fault to the synthesis cost
;                                  with no other candidate left standing.
;   rung 1 clean, rung 2 WEDGES  -> the dispatcher is implicated -- the record
;                                  read, the ledger, the copy loop or n7 -- and
;                                  the renderer is NOT.
;   rung 1 wedges                -> the hook itself; nothing below it matters.
;
; IT RENDERS NOTHING. X:0 is zeros, exactly as the production silence path.
; ===========================================================================
pk3d_source:
        move    a,x:>$20e               ; replay the displaced stock instruction

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

        ; --- the state load: record word 0x14 is the word count, 0x16+ the
        ; --- compact state. Zero the block first, then copy, with the same
        ; --- zero guard the production dispatcher uses (`do` with LC = 0 runs
        ; --- 65,536 times on this DSP).
        move    #>$3800,r0
        move    #>$ffffff,m0
        clr     a
        do      #$6c,pk3h_zeroed
        move    a1,x:(r0)+
pk3h_zeroed:
        move    x:(r4+$14),a
        move    a1,n1
        tst     a
        beq     pk3h_stored
        move    #>$3800,r0
        move    r4,r1
        lua     (r1+$16),r1
        do      n1,pk3h_copied
        move    x:(r1)+,b
        move    b1,x:(r0)+
pk3h_copied:
pk3h_stored:

        ; --- n7 = 16 and the silence output, as the production path does
        move    #$0,r0
        move    #>$10,n7
        clr     a
        do      #$20,pk3h_silent
        move    a1,x:(r0)+
pk3h_silent:

        move    ssh,x0                  ; discard the seam's JSR return
        jmp     @CONT@

pk3d_not_admitted:
        rts                             ; not ours: pop and run the stock source

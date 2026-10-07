; PĒRKONS v1.2.1 Karplus production-form HW4 seam.
;
; Inputs on entry:
;   r4 = prepared PK/Y1 source record (controls intentionally ignored by the
;        first audition candidate; engine id is fixed by the HW4 CF profile)
;   r6 = 58-word per-track overlay, first 32 words are exact Karplus state
;
; Memory owned by the HW4 audition profile:
;   X:$3900..$397f  shared 128-word renderer scratch
;   X:$39c4..$39e3  frozen pre-trigger snapshot for generated trigger plans
;   Y:$1600..$1dff  one 2,048-word Karplus delay ring
;   overlay +$20    has-triggered flag (outside the 32-word compact state)
;
; The exact first-trigger and active-retrigger routines are generated locally
; from original v1.2.1 ARM snapshots.  The renderer itself is independently
; native/ARM qualified.  This first hardware audition intentionally freezes the
; four sound controls at an authentic middle-corner ARM fixture; live EDGE /
; TWANG / TUNE / DECAY transport is a later qualification step.

pks_karplus_entry:
        jsrl    pk_multi_karplus_init

        move    #>$003900,r5
        move    #>$ffffff,m0
        move    #>$ffffff,m1
        move    #>$ffffff,m2
        move    #>$ffffff,m3
        move    #>$ffffff,m4
        move    #>$ffffff,m5
        move    #>$ffffff,m6
        move    #$0,r0

        ; Karplus' qualified noise helper keeps the four RNG limbs in the top
        ; of its 128-word scratch ABI.  Import the common production RNG once;
        ; prefix/retrigger/suffix rendering then shares one continuous stream.
        move    x:>$38e8,a
        move    a1,x:(r5+$72)
        move    x:>$38e9,a
        move    a1,x:(r5+$73)
        move    x:>$38ea,a
        move    a1,x:(r5+$74)
        move    x:>$38eb,a
        move    a1,x:(r5+$75)

        ; Default to no trigger.  As in the Fold/Simple production seams, the
        ; PK/Y1 flag prevents a stale stock event offset from manufacturing one.
        move    #>$10,a
        move    a1,x:>$38ec
        move    x:(r4+$3),a
        and     #>$ffff,a
        tst     a
        beq     pkk_event_ready
        move    x:>$20c,a
        tst     a
        blt     pkk_event_ready
        cmp     #>$10,a
        bge     pkk_event_ready
        move    a1,x:>$38ec
pkk_event_ready:
        move    x:>$38ec,a
        cmp     #>$10,a
        beq     pkk_full
        tst     a
        beq     pkk_retrigger

        ; Prefix [0,event) from the sounding pre-trigger state.
        move    a1,n7
        move    #>$001600,r4
        jsrl    pk_karplus_voice

pkk_retrigger:
        ; The original first trigger and an active retrigger are observably
        ; different, so retain one explicit bit outside compact state.
        move    x:(r6+$20),a
        tst     a
        bne     pkk_active_trigger
        jsrl    pk_karplus_trigger_first
        move    #>$1,a
        move    a1,x:(r6+$20)
        bra     pkk_trigger_done
pkk_active_trigger:
        jsrl    pk_karplus_trigger_active
pkk_trigger_done:
        ; Generated trigger routines use r5 for the frozen 32-word snapshot.
        ; Restore the renderer ABI without disturbing its scratch contents.
        move    #>$003900,r5
        move    #>$001600,r4
        move    #>$10,a
        move    x:>$38ec,x0
        sub     x0,a
        move    a1,n7
        jsrl    pk_karplus_voice
        bra     pkk_finish

pkk_full:
        move    #>$001600,r4
        move    #>$10,n7
        jsrl    pk_karplus_voice

pkk_finish:
        ; Publish the advanced random stream for the next PERKY engine/track.
        move    x:(r5+$72),a
        move    a1,x:>$38e8
        move    x:(r5+$73),a
        move    a1,x:>$38e9
        move    x:(r5+$74),a
        move    a1,x:>$38ea
        move    x:(r5+$75),a
        move    a1,x:>$38eb
        bra     pks_continue

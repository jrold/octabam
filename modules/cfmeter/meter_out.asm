; CF METER -- the DSP half. Prints one value per 125 ms slot as a square
; wave, L = value * 128, R = 8192 * 128, the sign flipped every block, so
; value = 8192 x rms(L) / rms(R) whatever the gain after this slot. The
; track's own audio is replaced.
;
; The ColdFire (modules/cfmeter/meter.s) writes three words into this
; track's FX2 page-2 lane: $c = N << 8 (its slot value), $d = 8192 << 8,
; $e = k << 8 (the slot, 0..15). Slots 0..7 print N. Slots 8..15 print
; this core's own meter, taken once per frame here:
;
;   8   spin count, min     core 0's wait for the next frame counts its
;   9   spin count, max     polls into x:$3f81 (P:0x4b-0x53, stored at P:0x92)
;   10  TUE frames          ESAI status x:$ffffb3 bit 14 (transmit underrun)
;   11  ROE frames          ESAI status bit 7 (receive overrun)
;   12  ESAI_1 frames       y:$ffff93 bits 14 | 7
;   13  period min / 4      timer 0 (CLK/2) between frames, counts / 4
;   14  period max / 4
;   15  frames              frames in the window (2 s = 5,512)
;
; A frame is one step of x:$415 (the housekeeping at P:0x549). The window
; runs from one k = 8 to the next; at k = 8 the accumulators are copied to
; the print slots and reset. TUE and ROE hold until the status register is
; read (the DSP56300 family manual: cleared by a read of SAISR followed by
; the next transmit writes / receive reads), and stock reads it only at
; boot, so one read per frame sees every event since the last.
;
; DBRN (page-1 slot 2) burns 24 x DBRN cycles per sample before the sample
; loop, SEND's form (dsp/burn_send.inc): the spin count must fall by the
; burn, which calibrates a poll's cost, and at the wall slot 9 jumps by a
; whole ring (a missed frame sync).
;
; r7 block (init zeroes $00..$17):
;   $00 sign          $01 last x:$415    $02 last timer    $03 spin min
;   $04 spin max      $05 TUE frames     $06 ROE frames    $07 ESAI_1 frames
;   $08 period min    $09 period max     $0a frames        $0b last k word
;   $0c timer armed   $10..$17 the print slots 8..15

init:
        move    r7,r5
        clr     a
        do      #$18,>ci_z
        move    a,x:(r5)+
ci_z:
        move    #>$7fffff,x0
        move    x0,x:(r7+$3)
        move    x0,x:(r7+$8)
        move    #>$ffff8e,r4            ; (peripherals through r4: the round-trip gate
        move    a,x:(r4)-               ; TLR0 = 0        reads x:>$ffff8e as its M_ name)
        move    #>$ffffff,x0
        move    x0,x:(r4)               ; TCPR0
        move    #>$ffff8f,r4
        move    #>$000201,x0
        move    x0,x:(r4)               ; TCSR0: TRM | TE, no interrupt (probe 55's setting)
        rts

proc:
        move    x:(r6+$2),a             ; DBRN: knob << 16
        and     #>$7f0000,a
        move    a1,y1
        move    n7,x0                   ; frames on this call
        mpy     x0,y1,a
        asl     #$a,a,a                 ; A1 = 8 * DBRN * n7; Z if either is 0
        beq     cm_noburn               ; DO with a count of 0 loops 65536 times
        do      a1,>cm_bend
        nop
        nop
        nop
cm_bend:
cm_noburn:
        move    x:>$415,x0
        move    x:(r7+$1),a
        cmp     x0,a
        beq     cm_skipf                ; the same frame as the last call
        move    x0,x:(r7+$1)
        move    x:(r7+$a),a
        move    #>1,x1
        add     x1,a
        move    a,x:(r7+$a)             ; frames++
        move    x:>$3f81,x0             ; this frame's spin count
        move    x0,a
        move    x:(r7+$3),b
        cmp     b,a
        tlt     x0,b
        move    b,x:(r7+$3)             ; min
        move    x:(r7+$4),b
        cmp     b,a
        tgt     x0,b
        move    b,x:(r7+$4)             ; max
        move    #>$ffffb3,r4
        move    x:(r4),x1               ; SAISR
        move    #>1,x0
        clr     b
        move    x1,a
        and     #>$004000,a             ; TUE
        tne     x0,b
        move    x:(r7+$5),a
        add     b,a
        move    a,x:(r7+$5)
        clr     b
        move    x1,a
        and     #>$000080,a             ; ROE
        tne     x0,b
        move    x:(r7+$6),a
        add     b,a
        move    a,x:(r7+$6)
        clr     b
        move    #>$ffff93,r4
        move    y:(r4),a                ; SAISR_1
        and     #>$004080,a
        tne     x0,b
        move    x:(r7+$7),a
        add     b,a
        move    a,x:(r7+$7)
        move    #>$ffff8c,r4
        move    x:(r4),x1               ; TCR0 now
        move    x:(r7+$2),b             ; last
        move    x1,x:(r7+$2)
        move    x:(r7+$c),a
        tst     a
        bne     cm_per
        move    x0,x:(r7+$c)            ; the first stamp arms the period
        bra     cm_skipf
cm_per:
        move    x1,a
        sub     b,a
        and     #>$ffffff,a             ; the advance, mod 2^24; a2 is stale after the and
        move    a1,x0
        move    x0,a                    ; clean a2 before the shift (the stale-extension trap)
        asr     #$2,a,a
        move    a1,x0
        move    x0,a                    ; drop a0
        move    x:(r7+$8),b
        cmp     b,a
        tlt     x0,b
        move    b,x:(r7+$8)             ; period min
        move    x:(r7+$9),b
        cmp     b,a
        tgt     x0,b
        move    b,x:(r7+$9)             ; period max
cm_skipf:
        move    x:(r6+$e),x0            ; k << 8
        move    x:(r7+$b),a
        cmp     x0,a
        beq     cm_nolatch
        move    x0,x:(r7+$b)
        move    x0,a
        cmp     #>$800,a
        bne     cm_nolatch              ; the window closes at k = 8
        move    x:(r7+$3),a
        move    a,x:(r7+$10)
        move    x:(r7+$4),a
        move    a,x:(r7+$11)
        move    x:(r7+$5),a
        move    a,x:(r7+$12)
        move    x:(r7+$6),a
        move    a,x:(r7+$13)
        move    x:(r7+$7),a
        move    a,x:(r7+$14)
        move    x:(r7+$8),a
        move    a,x:(r7+$15)
        move    x:(r7+$9),a
        move    a,x:(r7+$16)
        move    x:(r7+$a),a
        move    a,x:(r7+$17)
        clr     a
        move    a,x:(r7+$4)
        move    a,x:(r7+$5)
        move    a,x:(r7+$6)
        move    a,x:(r7+$7)
        move    a,x:(r7+$9)
        move    a,x:(r7+$a)
        move    #>$7fffff,x0
        move    x0,x:(r7+$3)
        move    x0,x:(r7+$8)
cm_nolatch:
        move    x:(r6+$e),a
        asr     #$8,a,a
        move    a1,x0
        move    x0,a                    ; k
        move    #>8,x1
        sub     x1,a
        bmi     cm_cfv                  ; k < 8: the ColdFire's value
        move    r7,x0
        add     x0,a
        move    #>$10,x1
        add     x1,a
        move    a,r4                    ; r7 + $10 + (k - 8)
        move    x:(r4),a
        move    #>32767,x0
        cmp     x0,a
        tgt     x0,a
        asl     #$8,a,a                 ; the $c convention: value << 8
        bra     cm_print
cm_cfv:
        move    x:(r6+$c),a
cm_print:
        asr     a
        move    a,x0                    ; +L
        neg     a
        move    a,x1                    ; -L
        move    x:(r6+$d),a
        asr     a
        move    a,y0                    ; +R
        neg     a
        move    a,y1                    ; -R
        move    #>1,a
        move    x:(r7),b
        sub     b,a                     ; next sign = 1 - sign; Z when it was 1
        move    a,x:(r7)
        move    x0,a
        teq     x1,a
        move    y0,b
        teq     y1,b
        move    #$1,n0                  ; (Character's form: n0 is not 1 on entry)
        do      n7,>cm_end
        move    a,x:(r0)
        move    b,x:(r0+n0)
        move    (r0)+n0
        move    (r0)+n0
cm_end:
        rts

| CC FEEDBACK -- the OT transmits a CC for every live knob byte that changed,
| whatever changed it: a pattern or part change, a project load, MODE
| DEFAULTS, a CC in, a page-2 knob turn. A controller with LED-ring or
| motorised encoders (a BCR2000) follows the unit. Stock transmits panel
| turns of page-1 knobs only (0x400552f0: current track, CC 10 + 6*page +
| slot) and nothing on a state change.
|
| Mechanism (0x40033e3c, disassembled): the stock emitter
| EMIT(track, cc, value) keeps the last value it queued per channel
| (CACHE + channel*128 + cc), sets the CC's bit in a per-channel dirty
| bitmap (0x46c7d7d8 + channel*16), the channel's bit in 0x46c7e0de, and
| forces interrupt source 34 (INTFRCH bit 2, the soft-timer dispatcher
| 0x400409f4) when 0x46c7ca34 is 0; the dispatcher drains the bitmap to
| UART0. It returns without queueing unless AUDIO CC OUT (CCOUT) bit 1 is
| set, the track's trig channel (TRIGCH + track) is >= 0, and no MIDI
| track uses that channel. Repeats coalesce in the bitmap.
|
| One track per UI tick (the keyrepeat task's loop 0x4005595c, one pass per
| DTIM1 tick: 120 Hz, handler 0x40055cb8 signals EVENT), the track's knob
| bytes in the PART are compared with the channel's cache: PLAYBACK page 1
| (Part +0x8edaa + t*30 + machine*6, machine from +0x8eda2 + t -> CC 16..21),
| the page-1 array (+0x8ee9a + t*24: LFO -> CC 28..33, AMP -> 22..27, FX1 ->
| 34..39, FX2 -> 40..45), FX1 page 2 (+0x8f07e + t*30 -> CC 68..73) and FX2
| page 2 (+0x8f084 + t*30 -> CC 62..67): the firmware's own CC numbering
| (docs/firmware/MIDI.md section 3, docs/firmware/PARAM_PAGES.md section 5a) and
| CC MAP's. A byte that differs is queued through EMIT, which updates the
| cache itself; stock's own knob echo goes through the same cache, so a
| panel turn is sent once. A track whose channel is off is skipped here;
| one that shares a channel with a MIDI track is refused by EMIT on every
| call (42 refused calls per sweep).
|
| The PART, not the live lane: the sequencer's parameter locks, slides and
| scenes rewrite the live lane (0x80000810 + t*72) every step and never
| the Part, and until 4 Oct 2026 this sweep watched the lane -- on a
| pattern with locks on two of T1's knobs the OT streamed 60 CCs a second
| at 32nd-note rate until the BCR2000 on the other end locked up, and the
| lane rewrites overwrote every incoming CC (Sam's MKII, image A1, a
| Midihub capture of the OT's output). The same build had the page-1
| array's AMP and LFO blocks swapped in its map (lane 6..11 is LFO, 12..17
| AMP), so an AMP turn went out under the LFO numbers and back.
|
| Paced: at most PACE messages per UI tick (120 Hz). A bank or pattern
| change with a different Kit differs on most of the 336 mapped slots, and
| the unpaced sweep put that whole dump on the wire in about a second --
| the BCR2000 locked up the moment the bank changed (Sam's MKII, image A2,
| 4 Oct 2026). The sweep keeps its place (cf_track, cf_pos) and carries
| on next tick; a track with nothing to send costs one tick as before.
|
| The sweep waits while the engine task runs a command (a project load, a
| bank or part change): ENGQ+0xc is the TCB the kernel's event wait
| (0x40000818) parks there while the engine is blocked on its queue, and
| the post (0x40000c3c) clears it. Stock transmits nothing during a load;
| under the port, 272 UART interrupts inside LOAD PROJECT re-ordered sys
| against the engine and tripped Octakit's part-byte lifecycle check
| (tools/emu/README.md, the ATA-latency note) -- measured 28 Sep 2026.
        .set    CCOUT,   0x8000004a    | AUDIO CC OUT: bit 0 INT, bit 1 EXT (0x40033e52)
        .set    TRIGCH,  0x8000003f    | +track: trig channel, -1 = off
        .set    DBPTR,   0x46c82456    | the bank pointer (long); the Part is DB + part*6322
        .set    PARTIX,  0x80000003    | the part index byte the page editors use
        .set    PARTLEN, 6322
        .set    MACHINE, 0x8eda2       | +t: the track's machine type
        .set    PBP1,    0x8edaa       | +t*30 + machine*6: PLAYBACK page 1
        .set    PAGE1,   0x8ee9a       | +t*24: LFO AMP FX1 FX2 page 1
        .set    PAGE2,   0x8f072       | +t*30: the page-2 array; FX1 at +12, FX2 at +18
        .set    CACHE,   0x46c7bf2c    | +channel*128 + cc: last value queued (0x40033ee6)
        .set    EMIT,    0x40033e3c    | (track, cc, value) on the stack
        .set    EVENT,   0x46c7e0e2    | the UI tick event the loop pends on
        .set    RESUME,  0x40055962    | the instruction after the displaced pea
        .set    ENGQ,    0x460d17ce    | the engine's command queue: +4 count, +8 event flag, +0xc waiting TCB
        .set    PACE,    1             | messages per UI tick

        .text
        .globl  cf_tick, cf_sweep, cf_track, cf_pos, cf_map

| jmp detour at 0x4005595c: replays the displaced `pea EVENT`. a2/a3 are
| the loop's function pointers; the sweep preserves them.
cf_tick:
        bsr.w   cf_sweep
        pea     EVENT
        jmp     RESUME

| cf_sweep(): track cf_track (advanced each call), the 42 mapped CCs.
| Preserves every register but d0/d1/a0/a1.
cf_sweep:
        lea     %sp@(-44),%sp
        movem.l %d2-%d7/%a2-%a6,%sp@
        moveq   #0,%d0
        move.b  CCOUT,%d0
        btst    #1,%d0
        beq.w   9f                      | EXT off: EMIT would refuse every call
        tst.l   ENGQ+12
        beq.w   9f                      | the engine is running a command: wait
        moveq   #0,%d2
        move.b  cf_track,%d2            | d2 = track
        lea     TRIGCH,%a0
        move.b  %a0@(0,%d2:l),%d3
        extb.l  %d3                     | d3 = channel
        blt.w   8f                      | off: the next track next tick
        move.l  DBPTR,%a2
        moveq   #0,%d0
        move.b  PARTIX,%d0
        move.l  #PARTLEN,%d1
        mulu.l  %d1,%d0
        adda.l  %d0,%a2                 | a2 = the Part
        move.l  %d2,%d0
        moveq   #30,%d1
        mulu.l  %d1,%d0                 | d0 = t*30
        move.l  %a2,%a6
        adda.l  #PAGE2,%a6
        adda.l  %d0,%a6                 | a6 = the track's page-2 row
        move.l  %a2,%a5
        adda.l  #PBP1,%a5
        adda.l  %d0,%a5
        move.l  %a2,%a0
        adda.l  #MACHINE,%a0
        moveq   #0,%d1
        move.b  %a0@(0,%d2:l),%d1
        moveq   #6,%d0
        mulu.l  %d0,%d1
        adda.l  %d1,%a5                 | a5 = the track's PLAYBACK page-1 block for its machine
        move.l  %d2,%d0
        moveq   #24,%d1
        mulu.l  %d1,%d0
        move.l  %a2,%a4
        adda.l  #PAGE1,%a4
        adda.l  %d0,%a4                 | a4 = the track's page-1 array (LFO AMP FX1 FX2)
        move.l  %d3,%d0
        lsl.l   #7,%d0
        lea     CACHE,%a3
        adda.l  %d0,%a3                 | a3 = the channel's cache
        lea     cf_map,%a2
        moveq   #0,%d0
        move.b  cf_pos,%d0
        adda.l  %d0,%a2                 | where the last tick stopped in this track's map
        moveq   #0,%d7                  | messages this tick
1:      moveq   #0,%d6
        move.b  %a2@+,%d6               | region: 0 PLAYBACK p1, 1 page-1 array, 2 page-2 row
        moveq   #0,%d4
        move.b  %a2@+,%d4               | offset in the region
        moveq   #0,%d5
        move.b  %a2@+,%d5               | CC number; 0 ends the table
        beq.s   8f                      | the track is done: the next track next tick
        move.l  %a5,%a0
        tst.l   %d6
        beq.s   2f
        move.l  %a4,%a0
        subq.l  #1,%d6
        beq.s   2f
        move.l  %a6,%a0
2:      moveq   #0,%d0
        move.b  %a0@(0,%d4:l),%d0       | the Part's value
        moveq   #0,%d1
        move.b  %a3@(0,%d5:l),%d1       | the last value queued for this CC
        cmp.l   %d0,%d1
        beq.s   1b
        move.l  %d0,%sp@-               | value
        move.l  %d5,%sp@-               | cc
        move.l  %d2,%sp@-               | track
        jsr     EMIT
        lea     %sp@(12),%sp
        addq.l  #1,%d7
        moveq   #PACE,%d0
        cmp.l   %d0,%d7
        blt.s   1b
        move.l  %a2,%d0
        sub.l   #cf_map,%d0
        move.b  %d0,cf_pos              | paced out: resume here next tick
        bra.s   9f
8:      clr.b   cf_pos
        move.l  %d2,%d0
        addq.l  #1,%d0
        moveq   #7,%d1
        and.l   %d1,%d0
        move.b  %d0,cf_track            | the next tick takes the next track
9:      movem.l %sp@,%d2-%d7/%a2-%a6
        lea     %sp@(44),%sp
        rts

cf_track:
        .byte   0                       | the track the next sweep takes
cf_pos:
        .byte   0                       | the map offset the next sweep resumes at (0 = the track's start)
        .balign 2
| (region, offset, CC) triples, 0 ends. Region 0: PLAYBACK page 1 -> CC
| 16..21. Region 1: the page-1 array, LFO +0..5 -> CC 28..33, AMP +6..11 ->
| 22..27, FX1 +12..17 -> 34..39, FX2 +18..23 -> 40..45. Region 2: the
| page-2 row, FX1 +12..17 -> CC 68..73, FX2 +18..23 -> 62..67 (modules/cc-map).
cf_map:
        .byte   0,0,16, 0,1,17, 0,2,18, 0,3,19, 0,4,20, 0,5,21
        .byte   1,6,22, 1,7,23, 1,8,24, 1,9,25, 1,10,26, 1,11,27
        .byte   1,0,28, 1,1,29, 1,2,30, 1,3,31, 1,4,32, 1,5,33
        .byte   1,12,34, 1,13,35, 1,14,36, 1,15,37, 1,16,38, 1,17,39
        .byte   1,18,40, 1,19,41, 1,20,42, 1,21,43, 1,22,44, 1,23,45
        .byte   2,12,68, 2,13,69, 2,14,70, 2,15,71, 2,16,72, 2,17,73
        .byte   2,18,62, 2,19,63, 2,20,64, 2,21,65, 2,22,66, 2,23,67
        .byte   0,0,0

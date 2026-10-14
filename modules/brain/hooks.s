
| ---- hooks.s: the two load-path detours and the per-remix table --------------
|
| Both sites are on the engine task's load path, before the banks are read:
|   0x40085342  LOAD PROJECT, before the empty-project init 0x400909d8:
|               `moveq #27,%d1 / movel %d1,%fp@(-570)`
|   0x40084d4a  the bank load every bank but the current (the power-up's
|               path too): `mvzb 0x80000002,%d1`
| Each stub keeps every register, calls brain_load and replays what the
| detour displaced.

        .include "remix.inc"           | brain_fx, brain_fx_n (manifest.py fx_inc)

| MODE DEFAULTS' view table, or 0 when that module is not in the remix
| (Linked.defsyms resolves MODEDEF_TABLE).
        .section .rodata
        .balign 4
        .globl  brain_modedef
brain_modedef: .long MODEDEF_TABLE
| LOAD METER's lm_stats (modules/load-meter), 0 without that module (LM_STATS defsym)
        .globl  brain_lm
brain_lm: .long LM_STATS
| its DSP figures (lm_dsp), 0 without it (LM_DSP defsym)
        .globl  brain_lmd
brain_lmd: .long LM_DSP
| its OTOP costs (lm_ot), 0 without it (LM_OT defsym)
        .globl  brain_lmo
brain_lmo: .long LM_OT

| the platform's DRAM: the arena base the build moved past octabam's reserve (the
| stock base is 0x40a955e0, where the runtime is linked) and the runtime's end
        .globl  brain_dram
brain_dram: .long ARENA_BASE, _end

        .text
        .globl  brain_on_load, brain_on_bankload
brain_on_load:
        lea     %sp@(-16),%sp
        movem.l %d0-%d1/%a0-%a1,%sp@
        jsr     brain_load
        movem.l %sp@,%d0-%d1/%a0-%a1
        lea     %sp@(16),%sp
        moveq   #27,%d1
        move.l  %d1,%fp@(-570)
        rts
brain_on_bankload:
        lea     %sp@(-16),%sp
        movem.l %d0-%d1/%a0-%a1,%sp@
        jsr     brain_load
        movem.l %sp@,%d0-%d1/%a0-%a1
        lea     %sp@(16),%sp
        mvz.b   0x80000002,%d1
        rts

| ---- SAVE PROJECT: card.work -> card.strd --------------------------------------
| The project store 0x4008ee74 is called from 0x40085642, 0x400856dc and
| 0x40085780; KITS hooks its entry. Each call site jumps here: copy, then
| tail-call the store with the caller's arguments (PLOCKS P2's form).
        .globl  brain_on_store
brain_on_store:
        lea     %sp@(-16),%sp
        movem.l %d0-%d1/%a0-%a1,%sp@
        jsr     brain_card_store
        movem.l %sp@,%d0-%d1/%a0-%a1
        lea     %sp@(16),%sp
        jmp     0x4008ee74

| ---- the engine task's job switch --------------------------------------------
|   0x4008485e  `mvzb %a2@,%d0 / moveq #45,%d1 / cmpl %d0,%d1`, then bcss
|               0x4008484e (a type above 45 goes back to the receive) and the
|               jump table. Type 0x41 runs brain_job and goes back to the
|               receive; every other type takes the stock path.
        .globl  brain_on_job
brain_on_job:
        mvz.b   %a2@,%d0
        cmp.l   #0x41,%d0
        bne.s   1f
        lea     %sp@(-16),%sp
        movem.l %d0-%d1/%a0-%a1,%sp@
        jsr     brain_job
        movem.l %sp@,%d0-%d1/%a0-%a1
        lea     %sp@(16),%sp
        jmp     0x4008484e
1:      moveq   #45,%d1
        cmp.l   %d0,%d1
        jmp     0x40084864

| ---- the debug log: the MIDI thread's handler call -----------------------------
|   0x40005572  `moveal %a2@(0,%d0:l:4),%a0 / jsr %a0@`: the handler for the
|               message (status>>4 in d0), with the message pointer and 0
|               pushed. The stub keeps its own return in a slot (the MIDI
|               thread is the only caller), calls the handler as stock does,
|               then logs the message and what the handler left.
        .globl  brain_on_midi
brain_on_midi:
        move.l  %sp@+,brain_midi_ret
        lea     brain_midi_msg,%a1      | the message as it came in: a handler
        move.b  %a0@,%a1@               | may overwrite it (program change does)
        move.b  %a0@(1),%a1@(1)
        move.b  %a0@(2),%a1@(2)
        moveal  %a2@(0,%d0:l:4),%a0
        jsr     %a0@
        lea     %sp@(-16),%sp
        movem.l %d0-%d1/%a0-%a1,%sp@
        pea     brain_midi_msg
        jsr     brain_midi_log
        addq.l  #4,%sp
        movem.l %sp@,%d0-%d1/%a0-%a1
        lea     %sp@(16),%sp
        move.l  brain_midi_ret,%sp@-
        rts
        .data
        .balign 4
brain_midi_ret: .long 0
brain_midi_msg: .long 0
        .text

| ---- the CTRL pages' knob labels (MIDI_TRACKS.md section 6) ---------------
| Detour at 0x4004e474 (`movel %fp@(-56),%sp@-` / `bras 0x4004e480`), the
| CTRL page drawer's label push for slot %a4 of descriptor %fp@(-80):
| brain_klabel(P, slot, stock label) chooses the label, which is pushed in
| its place before the draw call's other arguments at 0x4004e480. The
| drawer keeps %d0, %d1 and %a0 live across the site.
        .globl  brain_klabel_hook
brain_klabel_hook:
        lea     %sp@(-12),%sp
        movem.l %d0-%d1/%a0,%sp@
        move.l  %fp@(-56),%sp@-
        move.l  %a4,%sp@-
        move.l  %fp@(-80),%sp@-
        jsr     brain_klabel
        lea     %sp@(12),%sp
        move.l  %d0,%a1
        movem.l %sp@,%d0-%d1/%a0
        lea     %sp@(12),%sp
        move.l  %a1,%sp@-
        jmp     0x4004e480

| ---- CREATE EMPTY PROJECT ---------------------------------------------------
| Detour at 0x40085176 (`jsr 0x40096f24`), right after the empty project's
| RAM is set up (0x400909d8) in the new-project job: brain_new_project puts
| the card's project settings on the settings bytes, then the displaced call
| runs with the return address the site gave.
        .globl  brain_on_newproj
brain_on_newproj:
        lea     %sp@(-16),%sp
        movem.l %d0-%d1/%a0-%a1,%sp@
        jsr     brain_new_project
        movem.l %sp@,%d0-%d1/%a0-%a1
        lea     %sp@(16),%sp
        jmp     0x40096f24

| ---- IO: the ATA dispatcher's commands (card reads and writes) ------------
| Entry 0x4001513c (`moveq #4,%d0 / andl 0x46c86576,%d0`, 8 bytes) is
| reached with a command dequeued; exit 0x40015284 (`moveq #-1,%d1 /
| cmpl %d0,%d1 / bnes 0x40015290`) is the common return, %d0 the result.
| brain_ata_begin stamps the command (opcode, sector count, timer 3);
| brain_ata_end counts it and its time. Both keep every register.
        .globl  brain_ata_in, brain_ata_out
brain_ata_in:
        lea     %sp@(-16),%sp
        movem.l %d0-%d1/%a0-%a1,%sp@
        jsr     brain_ata_begin
        movem.l %sp@,%d0-%d1/%a0-%a1
        lea     %sp@(16),%sp
        moveq   #4,%d0
        and.l   0x46c86576,%d0
        rts
brain_ata_out:
        lea     %sp@(-16),%sp
        movem.l %d0-%d1/%a0-%a1,%sp@
        jsr     brain_ata_end
        movem.l %sp@,%d0-%d1/%a0-%a1
        lea     %sp@(16),%sp
        moveq   #-1,%d1
        cmp.l   %d0,%d1
        bne.s   1f
        jmp     0x4001528a
1:      jmp     0x40015290

| other modules' counters for IO, 0 when that module is not in the image
        .section .rodata
        .balign 4
        .globl  brain_usb
brain_usb:
        .long   usbaudio_underruns, usbaudio_overruns, in_counters, usbmidi_tx_drops
        .text

| ---- CPU: the time each task runs ---------------------------------------------
| Detour at 0x40000554 in the scheduler's entry (vector 32, trap #0, and vector
| 171, PIT0): the stock `movew #0x2700,%sr` at 0x40000550 has run, so no
| interrupt comes in here. A detour on that first instruction left one
| instruction with the mask unraised on a trap #0 entry, and an interrupt
| taken there entered the scheduler again halfway through: a task resumed at
| a garbage PC (0x80000000 under the port, 13 Oct 2026). Whatever task is
| current on entry is the one that ran since the last entry: its slot in
| brain_ts gets the DMA timer 3 counts (132 MHz) since brain_ts_last. A TCB
| that is in no slot goes to the last one. The registers are kept in
| brain_ts_save, not on the task's stack; the displaced `movel %a0,0x80006900`
| and the jump back end it.
        .globl  brain_sched, brain_ts, brain_ts_last
brain_sched:
        move.l  %d0,brain_ts_save
        move.l  %d1,brain_ts_save+4
        move.l  %a0,brain_ts_save+8
        move.l  0xfc07c00c,%d0
        move.l  0x800068fc,%d1
        lea     brain_ts,%a0
1:      cmp.l   %a0@,%d1
        beq.s   2f
        addq.l  #8,%a0
        cmpa.l  #brain_ts_other,%a0
        bne.s   1b
2:      move.l  %d0,%d1
        sub.l   brain_ts_last,%d1
        add.l   %d1,%a0@(4)
        move.l  %d0,brain_ts_last
        move.l  brain_ts_save,%d0
        move.l  brain_ts_save+4,%d1
        move.l  brain_ts_save+8,%a0
        move.l  %a0,0x80006900
        jmp     0x4000055a

        .data
        .balign 4
brain_ts_last: .long 0
brain_ts_save: .long 0, 0, 0
| {TCB, counts}: KERNEL.md "Tasks", in brain.c cpu_name's order
brain_ts:
        .long   0x46c7fb0c, 0
        .long   0x460bcc2c, 0
        .long   0x460d4f80, 0
        .long   0x460d59d4, 0
        .long   0x460fab80, 0
        .long   0x460ffd44, 0
        .long   0x460e0e38, 0
        .long   0x460ddde4, 0
        .long   0x46105508, 0
        .long   0x46c7bed8, 0
        .long   0x46c7ae84, 0
brain_ts_other:
        .long   0, 0
        .text

| ---- PART INIT -------------------------------------------------------------------
| Detour at 0x40005a38, in stock's Part initialiser (0x40005638(part)) at its end: its two
| last instructions before `lea %sp@(88),%sp` and the tail call to the Part validator
| 0x40002318. a2 is the Part. Part Clear, every Part of a new project and KITS' default Part
| (its test for a free slot) come from this routine, so the card's PART default put on the
| Part here is what all of them mean by a default Part. The displaced `movel %a2,%sp@(92)` and
| `moveml %sp@,%d2-%d7/%a2-%fp` are replayed.
        .text
        .globl  brain_partinit
brain_partinit:
        lea     %sp@(-16),%sp
        movem.l %d0-%d1/%a0-%a1,%sp@
        move.l  %a2,%sp@-
        jsr     brain_part_init
        addq.l  #4,%sp
        movem.l %sp@,%d0-%d1/%a0-%a1
        lea     %sp@(16),%sp
        move.l  %a2,%sp@(92)
        movem.l %sp@,%d2-%d7/%a2-%fp
        jmp     0x40005a40

| PERKY source-machine registration, following the measured Analog BD chooser
| path. Underlying track type stays FLEX; PK/1 uses the same proven three-byte
| signature area. Engine family lives in hidden persisted source slot 11;
| source slot 6 remains the visible three-way PERKY MODE parameter.
        .text
        .global pk_machine_name
        .global pk_src_names
        .global pk_main_commit
        .global pk_src_commit
        .global pk_name_a, pk_name_b
        .global pk_setup_row, pk_chooser_row
        .global pk_setup_open, pk_chooser_open
        .global pk_src_commit2, pk_setup_edit6, pk_setup_draw6
        .global pk_resolve_pb
        .global pk_sig_check
        .global pk_validate

        .equ    PK_ROW, 5
        .equ    FLEX, 1
        .equ    SRC_CURSOR, 0x460d5c30
        .equ    BANK_PTR, 0x46c82456
        .equ    PART_IDX, 0x100b14cf
        .equ    PART_STRIDE, 6322
        .equ    PART_OFF, 0x8ed80
        .equ    SRAM_PART, 0x100a4ece
        .equ    SIG_OFF, 0x2a + 18
        .equ    FLEX_P, 0x400d31ae
        .equ    PAGE2_GAP, 0x1da - 0x2a
        .equ    PB_TABLE, 0x400d5f38
        .equ    FLEX_SLOT_OFF, 0x2ca
        .equ    FLEX_SLOT_KIND, 1
        .equ    RECORDER_BASE, 128

pk_sig_check:
        lea     -8(%sp),%sp
        movem.l %d1/%a1,(%sp)
        moveq   #0,%d1
        move.b  0x22(%a0,%d0.l),%d1
        cmpi.l  #FLEX,%d1
        bne.s   .sc_no
        move.l  %d0,%d1
        mulu.w  #30,%d1
        lea     SIG_OFF(%a0,%d1.l),%a1
        move.b  (%a1),%d1
        cmpi.b  #'P',%d1
        bne.s   .sc_no
        move.b  1(%a1),%d1
        cmpi.b  #'K',%d1
        bne.s   .sc_no
        move.b  2(%a1),%d1
        cmpi.b  #1,%d1
        bne.s   .sc_no
        moveq   #1,%d0
        bra.s   .sc_done
.sc_no:
        moveq   #0,%d0
.sc_done:
        movem.l (%sp),%d1/%a1
        lea     8(%sp),%sp
        rts

| d1 != 0 marks PERKY; d1 == 0 removes PERKY. A fresh mark seeds all twelve
| source bytes from pk_defaults, including hidden model slot 11. Reselecting an
| existing PERKY track preserves its sound, MODE and family.
pk_sig_write:
        lea     -20(%sp),%sp
        movem.l %d0-%d3/%a1,(%sp)

| PERKY is sample-free, but the stock FLEX scheduler still needs a valid source
| object in the Part before it will create/call a FLEX voice. Point each PERKY
| track at its own recorder buffer (FLEX slots 129..136, stored zero-based as
| 128..135). The custom renderer replaces that silent donor PCM completely.
| Mirror the byte into the SRAM Part exactly like the PK/1 signature so a fresh
| project remains schedulable after reload/power-cycle without a file sample.
        tst.l   %d1
        beq.s   .sw_donor_done
        move.l  %d0,%d3
        mulu.w  #5,%d3
        move.l  %d0,%d2
        addi.l  #RECORDER_BASE,%d2
        move.b  %d2,FLEX_SLOT_OFF+FLEX_SLOT_KIND(%a0,%d3.l)
        move.l  %a0,%d2
        sub.l   (BANK_PTR).l,%d2
        subi.l  #PART_OFF,%d2
        addi.l  #SRAM_PART+FLEX_SLOT_OFF+FLEX_SLOT_KIND,%d2
        add.l   %d3,%d2
        movea.l %d2,%a1
        move.l  %d0,%d2
        addi.l  #RECORDER_BASE,%d2
        move.b  %d2,(%a1)
.sw_donor_done:
        mulu.w  #30,%d0
        lea     SIG_OFF(%a0,%d0.l),%a1
        bsr.s   .sw_one
        move.l  %a0,%d2
        sub.l   (BANK_PTR).l,%d2
        subi.l  #PART_OFF,%d2
        addi.l  #SRAM_PART + SIG_OFF,%d2
        add.l   %d0,%d2
        movea.l %d2,%a1
        bsr.s   .sw_one
        movem.l (%sp),%d0-%d3/%a1
        lea     20(%sp),%sp
        rts
.sw_one:
        tst.l   %d1
        beq.w   .sw_clear
        move.b  (%a1),%d2
        cmpi.b  #'P',%d2
        beq.s   .sw_mark
        move.l  %a0,-(%sp)
        move.l  %d0,-(%sp)
        lea     pk_defaults,%a0
        moveq   #5,%d0
.sw_defaults1:
        move.b  (%a0)+,-12(%a1)
        addq.l  #1,%a1
        subq.l  #1,%d0
        bpl.s   .sw_defaults1
        lea     -6(%a1),%a1
        moveq   #5,%d0
.sw_defaults2:
        move.b  (%a0)+,PAGE2_GAP-12(%a1)
        addq.l  #1,%a1
        subq.l  #1,%d0
        bpl.s   .sw_defaults2
        lea     -6(%a1),%a1
        move.l  (%sp)+,%d0
        move.l  (%sp)+,%a0
.sw_mark:
        move.b  #'P',(%a1)
        move.b  #'K',1(%a1)
        move.b  #1,2(%a1)
        rts
.sw_clear:
        move.b  (%a1),%d2
        cmpi.b  #'P',%d2
        bne.s   .sw_out
        clr.b   (%a1)
        clr.b   1(%a1)
        clr.b   2(%a1)
.sw_out:
        rts

pk_machine_name:
        move.l  4(%sp),%d0
        cmpi.l  #PK_ROW,%d0
        beq.s   1f
        move.l  %d2,-(%sp)
        move.l  8(%sp),%d1
        jmp     (0x400334de).l
1:      lea     pk_name(%pc),%a0
        move.l  %a0,%d0
        rts

        .balign 4
pk_src_names:
        .long   0x400b3eac
        .long   0x400b3e98
        .long   0x400b7c67
        .long   0x400b5413
        .long   0x400b7a63
        .long   pk_name

pk_admit:
        lea     -20(%sp),%sp
        movem.l %d1/%a0-%a1,8(%sp)
        move.l  %a0,(%sp)
        move.l  %d0,4(%sp)
        jsr     pk_admit_track
        movem.l 8(%sp),%d1/%a0-%a1
        lea     20(%sp),%sp
        rts

pk_main_commit:
        lea     -12(%sp),%sp
        movem.l %d0-%d1/%a0,(%sp)
        movea.l %a1,%a0
        adda.l  %d0,%a0
        adda.l  #PART_OFF,%a0
        move.l  %d1,%d0
        cmpi.l  #PK_ROW,%d4
        bne.s   .mc_other
        bsr     pk_admit
        tst.l   %d0
        beq.s   .mc_refuse
        move.l  %d1,%d0
        moveq   #1,%d1
        bsr     pk_sig_write
        moveq   #FLEX,%d4
        bra.s   .mc_store
.mc_other:
        moveq   #0,%d1
        bsr     pk_sig_write
.mc_store:
        movem.l (%sp),%d0-%d1/%a0
        lea     12(%sp),%sp
        .word   0x7710,0x1084,0xd081
        jmp     (0x40079822).l
.mc_refuse:
        movem.l (%sp),%d0-%d1/%a0
        lea     12(%sp),%sp
        pea     0x30.w
        pea     pk_reject_name(%pc)
        jsr     (0x4005a2b8).l
        addq.l  #8,%sp
        jmp     (0x4007989c).l

pk_src_commit:
        pea     (0x4005a61c).l
        bra.s   pk_src_common
pk_src_commit2:
        pea     (0x4005a856).l
pk_src_common:
        move.l  (SRC_CURSOR).l,%d1
        lea     -12(%sp),%sp
        movem.l %d0/%d2/%a0,(%sp)
        movea.l %a1,%a0
        adda.l  %d0,%a0
        adda.l  #PART_OFF,%a0
        move.l  %d2,%d0
        cmpi.l  #PK_ROW,%d1
        bne.s   .sc_other
        bsr     pk_admit
        tst.l   %d0
        beq.s   .sc_refuse
        move.l  %d2,%d0
        moveq   #1,%d1
        bsr     pk_sig_write
        moveq   #FLEX,%d1
        bra.s   .sc_go
.sc_other:
        move.l  %d1,-(%sp)
        moveq   #0,%d1
        bsr     pk_sig_write
        move.l  (%sp)+,%d1
.sc_go:
        movem.l (%sp),%d0/%d2/%a0
        lea     12(%sp),%sp
        rts
.sc_refuse:
        movem.l (%sp),%d0/%d2/%a0
        lea     12(%sp),%sp
        moveq   #0,%d1
        move.b  (%a0),%d1
        move.l  %d1,(SRC_CURSOR).l
        pea     0x30.w
        pea     pk_reject_name(%pc)
        jsr     (0x4005a2b8).l
        addq.l  #8,%sp
        rts

pk_setup_open:
        move.b  (%a0),%d3
        move.l  %d0,-(%sp)
        mvs.b   %d3,%d0
        bsr     pk_row_type
        move.l  %d0,%d3
        move.l  (%sp)+,%d0
        mvs.b   %d3,%d4
        pea     (0x400bb704).l
        jmp     (0x400585e6).l

| PERKY's slot 6 is a real MODE selector, not Analog BD's hidden MODEL slot.
pk_setup_edit6:
        cmpi.l  #PK_ROW,%d2
        bne.s   1f
        moveq   #FLEX,%d2
1:      move.l  %d2,%d0
        lsl.l   #3,%d0
        add.l   %d2,%d2
        sub.l   %d2,%d0
        jmp     (0x4003a536).l

pk_setup_draw6:
        cmpi.l  #PK_ROW,%d6
        bne.s   1f
        moveq   #FLEX,%d6
1:      move.l  %d6,%d7
        lsl.l   #3,%d7
        add.l   %d6,%d6
        sub.l   %d6,%d7
        jmp     (0x4003cda0).l

pk_chooser_open:
        mvs.b   (%a0),%d0
        bsr     pk_row_type
        move.l  %d0,-(%sp)
        pea     (0x460e7386).l
        jmp     (0x40078890).l

pk_name_a:
        bsr.s   pk_name_pick
        jmp     (0x4003d722).l
pk_name_b:
        bsr.s   pk_name_pick
        jmp     (0x4004c374).l
pk_name_pick:
        bsr     pk_row_type
        lea     pk_src_names(%pc),%a0
        move.l  (%a0,%d0.l*4),%d1
        rts

pk_setup_row:
        mvs.b   (%a0),%d0
        lea     24(%sp),%sp
        bsr.s   pk_row_type
        jmp     (0x4003c986).l
pk_chooser_row:
        mvs.b   (%a0),%d0
        bsr.s   pk_row_type
        cmp.l   %d0,%d2
        bne.s   1f
        jmp     (0x400786ce).l
1:      jmp     (0x400786fc).l

pk_row_type:
        lea     -20(%sp),%sp
        movem.l %d1/%a0-%a1,8(%sp)
        move.l  %d0,(%sp)
        move.l  %a0,4(%sp)
        jsr     pk_type
        movem.l 8(%sp),%d1/%a0-%a1
        lea     20(%sp),%sp
        rts

pk_resolve_pb:
        mvs.b   %d5,%d0
        bsr     pk_row_type
        cmpi.l  #PK_ROW,%d0
        bne.s   1f
        move.l  %a0,-(%sp)
        jsr     pk_track_page
        addq.l  #4,%sp
        jmp     (0x40031ed6).l
1:      lea     (PB_TABLE).l,%a0
        jmp     (0x40031ece).l

pk_validate:
        jmp     pk_validate_part
        .global pk_stock_validate
pk_stock_validate:
        lea     -96(%sp),%sp
        movem.l %d2-%d7/%a2-%fp,(%sp)
        jmp     (0x40002320).l

        .global pk_tick_hook
pk_tick_hook:
        jsr     0x4005213c
        jsr     0x4007e940
        jsr     pk_ui_tick
        jmp     0x40052228

pk_name:
        .asciz  "PERKY"
pk_reject_name:
        .asciz  "PERKY: INVALID TRACK"
        .balign 2

| Track double-tap: signed PERKY opens its engine-family browser; ordinary
| FLEX falls through to the stock sample pool.
        .global pk_pool_open
pk_pool_open:
        lea     -16(%sp),%sp
        movem.l %d0-%d1/%a0-%a1,(%sp)
        jsr     pk_selected_source
        tst.l   %d0
        bne.s   .pool_source
        movem.l (%sp),%d0-%d1/%a0-%a1
        lea     16(%sp),%sp
        .global pk_stock_pool_open
pk_stock_pool_open:
        move.l  %a2,-(%sp)
        tst.l   (0x460e70e0).l
        jmp     (0x400791ec).l
.pool_source:
        movem.l (%sp),%d0-%d1/%a0-%a1
        lea     16(%sp),%sp
        jmp     pk_engine_open

        .global pk_list_draw
pk_list_draw:
        lea     -16(%sp),%sp
        movem.l %d0-%d1/%a0-%a1,(%sp)
        jsr     pk_engine_draw
        tst.l   %d0
        beq.s   .list_stock
        movem.l (%sp),%d0-%d1/%a0-%a1
        lea     16(%sp),%sp
        rts
.list_stock:
        movem.l (%sp),%d0-%d1/%a0-%a1
        lea     16(%sp),%sp
        lea     -24(%sp),%sp
        movem.l %d2-%d3/%a2-%a5,(%sp)
        jmp     (0x4006d78c).l

        .global pk_pool_title
pk_pool_title:
        moveq   #1,%d6
        cmpi.l  #PK_ROW,%d0
        bne.s   .title_stock
        lea     -16(%sp),%sp
        movem.l %d0-%d1/%a0-%a1,(%sp)
        jsr     pk_selected_source
        tst.l   %d0
        beq.s   .title_unsigned
        movem.l (%sp),%d0-%d1/%a0-%a1
        lea     16(%sp),%sp
        bra.s   .title_pool
.title_unsigned:
        movem.l (%sp),%d0-%d1/%a0-%a1
        lea     16(%sp),%sp
.title_stock:
        cmp.l   %d0,%d6
        bcs.s   .title_plain
.title_pool:
        jmp     (0x40077b62).l
.title_plain:
        jmp     (0x40077b70).l

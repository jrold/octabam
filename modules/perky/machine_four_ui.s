| PERKY4 cosmetic hooks. Keep the stock machine type and icon priorities.
        .text
        .global pk_four_machine_glyph
pk_four_machine_glyph:
        pea     (0x400bf10a).l
        move.l  -24(%fp,%a4.l*4),-(%sp)
        lea     -24(%sp),%sp
        movem.l %d0-%d1/%a0-%a1,8(%sp)
        move.l  %d4,(%sp)
        move.l  24(%sp),4(%sp)
        jsr     pk_machine_glyph
        move.l  %d0,24(%sp)
        movem.l 8(%sp),%d0-%d1/%a0-%a1
        lea     24(%sp),%sp
        jmp     (0x4004013c).l

        .global pk_four_play_glyph
pk_four_play_glyph:
        lea     -24(%sp),%sp
        movem.l %d0-%d1/%a0-%a1,8(%sp)
        move.l  %d3,(%sp)
        moveq   #0,%d0
        move.b  (%a0),%d0
        move.l  %d0,4(%sp)
        jsr     pk_ui_playing
        tst.l   %d0
        movem.l 8(%sp),%d0-%d1/%a0-%a1
        lea     24(%sp),%sp
        bne.s   .play_event
        clr.l   %d2
        jmp     (0x4004bec2).l
.play_event:
        jmp     (0x4004beb4).l

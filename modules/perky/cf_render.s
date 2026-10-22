/* pk_render: the per-chunk PĒRKONS source dispatcher in assembly.
 *
 *   int pk_render(unsigned track, unsigned ping, unsigned start, unsigned end)
 *
 * Mirrors pk_hybrid_render (the C, now pk_render_c, pinned by its text in
 * tools/perky/generate_cf_render_asm.py) for a chunk of a placed voice:
 * track 0, 1, 4 or 5 (voice 0..3), a signed project slot (signed_track on
 * part_base()), its placement_mask bit, and start <= end <= 16. Those checks
 * only read memory; any other chunk jumps, stack untouched, to pk_render_c.
 *
 * From there, in the C's order: the bank/part generation observation,
 * placement_production_observe(generation), the profiler start time, the
 * trig latch, the deferred prefix, at end == 16 the input record (algo
 * through fm_voice_engine, mode clamped to 2, decay, tune, p1, p2, velocity
 * 255, note 45, start, trig) with the boundary no-op merge, the deferred
 * segment and placement_prepare for voices 0-2, then the voice's segment or
 * a new deferred prefix, pk_prod_clear of the packet words, and at end == 16
 * pk_nhr_frame (voice 3) or pk_prod_pack, the call count and the trig clear,
 * and the profiler's cycle and voice-mask accounting. Returns 0.
 *
 * Statics and project constants are the control unit's exports (pk_r_*,
 * PK_R_*). The literal addresses below are the C body's own.
 */
.set R_BEGIN, 40                /* profiler start time */
.set R_FRAME, 44
.set R_TRACK, R_FRAME+4
.set R_PING, R_FRAME+8
.set R_START, R_FRAME+12
.set R_END, R_FRAME+16

.section .text.pk_render_asm,"ax",@progbits
.balign 16
.globl pk_render
.type pk_render,@function
pk_render:                     /* the decision: d0, d1 and a0 only */
 move.l 4(%sp),%d0             /* track */
 moveq #-6,%d1
 and.l %d0,%d1
 bne .Lr_c                     /* not track 0, 1, 4 or 5 */
 move.l PK_R_BANK,%a0          /* part_base() */
 mvz.b PK_R_PART_IDX,%d1
 andi.l #3,%d1
 mulu.w #PK_R_PART_STRIDE,%d1
 add.l %d1,%a0
 adda.l #PK_R_PART_OFF,%a0
 mvz.b 0x22(%a0,%d0.l),%d1     /* underlying FLEX */
 subq.l #1,%d1
 bne .Lr_c
 move.l %d0,%d1
 mulu.w #30,%d1
 add.l %d1,%a0                 /* signature = part + SIG + 30 * track */
 mvz.b PK_R_SIG(%a0),%d1
 cmp.l #0x50,%d1               /* 'P' */
 bne .Lr_c
 mvz.b PK_R_SIG+1(%a0),%d1
 cmp.l #0x4b,%d1               /* 'K' */
 bne .Lr_c
 mvz.b PK_R_SIG+2(%a0),%d1
 subq.l #2,%d1
 bne .Lr_c
 move.l %d0,%d1                /* voice = track - 2 * (track >> 2) */
 lsr.l #2,%d1
 add.l %d1,%d1
 sub.l %d1,%d0
 move.l placement_mask,%d1
 btst %d0,%d1
 beq .Lr_c
 move.l 16(%sp),%d1            /* end */
 cmp.l 12(%sp),%d1
 bcs .Lr_c                     /* end < start */
 cmp.l #16,%d1
 bhi .Lr_c                     /* end > 16 */

 lea -R_FRAME(%sp),%sp
 movem.l %d2-%d7/%a2-%a5,(%sp)
 move.l R_TRACK(%sp),%d7
 move.l %d0,%d6                /* voice */
 move.l R_START(%sp),%d5
 move.l R_END(%sp),%d4

 move.l PK_R_BANK,%d0          /* pk_hybrid_observe_generation */
 mvz.b PK_R_PART_IDX,%d1
 moveq #3,%d2
 and.l %d2,%d1
 cmp.l pk_r_bank,%d0
 bne.s 1f
 mvz.b pk_r_part,%d2
 cmp.l %d1,%d2
 beq.s 2f
1:
 move.l %d0,pk_r_bank
 move.b %d1,pk_r_part
 move.l pk_r_generation,%d0
 addq.l #1,%d0
 move.l %d0,pk_r_generation
 move.l %d0,pk_r_prof_handoff
2:
 move.l pk_r_generation,-(%sp)
 jsr placement_production_observe
 addq.l #4,%sp
 moveq #0,%d0
 tst.l pk_hybrid_profiler_enable
 beq.s 3f
 move.l 0xfc07c00c,%d0         /* PK_HYB_DTCN3 */
3:
 move.l %d0,R_BEGIN(%sp)
 lea pk_r_trigger,%a4
 lea (%a4,%d6.l*4),%a4         /* &placement_trigger[voice] */
 lea 0x46104d0c,%a0
 mvz.b (%a0,%d7.l),%d0
 btst #4,%d0
 beq.s 4f
 moveq #1,%d0
 move.l %d0,(%a4)
4:
 moveq #0,%d3                  /* deferred */
 moveq #0,%d2                  /* merged */
 lea placement_deferred,%a2
 lea (%a2,%d6.l*4),%a2         /* &placement_deferred[voice] */
 moveq #3,%d0
 cmp.l %d0,%d6
 beq.s 5f
 move.l (%a2),%d3
 moveq #-1,%d0
 move.l %d0,(%a2)
 move.l %d3,%d0
 subq.l #1,%d0
 moveq #14,%d1
 cmp.l %d1,%d0
 bls.s 5f
 moveq #0,%d3
5:
 moveq #16,%d0
 cmp.l %d0,%d4
 bne .Lr_partial

 move.l 0x800062a8,%a5         /* fp: the page's source values */
 lea placement_inputs,%a3
 move.l %d6,%d0
 mulu.w #40,%d0
 add.l %d0,%a3                 /* p = placement_inputs[voice] */
 mvz.w PK_R_ALGO(%a5),%d0
 lsr.l #8,%d0
 move.l %d0,-(%sp)
 move.l %d6,-(%sp)
 jsr fm_voice_engine
 addq.l #8,%sp
 mvz.b %d0,%d0
 move.l %d0,(%a3)              /* p[0] */
 mvz.w PK_R_MODE(%a5),%d0
 lsr.l #8,%d0
 moveq #2,%d1
 cmp.l %d1,%d0
 bls.s 6f
 move.l %d1,%d0
6:
 move.l %d0,4(%a3)             /* p[1] */
 mvz.w PK_R_DECAY(%a5),%d0
 lsr.l #8,%d0
 move.l %d0,8(%a3)
 mvz.w PK_R_TUNE(%a5),%d0
 lsr.l #8,%d0
 move.l %d0,12(%a3)
 mvz.w PK_R_PARAM1(%a5),%d0
 lsr.l #8,%d0
 move.l %d0,16(%a3)
 mvz.w PK_R_PARAM2(%a5),%d0
 lsr.l #8,%d0
 move.l %d0,20(%a3)
 move.l #255,%d0
 move.l %d0,24(%a3)
 moveq #45,%d0
 move.l %d0,28(%a3)
 move.l %d5,32(%a3)            /* p[8] = start */
 move.l (%a4),36(%a3)          /* p[9] = trig */
 moveq #3,%d0
 cmp.l %d0,%d6
 beq .Lr_body
 tst.l %d3
 beq.s .Lr_prepare
 cmp.l %d3,%d5
 bne.s .Lr_prefix
 tst.l 36(%a3)                 /* placement_boundary_noop(voice, p, p[9] != 0) */
 sne %d0
 moveq #1,%d1
 and.l %d1,%d0
 move.l %d0,-(%sp)
 move.l %a3,-(%sp)
 move.l %d6,-(%sp)
 jsr placement_boundary_noop
 lea 12(%sp),%sp
 tst.l %d0
 beq.s .Lr_prefix
 moveq #1,%d2
 bra.s .Lr_prepare
.Lr_prefix:                    /* placement_segment(voice, 0, deferred, 0) */
 clr.l -(%sp)
 move.l %d3,-(%sp)
 clr.l -(%sp)
 move.l %d6,-(%sp)
 jsr placement_segment
 lea 16(%sp),%sp
 tst.l %d0
 bne.s .Lr_prepare
 clr.l placement_status
.Lr_prepare:                   /* placement_prepare(voice, p, p[9] != 0) */
 tst.l 36(%a3)
 sne %d0
 moveq #1,%d1
 and.l %d1,%d0
 move.l %d0,-(%sp)
 move.l %a3,-(%sp)
 move.l %d6,-(%sp)
 jsr placement_prepare
 lea 12(%sp),%sp
 tst.l %d0
 bne.s .Lr_body
 clr.l placement_status
 bra.s .Lr_body

.Lr_partial:                   /* end < 16: a pending prefix renders first */
 tst.l %d3
 beq.s .Lr_body
 clr.l -(%sp)
 move.l %d3,-(%sp)
 clr.l -(%sp)
 move.l %d6,-(%sp)
 jsr placement_segment
 lea 16(%sp),%sp
 tst.l %d0
 bne.s .Lr_body
 clr.l placement_status

.Lr_body:
 moveq #3,%d0
 cmp.l %d0,%d6
 beq .Lr_clear
 tst.l %d2
 beq.s 7f
 clr.l -(%sp)                  /* merged: placement_segment(voice, 0, 16, 0) */
 moveq #16,%d0
 move.l %d0,-(%sp)
 clr.l -(%sp)
 move.l %d6,-(%sp)
 bra.s .Lr_segment
7:
 moveq #16,%d0                 /* a first half with no start defers */
 cmp.l %d0,%d4
 bcc.s 8f
 tst.l %d5
 bne.s 8f
 tst.l %d4
 beq.s 8f
 tst.l placement_trace_enabled
 bne.s 8f
 move.l %d4,(%a2)
 bra.s .Lr_clear
8:
 tst.l %d5                     /* placement_segment(voice, start, end, start ? 1 : 0) */
 sne %d0
 moveq #1,%d1
 and.l %d1,%d0
 move.l %d0,-(%sp)
 move.l %d4,-(%sp)
 move.l %d5,-(%sp)
 move.l %d6,-(%sp)
.Lr_segment:
 jsr placement_segment
 lea 16(%sp),%sp
 tst.l %d0
 bne.s .Lr_clear
 clr.l placement_status

.Lr_clear:                     /* cursor = pk_prod_clear(cursor, 4 + 2n) */
 move.l %d4,%d0
 sub.l %d5,%d0
 addq.l #2,%d0
 add.l %d0,%d0
 move.l %d0,-(%sp)
 move.l 0x80001c80,-(%sp)
 jsr pk_prod_clear
 addq.l #8,%sp
 move.l %d0,0x80001c80
 moveq #16,%d0
 cmp.l %d0,%d4
 bne.s .Lr_profile
 moveq #1,%d0                  /* pk_hybrid_fixed_slot(track, ping) */
 and.l R_PING(%sp),%d0
 move.l #PK_R_PING_BYTES,%d1
 mulu.l %d1,%d0
 move.l #PK_R_SLOT_BYTES,%d1
 mulu.l %d7,%d1
 add.l %d1,%d0
 add.l #PK_R_SLOT_BASE,%d0
 moveq #3,%d1
 cmp.l %d1,%d6
 bne.s 9f
 move.l %d0,-(%sp)             /* pk_nhr_frame(start, slot) */
 move.l %d5,-(%sp)
 jsr pk_nhr_frame
 addq.l #8,%sp
 bra.s 10f
9:
 move.l %d5,-(%sp)             /* pk_prod_pack(slot, placement_output[voice], start) */
 move.l %d6,%d1
 lsl.l #6,%d1
 add.l #placement_output,%d1
 move.l %d1,-(%sp)
 move.l %d0,-(%sp)
 jsr pk_prod_pack
 lea 12(%sp),%sp
10:
 lea placement_calls,%a0
 addq.l #1,(%a0,%d6.l*4)
 clr.l (%a4)                   /* placement_trigger[voice] = 0 */

.Lr_profile:
 tst.l pk_hybrid_profiler_enable
 beq.s 11f
 move.l 0xfc07c00c,%d0
 sub.l R_BEGIN(%sp),%d0
 add.l %d0,pk_r_cf_ticks
 moveq #1,%d0
 lsl.l %d7,%d0
 or.l %d0,pk_r_voice_mask
11:
 moveq #0,%d0
 movem.l (%sp),%d2-%d7/%a2-%a5
 lea R_FRAME(%sp),%sp
 rts

.Lr_c:
 jmp pk_render_c
.size pk_render,.-pk_render

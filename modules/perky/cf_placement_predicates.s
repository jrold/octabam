/* placement_boundary_noop and placement_v4_merge_eligible in assembly.
 *
 * Pure predicates (they read state and return 0 or 1), mirroring the C of
 * tools/perky/generate_cf_merged_segments.py (PKFM22) and
 * tools/perky/generate_cf_v4_merge.py (PKFM26) term for term. Layout comes
 * from the placement unit's exports (tools/perky/generate_cf_placement_asm.py).
 *
 *   int placement_boundary_noop(unsigned tr, const uint32_t *input, int trig)
 * 1 when: no trig; algo <= 9, mode <= 2, tr <= 2; assets bound; tracing off;
 * the voice's generation current; the algorithm initialized and active with
 * this mode; and its control (Noise/Tone mode 0: the M1 control) valid with
 * this mode and the same four raw bytes.
 *
 *   int placement_v4_merge_eligible(const uint32_t *input)
 * 1 when: no trig; algo Noise/Tone, mode 1 or 2; assets bound; tracing off;
 * track 3's generation current; initialized, active with this mode; the
 * shared control valid with this mode and raw bytes; the envelope curve's
 * table present (curve 1/2); and each of the four wave views (object
 * 0x38, 0x3c, 0xd0, 0xd4, little-endian) is one of the bound tables.
 */
.section .text.pk_placement_predicates,"ax",@progbits
.balign 16
.globl placement_boundary_noop
.type placement_boundary_noop,@function
placement_boundary_noop:
 lea -8(%sp),%sp
 movem.l %d2-%d3,(%sp)
 tst.l 20(%sp)                 /* trig */
 bne .Lb_no
 move.l 16(%sp),%a1            /* input */
 mvz.b 3(%a1),%d0              /* algo */
 moveq #9,%d3
 cmp.l %d3,%d0
 bhi .Lb_no
 mvz.b 7(%a1),%d1              /* mode */
 moveq #2,%d3
 cmp.l %d3,%d1
 bhi .Lb_no
 move.l 12(%sp),%d2            /* tr */
 cmp.l %d3,%d2
 bhi .Lb_no
 tst.l placement_engine_assets
 beq .Lb_no
 tst.l placement_trace_enabled
 bne .Lb_no
 lea pk_prod_voice_generation,%a0
 move.l (%a0,%d2.l*4),%d3
 cmp.l pk_prod_generation,%d3
 bne .Lb_no
 move.l #PK_TRACK_BYTES,%d3
 mulu.l %d2,%d3
 lea placement_engine_tracks,%a0
 add.l %d3,%a0                 /* t */
 mvz.w PK_TRACK_INITMASK(%a0),%d3
 btst %d0,%d3
 beq .Lb_no
 mvz.b PK_TRACK_ACTIVE_ALGO(%a0),%d3
 cmp.l %d0,%d3
 bne .Lb_no
 mvz.b PK_TRACK_ACTIVE_MODE(%a0),%d3
 cmp.l %d1,%d3
 bne .Lb_no
 cmp.l #PK_ALGO_NT,%d0
 bne.s 1f
 tst.l %d1
 bne.s 1f
 lea PK_CTL_NT_M1(%a0),%a0
 bra.s 2f
1:
 lea .Lb_controls,%a1
 move.l (%a1,%d0.l*4),%d3
 add.l %d3,%a0                 /* c */
2:
 tst.b PK_CONTROL_VALID(%a0)
 beq .Lb_no
 mvz.b PK_CONTROL_LAST_MODE(%a0),%d3
 cmp.l %d1,%d3
 bne .Lb_no
 move.l 16(%sp),%a1
 mvz.b PK_CONTROL_LAST_RAW(%a0),%d3
 mvz.b 15(%a1),%d2             /* (uint8_t)input[3] */
 cmp.l %d2,%d3
 bne .Lb_no
 mvz.b PK_CONTROL_LAST_RAW+1(%a0),%d3
 mvz.b 11(%a1),%d2             /* (uint8_t)input[2] */
 cmp.l %d2,%d3
 bne .Lb_no
 mvz.b PK_CONTROL_LAST_RAW+2(%a0),%d3
 mvz.b 19(%a1),%d2             /* (uint8_t)input[4] */
 cmp.l %d2,%d3
 bne .Lb_no
 mvz.b PK_CONTROL_LAST_RAW+3(%a0),%d3
 mvz.b 23(%a1),%d2             /* (uint8_t)input[5] */
 cmp.l %d2,%d3
 bne .Lb_no
 moveq #1,%d0
 bra.s .Lb_out
.Lb_no:
 moveq #0,%d0
.Lb_out:
 movem.l (%sp),%d2-%d3
 lea 8(%sp),%sp
 rts
.size placement_boundary_noop,.-placement_boundary_noop

.balign 16
.globl placement_v4_merge_eligible
.type placement_v4_merge_eligible,@function
placement_v4_merge_eligible:
 lea -16(%sp),%sp
 movem.l %d2-%d3/%a2-%a3,(%sp)
 move.l 20(%sp),%a1            /* input */
 tst.l 36(%a1)                 /* input[9]: trig */
 bne .Lv_no
 mvz.b 3(%a1),%d0              /* algo */
 cmp.l #PK_ALGO_NT,%d0
 bne .Lv_no
 mvz.b 7(%a1),%d1              /* mode */
 move.l %d1,%d2
 subq.l #1,%d2
 moveq #1,%d3
 cmp.l %d3,%d2
 bhi .Lv_no                    /* mode not 1 or 2 */
 move.l placement_engine_assets,%d2
 beq .Lv_no
 move.l %d2,%a2                /* assets */
 tst.l placement_trace_enabled
 bne .Lv_no
 move.l pk_prod_voice_generation+12,%d2
 cmp.l pk_prod_generation,%d2
 bne .Lv_no
 move.l #PK_TRACK_BYTES,%d2
 moveq #3,%d3
 mulu.l %d3,%d2
 lea placement_engine_tracks,%a0
 add.l %d2,%a0                 /* t = &tracks[3] */
 mvz.w PK_TRACK_INITMASK(%a0),%d3
 btst %d0,%d3
 beq .Lv_no
 mvz.b PK_TRACK_ACTIVE_ALGO(%a0),%d3
 cmp.l %d0,%d3
 bne .Lv_no
 mvz.b PK_TRACK_ACTIVE_MODE(%a0),%d3
 cmp.l %d1,%d3
 bne .Lv_no
 lea PK_CTL_NT_SHARED(%a0),%a3 /* c */
 tst.b PK_CONTROL_VALID(%a3)
 beq .Lv_no
 mvz.b PK_CONTROL_LAST_MODE(%a3),%d3
 cmp.l %d1,%d3
 bne .Lv_no
 mvz.b PK_CONTROL_LAST_RAW(%a3),%d3
 mvz.b 15(%a1),%d2
 cmp.l %d2,%d3
 bne .Lv_no
 mvz.b PK_CONTROL_LAST_RAW+1(%a3),%d3
 mvz.b 11(%a1),%d2
 cmp.l %d2,%d3
 bne .Lv_no
 mvz.b PK_CONTROL_LAST_RAW+2(%a3),%d3
 mvz.b 19(%a1),%d2
 cmp.l %d2,%d3
 bne .Lv_no
 mvz.b PK_CONTROL_LAST_RAW+3(%a3),%d3
 mvz.b 23(%a1),%d2
 cmp.l %d2,%d3
 bne .Lv_no
 lea PK_TRACK_NT_SHARED(%a0),%a0 /* s */
 mvz.b 0x75(%a0),%d2           /* envelope curve */
 subq.l #1,%d2
 moveq #1,%d3
 cmp.l %d3,%d2
 bhi.s 3f                      /* linear */
 move.l #PK_ASSETS_ENV1,%d3
 tst.l %d2
 beq.s 4f
 move.l #PK_ASSETS_ENV2,%d3
4:
 tst.l (%a2,%d3.l)
 beq .Lv_no
3:
 lea PK_ASSETS_WAVES(%a2),%a2  /* the four bound wave views */
 move.l 0x38(%a0),%d2
 byterev %d2
 bsr .Lv_view
 beq .Lv_no
 move.l 0x3c(%a0),%d2
 byterev %d2
 bsr .Lv_view
 beq .Lv_no
 move.l 0xd0(%a0),%d2
 byterev %d2
 bsr .Lv_view
 beq .Lv_no
 move.l 0xd4(%a0),%d2
 byterev %d2
 bsr .Lv_view
 beq .Lv_no
 moveq #1,%d0
 bra.s .Lv_out
.Lv_no:
 moveq #0,%d0
.Lv_out:
 movem.l (%sp),%d2-%d3/%a2-%a3
 lea 16(%sp),%sp
 rts

/* d2 = wanted address; Z clear (d0 = 1) when a bound view has it. */
.Lv_view:
 moveq #1,%d0
 tst.l 4(%a2)
 beq.s 5f
 cmp.l (%a2),%d2
 beq.s 9f
5:
 tst.l 12(%a2)
 beq.s 6f
 cmp.l 8(%a2),%d2
 beq.s 9f
6:
 tst.l 20(%a2)
 beq.s 7f
 cmp.l 16(%a2),%d2
 beq.s 9f
7:
 tst.l 28(%a2)
 beq.s 8f
 cmp.l 24(%a2),%d2
 beq.s 9f
8:
 moveq #0,%d0
 rts
9:
 tst.l %d0
 rts
.size placement_v4_merge_eligible,.-placement_v4_merge_eligible

.section .rodata.pk_placement_predicates,"a",@progbits
.balign 4
.Lb_controls:
 .long PK_CTL_FOLD1, PK_CTL_FOLD2, PK_CTL_KARPLUS, PK_CTL_NT_SHARED, PK_CTL_RES_SNARE
 .long PK_CTL_NH, PK_CTL_SD, PK_CTL_CD, PK_CTL_SLAP, PK_CTL_WT

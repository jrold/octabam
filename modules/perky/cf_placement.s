/* placement_prepare and placement_segment: assembly fast paths, seams intact.
 *
 * Both keep their C signatures and are the frozen oracle's seams (entry, and
 * for segment the return). Struct layout comes from absolute symbols the
 * placement unit exports (tools/perky/generate_cf_placement_asm.py), with
 * placement_engine_tracks and placement_engine_assets as addresses.
 *
 *   int placement_prepare(unsigned tr, const uint32_t *input, int trig)
 * Exactly the C: algorithm/mode/track range check; placement_production_event
 * (tr, algo); record algorithm and mode; when no trigger, algo < 10, assets
 * bound, the algorithm initialized and its control (Noise/Tone mode 0: the M1
 * control) valid with the same mode and raw bytes, reset the native clock
 * only on an algorithm change, set active algorithm/mode and return 1.
 * Otherwise jump, stack untouched, to placement_prepare_slow.
 *
 *   int placement_segment(unsigned tr, uint32_t start, uint32_t end, unsigned half)
 * Fast only for tr <= 3, active algorithm not Acoustic Hats (10), 0 < end -
 * start, end <= 16, tracing off, assets bound, native phase < 147 and the
 * native need fitting 20 samples. It renders through the same renderer
 * pk4_render would choose (Wavetable, Slap and Noise/Tone shared directly,
 * every other engine through pk4_render), converts with
 * pk_nhb_native_convert_fast and counts the native samples. Everything else
 * jumps to placement_segment_c, the original.
 */
.section .text.pk_placement_asm,"ax",@progbits
.balign 16
.globl placement_prepare
.type placement_prepare,@function
placement_prepare:
 lea -20(%sp),%sp
 movem.l %d2-%d4/%a2-%a3,(%sp)
 move.l 28(%sp),%a2            /* input */
 mvz.b 3(%a2),%d3              /* algo = (uint8_t)input[0] */
 moveq #10,%d0
 cmp.l %d0,%d3
 bhi .Lp_zero
 mvz.b 7(%a2),%d4              /* mode = (uint8_t)input[1] */
 moveq #2,%d0
 cmp.l %d0,%d4
 bhi .Lp_zero
 move.l 24(%sp),%d2            /* tr */
 moveq #3,%d0
 cmp.l %d0,%d2
 bhi .Lp_zero
 move.l %d3,-(%sp)
 move.l %d2,-(%sp)
 jsr placement_production_event
 addq.l #8,%sp
 lea pk_prod_algorithms,%a0
 move.l %d3,(%a0,%d2.l*4)
 lea pk_prod_modes,%a0
 move.l %d4,(%a0,%d2.l*4)
 tst.l 32(%sp)                 /* trig */
 bne .Lp_slow
 moveq #10,%d0
 cmp.l %d0,%d3
 beq .Lp_slow
 tst.l placement_engine_assets
 beq .Lp_slow
 move.l #PK_TRACK_BYTES,%d0
 mulu.l %d2,%d0
 lea placement_engine_tracks,%a3
 add.l %d0,%a3                 /* t */
 mvz.w PK_TRACK_INITMASK(%a3),%d0
 btst %d3,%d0
 beq .Lp_slow
 lea .Lp_controls,%a0
 move.l (%a0,%d3.l*4),%d0
 lea (%a3,%d0.l),%a0           /* c */
 move.l #PK_ALGO_NT,%d0
 cmp.l %d0,%d3
 bne.s 1f
 tst.l %d4
 bne.s 1f
 lea PK_CTL_NT_M1(%a3),%a0
1:
 tst.b PK_CONTROL_VALID(%a0)
 beq .Lp_slow
 mvz.b PK_CONTROL_LAST_MODE(%a0),%d0
 cmp.l %d4,%d0
 bne .Lp_slow
 mvz.b PK_CONTROL_LAST_RAW(%a0),%d0
 mvz.b 15(%a2),%d1             /* (uint8_t)input[3] */
 cmp.l %d1,%d0
 bne .Lp_slow
 mvz.b PK_CONTROL_LAST_RAW+1(%a0),%d0
 mvz.b 11(%a2),%d1             /* (uint8_t)input[2] */
 cmp.l %d1,%d0
 bne .Lp_slow
 mvz.b PK_CONTROL_LAST_RAW+2(%a0),%d0
 mvz.b 19(%a2),%d1             /* (uint8_t)input[4] */
 cmp.l %d1,%d0
 bne .Lp_slow
 mvz.b PK_CONTROL_LAST_RAW+3(%a0),%d0
 mvz.b 23(%a2),%d1             /* (uint8_t)input[5] */
 cmp.l %d1,%d0
 bne .Lp_slow
 mvz.b PK_TRACK_ACTIVE_ALGO(%a3),%d0
 cmp.l %d3,%d0
 beq.s 2f
 move.l #PK_CLOCK_BYTES,%d0    /* pk_cf_native_reset(&placement_clocks[tr]) */
 mulu.l %d2,%d0
 lea placement_clocks,%a0
 add.l %d0,%a0
 clr.l PK_CLOCK_PHASE(%a0)
 clr.l PK_CLOCK_HAVE(%a0)
 clr.l PK_CLOCK_CARRY(%a0)
2:
 move.b %d3,PK_TRACK_ACTIVE_ALGO(%a3)
 move.b %d4,PK_TRACK_ACTIVE_MODE(%a3)
 moveq #1,%d0
 movem.l (%sp),%d2-%d4/%a2-%a3
 lea 20(%sp),%sp
 rts
.Lp_zero:
 moveq #0,%d0
 movem.l (%sp),%d2-%d4/%a2-%a3
 lea 20(%sp),%sp
 rts
.Lp_slow:
 movem.l (%sp),%d2-%d4/%a2-%a3
 lea 20(%sp),%sp
 jmp placement_prepare_slow
.size placement_prepare,.-placement_prepare

.section .rodata.pk_placement_asm,"a",@progbits
.balign 4
.Lp_controls:
 .long PK_CTL_FOLD1, PK_CTL_FOLD2, PK_CTL_KARPLUS, PK_CTL_NT_SHARED, PK_CTL_RES_SNARE
 .long PK_CTL_NH, PK_CTL_SD, PK_CTL_CD, PK_CTL_SLAP, PK_CTL_WT

/* ---- placement_segment ------------------------------------------------- */
/* frame: 44 saved, 40 data[20], 44 tables, 8 rng */
.set S_DATA, 44
.set S_TAB, 84
.set S_RNG, 128
.set S_FRAME, 136
.set S_TR, S_FRAME+4
.set S_START, S_FRAME+8
.set S_END, S_FRAME+12

.section .text.pk_placement_asm
.balign 16
.globl placement_segment
.type placement_segment,@function
placement_segment:
 lea -S_FRAME(%sp),%sp
 movem.l %d2-%d7/%a2-%a6,(%sp)
 move.l S_TR(%sp),%d7          /* tr */
 moveq #3,%d0
 cmp.l %d0,%d7
 bhi .Ls_c
 move.l S_END(%sp),%d2
 moveq #16,%d0
 cmp.l %d0,%d2
 bhi .Ls_c                     /* end > 16 */
 sub.l S_START(%sp),%d2        /* n = end - start */
 bls .Ls_c                     /* end <= start: empty, or C's bounds failure */
 tst.l placement_trace_enabled
 bne .Ls_c
 move.l placement_engine_assets,%d0
 beq .Ls_c
 move.l %d0,%a2                /* assets */
 move.l #PK_TRACK_BYTES,%d0
 mulu.l %d7,%d0
 lea placement_engine_tracks,%a3
 add.l %d0,%a3                 /* t */
 mvz.b PK_TRACK_ACTIVE_ALGO(%a3),%d3
 moveq #10,%d0
 cmp.l %d0,%d3
 beq .Ls_c                     /* Acoustic Hats */
 move.l #PK_CLOCK_BYTES,%d0
 mulu.l %d7,%d0
 lea placement_clocks,%a4
 add.l %d0,%a4                 /* c */
 move.l PK_CLOCK_PHASE(%a4),%d0
 cmp.l #147,%d0
 bcc .Ls_c                     /* pk_nhb_native_needed's general case */
 /* pk_nhb_native_needed: sum = phase + 13n (< 441); extra = sum>=294 ? 2 :
  * sum>=147; phase' = sum - 147*extra; need = n + extra + (phase'>=13) - have */
 moveq #13,%d1
 mulu.l %d2,%d1
 add.l %d0,%d1                 /* sum */
 move.l %d2,%d6
 cmp.l #294,%d1
 bcs.s 1f
 addq.l #2,%d6
 sub.l #294,%d1
 bra.s 2f
1:
 cmp.l #147,%d1
 bcs.s 2f
 addq.l #1,%d6
 sub.l #147,%d1
2:
 moveq #13,%d0
 cmp.l %d0,%d1
 bcs.s 3f
 addq.l #1,%d6
3:
 move.l PK_CLOCK_HAVE(%a4),%d5
 sub.l %d5,%d6                 /* need */
 move.l %d6,%d0
 add.l %d5,%d0
 moveq #20,%d1
 cmp.l %d1,%d0
 bhi .Ls_c                     /* need + have > 20 */
 /* committed: nothing was written before this point */
 lea S_DATA(%sp),%a5           /* data */
 tst.l %d5
 beq.s 4f
 move.l PK_CLOCK_CARRY(%a4),%d0
 move.w %d0,(%a5)              /* data[0] = (int16_t)carry */
4:
 lea (%a5,%d5.l*2),%a6         /* data + have */
 move.l #PK_ALGO_WT,%d0
 cmp.l %d0,%d3
 beq .Ls_wt
 move.l #PK_ALGO_SLAP,%d0
 cmp.l %d0,%d3
 beq .Ls_slap
 move.l #PK_ALGO_NT,%d0
 cmp.l %d0,%d3
 bne.s .Ls_generic
 tst.b PK_TRACK_ACTIVE_MODE(%a3)
 bne .Ls_nt
.Ls_generic:                   /* pk4_render(&placement_engine, tr, data + have, need) */
 move.l %d6,-(%sp)
 move.l %a6,-(%sp)
 move.l %d7,-(%sp)
 pea placement_engine
 jsr pk4_render
 lea 16(%sp),%sp
 tst.l %d0
 beq .Ls_fail
 bra .Ls_convert

.Ls_wt:                        /* pk_cf_wt_tables {pitch, envelope1, envelope2, base_wave, bank} */
 lea S_TAB(%sp),%a1
 move.l PK_ASSETS_PITCH(%a2),(%a1)
 move.l PK_ASSETS_ENV1(%a2),4(%a1)
 move.l PK_ASSETS_ENV2(%a2),8(%a1)
 move.l PK_ASSETS_WT_BASE(%a2),12(%a1)
 move.l PK_ASSETS_WT_BANK(%a2),16(%a1)
 move.l %a1,-(%sp)
 move.l %d6,-(%sp)
 move.l %a6,-(%sp)
 lea PK_TRACK_WT(%a3),%a0
 move.l %a0,-(%sp)
 jsr pk_cf_wt_render
 lea 16(%sp),%sp
 tst.l %d0
 beq .Ls_fail
 bra .Ls_convert

.Ls_slap:                      /* pk_cf_fold_tables {pitch, envelope1, envelope2, waves[4]}, rng */
 lea S_TAB(%sp),%a1
 move.l PK_ASSETS_PITCH(%a2),(%a1)
 move.l PK_ASSETS_ENV1(%a2),4(%a1)
 move.l PK_ASSETS_ENV2(%a2),8(%a1)
 lea PK_ASSETS_WAVES(%a2),%a0
 move.l (%a0),12(%a1)
 move.l 4(%a0),16(%a1)
 move.l 8(%a0),20(%a1)
 move.l 12(%a0),24(%a1)
 move.l 16(%a0),28(%a1)
 move.l 20(%a0),32(%a1)
 move.l 24(%a0),36(%a1)
 move.l 28(%a0),40(%a1)
 lea S_RNG(%sp),%a0
 move.l PK_TRACK_RNG_LOW(%a3),(%a0)
 move.l PK_TRACK_RNG_HIGH(%a3),4(%a0)
 move.l %a0,-(%sp)
 move.l %a1,-(%sp)
 move.l %d6,-(%sp)
 move.l %a6,-(%sp)
 lea PK_TRACK_SLAP(%a3),%a0
 move.l %a0,-(%sp)
 jsr pk_cf_slap_render
 lea 20(%sp),%sp
 tst.l %d0
 beq .Ls_fail
 move.l S_RNG(%sp),PK_TRACK_RNG_LOW(%a3)
 move.l S_RNG+4(%sp),PK_TRACK_RNG_HIGH(%a3)
 bra .Ls_convert

.Ls_nt:                        /* pk_cf_nt_shared_tables {envelope1, envelope2, waves[4]}, rng */
 lea S_TAB(%sp),%a1
 move.l PK_ASSETS_ENV1(%a2),(%a1)
 move.l PK_ASSETS_ENV2(%a2),4(%a1)
 lea PK_ASSETS_WAVES(%a2),%a0
 move.l (%a0),8(%a1)
 move.l 4(%a0),12(%a1)
 move.l 8(%a0),16(%a1)
 move.l 12(%a0),20(%a1)
 move.l 16(%a0),24(%a1)
 move.l 20(%a0),28(%a1)
 move.l 24(%a0),32(%a1)
 move.l 28(%a0),36(%a1)
 lea S_RNG(%sp),%a0
 move.l PK_TRACK_RNG_LOW(%a3),(%a0)
 move.l PK_TRACK_RNG_HIGH(%a3),4(%a0)
 move.l %a0,-(%sp)
 move.l %a1,-(%sp)
 move.l %d6,-(%sp)
 move.l %a6,-(%sp)
 lea PK_TRACK_NT_SHARED(%a3),%a0
 move.l %a0,-(%sp)
 jsr pk_cf_nt_shared_render
 lea 20(%sp),%sp
 tst.l %d0
 beq .Ls_fail
 move.l S_RNG(%sp),PK_TRACK_RNG_LOW(%a3)
 move.l S_RNG+4(%sp),PK_TRACK_RNG_HIGH(%a3)

.Ls_convert:                   /* pk_cf_native_convert(c, data, n, placement_output[tr] + start) */
 move.l %d7,%d0
 lsl.l #4,%d0
 add.l S_START(%sp),%d0
 lea placement_output,%a0
 lea (%a0,%d0.l*4),%a0
 move.l %a0,-(%sp)
 move.l %d2,-(%sp)
 move.l %a5,-(%sp)
 move.l %a4,-(%sp)
 jsr pk_nhb_native_convert_fast
 lea 16(%sp),%sp
 lea placement_native_samples,%a0
 add.l %d6,(%a0,%d7.l*4)
 moveq #1,%d0
.Ls_out:
 movem.l (%sp),%d2-%d7/%a2-%a6
 lea S_FRAME(%sp),%sp
 rts
.Ls_fail:
 moveq #0,%d0
 bra.s .Ls_out
.Ls_c:
 movem.l (%sp),%d2-%d7/%a2-%a6
 lea S_FRAME(%sp),%sp
 jmp placement_segment_c
.size placement_segment,.-placement_segment

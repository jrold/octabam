/* pk_cf_slap_render: the PKFM24 Slap chunk with its loops in assembly.
 *
 *   int pk_cf_slap_render(uint8_t *s, int16_t *d, uint32_t n,
 *                         const pk_cf_fold_tables *t, pk_cf_fold_rng *rng)
 *
 * Exactly the C (slap-env-asm.c, renamed pk_cf_slap_render_c) for 1 <= n <= 20
 * with s, d, t, t->envelope1 and rng non-null and an envelope curve (s[0x75])
 * that is linear or has its table: the same EMAC context (MACSR 0x20, ACC0
 * cleared, all three restored), the noise source and its 64-bit LCG, the same
 * pk_budget_slap_filter, pk_cf_env_block segments split at each counter
 * retrigger, the >>16 envelope scale, pk_cf_slap_delay_span and the velocity
 * scale with int16 saturation. The object is little-endian at the firmware's
 * offsets. Every other case jumps, stack untouched, to pk_cf_slap_render_c.
 *
 * The C's per-sample counter loop is taken here a run at a time: while
 * target > first, first advances min(target - first, remaining) samples at
 * once; at target, a retrigger consumes one sample (second < limit), and
 * with neither left the remaining samples change nothing. The noise state,
 * RNG and filter history are written back as soon as they are final; no
 * callee reads them.
 */
.set F_SAVE, 0
.set F_MAC, 44          /* status, acc0, accext01 */
.set F_FS, 56           /* slap_filter_state: coeff, damp, first, second, velocity */
.set F_DS, 76           /* slap_delay_state: u16 index, mix, delay[5], gain[5] */
.set F_ENV, 100         /* pk_cf_env_ctx: v, st, up, dn, curve, flags */
.set F_NOISE, 124       /* int16_t[20] */
.set F_FILT, 164        /* int32_t[20] */
.set F_INNER, 244       /* int32_t[20] */
.set F_AMPS, 324        /* uint16_t[20] */
.set FRAME, 364
.set A_S, FRAME+4
.set A_D, FRAME+8
.set A_N, FRAME+12
.set A_T, FRAME+16
.set A_RNG, FRAME+20

.section .text.pk_cf_slap_render_asm,"ax",@progbits
.balign 16
.globl pk_cf_slap_render
.type pk_cf_slap_render,@function
pk_cf_slap_render:
 move.l 12(%sp),%d0
 subq.l #1,%d0
 moveq #19,%d1
 cmp.l %d1,%d0
 bhi .Lc                       /* n == 0 or n > 20 */
 tst.l 4(%sp)
 beq .Lc
 tst.l 8(%sp)
 beq .Lc
 tst.l 20(%sp)
 beq .Lc
 move.l 16(%sp),%d0
 beq .Lc
 move.l %d0,%a0                /* t */
 tst.l 4(%a0)
 beq .Lc                       /* !t->envelope1 */
 move.l 4(%sp),%a1
 mvz.b 0x75(%a1),%d0
 subq.l #1,%d0
 moveq #1,%d1
 cmp.l %d1,%d0
 bhi.s 1f                      /* linear */
 tst.l 4(%a0,%d0.l*4)
 beq .Lc                       /* curve without its table: per-sample C path */
1:
 lea -FRAME(%sp),%sp
 movem.l %d2-%d7/%a2-%a6,(%sp)
 move.l %macsr,%d0             /* pk_cf_render_math_begin */
 move.l #0,%macsr
 move.l %acc0,%d1
 move.l %accext01,%d2
 move.l #0,%acc0
 move.l #0x20,%macsr
 movem.l %d0-%d2,F_MAC(%sp)

 move.l A_S(%sp),%a5
 move.l A_N(%sp),%d2
 /* noise: d3 count, a6 reload, d1 held, d5/d6 RNG low/high, d7 LCG b */
 move.l 0x60(%a5),%d0
 byterev %d0
 mvz.w %d0,%d3
 swap %d0
 mvz.w %d0,%d0
 move.l %d0,%a6
 move.l 0x70(%a5),%d0
 byterev %d0
 mvs.w %d0,%d1
 move.l A_RNG(%sp),%a0
 move.l (%a0),%d5
 move.l 4(%a0),%d6
 move.l #0x4c957f2d,%d7
 lea F_NOISE(%sp),%a0
 lea (%a0,%d2.l*2),%a1
.Lnz:
 tst.l %d3
 beq .Lnz_rnd
 subq.l #1,%d3
.Lnz_put:
 move.w %d1,(%a0)+
 cmp.l %a1,%a0
 bcs.s .Lnz
 move.l %d3,%d0                /* w16(0x60, count) */
 byterev %d0
 swap %d0
 move.w %d0,0x60(%a5)
 move.l %d1,%d0                /* w16(0x70, held) */
 byterev %d0
 swap %d0
 move.w %d0,0x70(%a5)
 move.l A_RNG(%sp),%a0
 move.l %d5,(%a0)
 move.l %d6,4(%a0)

 /* filter: fs = {coeff r16(0xaa), damp r16(0xa8), first, second, velocity} */
 move.l 0xa8(%a5),%d0
 byterev %d0
 mvz.w %d0,%d1
 move.l %d1,F_FS+4(%sp)
 swap %d0
 mvz.w %d0,%d0
 move.l %d0,F_FS(%sp)
 move.l 0xac(%a5),%d0
 byterev %d0
 move.l %d0,F_FS+8(%sp)
 move.l 0xb0(%a5),%d0
 byterev %d0
 move.l %d0,F_FS+12(%sp)
 move.l 0xb4(%a5),%d0
 byterev %d0
 move.l %d0,F_FS+16(%sp)
 lea F_FS(%sp),%a0
 lea F_NOISE(%sp),%a1
 lea F_FILT(%sp),%a2
 move.l %d2,-(%sp)
 move.l %a2,-(%sp)
 move.l %a1,-(%sp)
 move.l %a0,-(%sp)
 jsr pk_budget_slap_filter
 lea 16(%sp),%sp
 move.l F_FS+8(%sp),%d0
 byterev %d0
 move.l %d0,0xac(%a5)
 move.l F_FS+12(%sp),%d0
 byterev %d0
 move.l %d0,0xb0(%a5)
 move.l F_FS+16(%sp),%d0
 byterev %d0
 move.l %d0,0xb4(%a5)

 /* envelope context */
 lea F_ENV(%sp),%a4
 move.l 0x80(%a5),%d0
 byterev %d0
 move.l %d0,(%a4)              /* v */
 mvz.b 0x74(%a5),%d0
 move.l %d0,4(%a4)             /* st */
 move.l 0x94(%a5),%d0
 byterev %d0
 mvz.w %d0,%d1
 move.l %d1,8(%a4)             /* up */
 swap %d0
 mvz.w %d0,%d0
 move.l %d0,12(%a4)            /* dn */
 moveq #0,%d0
 mvz.b 0x75(%a5),%d1
 subq.l #1,%d1
 moveq #1,%d3
 cmp.l %d3,%d1
 bhi.s 2f
 move.l A_T(%sp),%a0
 move.l 4(%a0,%d1.l*4),%d0
2:
 move.l %d0,16(%a4)            /* curve */
 moveq #0,%d1
 tst.b 0x78(%a5)
 sne %d1
 moveq #1,%d0
 and.l %d0,%d1                 /* f4 */
 tst.b 0x7a(%a5)
 sne %d0
 andi.l #2,%d0
 or.l %d0,%d1                  /* f6 */
 tst.b 0x7b(%a5)
 sne %d0
 andi.l #4,%d0
 or.l %d0,%d1                  /* f7 */
 tst.b 0x84(%a5)
 sne %d0
 andi.l #8,%d0
 or.l %d0,%d1                  /* f10 */
 move.l %d1,20(%a4)

 /* counters: d3 first, d4 second, d5 limit, d6 target, d7 i, a2 start */
 move.l 0xc2(%a5),%d0
 byterev %d0
 mvz.w %d0,%d3
 swap %d0
 mvz.w %d0,%d4
 move.l 0xc6(%a5),%d0
 byterev %d0
 mvz.w %d0,%d5
 move.l 0xca(%a5),%d0
 byterev %d0
 mvz.w %d0,%d6
 lea F_AMPS(%sp),%a3
 moveq #0,%d7
 suba.l %a2,%a2
.Lct:
 cmp.l %d3,%d6
 bls.s .Lct_at                 /* target <= first */
 move.l %d6,%d0
 sub.l %d3,%d0                 /* target - first */
 move.l %d2,%d1
 sub.l %d7,%d1                 /* remaining */
 cmp.l %d1,%d0
 bls.s 3f
 move.l %d1,%d0
3:
 add.l %d0,%d3
 add.l %d0,%d7
 cmp.l %d2,%d7
 bcc.s .Lct_done
.Lct_at:
 cmp.l %d4,%d5
 bls.s .Lct_done               /* limit <= second: nothing changes again */
 addq.l #1,%d4
 moveq #0,%d3
 cmp.l %a2,%d7
 bls.s 4f
 move.l %d7,%d0                /* pk_cf_env_block(&x, amps + start, i - start) */
 sub.l %a2,%d0
 move.l %d0,-(%sp)
 lea (%a3,%a2.l*2),%a0
 move.l %a0,-(%sp)
 move.l %a4,-(%sp)
 jsr pk_cf_env_block
 lea 12(%sp),%sp
 move.l %d7,%a2
4:
 move.b #1,0x84(%a5)           /* retrigger: s[0x84]=1, x.flags|=8, x.st=1 */
 moveq #8,%d0
 or.l %d0,20(%a4)
 moveq #1,%d0
 move.l %d0,4(%a4)
 tst.b 0x7c(%a5)
 beq.s 5f
 clr.l (%a4)
5:
 addq.l #1,%d7
 cmp.l %d2,%d7
 bcs.s .Lct
.Lct_done:
 cmp.l %a2,%d2
 bls.s 6f
 move.l %d2,%d0
 sub.l %a2,%d0
 move.l %d0,-(%sp)
 lea (%a3,%a2.l*2),%a0
 move.l %a0,-(%sp)
 move.l %a4,-(%sp)
 jsr pk_cf_env_block
 lea 12(%sp),%sp
6:
 move.l 4(%a4),%d0
 move.b %d0,0x74(%a5)          /* s[0x74] = x.st */
 move.l (%a4),%d0
 byterev %d0
 move.l %d0,0x80(%a5)          /* w32(0x80, x.v) */
 move.l %d4,%d0                /* w16(0xc2, first); w16(0xc4, second) */
 swap %d0
 or.l %d3,%d0
 byterev %d0
 move.l %d0,0xc2(%a5)

 /* inner[i] = (filtered[i] * amps[i]) >> 16 */
 lea F_FILT(%sp),%a0
 lea F_INNER(%sp),%a2
 moveq #16,%d1
 move.l %d2,%d3
.Lmul:
 mvz.w (%a3)+,%d0
 muls.l (%a0)+,%d0
 asr.l %d1,%d0
 move.l %d0,(%a2)+
 subq.l #1,%d3
 bne.s .Lmul

 /* delay: ds = {index r16(0x266a), mix r16(0x266c), delay[5] r16(0xcc..), gain[5] r16(0xd6..)} */
 move.l 0x266a(%a5),%d0
 byterev %d0
 swap %d0
 move.l %d0,F_DS(%sp)
 move.l 0xcc(%a5),%d0
 byterev %d0
 swap %d0
 move.l %d0,F_DS+4(%sp)
 move.l 0xd0(%a5),%d0
 byterev %d0
 swap %d0
 move.l %d0,F_DS+8(%sp)
 move.l 0xd4(%a5),%d0
 byterev %d0
 swap %d0
 move.l %d0,F_DS+12(%sp)
 move.l 0xd8(%a5),%d0
 byterev %d0
 swap %d0
 move.l %d0,F_DS+16(%sp)
 move.l 0xdc(%a5),%d0
 byterev %d0
 swap %d0
 move.l %d0,F_DS+20(%sp)
 lea F_DS(%sp),%a0
 lea 0xe0(%a5),%a1             /* PK_CF_SLAP_RING_OFF */
 lea F_INNER(%sp),%a2
 move.l %d2,-(%sp)
 move.l %a2,-(%sp)
 move.l %a1,-(%sp)
 move.l %a0,-(%sp)
 jsr pk_cf_slap_delay_span
 lea 16(%sp),%sp
 mvz.w F_DS(%sp),%d0           /* w16(0x266a, ds.index) */
 byterev %d0
 swap %d0
 move.w %d0,0x266a(%a5)

 /* d[i] = clamp16((inner[i] * velocity) >> 8) */
 mvz.b 6(%a5),%d4
 lea F_INNER(%sp),%a0
 move.l A_D(%sp),%a1
 move.l %d2,%d3
.Lvel:
 move.l (%a0)+,%d0
 muls.l %d4,%d0
 asr.l #8,%d0
 mvs.w %d0,%d1
 cmp.l %d0,%d1
 bne.s .Lvel_sat
.Lvel_put:
 move.w %d0,(%a1)+
 subq.l #1,%d3
 bne.s .Lvel

 moveq #1,%d0
 movem.l F_MAC(%sp),%d1-%d3    /* pk_cf_render_math_end_saved */
 move.l #0,%macsr
 move.l %d2,%acc0
 move.l %d3,%accext01
 move.l %d1,%macsr
 movem.l (%sp),%d2-%d7/%a2-%a6
 lea FRAME(%sp),%sp
 rts

.Lvel_sat:
 tst.l %d0
 bmi.s 7f
 move.l #32767,%d0
 bra.s .Lvel_put
7:
 move.l #-32768,%d0
 bra.s .Lvel_put

.Lnz_rnd:                      /* count = reload; held = (int16)LCG */
 move.l %a6,%d3
 move.l #0x5851f42d,%d0
 mulu.l %d5,%d0                /* ol * a */
 move.l %d6,%d4
 mulu.l %d7,%d4                /* oh * b */
 add.l %d4,%d0
 mac.l %d5,%d7,%acc0           /* pk_cf_render_rng_hi(ol) */
 movclr.l %acc0,%d4
 asr.l #1,%d4
 tst.l %d5
 bpl.s 8f
 add.l %d7,%d4
8:
 mulu.l %d7,%d5                /* pl = ol * b */
 addq.l #1,%d5                 /* nl = pl + 1, X = carry */
 addx.l %d4,%d0                /* nh = acc + ph + carry */
 move.l %d0,%d6
 mvs.w %d0,%d1
 bra .Lnz_put

.Lc:
 jmp pk_cf_slap_render_c
.size pk_cf_slap_render,.-pk_cf_slap_render

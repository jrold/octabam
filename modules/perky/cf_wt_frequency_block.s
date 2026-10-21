/* Wavetable pitch-envelope frequency pass (wt_frequency_block's arithmetic).
 *
 * For each u16 pitch-envelope value pe:
 *   f = (base + ((pe_amount * factors[pe >> 6]) >> 9)) >> half_rate     (u32)
 *   a = f << 20
 *   step = ((mac.l a, 0x057619f1 -> movclr.l) >> 1) >> 10  -  (a >> 31)   (asr)
 * which is wt_frequency_step(): pk_cf_render_frequency_hi is the same mac.l
 * and movclr.l pair, so the caller's render-math context (MACSR 0x20,
 * fractional, no rounding) is required and left unchanged. With pe_amount 0
 * every step is the one value of base >> half_rate, exactly as the C.
 *
 *   void pk_cf_wt_frequency_block(const uint16_t *pe, uint32_t *steps,
 *       uint32_t n, uint32_t base, uint32_t pe_amount, uint32_t half_rate,
 *       const uint8_t *factors)
 *   pk_cf_wt_frequency_core: a0 pe, a1 steps, a3 steps + n, d6 base,
 *       d5 pe_amount, d4 half_rate, a2 factors; clobbers d0-d7, a0, a1.
 */
.section .text.pk_cf_wt_frequency_block,"ax",@progbits
.balign 16
.globl pk_cf_wt_frequency_block
.type pk_cf_wt_frequency_block,@function
pk_cf_wt_frequency_block:
 lea -40(%sp),%sp
 movem.l %d2-%d7/%a2-%a5,(%sp)
 move.l 44(%sp),%a0            /* pe */
 move.l 48(%sp),%a1            /* steps */
 move.l 52(%sp),%d0            /* n */
 move.l 56(%sp),%d6            /* base */
 move.l 60(%sp),%d5            /* pe_amount */
 move.l 64(%sp),%d4            /* half_rate */
 move.l 68(%sp),%a2            /* factors */
 lea (%a1,%d0.l*4),%a3         /* end */
 bsr.s .Lf_core
 movem.l (%sp),%d2-%d7/%a2-%a5
 lea 40(%sp),%sp
 rts
.globl pk_cf_wt_frequency_core
pk_cf_wt_frequency_core:
.Lf_core:
 move.l #0x057619f1,%d3
 moveq #20,%d7
 moveq #10,%d2
 cmp.l %a3,%a1
 beq .Lf_done
 tst.l %d5
 bne.s .Lf_loop
 /* No pitch envelope: one step for the whole block. */
 move.l %d6,%d0
 lsr.l %d4,%d0
 lsl.l %d7,%d0
 mac.l %d0,%d3,%acc0
 movclr.l %acc0,%d1
 asr.l #1,%d1
 asr.l %d2,%d1
 add.l %d0,%d0
 subx.l %d0,%d0
 sub.l %d0,%d1
.Lf_fill:
 move.l %d1,(%a1)+
 cmp.l %a3,%a1
 bne.s .Lf_fill
 bra.s .Lf_done
.balign 4
.Lf_loop:
 mvz.w (%a0)+,%d0
 lsr.l #6,%d0
 mvz.b (%a2,%d0.l),%d0
 muls.l %d5,%d0
 lsr.l #8,%d0
 lsr.l #1,%d0
 add.l %d6,%d0
 lsr.l %d4,%d0
 lsl.l %d7,%d0
 mac.l %d0,%d3,%acc0
 movclr.l %acc0,%d1
 asr.l #1,%d1
 asr.l %d2,%d1
 add.l %d0,%d0                 /* X = sign of f << 20 */
 subx.l %d0,%d0                /* (f << 20) >> 31 */
 sub.l %d0,%d1
 move.l %d1,(%a1)+
 cmp.l %a3,%a1
 bne.s .Lf_loop
.Lf_done:
 rts
.size pk_cf_wt_frequency_block,.-pk_cf_wt_frequency_block

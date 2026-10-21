/* Common PĒRKONS envelope, a block of n samples into u16[n].
 *
 * Exactly the per-sample step the Wavetable, Noise/Tone and Slap renderers
 * share (wt_env_step / nt_lin_step / slap_env):
 *   0: if (f7 || f4) st = 1
 *   1: v += up; if (v > 0xffffe) { st = (f4 || f6) ? 4 : 3; if (v >= 0x100000) v = 0xfffff }
 *   2: -
 *   3: if (!f7 && (f4 || !f10)) st = 4
 *   4: if (f7) st = 1; else { v -= dn; if (v <= 0) { v = 0; st = f4 ? 1 : 0 } }
 *   other: -
 * then the sample is (v >> 4) & 0xffff (linear) or the curve table's
 * interpolation a + ((z - a) * (v & 0x3ff) >> 10) at index (v >> 10) & 0x7ff,
 * z at the next index modulo 2048 (u16 little-endian table, signed 32-bit
 * product, arithmetic shift). All arithmetic is modulo 2^32 with signed
 * comparisons and logical index shifts, as the C does.
 *
 * Context (all longs): +0 v, +4 st, +8 up, +12 dn, +16 curve table (0 for
 * linear), +20 flags (bit0 f4, bit1 f6, bit2 f7, bit3 f10). v and st are
 * written back. Attack and decay run in tight loops; states in which v and
 * st cannot change fill a constant; every other transition takes the general
 * one-sample step. No EMAC, IRQ mask or peripheral access.
 *
 *   void pk_cf_env_block(pk_cf_env_ctx *ctx, uint16_t *out, uint32_t n)
 *   pk_cf_env_core: the same with a5 = ctx, a1 = out, a4 = out + n and no
 *   register preservation (clobbers d0-d7, a0-a4, a6); for assembly callers.
 *
 * Registers: d0 v, d4 st, d3 #10, d5 a, d6 cached index, d7 z-a, d1/d2
 * scratch, a0 curve, a1 out, a2 up, a3 dn, a4 end, a5 ctx, a6 flags.
 */
.section .text.pk_cf_env_block,"ax",@progbits
.balign 4
.globl pk_cf_env_block
.type pk_cf_env_block,@function
pk_cf_env_block:
 lea -44(%sp),%sp
 movem.l %d2-%d7/%a2-%a6,(%sp)
 move.l 48(%sp),%a5
 move.l 52(%sp),%a1
 move.l 56(%sp),%d1
 lea (%a1,%d1.l*2),%a4
 bsr .Lcore
 movem.l (%sp),%d2-%d7/%a2-%a6
 lea 44(%sp),%sp
 rts

.globl pk_cf_env_core
pk_cf_env_core:
.Lcore:
 move.l (%a5),%d0
 move.l 4(%a5),%d4
 move.l 8(%a5),%a2
 move.l 12(%a5),%a3
 move.l 16(%a5),%a0
 move.l 20(%a5),%a6
 moveq #10,%d3
 moveq #-1,%d6
 cmp.l %a4,%a1
 beq .Ldone
 cmp.l #0,%a0
 beq .Llin_dispatch
 bra .Lcrv_dispatch

/* ---- curve output: d1 = sample from d0 ------------------------------- */
.macro CURVE_VALUE
 move.l %d0,%d2
 lsr.l %d3,%d2
 and.l #0x7ff,%d2
 cmp.l %d6,%d2
 beq.s 8f
 move.l %d2,%d6
 cmp.l #0x7ff,%d2
 beq.s 7f
 move.l (%a0,%d2.l*2),%d5
 byterev %d5
 move.l %d5,%d7
 swap %d7
 mvz.w %d7,%d7
 mvz.w %d5,%d5
 sub.l %d5,%d7
 bra.s 8f
7:
 bsr .Lcrv_wrap
8:
 move.l %d0,%d1
 and.l #0x3ff,%d1
 muls.l %d7,%d1
 asr.l %d3,%d1
 add.l %d5,%d1
.endm

.macro LINEAR_VALUE
 move.l %d0,%d1
 lsr.l #4,%d1
.endm

/* a = tab[2047], z = tab[0]: two u16 little-endian reads. */
.Lcrv_wrap:
 mvz.b 4095(%a0),%d5
 lsl.l #8,%d5
 mvz.b 4094(%a0),%d1
 or.l %d1,%d5
 mvz.b 1(%a0),%d7
 lsl.l #8,%d7
 mvz.b (%a0),%d1
 or.l %d1,%d7
 sub.l %d5,%d7
 rts

/* ---- dispatch: choose the run for the current state ------------------- */
.macro DISPATCH attack,decay,general,fill
 cmp.l #1,%d4
 beq \attack
 move.l %a6,%d1
 cmp.l #4,%d4
 bne.s 1f
 btst #2,%d1
 beq \decay
 bra \general
1:
 tst.l %d4
 bne.s 2f
 and.l #5,%d1                  /* 0: f7 or f4 moves to 1 */
 bne \general
 bra \fill
2:
 cmp.l #3,%d4
 bne \fill                     /* 2 and any other value never change */
 btst #2,%d1                   /* 3: !f7 && (f4 || !f10) moves to 4 */
 bne \fill
 btst #0,%d1
 bne \general
 btst #3,%d1
 bne \fill
 bra \general
.endm

.Lcrv_dispatch:
 DISPATCH .Lcrv_attack,.Lcrv_decay,.Lcrv_general,.Lcrv_fill

.balign 4
.Lcrv_decay:
 sub.l %a3,%d0
 tst.l %d0                     /* the wrapped value, not the subtraction's overflow */
 ble .Lcrv_bottom
 CURVE_VALUE
 move.w %d1,(%a1)+
 cmp.l %a4,%a1
 bne .Lcrv_decay
 moveq #4,%d4
 bra .Ldone

.balign 4
.Lcrv_attack:
 add.l %a2,%d0
 cmp.l #0xffffe,%d0
 bgt .Lcrv_top
 CURVE_VALUE
 move.w %d1,(%a1)+
 cmp.l %a4,%a1
 bne .Lcrv_attack
 moveq #1,%d4
 bra .Ldone

.Lcrv_bottom:
 bsr .Lbottom
 bra.s .Lcrv_one
.Lcrv_top:
 bsr .Ltop
 bra.s .Lcrv_one
.Lcrv_general:
 bsr .Lgeneral_step
.Lcrv_one:
 CURVE_VALUE
 move.w %d1,(%a1)+
 cmp.l %a4,%a1
 bne .Lcrv_dispatch
 bra .Ldone

.Lcrv_fill:
 CURVE_VALUE
 bra .Lfill

/* ---- linear output ---------------------------------------------------- */
.Llin_dispatch:
 DISPATCH .Llin_attack,.Llin_decay,.Llin_general,.Llin_fill

.balign 4
.Llin_decay:
 sub.l %a3,%d0
 tst.l %d0
 ble .Llin_bottom
 LINEAR_VALUE
 move.w %d1,(%a1)+
 cmp.l %a4,%a1
 bne .Llin_decay
 moveq #4,%d4
 bra .Ldone

.balign 4
.Llin_attack:
 add.l %a2,%d0
 cmp.l #0xffffe,%d0
 bgt .Llin_top
 LINEAR_VALUE
 move.w %d1,(%a1)+
 cmp.l %a4,%a1
 bne .Llin_attack
 moveq #1,%d4
 bra .Ldone

.Llin_bottom:
 bsr .Lbottom
 bra.s .Llin_one
.Llin_top:
 bsr .Ltop
 bra.s .Llin_one
.Llin_general:
 bsr .Lgeneral_step
.Llin_one:
 LINEAR_VALUE
 move.w %d1,(%a1)+
 cmp.l %a4,%a1
 bne .Llin_dispatch
 bra .Ldone

.Llin_fill:
 LINEAR_VALUE

/* ---- constant tail: d1 the sample, v and st unchanged ----------------- */
.Lfill:
 move.w %d1,(%a1)+
 cmp.l %a4,%a1
 bne.s .Lfill
 bra .Ldone

/* ---- transitions ------------------------------------------------------ */
/* Decay reached v <= 0: v = 0, st = f4 ? 1 : 0. */
.Lbottom:
 clr.l %d0
 moveq #0,%d4
 move.l %a6,%d1
 btst #0,%d1
 beq.s 1f
 moveq #1,%d4
1:
 rts

/* Attack passed 0xffffe: st = (f4 || f6) ? 4 : 3, clamp at 0xfffff. */
.Ltop:
 moveq #4,%d4
 move.l %a6,%d1
 and.l #3,%d1
 bne.s 1f
 moveq #3,%d4
1:
 cmp.l #0x100000,%d0
 blt.s 2f
 move.l #0xfffff,%d0
2:
 rts

/* One general step of the current state (d4, d0). */
.Lgeneral_step:
 move.l %a6,%d1
 tst.l %d4
 bne.s 10f
 and.l #5,%d1
 beq.s 19f
 moveq #1,%d4
 rts
10:
 cmp.l #1,%d4
 bne.s 11f
 add.l %a2,%d0
 cmp.l #0xffffe,%d0
 bgt .Ltop
 rts
11:
 cmp.l #3,%d4
 bne.s 13f
 btst #2,%d1
 bne.s 19f
 btst #0,%d1
 bne.s 14f
 btst #3,%d1
 bne.s 19f
14:
 moveq #4,%d4
 rts
13:
 cmp.l #4,%d4
 bne.s 19f
 btst #2,%d1
 beq.s 15f
 moveq #1,%d4
 rts
15:
 sub.l %a3,%d0
 tst.l %d0
 ble .Lbottom
19:
 rts

.Ldone:
 move.l %d0,(%a5)
 move.l %d4,4(%a5)
 rts
.size pk_cf_env_block,.-pk_cf_env_block

/* Noise/Tone shared renderer (Waveform2 M2/M3 and Resonant M3), one assembly
 * chunk with the C's arithmetic (noise-tone-native20.c nt_shared_chunk).
 *
 *   int pk_cf_nt_shared_render(uint8_t *s, int16_t *d, uint32_t n,
 *       const pk_cf_nt_shared_tables *t, pk_cf_nt_rng *r)
 *
 * Fast path only when proven before any state changes: s, d, t, r non-null,
 * 1 <= n <= 20, the envelope linear or its curve table present, and both
 * oscillators' current and next waves found in t->waves. Anything else
 * tail-calls the original C (pk_cf_nt_shared_render_c).
 *
 * Order and arithmetic are the original's: render-math context begin; the
 * amplitude envelope (pk_cf_env_core) committed to 0x74/0x80; the noise
 * source and the twice-stepped filter, with the shared RNG, committed to
 * 0x60/0x70 and 0xac/0xb0/0xb4; the mix of noise and both 256-point
 * oscillators into d; the oscillator phase/current commits; context end.
 *
 * RNG capture (for a merged V4 frame): when pk_nt_capture_at <= n, the RNG
 * (low, high) after that many native samples of the noise pass is stored in
 * pk_nt_capture_rng and pk_nt_capture_done is set. The noise pass runs in two
 * pieces around that index; nothing else changes. The default ~0 never
 * captures.
 */
.data
.balign 4
.globl pk_nt_capture_at, pk_nt_capture_done, pk_nt_capture_rng
pk_nt_capture_at:   .long 0xffffffff
pk_nt_capture_done: .long 0
pk_nt_capture_rng:  .long 0, 0
.set SAVE,    0
.set ENV,    44
.set NOISE,  68
.set AMPS,  108                /* NOISE + 40: the mix reads 40(a0) */
.set O1,    148                /* table, next table, cur, next, wrapped */
.set O2,    168
.set MAC,   188
.set VEL,   200
.set ENDP,  204
.set FRAME, 208
.set ARG_S, FRAME+48
.set ARG_D, FRAME+52
.set ARG_N, FRAME+56
.set ARG_T, FRAME+60
.set ARG_R, FRAME+64

.macro LD32 off,reg
 move.l \off(%a5),\reg
 byterev \reg
.endm
.macro LD16 off,reg
 move.l \off(%a5),\reg
 byterev \reg
 mvz.w \reg,\reg
.endm
.macro ST32 reg,off
 byterev \reg
 move.l \reg,\off(%a5)
.endm
.macro ST16 reg,off
 move.b \reg,\off(%a5)
 lsr.l #8,\reg
 move.b \reg,\off+1(%a5)
.endm

.section .text.pk_cf_nt_shared_render,"ax",@progbits
.balign 16
.globl pk_cf_nt_shared_render
.type pk_cf_nt_shared_render,@function
pk_cf_nt_shared_render:
 lea -44(%sp),%sp
 movem.l %d2-%d7/%a2-%a6,(%sp)
 lea -FRAME(%sp),%sp
 move.l ARG_S(%sp),%a5
 cmp.l #0,%a5
 beq .Lfallback
 tst.l ARG_D(%sp)
 beq .Lfallback
 move.l ARG_T(%sp),%a2
 cmp.l #0,%a2
 beq .Lfallback
 tst.l ARG_R(%sp)
 beq .Lfallback
 move.l ARG_N(%sp),%d7
 beq .Lfallback
 moveq #20,%d0
 cmp.l %d0,%d7
 bhi .Lfallback
 /* envelope curve: 1 -> envelope1, 2 -> envelope2, else linear */
 mvz.b 0x75(%a5),%d0
 sub.l %a0,%a0
 cmp.l #1,%d0
 bne.s 1f
 move.l (%a2),%a0
 bra.s 2f
1:
 cmp.l #2,%d0
 bne.s 3f
 move.l 4(%a2),%a0
2:
 cmp.l #0,%a0
 beq .Lfallback
3:
 move.l %a0,ENV+16(%sp)
 /* oscillator views */
 LD32 0x38,%d0
 bsr .Lfind
 cmp.l #0,%a0
 beq .Lfallback
 move.l %a0,O1(%sp)
 move.l %a0,O1+4(%sp)
 move.l %d0,O1+8(%sp)
 LD32 0x3c,%d1
 move.l %d1,O1+12(%sp)
 cmp.l %d0,%d1
 beq.s 4f
 move.l %d1,%d0
 bsr .Lfind
 cmp.l #0,%a0
 beq .Lfallback
 move.l %a0,O1+4(%sp)
4:
 LD32 0xd0,%d0
 bsr .Lfind
 cmp.l #0,%a0
 beq .Lfallback
 move.l %a0,O2(%sp)
 move.l %a0,O2+4(%sp)
 move.l %d0,O2+8(%sp)
 LD32 0xd4,%d1
 move.l %d1,O2+12(%sp)
 cmp.l %d0,%d1
 beq.s 5f
 move.l %d1,%d0
 bsr .Lfind
 cmp.l #0,%a0
 beq .Lfallback
 move.l %a0,O2+4(%sp)
5:
 clr.l O1+16(%sp)
 clr.l O2+16(%sp)
 /* ---- render-math context begin ---- */
 move.l %macsr,%d0
 move.l %d0,MAC(%sp)
 move.l #0,%macsr
 move.l %acc0,%d0
 move.l %d0,MAC+4(%sp)
 move.l %accext01,%d0
 move.l %d0,MAC+8(%sp)
 move.l #0,%acc0
 move.l #0x20,%macsr
 /* ---- amplitude envelope (nt_envelope_block) ---- */
 LD32 0x80,%d0
 move.l %d0,ENV(%sp)
 mvz.b 0x74(%a5),%d0
 move.l %d0,ENV+4(%sp)
 LD16 0x94,%d0
 move.l %d0,ENV+8(%sp)
 LD16 0x96,%d0
 move.l %d0,ENV+12(%sp)
 moveq #0,%d0
 tst.b 0x78(%a5)
 beq.s 6f
 moveq #1,%d0
6:
 tst.b 0x7a(%a5)
 beq.s 7f
 addq.l #2,%d0
7:
 tst.b 0x7b(%a5)
 beq.s 8f
 addq.l #4,%d0
8:
 tst.b 0x84(%a5)
 beq.s 9f
 addq.l #8,%d0
9:
 move.l %d0,ENV+20(%sp)
 move.l %a5,-(%sp)
 move.l %d7,-(%sp)
 lea ENV+8(%sp),%a5
 lea AMPS+8(%sp),%a1
 lea (%a1,%d7.l*2),%a4
 jsr pk_cf_env_core
 move.l (%sp)+,%d7
 move.l (%sp)+,%a5
 move.l ENV+4(%sp),%d0
 move.b %d0,0x74(%a5)
 move.l ENV(%sp),%d0
 ST32 %d0,0x80
 /* ---- noise and filter (nt_noise_filter_block) ---- */
 move.l %a5,-(%sp)
 move.l %d7,-(%sp)
 lea NOISE+8(%sp),%a0
 lea (%a0,%d7.l*2),%a1
 move.l ARG_R+8(%sp),%a6
 LD16 0x60,%d0
 move.l %d0,%a3                /* count */
 LD16 0x62,%d0
 move.l %d0,%a2                /* reload */
 LD16 0x70,%d1
 mvs.w %d1,%d1                 /* held value, s16 */
 LD16 0xa8,%d6                 /* drive */
 LD16 0xaa,%d5                 /* coeff */
 LD32 0xac,%d2                 /* first */
 LD32 0xb0,%d3                 /* second */
 LD32 0xb4,%d4                 /* velocity */
 move.l #32767,%a4
 move.l #-32767,%a5
 move.l pk_nt_capture_at,%d0
 cmp.l %d7,%d0
 bhi.s 12f                     /* no capture: one pass */
 move.l %a1,-(%sp)
 lea (%a0,%d0.l*2),%a1         /* first piece ends at the capture index */
 cmp.l %a1,%a0
 beq.s 13f
 bsr .Lnoise_filter
13:
 move.l (%a6),pk_nt_capture_rng
 move.l 4(%a6),%d0
 move.l %d0,pk_nt_capture_rng+4
 moveq #1,%d0
 move.l %d0,pk_nt_capture_done
 move.l (%sp)+,%a1
 cmp.l %a1,%a0
 beq.s 14f
12:
 bsr .Lnoise_filter
14:
 move.l (%sp)+,%d7
 move.l (%sp)+,%a5
 move.l %a3,%d0
 ST16 %d0,0x60
 move.l %d1,%d0
 ST16 %d0,0x70
 ST32 %d2,0xac
 ST32 %d3,0xb0
 ST32 %d4,0xb4
 /* ---- mix ---- */
 move.l %a5,-(%sp)
 move.l %d7,-(%sp)
 move.l %a5,%a1               /* s */
 move.l 0xf8(%a1),%d5
 byterev %d5                   /* mix */
 move.l #0xfff,%d6
 sub.l %d5,%d6                 /* tonal mix */
 mvz.b 6(%a1),%d0
 move.l %d0,VEL+8(%sp)
 move.l 0x30(%a1),%d0
 byterev %d0                   /* phase 1 */
 move.l 0x34(%a1),%d2
 byterev %d2
 move.l %d2,%a5                /* inc 1 */
 move.l 0xc8(%a1),%d1
 byterev %d1                   /* phase 2 */
 move.l 0xcc(%a1),%d2
 byterev %d2
 move.l %d2,%a6                /* inc 2 */
 move.l O1+8(%sp),%a3
 move.l O2+8(%sp),%a4
 lea NOISE+8(%sp),%a0
 lea (%a0,%d7.l*2),%a1
 move.l ARG_D+8(%sp),%a2
 bsr .Lmix
 move.l (%sp)+,%d7
 move.l (%sp)+,%a5
 /* ---- oscillator commits (osc_fast_store) ---- */
 ST32 %d0,0x30
 move.l O1+8(%sp),%d0
 tst.l O1+16(%sp)
 beq.s 10f
 move.l O1+12(%sp),%d0
10:
 ST32 %d0,0x38
 ST32 %d1,0xc8
 move.l O2+8(%sp),%d0
 tst.l O2+16(%sp)
 beq.s 11f
 move.l O2+12(%sp),%d0
11:
 ST32 %d0,0xd0
 /* ---- render-math context end ---- */
 move.l #0,%macsr
 move.l MAC+4(%sp),%d0
 move.l %d0,%acc0
 move.l MAC+8(%sp),%d0
 move.l %d0,%accext01
 move.l MAC(%sp),%d0
 move.l %d0,%macsr
 moveq #1,%d0
 lea FRAME(%sp),%sp
 movem.l (%sp),%d2-%d7/%a2-%a6
 lea 44(%sp),%sp
 rts

.Lfallback:
 lea FRAME(%sp),%sp
 movem.l (%sp),%d2-%d7/%a2-%a6
 lea 44(%sp),%sp
 jmp pk_cf_nt_shared_render_c

/* d0 = wave address -> a0 = the first t->waves[i].table whose address
 * matches with a non-null table, else 0 (findwave). a2 = t; uses d2. */
.Lfind:
 lea 8(%a2),%a1
 moveq #4,%d2
1:
 tst.l 4(%a1)
 beq.s 2f
 cmp.l (%a1),%d0
 bne.s 2f
 move.l 4(%a1),%a0
 rts
2:
 addq.l #8,%a1
 subq.l #1,%d2
 bne.s 1b
 sub.l %a0,%a0
 rts

/* ---- noise source and two filter steps per sample -------------------- */
/* a0 noise out, a1 end, a2 reload, a3 count, a6 rng; d1 held (s16), d2 first,
 * d3 second, d4 velocity, d5 coeff, d6 drive; a4 #32767, a5 #-32767. */
.macro ROUND16 reg                /* (p + (p < 0 ? 0xffff : 0)) >> 16 */
 move.l \reg,%d0
 add.l %d0,%d0
 subx.l %d0,%d0
 and.l #0xffff,%d0
 add.l %d0,\reg
 swap \reg
 ext.l \reg
.endm
.macro CLAMP reg
 cmp.l %a4,\reg
 ble.s 1f
 move.l %a4,\reg
 bra.s 2f
1:
 cmp.l %a5,\reg
 bge.s 2f
 move.l %a5,\reg
2:
.endm
.macro FILTER_STEP
 move.l %d4,%d7
 muls.l %d5,%d7
 ROUND16 %d7
 add.l %d7,%d2
 CLAMP %d2
 move.l %d1,%d3
 sub.l %d2,%d3
 move.l %d4,%d7
 muls.l %d6,%d7
 asr.l #8,%d7
 asr.l #2,%d7
 sub.l %d7,%d3
 CLAMP %d3
 move.l %d3,%d7
 muls.l %d5,%d7
 ROUND16 %d7
 add.l %d7,%d4
 CLAMP %d4
.endm
.balign 4
.Lnoise_filter:
 cmp.l #0,%a3
 beq .Lnf_draw
 subq.l #1,%a3
.Lnf_have:
 move.w %d1,(%a0)+
 FILTER_STEP
 FILTER_STEP
 cmp.l %a1,%a0
 bne .Lnoise_filter
 rts
.Lnf_draw:
 move.l %a2,%a3                /* count = reload */
 bsr .Lrnd
 bra .Lnf_have

/* rnd(): the shared 64-bit LCG with the EMAC high product; d1 <- s16 of the
 * new high word's low half. a6 = {low, high}. Uses d0, d7 and the stack. */
.Lrnd:
 move.l %d2,-(%sp)
 move.l %d3,-(%sp)
 move.l (%a6),%d0              /* ol */
 move.l #0x4c957f2d,%d3        /* b */
 move.l %d0,%d1
 move.l #0x5851f42d,%d7
 muls.l %d7,%d1                /* acc = ol * a */
 move.l %d0,%d2
 muls.l %d3,%d2                /* pl = ol * b */
 mac.l %d0,%d3,%acc0
 movclr.l %acc0,%d7
 asr.l #1,%d7                  /* ph */
 tst.l %d0
 bpl.s 1f
 add.l %d3,%d7
1:
 move.l 4(%a6),%d0             /* oh */
 muls.l %d3,%d0
 add.l %d0,%d1                 /* acc += oh * b */
 move.l %d2,%d0
 addq.l #1,%d0                 /* nl = pl + 1 */
 move.l %d0,(%a6)
 cmp.l %d2,%d0                 /* carry = nl < pl (unsigned) */
 bcc.s 2f
 addq.l #1,%d1
2:
 add.l %d7,%d1                 /* nh = acc + ph + carry */
 move.l %d1,4(%a6)
 mvs.w %d1,%d1
 move.l (%sp)+,%d3
 move.l (%sp)+,%d2
 rts

/* ---- mix: a0 noise (amps at 40(a0)), a1 end, a2 out; d0/d1 phases,
 * a5/a6 increments, a3/a4 current tables; d5 mix, d6 tonal mix. ---- */
.set MIXD, 12                  /* frame offset inside .Lmix: two pushes and the return */
.macro OSC phase,inc,table,slot,out
 add.l \inc,\phase
 cmp.l #0x100000,\phase
 ble.s 1f
 sub.l #0x100000,\phase
 move.l \slot+4+MIXD(%sp),\table    /* next table (the current one when equal) */
 moveq #1,\out
 move.l \out,\slot+16+MIXD(%sp)
1:
 move.l \phase,\out
 lsr.l #8,\out
 lsr.l #4,\out
 and.l #0xff,\out
 cmp.l #0xff,\out
 beq.s 2f
 move.l (\table,\out\().l*2),\out
 byterev \out
 bra.s 3f
2:
 /* index 255: a = tab[255], z = tab[0], as (z << 16) | a */
 mvz.b 511(\table),\out
 lsl.l #8,\out
 mvz.b 510(\table),%d7
 or.l %d7,\out
 mvz.b 1(\table),%d7
 lsl.l #8,%d7
 mvz.b (\table),%d4
 or.l %d4,%d7
 swap %d7
 or.l %d7,\out
3:
 move.l \out,%d7
 swap %d7
 ext.l %d7                     /* z */
 mvs.w \out,\out               /* a */
 sub.l \out,%d7
 move.l \phase,%d4
 and.l #0xfff,%d4
 muls.l %d4,%d7
 asr.l #8,%d7
 asr.l #4,%d7
 add.l %d7,\out
 mvs.w \out,\out
.endm
.balign 4
.Lmix:
 OSC %d0,%a5,%a3,O1,%d2
 OSC %d1,%a6,%a4,O2,%d3
 add.l %d3,%d2
 asr.l #4,%d2                  /* sum */
 muls.l %d6,%d2
 asr.l #8,%d2
 asr.l #1,%d2                  /* tonal >> 9 */
 mvs.w (%a0),%d3
 muls.l %d5,%d3
 asr.l #8,%d3
 asr.l #5,%d3                  /* noise >> 13 */
 add.l %d2,%d3
 mvz.w 40(%a0),%d4
 addq.l #2,%a0
 muls.l %d4,%d3
 swap %d3
 ext.l %d3
 muls.l VEL+MIXD(%sp),%d3
 asr.l #8,%d3
 cmp.l #32767,%d3
 ble.s 4f
 move.l #32767,%d3
 bra.s 5f
4:
 cmp.l #-32768,%d3
 bge.s 5f
 move.l #-32768,%d3
5:
 move.w %d3,(%a2)+
 cmp.l %a1,%a0
 bne .Lmix
 rts

.size pk_cf_nt_shared_render,.-pk_cf_nt_shared_render

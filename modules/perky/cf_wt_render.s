/* Wavetable Drum render (V1/V2 a2), one assembly chunk with the C's arithmetic.
 *
 *   int pk_cf_wt_render(uint8_t *s, int16_t *d, uint32_t n, const pk_cf_wt_tables *t)
 *
 * Fast path, taken only when every condition is proven before any state is
 * touched: s, d, t and its pitch/base/bank pointers non-null; 1 <= n <= 20;
 * each envelope either linear or with its curve table present; the current
 * wave views valid and, when the target differs, the target views valid.
 * Anything else tail-calls the original C renderer (pk_cf_wt_render_c),
 * which also owns the partial-failure commit.
 *
 * The fast path is the original's valid-view path in order: render-math
 * context begin (MACSR/ACC0/ACCEXT01 saved, MACSR 0x20), base pitch, the
 * amplitude and pitch envelopes (pk_cf_env_core), the frequency pass
 * (pk_cf_wt_frequency_core), the two-oscillator block, the commit of phase,
 * step, current/secondary views, mix and both envelopes, and the context end.
 * Object fields are the ARM object's little-endian bytes.
 */
.set SAVE,    0
.set ENVA,   44
.set ENVP,   68
.set AMPS,   92
.set PE,    132
.set STEPS, 172
.set OSC,   252
.set MAC,   308
.set FRAME, 320
.set ARG_S, FRAME+48
.set ARG_D, FRAME+52
.set ARG_N, FRAME+56
.set ARG_T, FRAME+60

/* oscillator context, as wt_oscillator_context */
.set O_PHASE, 0
.set O_MIX, 4
.set O_VEL, 8
.set O_TMIX, 12
.set O_WAVE, 16
.set O_SEC, 20
.set O_TWAVE, 24
.set O_TSEC, 28
.set O_CHANGED, 32
.set O_MUTE, 36
.set O_DEST, 40
.set O_STEPS, 44
.set O_AMPS, 48
.set O_COUNT, 52

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

.section .text.pk_cf_wt_render,"ax",@progbits
.balign 16
.globl pk_cf_wt_render
.type pk_cf_wt_render,@function
pk_cf_wt_render:
 lea -44(%sp),%sp
 movem.l %d2-%d7/%a2-%a6,(%sp)
 lea -FRAME(%sp),%sp
 /* ---- preconditions, no state change ---- */
 move.l ARG_S(%sp),%a5
 cmp.l #0,%a5
 beq .Lfallback
 tst.l ARG_D(%sp)
 beq .Lfallback
 move.l ARG_T(%sp),%a2
 cmp.l #0,%a2
 beq .Lfallback
 tst.l (%a2)
 beq .Lfallback
 tst.l 12(%a2)
 beq .Lfallback
 tst.l 16(%a2)
 beq .Lfallback
 move.l ARG_N(%sp),%d7
 beq .Lfallback
 moveq #20,%d0
 cmp.l %d0,%d7
 bhi .Lfallback
 /* envelope curve tables */
 mvz.b 0x75(%a5),%d0
 bsr .Lcurve
 cmp.l #-1,%a0
 beq .Lfallback
 move.l %a0,ENVA+16(%sp)
 mvz.b 0xc5(%a5),%d0
 bsr .Lcurve
 cmp.l #-1,%a0
 beq .Lfallback
 move.l %a0,ENVP+16(%sp)
 /* wave views */
 LD32 0x100,%d0
 bsr .Lwave
 cmp.l #0,%a0
 beq .Lfallback
 move.l %a0,OSC+O_WAVE(%sp)
 move.l %a0,OSC+O_TWAVE(%sp)
 LD32 0x108,%d0
 bsr .Lwave
 cmp.l #0,%a0
 beq .Lfallback
 move.l %a0,OSC+O_SEC(%sp)
 move.l %a0,OSC+O_TSEC(%sp)
 LD32 0x100,%d0
 LD32 0x104,%d1
 cmp.l %d0,%d1
 beq.s 1f
 move.l %d1,%d0
 bsr .Lwave
 cmp.l #0,%a0
 beq .Lfallback
 move.l %a0,OSC+O_TWAVE(%sp)
 LD32 0x10c,%d0
 bsr .Lwave
 cmp.l #0,%a0
 beq .Lfallback
 move.l %a0,OSC+O_TSEC(%sp)
1:
 /* ---- render-math context begin, as pk_cf_render_math_begin ---- */
 move.l %macsr,%d0
 move.l %d0,MAC(%sp)
 move.l #0,%macsr
 move.l %acc0,%d0
 move.l %d0,MAC+4(%sp)
 move.l %accext01,%d0
 move.l %d0,MAC+8(%sp)
 move.l #0,%acc0
 move.l #0x20,%macsr
 /* ---- envelope contexts ---- */
 LD32 0x80,%d0
 move.l %d0,ENVA(%sp)
 mvz.b 0x74(%a5),%d0
 move.l %d0,ENVA+4(%sp)
 LD16 0x94,%d0
 move.l %d0,ENVA+8(%sp)
 LD16 0x96,%d0
 move.l %d0,ENVA+12(%sp)
 lea 0x74(%a5),%a0
 bsr .Lflags
 move.l %d0,ENVA+20(%sp)
 LD32 0xd0,%d0
 move.l %d0,ENVP(%sp)
 mvz.b 0xc4(%a5),%d0
 move.l %d0,ENVP+4(%sp)
 LD16 0xe4,%d0
 move.l %d0,ENVP+8(%sp)
 LD16 0xe6,%d0
 move.l %d0,ENVP+12(%sp)
 lea 0xc4(%a5),%a0
 bsr .Lflags
 move.l %d0,ENVP+20(%sp)
 /* ---- base pitch: mullo(pitch(raw), 0xbb80) >> 20 ---- */
 LD16 0xba,%d0
 move.l (%a2),%a0
 bsr .Lpitch
 move.l %d0,%d6                /* base */
 /* ---- envelopes ---- */
 move.l %a5,-(%sp)
 lea ENVA+4(%sp),%a5
 lea AMPS+4(%sp),%a1
 lea (%a1,%d7.l*2),%a4
 move.l %d6,-(%sp)
 move.l %d7,-(%sp)
 jsr pk_cf_env_core
 move.l (%sp)+,%d7
 lea ENVP+8(%sp),%a5
 lea PE+8(%sp),%a1
 lea (%a1,%d7.l*2),%a4
 move.l %d7,-(%sp)
 jsr pk_cf_env_core
 move.l (%sp)+,%d7
 move.l (%sp)+,%d6
 move.l (%sp)+,%a5
 /* ---- frequency pass ---- */
 lea PE(%sp),%a0
 lea STEPS(%sp),%a1
 lea (%a1,%d7.l*4),%a3
 LD16 0xec,%d5
 moveq #0,%d4
 mvz.b 0x128(%a5),%d0
 cmp.l #1,%d0
 bne.s 2f
 moveq #1,%d4
2:
 move.l pk_cf_wt_pe_factors,%a2
 move.l %d7,-(%sp)
 jsr pk_cf_wt_frequency_core
 move.l (%sp)+,%d7
 /* ---- oscillator context ---- */
 LD32 0xf4,%d0
 move.l %d0,OSC+O_PHASE(%sp)
 LD16 0x112,%d0
 move.l %d0,OSC+O_MIX(%sp)
 mvz.b 6(%a5),%d0
 move.l %d0,OSC+O_VEL(%sp)
 LD16 0x114,%d0
 move.l %d0,OSC+O_TMIX(%sp)
 clr.l OSC+O_CHANGED(%sp)
 mvz.b 0xb8(%a5),%d0
 move.l %d0,OSC+O_MUTE(%sp)
 move.l ARG_D(%sp),OSC+O_DEST(%sp)
 lea STEPS(%sp),%a0
 move.l %a0,OSC+O_STEPS(%sp)
 lea AMPS(%sp),%a0
 move.l %a0,OSC+O_AMPS(%sp)
 move.l %d7,OSC+O_COUNT(%sp)
 move.l %a5,-(%sp)
 move.l %d7,-(%sp)
 lea OSC+8(%sp),%a6
 bsr .Losc
 move.l (%sp)+,%d7
 move.l (%sp)+,%a5
 /* ---- commit: phase, step, views, mix, envelopes ---- */
 move.l OSC+O_PHASE(%sp),%d0
 ST32 %d0,0xf4
 lea STEPS(%sp),%a0
 move.l -4(%a0,%d7.l*4),%d0
 ST32 %d0,0xf8
 LD32 0x100,%d0                /* cur */
 LD32 0x108,%d1                /* sec */
 tst.l OSC+O_CHANGED(%sp)
 beq.s 3f
 LD32 0x104,%d2
 cmp.l %d0,%d2
 beq.s 3f
 move.l %d2,%d0
 LD32 0x10c,%d1
3:
 ST32 %d0,0x100
 ST32 %d1,0x108
 move.l OSC+O_MIX(%sp),%d0
 move.b %d0,0x112(%a5)
 lsr.l #8,%d0
 move.b %d0,0x113(%a5)
 move.l ENVA+4(%sp),%d0
 move.b %d0,0x74(%a5)
 move.l ENVA(%sp),%d0
 ST32 %d0,0x80
 move.l ENVP+4(%sp),%d0
 move.b %d0,0xc4(%a5)
 move.l ENVP(%sp),%d0
 ST32 %d0,0xd0
 /* ---- render-math context end, as pk_cf_render_math_end ---- */
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
 jmp pk_cf_wt_render_c

/* d0 = curve byte -> a0 = table, 0 for linear, -1 when the table is absent. */
.Lcurve:
 sub.l %a0,%a0
 cmp.l #1,%d0
 bne.s 1f
 move.l 4(%a2),%a0
 bra.s 2f
1:
 cmp.l #2,%d0
 bne.s 3f
 move.l 8(%a2),%a0
2:
 cmp.l #0,%a0
 bne.s 3f
 move.l #-1,%a0
3:
 rts

/* d0 = wave address -> a0 = table or 0, as pk_cf_wt_wave; uses d1. */
.Lwave:
 cmp.l #0x080222A0,%d0
 bne.s 1f
 move.l 12(%a2),%a0
 rts
1:
 sub.l #0x080327CC,%d0
 bcs.s 2f
 move.l %d0,%d1
 and.l #0xfff,%d1
 bne.s 2f
 cmp.l #0x30000,%d0
 bcc.s 2f
 move.l 16(%a2),%a0
 add.l %d0,%a0
 rts
2:
 sub.l %a0,%a0
 rts

/* a0 = envelope bytes (b) -> d0 flags: bit0 b[4], bit1 b[6], bit2 b[7], bit3 b[0x10]. */
.Lflags:
 moveq #0,%d0
 tst.b 4(%a0)
 beq.s 1f
 moveq #1,%d0
1:
 tst.b 6(%a0)
 beq.s 2f
 addq.l #2,%d0
2:
 tst.b 7(%a0)
 beq.s 3f
 addq.l #4,%d0
3:
 tst.b 0x10(%a0)
 beq.s 4f
 addq.l #8,%d0
4:
 rts

/* d0 = raw pitch (u16), a0 = pitch table -> d0 = mullo(pitch, 0xbb80) >> 20.
 * pitch(): p = s16(raw); a negative p becomes s16(-raw), negating the result
 * when that is >= 0x1000; p < 0x1000 reads the table at (u16)p; otherwise
 * the octave form tab[(u16)s16(q + (sh*127 << 9) - 0x200)] << ((sh+1)&0xff),
 * sh = ((q - 0x1000) >> 9) & 0x7f. Uses d1-d4. */
.Lpitch:
 moveq #0,%d4                  /* neg */
 mvs.w %d0,%d1                 /* p */
 tst.l %d1
 bpl.s 1f
 neg.l %d0
 mvs.w %d0,%d1
 cmp.l #0x1000,%d1
 blt.s 1f
 moveq #1,%d4
1:
 cmp.l #0x1000,%d1
 bge.s 2f
 mvz.w %d1,%d1
 move.l (%a0,%d1.l*2),%d0
 byterev %d0
 mvz.w %d0,%d0
 bra.s 3f
2:
 mvz.w %d1,%d1                 /* q */
 move.l %d1,%d2
 sub.l #0x1000,%d2
 lsr.l #8,%d2
 lsr.l #1,%d2
 and.l #0x7f,%d2               /* sh */
 move.l %d2,%d3
 lsl.l #7,%d3
 sub.l %d2,%d3                 /* ad = sh * 127 */
 moveq #9,%d0
 lsl.l %d0,%d3
 add.l %d3,%d1
 sub.l #0x200,%d1
 mvz.w %d1,%d1                 /* (u16) of the s16 index */
 move.l (%a0,%d1.l*2),%d0
 byterev %d0
 mvz.w %d0,%d0
 addq.l #1,%d2
 and.l #0xff,%d2
 lsl.l %d2,%d0
3:
 tst.l %d4
 beq.s 4f
 neg.l %d0
4:
 move.l #0xbb80,%d1
 mulu.l %d1,%d0
 moveq #20,%d1
 lsr.l %d1,%d0
 rts

/* ---- two-oscillator block: a6 = context (wt_oscillator_context) ------- */
/* As tools/harness/perky_cf/wt_oscillator_block.s, with velocity held in d7
 * and the target mix read at the (rare) phase wrap. */
.balign 16
.Losc:
 move.l O_STEPS(%a6),%a0
 move.l O_AMPS(%a6),%a1
 move.l O_DEST(%a6),%a2
 move.l O_WAVE(%a6),%a3
 move.l O_SEC(%a6),%a4
 move.l O_COUNT(%a6),%d2
 lea (%a0,%d2.l*4),%a5
 move.l O_PHASE(%a6),%d0
 move.l O_MIX(%a6),%d1
 move.l O_VEL(%a6),%d7
 tst.l O_MUTE(%a6)
 bne .Lo_silent
 tst.l %d7
 beq .Lo_silent
.Lo_sample:
 move.l (%a0)+,%d2
 add.l %d2,%d0
 cmp.l #1048576,%d0
 ble .Lo_ready
 sub.l #1048576,%d0
 move.l O_TMIX(%a6),%d1
 move.l O_TWAVE(%a6),%a3
 move.l O_TSEC(%a6),%a4
 moveq #1,%d6
 move.l %d6,O_CHANGED(%a6)
.Lo_ready:
 mvz.w (%a1)+,%d5
 beq .Lo_zero
 move.l %d0,%d2
 moveq #9,%d6
 lsr.l %d6,%d2
 and.l #2047,%d2
 cmp.l #2047,%d2
 beq .Lo_edge
 move.l (%a3,%d2.l*2),%d3
 move.l (%a4,%d2.l*2),%d4
 byterev %d3
 byterev %d4
 move.l %d3,%d6
 swap %d6
 ext.l %d6
 mvs.w %d3,%d3
 sub.l %d3,%d6
 move.l %d0,%d2
 and.l #511,%d2
 muls.l %d2,%d6
 asr.l #8,%d6
 asr.l #1,%d6
 add.l %d6,%d3
 mvs.w %d3,%d3
 move.l %d4,%d6
 swap %d6
 ext.l %d6
 mvs.w %d4,%d4
 sub.l %d4,%d6
 muls.l %d2,%d6
 asr.l #8,%d6
 asr.l #1,%d6
 add.l %d6,%d4
 mvs.w %d4,%d4
.Lo_blend:
 sub.l %d3,%d4
 muls.l %d1,%d4
 move.l %d3,%d6
 lsl.l #8,%d6
 sub.l %d3,%d6
 add.l %d4,%d6
 lsr.l #8,%d6
 mvs.w %d6,%d6
 muls.l %d5,%d6
 swap %d6
 ext.l %d6
 muls.l %d7,%d6
 asr.l #8,%d6
 move.w %d6,(%a2)+
.Lo_next:
 cmp.l %a5,%a0
 bne .Lo_sample
 bra .Lo_done
.Lo_zero:
 clr.w (%a2)+
 bra .Lo_next
.Lo_edge:
 /* The following point may belong to the target wave before the wrap. */
 move.l (%a3,%d2.l*2),%d3
 move.l O_TWAVE(%a6),%d6
 move.l %d6,%a3
 move.l (%a3),%d6
 move.l O_WAVE(%a6),%a3
 tst.l O_CHANGED(%a6)
 beq .Lo_edge_primary
 move.l O_TWAVE(%a6),%a3
.Lo_edge_primary:
 byterev %d3
 byterev %d6
 mvs.w %d3,%d3
 mvs.w %d6,%d6
 sub.l %d3,%d6
 move.l %d0,%d2
 and.l #511,%d2
 muls.l %d2,%d6
 asr.l #8,%d6
 asr.l #1,%d6
 add.l %d6,%d3
 mvs.w %d3,%d3
 move.l O_TSEC(%a6),%d6
 move.l %d6,%a4
 move.l (%a4),%d6
 move.l O_SEC(%a6),%a4
 tst.l O_CHANGED(%a6)
 beq .Lo_edge_secondary
 move.l O_TSEC(%a6),%a4
.Lo_edge_secondary:
 move.l 4094(%a4),%d4
 byterev %d4
 byterev %d6
 mvs.w %d4,%d4
 mvs.w %d6,%d6
 sub.l %d4,%d6
 muls.l %d2,%d6
 asr.l #8,%d6
 asr.l #1,%d6
 add.l %d6,%d4
 mvs.w %d4,%d4
 bra .Lo_blend
.Lo_silent:
 move.l (%a0)+,%d2
 add.l %d2,%d0
 cmp.l #1048576,%d0
 ble .Lo_silent_ready
 sub.l #1048576,%d0
 move.l O_TMIX(%a6),%d1
 moveq #1,%d6
 move.l %d6,O_CHANGED(%a6)
.Lo_silent_ready:
 clr.w (%a2)+
 cmp.l %a5,%a0
 bne .Lo_silent
.Lo_done:
 move.l %d0,O_PHASE(%a6)
 move.l %d1,O_MIX(%a6)
 rts
.size pk_cf_wt_render,.-pk_cf_wt_render

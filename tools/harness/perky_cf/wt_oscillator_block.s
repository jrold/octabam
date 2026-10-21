/* WT native oscillator block. Caller validates every possible wave address.
 * All arithmetic is the original modulo-32 interpolation and blend. Envelope
 * output is u16, so the final amplitude/velocity result always fits s16.
 * No EMAC, IRQ mask, peripheral access or extra source latency.
 */
.section .text.pk_cf_wt_oscillator_block,"ax",@progbits
.balign 2
.globl pk_cf_wt_oscillator_block
.type pk_cf_wt_oscillator_block,@function
pk_cf_wt_oscillator_block:
 lea -44(%sp),%sp
 movem.l %d2-%d7/%a2-%a6,(%sp)
 move.l 48(%sp),%a6
 move.l 44(%a6),%a0
 move.l 48(%a6),%a1
 move.l 40(%a6),%a2
 move.l 16(%a6),%a3
 move.l 20(%a6),%a4
 move.l 52(%a6),%d2
 lea (%a0,%d2.l*4),%a5
 move.l (%a6),%d0
 move.l 4(%a6),%d1
 move.l 12(%a6),%d7
 tst.l 36(%a6)
 bne .Lwt_silent
 tst.l 8(%a6)
 beq .Lwt_silent
.Lwt_sample:
 move.l (%a0)+,%d2
 add.l %d2,%d0
 cmp.l #1048576,%d0
 ble .Lwt_phase_ready
 sub.l #1048576,%d0
 move.l %d7,%d1
 move.l 24(%a6),%a3
 move.l 28(%a6),%a4
 moveq #1,%d6
 move.l %d6,32(%a6)
.Lwt_phase_ready:
 mvz.w (%a1)+,%d5
 beq .Lwt_zero
 move.l %d0,%d2
 moveq #9,%d6
 lsr.l %d6,%d2
 and.l #2047,%d2
 cmp.l #2047,%d2
 beq .Lwt_table_edge
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
.Lwt_blend:
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
 muls.l 8(%a6),%d6
 asr.l #8,%d6
 move.w %d6,(%a2)+
.Lwt_next:
 cmp.l %a5,%a0
 bne .Lwt_sample
 bra .Lwt_done
.Lwt_zero:
 clr.w (%a2)+
 bra .Lwt_next
.Lwt_table_edge:
 /* The following point may belong to the target wave before phase wraps. */
 move.l (%a3,%d2.l*2),%d3
 move.l 24(%a6),%d6
 move.l %d6,%a3
 move.l (%a3),%d6
 move.l 16(%a6),%a3
 tst.l 32(%a6)
 beq .Lwt_edge_primary
 move.l 24(%a6),%a3
.Lwt_edge_primary:
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
 move.l 28(%a6),%d6
 move.l %d6,%a4
 move.l (%a4),%d6
 move.l 20(%a6),%a4
 tst.l 32(%a6)
 beq .Lwt_edge_secondary
 move.l 28(%a6),%a4
.Lwt_edge_secondary:
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
 bra .Lwt_blend
.Lwt_silent:
 move.l (%a0)+,%d2
 add.l %d2,%d0
 cmp.l #1048576,%d0
 ble .Lwt_silent_ready
 sub.l #1048576,%d0
 move.l %d7,%d1
 moveq #1,%d6
 move.l %d6,32(%a6)
.Lwt_silent_ready:
 clr.w (%a2)+
 cmp.l %a5,%a0
 bne .Lwt_silent
.Lwt_done:
 move.l %d0,(%a6)
 move.l %d1,4(%a6)
 movem.l (%sp),%d2-%d7/%a2-%a6
 lea 44(%sp),%sp
 rts
.size pk_cf_wt_oscillator_block,.-pk_cf_wt_oscillator_block

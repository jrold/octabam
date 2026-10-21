/* Generic bounded Slap delay spans. All tap/gain metadata remains dynamic.
 * Hoist ring-address construction only when every read/write span avoids
 * wrapping. Rejected spans tail-call the unchanged PKFM20 generic helper.
 * Native state: u16 index,mix,delay[5],gain[5]; LE int16 ring, native int32 data.
 * No EMAC, interrupt-mask, peripheral or cross-call cached state.
 */
.text
.balignw 4,0x4e71
.globl pk_cf_slap_delay_span
.type pk_cf_slap_delay_span,@function
pk_cf_slap_delay_span:
 lea -76(%sp),%sp
 movem.l %d2-%d7/%a2-%a6,32(%sp)
 move.l 80(%sp),%a0
 move.l 84(%sp),%a6
 move.l 88(%sp),%a5
 move.l 92(%sp),%d2
 move.l %a0,24(%sp)
 tst.l %d2
 beq .Lslspan_fallback
 cmp.l #20,%d2
 bhi .Lslspan_fallback
 mvz.w (%a0),%d5
 move.l %d5,%d1
 add.l %d2,%d1
 cmp.l #4805,%d1
 bhs .Lslspan_fallback
 move.l %d1,28(%sp)
 mvs.w 2(%a0),%d6
 .macro SLSPAN_INIT reg,tap
 move.l %d5,%d4
 mvz.w 4+2*\tap(%a0),%d3
 sub.l %d3,%d4
 bcc 1f
 add.l #4805,%d4
1:
 cmp.l #4805,%d4
 bhs .Lslspan_fallback
 move.l %d4,%d1
 add.l %d2,%d1
 cmp.l #4805,%d1
 bhi .Lslspan_fallback
 mvz.w 14+2*\tap(%a0),%d3
 move.l %d3,4*\tap(%sp)
 lea (%a6,%d4.l*2),\reg
 .endm
 SLSPAN_INIT %a1,0
 SLSPAN_INIT %a2,1
 SLSPAN_INIT %a3,2
 SLSPAN_INIT %a4,3
 SLSPAN_INIT %a0,4
 addq.l #1,%d5
 lea (%a6,%d5.l*2),%a6
 move.l #4095,%d5
 sub.l %d6,%d5
.globl pk_cf_slap_delay_span_fast
.type pk_cf_slap_delay_span_fast,@function
pk_cf_slap_delay_span_fast:
 .macro SLSPAN_TAP reg,tap
 move.l (\reg),%d4
 addq.l #2,\reg
 byterev %d4
 mvs.w %d4,%d4
 add.l %d1,%d4
 muls.l 4*\tap(%sp),%d4
 move.l %d1,%d7
 lsl.l #4,%d7
 sub.l %d7,%d4
 asr.l #4,%d4
 cmp.l #32767,%d4
 ble 1f
 move.l #32767,%d4
 bra 2f
1:
 cmp.l #-32767,%d4
 bge 2f
 move.l #-32767,%d4
2:
 move.l %d4,%d1
 .endm
.Lslspan_loop:
 move.l (%a5),%d0
 move.l %d0,%d1
 SLSPAN_TAP %a1,0
 SLSPAN_TAP %a2,1
 SLSPAN_TAP %a3,2
 SLSPAN_TAP %a4,3
 SLSPAN_TAP %a0,4
 move.l %d1,%d4
 lsl.l #2,%d4
 add.l %d1,%d4
 asr.l #1,%d4
 muls.l %d6,%d4
 move.l %d5,%d7
 muls.l %d0,%d7
 add.l %d7,%d4
 asr.l #8,%d4
 asr.l #4,%d4
 byterev %d1
 swap %d1
 move.w %d1,(%a6)+
 move.l %d4,(%a5)+
 subq.l #1,%d2
 bne .Lslspan_loop
 move.l 24(%sp),%a0
 move.l 28(%sp),%d2
 move.w %d2,(%a0)
 movem.l 32(%sp),%d2-%d7/%a2-%a6
 lea 76(%sp),%sp
 rts
.size pk_cf_slap_delay_span_fast,.-pk_cf_slap_delay_span_fast
.Lslspan_fallback:
 movem.l 32(%sp),%d2-%d7/%a2-%a6
 lea 76(%sp),%sp
 jmp pk_cf_slap_delay_block
.size pk_cf_slap_delay_span,.-pk_cf_slap_delay_span

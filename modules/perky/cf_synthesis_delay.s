/* Original five-stage 4805-sample delay, integer CF implementation.
 * Native state: index,mix,delay[5],gain[5]. Ring stays little-endian int16.
 * Input/output block is native int32. No EMAC, MACSR or interrupt-mask use.
 */
.text
.balign 2
.macro tap offset,delay=8,gain=28,compact=0
 move.l %d2,%d5
 .if \compact
 mvz.w \delay+(\offset/2)(%a0),%d3
 sub.l %d3,%d5
 .else
 sub.l \delay+\offset(%a0),%d5
 .endif
 bcc 1f
 add.l #4805,%d5
1:
 move.l (%a2,%d5.l*2),%d4
 byterev %d4
 mvs.w %d4,%d4
 .if \compact
 mvz.w \gain+(\offset/2)(%a0),%d3
 .else
 move.l \gain+\offset(%a0),%d3
 .endif
 add.l %d1,%d4
 muls.l %d3,%d4
 move.l %d1,%d7
 lsl.l #4,%d7
 sub.l %d7,%d4
 asr.l #4,%d4
 cmp.l #32767,%d4
 ble 2f
 move.l #32767,%d4
 bra 3f
2:
 cmp.l #-32767,%d4
 bge 3f
 move.l #-32767,%d4
3:
 move.l %d4,%d1
.endm
.macro block name,index=0,mix=4,delay=8,gain=28,compact=0,slap=0
.globl \name
.type \name,@function
\name:
 lea -32(%sp),%sp
 movem.l %d2-%d7/%a2-%a3,(%sp)
 move.l 36(%sp),%a0
 move.l 40(%sp),%a2
 move.l 44(%sp),%a1
 move.l 48(%sp),%d0
 lsl.l #2,%d0
 lea (%a1,%d0.l),%a3
 .if \slap
 mvz.w \index(%a0),%d2
 mvs.w \mix(%a0),%d6
 .else
 move.l \index(%a0),%d2
 move.l \mix(%a0),%d6
 .endif
 cmp.l %a3,%a1
 beq 6f
4:
 move.l (%a1),%d0
 move.l %d0,%d1
 tap 0,\delay,\gain,\compact
 tap 4,\delay,\gain,\compact
 tap 8,\delay,\gain,\compact
 tap 12,\delay,\gain,\compact
 tap 16,\delay,\gain,\compact
 move.l %d1,%d4
 lsl.l #2,%d4
 add.l %d1,%d4
 asr.l #1,%d4
 muls.l %d6,%d4
 move.l #4095,%d7
 sub.l %d6,%d7
 muls.l %d0,%d7
 add.l %d7,%d4
 asr.l #8,%d4
 asr.l #4,%d4
 addq.l #1,%d2
 cmp.l #4805,%d2
 bcs 5f
 moveq #0,%d2
5:
 byterev %d1
 swap %d1
 move.w %d1,(%a2,%d2.l*2)
 move.l %d4,(%a1)+
 cmp.l %a3,%a1
 bne 4b
6:
 .if \slap
 move.w %d2,\index(%a0)
 .else
 move.l %d2,\index(%a0)
 .endif
 movem.l (%sp),%d2-%d7/%a2-%a3
 lea 32(%sp),%sp
 rts
.size \name,.-\name
.endm
.ifdef CF_SYNTHESIS_TEST
block pk_cf_delay_block
.endif
block pk_cf_nh_delay_block,20,24,0,10,1
block pk_cf_slap_delay_block,0,2,4,14,1,1

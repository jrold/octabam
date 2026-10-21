/* Guarded classic-Hat specialization. The C dispatcher verifies the five
 * delay/gain pairs. Input and output are native int16; ring is little-endian.
 * gain in 1..7 and int16 input imply no product overflow and each shifted
 * stage lies in -32768..32767. The sole clamp case is therefore -32768.
 * The C dispatcher retains the original recurrence for other metadata.
 */
.text
.balign 2
.macro nhitap delay,gain
 move.l %d2,%d5
 sub.l #\delay,%d5
 bcc 1f
 add.l #4805,%d5
1:
 move.l (%a2,%d5.l*2),%d4
 byterev %d4
 mvs.w %d4,%d4
 add.l %d1,%d4
.if \gain-1
 moveq #\gain,%d3
 muls.l %d3,%d4
.endif
 asr.l #4,%d4
 sub.l %d1,%d4
 cmp.l #-32768,%d4
 bne 2f
 addq.l #1,%d4
2:
 move.l %d4,%d1
.endm
.globl pk_cf_nh_delay_i16
.type pk_cf_nh_delay_i16,@function
pk_cf_nh_delay_i16:
.ifdef CF_SYNTHESIS_TEST
.globl pk_cf_nh_fast_marker
.type pk_cf_nh_fast_marker,@object
pk_cf_nh_fast_marker:
.size pk_cf_nh_fast_marker,1
.endif
 lea -32(%sp),%sp
 movem.l %d2-%d7/%a2-%a3,(%sp)
 move.l 36(%sp),%a0
 move.l 40(%sp),%a2
 move.l 44(%sp),%a1
 move.l 48(%sp),%d0
 add.l %d0,%d0
 lea (%a1,%d0.l),%a3
 move.l 20(%a0),%d2
 move.l 24(%a0),%d6
 cmp.l %a3,%a1
 beq 5f
3:
 mvs.w (%a1),%d0
 move.l %d0,%d1
 nhitap 573,1
 nhitap 1201,1
 nhitap 1538,3
 nhitap 3139,5
 nhitap 4804,7
 moveq #5,%d4
 muls.l %d1,%d4
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
 bcs 4f
 moveq #0,%d2
4:
 byterev %d1
 swap %d1
 move.w %d1,(%a2,%d2.l*2)
 move.w %d4,(%a1)+
 cmp.l %a3,%a1
 bne 3b
5:
 move.l %d2,20(%a0)
 movem.l (%sp),%d2-%d7/%a2-%a3
 lea 32(%sp),%sp
 rts
.size pk_cf_nh_delay_i16,.-pk_cf_nh_delay_i16

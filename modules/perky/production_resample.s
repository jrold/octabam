/* Production exact 48 kHz -> 44.1 kHz source converter. The synthesis stays C.
 * Input int16 samples are native CF endian. Phase is the original 0..146.
 * All arithmetic matches cf_native_clock.h, including negative floor rounding.
 */
.section .text.pk_nhb_native_convert_fast,"ax",@progbits
.balign 2
.globl pk_nhb_native_convert_fast
.type pk_nhb_native_convert_fast,@function
pk_nhb_native_convert_fast:
 lea -36(%sp),%sp
 movem.l %d2-%d4/%d6/%a3-%a4,(%sp)
 move.l %macsr,%d2
 move.l %d2,24(%sp)
 move.l #0,%macsr
 move.l %acc0,%d2
 move.l %d2,28(%sp)
 move.l %accext01,%d2
 move.l %d2,32(%sp)
 move.l #0,%acc0
 move.l #0x20,%macsr
 move.l 40(%sp),%a3
 move.l 44(%sp),%a0
 move.l 52(%sp),%a1
 move.l 48(%sp),%d0
 lsl.l #2,%d0
 lea (%a1,%d0.l),%a4
 move.l (%a3),%d0
 move.l #233739717,%d6
 cmp.l %a4,%a1
 beq .Lnhbc_end
.Lnhbc_loop:
 mvs.w (%a0),%d1
 tst.l %d0
 beq .Lnhbc_zero
 mvs.w 2(%a0),%d2
 sub.l %d1,%d2
 muls.l %d0,%d2
 lsl.l #5,%d2
 smi %d3
 extb.l %d3
 eor.l %d3,%d2
 sub.l %d3,%d2
 move.l %d3,%d4
 and.l #146,%d4
 add.l %d4,%d2
 /* For 0 <= n <= 306179666, floor(n/147) equals
  * floor(n * ceil(2^35/147) / 2^35). Fractional EMAC
  * supplies product>>31; the remaining four bits use ASR. */
 mac.l %d2,%d6,%acc0
 movclr.l %acc0,%d2
 asr.l #4,%d2
 eor.l %d3,%d2
 sub.l %d3,%d2
 lsl.l #5,%d1
 add.l %d2,%d1
 bra .Lnhbc_store
.Lnhbc_zero:
 lsl.l #5,%d1
.Lnhbc_store:
 move.l %d1,(%a1)+
 addq.l #2,%a0
 add.l #13,%d0
 cmp.l #147,%d0
 bcs .Lnhbc_next
 sub.l #147,%d0
 addq.l #2,%a0
.Lnhbc_next:
 cmp.l %a4,%a1
 bne .Lnhbc_loop
.Lnhbc_end:
 move.l %d0,(%a3)
 clr.l 4(%a3)
 clr.l 8(%a3)
 cmp.l #13,%d0
 bcs .Lnhbc_return
 moveq #1,%d1
 move.l %d1,4(%a3)
 mvs.w (%a0),%d1
 move.l %d1,8(%a3)
.Lnhbc_return:
 move.l #0,%macsr
 move.l 28(%sp),%d2
 move.l %d2,%acc0
 move.l 32(%sp),%d2
 move.l %d2,%accext01
 move.l 24(%sp),%d2
 move.l %d2,%macsr
 movem.l (%sp),%d2-%d4/%d6/%a3-%a4
 lea 36(%sp),%sp
 rts
.size pk_nhb_native_convert_fast,.-pk_nhb_native_convert_fast

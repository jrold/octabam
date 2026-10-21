/* Bounded copies of stock DELAY arithmetic. Guards retain stock for every
 * counter shape outside the producer's fixed sixteen-sample contract.
 * No source/ring/filter/EMAC operation is omitted from the admitted blocks.
 */
.text
.balign 2
.globl pk_stock_delay_mix16
.type pk_stock_delay_mix16,@function
pk_stock_delay_mix16:
 cmp.l #16,%d2
 bne .Ldelay_mix_original
 .rept 16
 mac.l %d3,%d0,%acc2
 mac.l %a2,%d0,(%a0),%d0,%acc0
 mac.l %a4,%d0,4(%a0),%d1,%acc2
 msac.l %a3,%d0,(%a1)+,%d0,%acc0
 mac.l %d3,%d0,%acc3
 mac.l %a2,%d0,%acc1
 mac.l %a4,%d1,%acc3
 msac.l %a3,%d1,(%a1)+,%d0,%acc1
 movclr.l %acc2,%d1
 adda.l %d4,%a3
 move.l %d1,-12(%a1)
 movclr.l %acc3,%d1
 move.l %d1,-8(%a1)
 adda.l %d5,%a4
 movclr.l %acc0,%d1
 move.l %d1,(%a0)+
 add.l %d7,%d3
 movclr.l %acc1,%d1
 move.l %d1,(%a0)+
 adda.l %d6,%a2
 .endr
 sub.l %d2,%d2
 jmp 0x4000377a
.Ldelay_mix_original:
 mac.l %d3,%d0,%acc2
 mac.l %a2,%d0,(%a0),%d0,%acc0
 jmp 0x40003740
.size pk_stock_delay_mix16,.-pk_stock_delay_mix16

.macro FILTER_UNROLL name,first
.balign 2
.globl \name
.type \name,@function
\name:
 move.l %d0,-(%sp)
 move.l %d5,%d0
 and.l #15,%d0
 bne .Ldelay_filter_original_\@
 move.l %d5,%d0
 asr.l #4,%d0
 cmp.l %d3,%d0
 bne .Ldelay_filter_original_\@
 tst.l %d3
 beq .Ldelay_filter_original_\@
 move.l (%sp)+,%d0
 .rept 16
 msac.l %d0,%a1,%acc2
 msac.l %d0,%a2,%acc3
 mac.l %d2,%a1,(%a5)+,%a1,%acc0
.if \first
 msac.l %d5,%a1,(%a0)+,%a1,%acc0
.else
 msac.l %d5,%a1,(%a0),%a1,%acc0
.endif
 msac.l %d4,%a1,%acc0
 mac.l %d2,%a2,(%a5)+,%a2,%acc1
.if \first
 msac.l %d5,%a2,(%a0),%a2,%acc1
.else
 msac.l %d5,%a2,4(%a0),%a2,%acc1
.endif
 msac.l %d4,%a2,%acc1
 mac.l %d1,%a3,%acc2
 mac.l %d1,%a4,%acc3
 movclr.l %acc0,%a1
 mac.l %d0,%a1,%acc2
 movclr.l %acc1,%a2
 mac.l %d0,%a2,%acc3
 add.l %d3,%d4
 movclr.l %acc2,%a3
 move.l %a3,(%a0)+
 movclr.l %acc3,%a4
.if \first
 move.l %a4,-8(%a0)
.else
 move.l %a4,(%a0)+
.endif
 sub.l %d3,%d5
 .endr
 jmp 0x400036ee
.Ldelay_filter_original_\@:
 move.l (%sp)+,%d0
 msac.l %d0,%a1,%acc2
 msac.l %d0,%a2,%acc3
.if \first
 jmp 0x4000366c
.else
 jmp 0x400036b2
.endif
.size \name,.-\name
.endm
FILTER_UNROLL pk_stock_delay_filter16_forward,1
FILTER_UNROLL pk_stock_delay_filter16_interleaved,0

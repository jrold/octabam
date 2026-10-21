/* Exact source records directly in their fixed slot. The unchanged engine
 * output is the input; no intermediate PCM packet is needed for transport. */
.text
.balign 2
.globl pk_prod_pack
.type pk_prod_pack,@function
pk_prod_pack:
 lea -8(%sp),%sp
 movem.l %d2-%d3,(%sp)
 move.l 12(%sp),%a0
 move.l 16(%sp),%a1
 move.l 20(%sp),%d3
 move.l %d3,%d0
 bsr .Lprod_record
 moveq #16,%d0
 sub.l %d3,%d0
 bsr .Lprod_record
 movem.l (%sp),%d2-%d3
 lea 8(%sp),%sp
 rts
.Lprod_record:
 move.l %d0,%d1
 lsl.l #8,%d1
 or.l %d0,%d1
 move.l %d1,(%a0)+
 clr.l (%a0)+
 move.l #0x04000000,%d1
 move.l %d1,(%a0)+
 clr.l (%a0)+
 tst.l %d0
 beq .Lprod_record_end
.Lprod_pcm:
 move.l (%a1)+,%d2
 lsl.l #8,%d2
 move.l %d2,(%a0)+
 move.l %d2,(%a0)+
 subq.l #1,%d0
 bne .Lprod_pcm
.Lprod_record_end:
 rts
.size pk_prod_pack,.-pk_prod_pack

.globl pk_prod_clear
.type pk_prod_clear,@function
pk_prod_clear:
 move.l 4(%sp),%a0
 move.l 8(%sp),%d0
 moveq #0,%d1
 cmp.l #16,%d0
 blo 2f
1:
 .rept 16
 move.l %d1,(%a0)+
 .endr
 sub.l #16,%d0
 cmp.l #16,%d0
 bhs 1b
2:
 tst.l %d0
 beq 4f
3:
 move.l %d1,(%a0)+
 subq.l #1,%d0
 bne 3b
4:
 move.l %a0,%d0
 rts
.size pk_prod_clear,.-pk_prod_clear

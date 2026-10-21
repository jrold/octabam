/* Non-overlapping pristine-object restore. Ordinary integer CF instructions;
 * preserves all callee-saved registers, SR mask, EMAC state and MACSR. */
.text
.balign 2
.globl pk_prod_copy
.type pk_prod_copy,@function
pk_prod_copy:
 move.l 4(%sp),%a0
 move.l 8(%sp),%a1
 move.l 12(%sp),%d0
 cmp.l #32,%d0
 blo 2f
1:
 .rept 8
 move.l (%a1)+,%d1
 move.l %d1,(%a0)+
 .endr
 sub.l #32,%d0
 cmp.l #32,%d0
 bhs 1b
2:
 cmp.l #4,%d0
 blo 4f
3:
 move.l (%a1)+,%d1
 move.l %d1,(%a0)+
 subq.l #4,%d0
 cmp.l #4,%d0
 bhs 3b
4:
 tst.l %d0
 beq 6f
5:
 move.b (%a1)+,%d1
 move.b %d1,(%a0)+
 subq.l #1,%d0
 bne 5b
6:
 rts
.size pk_prod_copy,.-pk_prod_copy

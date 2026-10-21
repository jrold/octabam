/* Restore boot-generated sparse raw state: clear every byte, then write
 * nonzero full words. Caller restores any trailing bytes from the pristine
 * object. No EMAC or SR-mask writes; D2 is callee-saved. */
.text
.balign 2
.globl pk_prod_zero_patch
.type pk_prod_zero_patch,@function
pk_prod_zero_patch:
 lea -4(%sp),%sp
 move.l %d2,(%sp)
 move.l 8(%sp),%a0
 move.l 12(%sp),%d0
 moveq #0,%d1
 cmp.l #128,%d0
 blo 2f
1:
 .rept 32
 move.l %d1,(%a0)+
 .endr
 sub.l #128,%d0
 cmp.l #128,%d0
 bhs 1b
2:
 cmp.l #4,%d0
 blo 4f
3:
 move.l %d1,(%a0)+
 subq.l #4,%d0
 cmp.l #4,%d0
 bhs 3b
4:
 tst.l %d0
 beq 6f
5:
 move.b %d1,(%a0)+
 subq.l #1,%d0
 bne 5b
6:
 move.l 8(%sp),%a0
 move.l 16(%sp),%a1
 move.l 20(%sp),%d0
 tst.l %d0
 beq 8f
7:
 move.l (%a1)+,%d1
 move.l (%a1)+,%d2
 move.l %d2,(%a0,%d1.l)
 subq.l #1,%d0
 bne 7b
8:
 move.l (%sp),%d2
 lea 4(%sp),%sp
 rts
.size pk_prod_zero_patch,.-pk_prod_zero_patch

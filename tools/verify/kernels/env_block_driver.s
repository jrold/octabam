/* Batch driver for pk_cf_env_block under cf_cycle_bench.
 * Cases at 0x300000, 28 bytes each: six context longs then n.
 * Outputs at 0x400000, 40 bytes each. Count at 0x2ffffc. */
.text
.globl _start
_start:
 move.l 0x2ffffc,%d7
 lea 0x300000,%a3
 lea 0x400000,%a2
1:
 tst.l %d7
 beq.s 2f
 move.l 24(%a3),-(%sp)
 move.l %a2,-(%sp)
 move.l %a3,-(%sp)
 jsr pk_cf_env_block
 lea 12(%sp),%sp
 lea 28(%a3),%a3
 lea 40(%a2),%a2
 subq.l #1,%d7
 bra.s 1b
2:
 rts

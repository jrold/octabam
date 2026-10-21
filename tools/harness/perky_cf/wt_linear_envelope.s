/* Native bounded linear envelope samples. The caller proves no state change.
 * uint32_t helper(uint16_t *dst,uint32_t n,uint32_t value,int32_t delta).
 * Preserve all callee-save/MAC registers. Output is native CF halfwords.
 */
.text
.balignw 4,0x4e71
.globl pk_cf_wt_linear_envelope
.type pk_cf_wt_linear_envelope,@function
pk_cf_wt_linear_envelope:
 lea -8(%sp),%sp
 movem.l %d2-%d3,(%sp)
 move.l 12(%sp),%a0
 move.l 16(%sp),%d2
 move.l 20(%sp),%d0
 move.l 24(%sp),%d1
 tst.l %d2
 beq 2f
1:
 add.l %d1,%d0
 move.l %d0,%d3
 lsr.l #4,%d3
 move.w %d3,(%a0)+
 subq.l #1,%d2
 bne 1b
2:
 movem.l (%sp),%d2-%d3
 lea 8(%sp),%sp
 rts
.size pk_cf_wt_linear_envelope,.-pk_cf_wt_linear_envelope

/* The isolated WT verifier links the existing oscillator through one object. */
.include "tools/harness/perky_cf/wt_oscillator_block.s"

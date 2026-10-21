/* Five fixed delay taps, original ring order, native-endian packet words.
 * No peripheral access, masks, wait or EMAC state. Last taps feed carry only.
 * Inputs are validated by the bounded C caller. */
.text
.balign 2
.globl pk_budget_gather_taps
.type pk_budget_gather_taps,@function
pk_budget_gather_taps:
 lea -44(%sp),%sp
 movem.l %d2-%d7/%a2-%a6,(%sp)
 move.l 48(%sp),%a6
 move.l 52(%sp),%a5
 move.l 56(%sp),%d6
 move.l 60(%sp),%d5
 move.l %a6,%d7
 add.l #9610,%d7
 .macro TAP_INIT reg,delay
 move.l %d6,%d0
 sub.l #\delay,%d0
 bpl 1f
 add.l #4805,%d0
1:
 lea (%a6,%d0.l*2),\reg
 .endm
 TAP_INIT %a0,573
 TAP_INIT %a1,1201
 TAP_INIT %a2,1538
 TAP_INIT %a3,3139
 TAP_INIT %a4,4804
 tst.l %d5
 beq .Lbudget_taps_done
 .macro TAP_READ reg
 move.l (\reg),%d0
 byterev %d0
 move.w %d0,(%a5)+
 addq.l #2,\reg
 cmp.l %d7,\reg
 bne 1f
 move.l %a6,\reg
1:
 .endm
.Lbudget_taps_loop:
 TAP_READ %a0
 TAP_READ %a1
 TAP_READ %a2
 TAP_READ %a3
 TAP_READ %a4
 subq.l #1,%d5
 bne .Lbudget_taps_loop
 move.l 64(%sp),%a0
 move.w -10(%a5),(%a0)+
 move.w -8(%a5),(%a0)+
 move.w -6(%a5),(%a0)+
 move.w -4(%a5),(%a0)+
 move.w -2(%a5),(%a0)+
.Lbudget_taps_done:
 move.l 60(%sp),%d0
 add.l %d6,%d0
 cmp.l #4805,%d0
 blo .Lbudget_taps_return
 sub.l #4805,%d0
.Lbudget_taps_return:
 movem.l (%sp),%d2-%d7/%a2-%a6
 lea 44(%sp),%sp
 rts
.size pk_budget_gather_taps,.-pk_budget_gather_taps

/* Original Slap filter recurrence twice per noise sample. Native temporary
 * state is {coeff,damp,first,second,velocity}, all int32. */
.macro BUDGET_CLAMP reg
 cmp.l #32767,\reg
 ble 1f
 move.l #32767,\reg
 bra 2f
1:
 cmp.l #-32767,\reg
 bge 2f
 move.l #-32767,\reg
2:
.endm
.macro BUDGET_FILTER_STEP
 move.l %d4,%d0
 muls.l %d5,%d0
 tst.l %d0
 bpl 1f
 add.l #65535,%d0
1:
 swap %d0
 ext.l %d0
 add.l %d0,%d2
 BUDGET_CLAMP %d2
 move.l %d4,%d0
 muls.l %d6,%d0
 asr.l #8,%d0
 asr.l #2,%d0
 move.l %d7,%d3
 sub.l %d2,%d3
 sub.l %d0,%d3
 BUDGET_CLAMP %d3
 move.l %d3,%d0
 muls.l %d5,%d0
 tst.l %d0
 bpl 1f
 add.l #65535,%d0
1:
 swap %d0
 ext.l %d0
 add.l %d0,%d4
 BUDGET_CLAMP %d4
.endm
.balign 2
.globl pk_budget_slap_filter
.type pk_budget_slap_filter,@function
pk_budget_slap_filter:
 lea -36(%sp),%sp
 movem.l %d2-%d7/%a2-%a4,(%sp)
 move.l 40(%sp),%a4
 move.l 44(%sp),%a1
 move.l 48(%sp),%a0
 move.l 52(%sp),%d0
 lsl.l #2,%d0
 lea (%a0,%d0.l),%a3
 move.l (%a4),%d5
 move.l 4(%a4),%d6
 move.l 8(%a4),%d2
 move.l 12(%a4),%d3
 move.l 16(%a4),%d4
 cmp.l %a3,%a0
 beq .Lbudget_filter_done
.Lbudget_filter_loop:
 mvs.w (%a1)+,%d7
 BUDGET_FILTER_STEP
 BUDGET_FILTER_STEP
 move.l %d2,(%a0)+
 cmp.l %a3,%a0
 bne .Lbudget_filter_loop
.Lbudget_filter_done:
 move.l %d2,8(%a4)
 move.l %d3,12(%a4)
 move.l %d4,16(%a4)
 movem.l (%sp),%d2-%d7/%a2-%a4
 lea 36(%sp),%sp
 rts
.size pk_budget_slap_filter,.-pk_budget_slap_filter

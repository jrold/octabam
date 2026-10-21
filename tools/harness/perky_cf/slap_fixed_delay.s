/* Guarded candidate Slap fixed delay. The caller checks all five tap pairs
 * and the cursor every render call. Filter clamp followed by uint16 envelope
 * multiplication and >>16 proves each int32 input lies in int16 range.
 * The ring recurrence is therefore the existing bounded Hat recurrence;
 * output remains int32 because Slap applies velocity after the wet mix.
 * No EMAC, interrupt masking, peripheral access or cross-call cached control.
 */
.text
.balign 2
/* Native compact metadata is twelve uint16 fields (24 bytes). Read all ten
 * tap words in five aligned long loads; every value is checked on every call.
 * Tail calls retain the incoming C stack shape and need no extra save area. */
.globl pk_cf_slap_delay_fixed_dispatch
.type pk_cf_slap_delay_fixed_dispatch,@function
pk_cf_slap_delay_fixed_dispatch:
 move.l 4(%sp),%a0
 mvz.w (%a0),%d0
 cmp.l #4805,%d0
 bhs.s .Lslap_fixed_generic
 move.l 4(%a0),%d0
 cmp.l #0x023d04b1,%d0
 bne.s .Lslap_fixed_generic
 move.l 8(%a0),%d0
 cmp.l #0x06020c43,%d0
 bne.s .Lslap_fixed_generic
 move.l 12(%a0),%d0
 cmp.l #0x12c40001,%d0
 bne.s .Lslap_fixed_generic
 move.l 16(%a0),%d0
 cmp.l #0x00010003,%d0
 bne.s .Lslap_fixed_generic
 move.l 20(%a0),%d0
 cmp.l #0x00050007,%d0
 bne.s .Lslap_fixed_generic
 bra.s pk_cf_slap_delay_fixed
.Lslap_fixed_generic:
 jmp pk_cf_slap_delay_block
.size pk_cf_slap_delay_fixed_dispatch,.-pk_cf_slap_delay_fixed_dispatch

.macro slap_fixed_tap delay,gain
 move.l %d2,%d5
 sub.l #\delay,%d5
 bcc.s 1f
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
 bne.s 2f
 addq.l #1,%d4
2:
 move.l %d4,%d1
.endm
.balignw 4,0x4e71
.globl pk_cf_slap_delay_fixed
.type pk_cf_slap_delay_fixed,@function
pk_cf_slap_delay_fixed:
 lea -32(%sp),%sp
 movem.l %d2-%d7/%a2-%a3,(%sp)
 move.l 36(%sp),%a0
 move.l 40(%sp),%a2
 move.l 44(%sp),%a1
 move.l 48(%sp),%d0
 lsl.l #2,%d0
 lea (%a1,%d0.l),%a3
 mvz.w (%a0),%d2
 mvs.w 2(%a0),%d6
 cmp.l %a3,%a1
 beq 5f
.balignw 4,0x4e71
3:
 move.l (%a1),%d0
 move.l %d0,%d1
 slap_fixed_tap 573,1
 slap_fixed_tap 1201,1
 slap_fixed_tap 1538,3
 slap_fixed_tap 3139,5
 slap_fixed_tap 4804,7
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
 bcs.s 4f
 moveq #0,%d2
4:
 byterev %d1
 swap %d1
 move.w %d1,(%a2,%d2.l*2)
 move.l %d4,(%a1)+
 cmp.l %a3,%a1
 bne 3b
5:
 move.w %d2,(%a0)
 movem.l (%sp),%d2-%d7/%a2-%a3
 lea 32(%sp),%sp
 rts
.size pk_cf_slap_delay_fixed,.-pk_cf_slap_delay_fixed

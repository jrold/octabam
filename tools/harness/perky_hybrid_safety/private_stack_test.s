/* Host instrument calibration only; never linked into firmware. */
.text
.global _start
_start:
 move.l %sp,0x41600dc0
 lea 0x41600da0,%sp
 lea -252(%sp),%sp
 nop
 lea 252(%sp),%sp
 move.l 0x41600dc0,%sp
 rte

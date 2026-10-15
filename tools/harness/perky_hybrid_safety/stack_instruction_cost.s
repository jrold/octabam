/* Individual instruction calibration only, not an IRQ wrapper or firmware.
 * Each six-byte specimen is executed independently by the host probe.
 */
        .text
        .globl _start
_start:
        jmp (0x40002020).l
        move.l %sp,(0x41600dc0).l
        lea (0x41600da0).l,%sp
        move.l (0x41600dc0).l,%sp

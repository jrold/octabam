; Exact two-pass filter, retaining bounded signed16 state in registers.
; x1 first, x0 velocity, y0 coefficient, y1 damping, r1 held input.
pk_filter_probe:
 move x:(r6+$10),y0
 move x:(r6+$f),y1
move x:(r6+$11),a
        asl #$8,a,a
        move a1,a
        asr #$8,a,a
pknf_load_first:
 move a1,x1
move x:(r6+$15),a
        asl #$8,a,a
        move a1,a
        asr #$8,a,a
pknf_load_vel:
 move a1,x0
move x:(r5+$61),a
        asl #$8,a,a
        move a1,a
        asr #$8,a,a
pknf_load_noise:
 move a1,r1
 do #$2,pknf_two_done
 mpy y0,x0,a
asr #$1,a,a
 tst a
 jpl pknf_first_rounded
 clr b
 move #>$00ffff,b0
 add b,a
pknf_first_rounded:
 asr #$10,a,a
 move a0,a
add x1,a
cmp #>$007fff,a
 ble pknf_first_clamped_low
 move #>$007fff,a
pknf_first_clamped_low:
 cmp #>$ff8001,a
 bge pknf_first_clamped_ok
 move #>$ff8001,a
pknf_first_clamped_ok:
move a1,x1
 move r1,a
 sub x1,a
 move a1,r2
 mpy x0,y1,a
 asr #$b,a,a
 move a0,a
 move a1,b
 move r2,a
 sub b,a
cmp #>$007fff,a
 ble pknf_second_clamped_low
 move #>$007fff,a
pknf_second_clamped_low:
 cmp #>$ff8001,a
 bge pknf_second_clamped_ok
 move #>$ff8001,a
pknf_second_clamped_ok:
move a1,r2
 move x0,r3
 move a1,x0
 mpy y0,x0,a
asr #$1,a,a
 tst a
 jpl pknf_feedback_rounded
 clr b
 move #>$00ffff,b0
 add b,a
pknf_feedback_rounded:
 asr #$10,a,a
 move a0,a
move r3,b
 add b,a
cmp #>$007fff,a
 ble pknf_velocity_clamped_low
 move #>$007fff,a
pknf_velocity_clamped_low:
 cmp #>$ff8001,a
 bge pknf_velocity_clamped_ok
 move #>$ff8001,a
pknf_velocity_clamped_ok:
move a1,x0
pknf_two_done:
 nop
move x1,a
 move a1,b
 and #>$00ffff,b
 move b1,x:(r6+$11)
 clr b
 tst a
 jpl pknf_write_first
 move #>$00ffff,b
pknf_write_first:
 move b1,x:(r6+$12)
move r2,a
 move a1,b
 and #>$00ffff,b
 move b1,x:(r6+$13)
 clr b
 tst a
 jpl pknf_write_second
 move #>$00ffff,b
pknf_write_second:
 move b1,x:(r6+$14)
move x0,a
 move a1,b
 and #>$00ffff,b
 move b1,x:(r6+$15)
 clr b
 tst a
 jpl pknf_write_velocity
 move #>$00ffff,b
pknf_write_velocity:
 move b1,x:(r6+$16)
rts

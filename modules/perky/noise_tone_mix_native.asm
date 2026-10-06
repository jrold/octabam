; Exact mixer specialized to mix0..4095 and signed16 source samples.
; DSP's 56-bit accumulator avoids limb staging. The amplitude product still
; wraps to signed32 before >>16, exactly as the reference.
pk_mix_probe:
move x:(r5+$61),a
        asl #$8,a,a
        move a1,a
        asr #$8,a,a
pknm_noise_sign:
move a1,x0
 move x:(r6+$27),y0
 mpy y0,x0,a
 asr #$e,a,a
 move a0,a
 move a1,x:(r5+$52)
move x:(r5+$62),a
        asl #$8,a,a
        move a1,a
        asr #$8,a,a
pknm_osc1_sign:
move a1,x:(r5+$54)
move x:(r5+$63),a
        asl #$8,a,a
        move a1,a
        asr #$8,a,a
pknm_osc2_sign:
move x:(r5+$54),x0
 add x0,a
 asr #$4,a,a
 move a1,x0
 move #>$000fff,b
 move x:(r6+$27),y0
 sub y0,b
 move b1,y0
 mpy y0,x0,a
 asr #$a,a,a
 move a0,a
 move x:(r5+$52),x0
 add x0,a
 move a1,x0
 move x:(r5+$60),y0
 mpy y0,x0,a
 asr #$11,a,a
 move a0,a
 and #>$00ffff,a
 btst #15,a1
 jcc pknm_amp_sign
 sub #>$010000,a
pknm_amp_sign:
 move a1,x0
 move x:(r6+$0),y0
 mpy y0,x0,a
 asr #$9,a,a
 move a0,a
move a1,b
 and #>$00ffff,b
 move b1,x:(r5+$48)
 move #>$0,b
 tst a
 jpl pknm_store_debug
 move #>$00ffff,b
pknm_store_debug:
 move b1,x:(r5+$49)
cmp #>$007fff,a
 ble pknm_clamp_low
 move #>$007fff,a
pknm_clamp_low:
 cmp #>$ff8000,a
 bge pknm_clamp_ok
 move #>$ff8000,a
pknm_clamp_ok:
 and #>$00ffff,a
 move a1,x:(r5+$47)
 rts

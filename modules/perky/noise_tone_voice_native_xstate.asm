; Shipping renderer: operate directly on the compact persistent fields.
; r0 stereo output, r5 scratch, r6 voice, n7 samples. Same 41-word live ABI.
pk_voice_xstate:
        do n7,pkvx_block_done
        lua (r6+$29),r4
        jsr pk_envelope_packed7_cached
        move x:(r5+$51),a
        move a1,x:(r5+$60)
        jsr pknv_noise
        jsr pk_filter_probe
        lua (r6+$17),r7
        jsr pk_osc_packed_probe
        move x:(r5+$48),a
        move a1,x:(r5+$62)
        lua (r6+$1f),r7
        jsr pk_osc_packed_probe
        move x:(r5+$48),a
        move a1,x:(r5+$63)
        jsr pk_mix_probe
        move x:(r5+$47),a
        asl #$8,a,a
        move a1,a
        asr #$8,a,a
pkvx_sample_ready:
        move a1,x:(r0)+
        move a1,x:(r0)+
pkvx_block_done:
        nop
        rts

pknv_noise:
        move x:(r6+$c),a
        tst a
        beq pknv_refresh
        sub #>$1,a
        and #>$00ffff,a
        move a1,x:(r6+$c)
        move x:(r6+$e),a
        move a1,x:(r5+$61)
        rts
pknv_refresh:
        move x:(r6+$d),a
        move a1,x:(r6+$c)
        move x:>$38e8,a
        move a1,x:(r5+$0)
        move x:>$38e9,a
        move a1,x:(r5+$1)
        move x:>$38ea,a
        move a1,x:(r5+$2)
        move x:>$38eb,a
        move a1,x:(r5+$3)
        jsr pk_rng_step
        move x:(r5+$0),a
        move a1,x:>$38e8
        move x:(r5+$1),a
        move a1,x:>$38e9
        move x:(r5+$2),a
        move a1,x:>$38ea
        move x:(r5+$3),a
        move a1,x:>$38eb
        move x:(r5+$10),a
        and #>$00ffff,a
        move a1,x:(r6+$e)
        move a1,x:(r5+$61)
        rts

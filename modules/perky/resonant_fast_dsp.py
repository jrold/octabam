"""Bounded native DSP path for the exact v1.2.1 resonator.

Guarded inputs: signed22 drive, signed16 position/velocity, unsigned16 cached
coefficients and modulation. Modulated ca<=69374, cb<=327547; filtered drive
fits signed24. Each multiply explicitly wraps low32 before its signed shift.
All other inputs use the exact two-limb fallback, including malformed high
limbs. r6 is the 14-word resonator; r4 owns generated variables; r5 scratch.
"""


def emit(e, input_value, slow):
    e.emit(f'move {e.addr(input_value, 1)},a', 'add #>$40,a', 'and #>$00ffff,a',
           'cmp #>$7f,a', 'bgt ' + slow)
    for offset in (4, 6, 8):
        e.emit(f'move x:(r6+${offset:x}),a', 'tst a', 'bne ' + slow)
    for offset, scratch in ((10, 0x76), (12, 0x77)):
        e.emit(f'move x:(r6+${offset:x}),a', 'asl #$8,a,a', 'move a1,a', 'asr #$8,a,a',
               f'move a1,x:(r5+${scratch:x})', 'asr #$10,a,a', 'and #>$00ffff,a', 'move a1,a',
               f'move x:(r6+${offset + 1:x}),x0', 'cmp x0,a', 'bne ' + slow)
    e.emit(f'move {e.addr(input_value, 1)},a', 'lsl #$10,a',
           f'move {e.addr(input_value)},x0', 'or x0,a', 'move a1,r1')
    text = '''
        move x:(r5+$76),r2
        move x:(r5+$77),x1
        move x:(r6+$5),y0
        move x:(r6+$3),y1
        move x:(r6+$7),x0
        move x0,a
        tst a
        beq pkrf_mod_done
        move #>$80,a
        move a1,x:(r5+$78)
        move r2,a
        cmp #>$1000,a
        ble pkrf_mod_small
        sub #>$800,a
        asr #$3,a,a
        add y0,a
        move a1,y0
        move r2,a
        asr #$4,a,a
        move a1,x:(r5+$78)
pkrf_mod_small:
        move y0,n1
        move x:(r5+$78),y0
        mpyuu x0,y0,a
        asr #$a,a,a
        move a0,a
        add y1,a
        move a1,y1
        move n1,y0
pkrf_mod_done:
        move r1,r7
        move x:(r6+$9),a
        tst a
        bne pkrf_bypass_done
        move x1,x0
        mpy y0,x0,a
        asr #$1,a,a
        asl #$18,a,a
        asr #$f,a,a
        move a1,a
        move r1,b
        sub a,b
        move b1,r7
pkrf_bypass_done:
        move x1,x0
        move y1,y0
        mpy y0,x0,a
        asr #$1,a,a
        asl #$18,a,a
        asr #$f,a,a
        move a1,a
        move r2,x0
        add x0,a
        cmp #>$007fff,a
        ble pkrf_pos_hi
        move #>$007fff,a
pkrf_pos_hi:
        cmp #>$ff8001,a
        bge pkrf_pos_lo
        move #>$ff8001,a
pkrf_pos_lo:
        move a1,r2
        move a1,b
        and #>$00ffff,b
        move b1,x:(r6+$a)
        move a1,b
        asr #$10,b,b
        and #>$00ffff,b
        move b1,x:(r6+$b)
        move r7,a
        move r2,x0
        sub x0,a
        move a1,x0
        move y1,y0
        mpy y0,x0,a
        asr #$1,a,a
        asl #$18,a,a
        asr #$f,a,a
        move a1,a
        add x1,a
        cmp #>$007fff,a
        ble pkrf_vel_hi
        move #>$007fff,a
pkrf_vel_hi:
        cmp #>$ff8001,a
        bge pkrf_vel_lo
        move #>$ff8001,a
pkrf_vel_lo:
        move a1,b
        and #>$00ffff,b
        move b1,x:(r6+$c)
        move a1,b
        asr #$10,b,b
        and #>$00ffff,b
        move b1,x:(r6+$d)
        rts
'''
    e.lines.extend(text.strip('\n').splitlines())


def decay(e, value, slow):
    # Positive signed24 multiplier/value, unsigned16 minimum, signed22 sign.
    # The unsigned low32 product >>12 is <= 0xfffff. A one-time magnitude
    # addition is at most 0x400000, so state/output still fit signed24.
    for offset in (1, 5):
        e.emit(f'move x:(r6+${offset:x}),a', 'cmp #>$7f,a', 'bgt ' + slow)
    e.emit('move x:(r6+$9),a', 'tst a', 'bne ' + slow,
           'move x:(r6+$7),a', 'add #>$40,a', 'and #>$00ffff,a',
           'cmp #>$7f,a', 'bgt ' + slow)
    negative_count = e.label()
    count_ready = e.label()
    e.emit('move x:(r6+$3),a', 'tst a', 'bne ' + negative_count,
           'move x:(r6+$2),r2', 'bra ' + count_ready)
    e.mark(negative_count)
    e.emit('cmp #>$00ffff,a', 'bne ' + slow, 'move #>$ffffff,r2')
    e.mark(count_ready)
    text = '''
        move x:(r6+$7),a
        lsl #$10,a
        move x:(r6+$6),x0
        or x0,a
        move a1,r1
        move x:(r6+$1),a
        lsl #$10,a
        move x:(r6),x0
        or x0,a
        move a1,x0
        move x:(r6+$5),a
        lsl #$10,a
        move x:(r6+$4),y0
        or y0,a
        move a1,y0
        mpyuu x0,y0,a
        asr #$1,a,a
        asl #$18,a,a
        asr #$c,a,a
        move a1,a
        and #>$0fffff,a
        move a1,a
        move x:(r6+$8),x0
        cmp x0,a
        bge pkrd_min_done
        move x0,a
pkrd_min_done:
        move a1,r3
        move r2,a
        tst a
        ble pkrd_count_done
        sub #>$1,a
        move a1,r2
        move a1,x:(r6+$2)
        tst a
        bne pkrd_count_done
        move r1,a
        abs a
        move r3,x0
        add x0,a
        move a1,r3
pkrd_count_done:
        move r3,a
        move a1,b
        and #>$00ffff,b
        move b1,x:(r6+$4)
        lsr #$10,a
        move a1,x:(r6+$5)
        move r3,a
        move a1,x0
        move x:(r5+$76),a
        tst a
        beq pkrd_sign_done
        move r1,a
        tst a
        bge pkrd_sign_done
        move x0,a
        neg a
        move a1,x0
pkrd_sign_done:
        move r2,a
        tst a
        beq pkrd_constant_done
        move x:(r5+$77),a
        add x0,a
        move a1,x0
pkrd_constant_done:
        move x0,a
        asr #$10,a,a
'''
    e.lines.extend(text.strip('\n').splitlines())
    e.save(value)
    e.emit('rts')

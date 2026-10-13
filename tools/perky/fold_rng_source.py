"""Exact modulo-2^64 Fold transient RNG using unsigned 16-bit columns.

This is the same LCG already translated in noise_tone_math.asm. Positive
16-bit limbs/constants permit ordinary signed DSP MPY/MAC without unsigned
operand ambiguities. Accumulator products retain fractional alignment (2x);
carry extraction uses the raw low accumulator word, as in the existing port.
The independent executable 64-bit carry corpus is mandatory for this profile.
"""


def generate():
    lines=['pk_rng_step:']
    outputs=(0x08,0x09,0x10,0x11)  # existing probe/scratch ABI is hexadecimal
    for i in range(4):
        lines += [f'        move x:(r5+${i:x}),a',f'        move a1,x:(r5+${0x20+i:x})']
    # Column k is sum(old_limb[j] * multiplier_limb[k-j]) + carry.
    multiplier=(0x7f2d,0x4c95,0xf42d,0x5851)
    for k in range(4):
        for j in range(k+1):
            lines += [f'        move x:(r5+${0x20+j:x}),x0',
                      f'        move #>${multiplier[k-j]:06x},y0',
                      '        '+('mpy' if j==0 else 'mac')+' y0,x0,a']
        lines += ['        move #>$1,y0',
                  '        move #>$1,x0' if k==0 else '        move x:(r5+$37),x0',
                  '        mac y0,x0,a',
                  '        move a0,b','        lsr b','        and #>$00ffff,b',
                  f'        move b1,x:(r5+${outputs[k]:x})']
        if k<3:
            lines += ['        asr #$11,a,a','        move a0,x:(r5+$37)']
    for i in range(4):
        lines += [f'        move x:(r5+${outputs[i]:x}),a',f'        move a1,x:(r5+${i:x})']
    lines += ['        rts']
    return '\n'.join(lines)+'\n'

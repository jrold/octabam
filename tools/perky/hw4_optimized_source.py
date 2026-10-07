"""Exact HW4 specializations: decoded tables and a fixed-constant RNG kernel.

Keep the earlier shipping profiles and generic primitive probes unchanged.
Generated table bytes originate only from the user's qualified local assets.
"""
from pathlib import Path
import noise_tone_tables as tables
import hw4_memory as memory


def replace_routine(source, start, end, replacement):
    assert source.count('\n' + start + ':') == 1, start
    begin = source.index('\n' + start + ':')
    finish = source.index('\n' + end + (':' if not end.startswith(';') else ''), begin)
    return source[:begin] + '\n' + replacement + source[finish:]


def rng_source():
    # The native two-word recurrence is a modulo-2^64 LCG. All operands
    # are positive 16-bit limbs; signed MAC y0,x0 is a stock instruction.
    # Accumulate one base-65536 column in the full 56-bit accumulator.
    constants = (0x7f2d, 0x4c95, 0xf42d, 0x5851)
    lines = ['pk_rng_step:', '        move #>$1,x1']
    for column in range(4):
        lines += ['        clr a', '        move x1,b', '        asl b',
                  '        move b1,a0']
        for limb in range(column + 1):
            lines += [f'        move x:(r5+${limb:x}),x0',
                      f'        move #>${constants[column-limb]:06x},y0',
                      '        mac y0,x0,a']
        lines += ['        asr #$1,a,a', '        move a0,b',
                  '        and #>$ffff,b',
                  f'        move b1,x:(r5+${0x20+column:x})',
                  '        asr #$10,a,a', '        move a0,x1']
    for limb, output in enumerate((8, 9, 0x10, 0x11)):
        lines += [f'        move x:(r5+${0x20+limb:x}),a',
                  f'        move a1,x:(r5+${limb:x})',
                  f'        move a1,x:(r5+${output:x})']
    return '\n'.join(lines + ['        rts', ''])


def optimize(source, out: Path, layout: dict, emit_words):
    low = [int(v, 16) for v in (out / 'tables.words').read_text().split()]
    banks = layout['banks']
    rows = []
    for name, base, bank, count, signed in (
        ('hw4-simple-waves', memory.SIMPLE_WAVES_BASE, 'simple_waves', 768, True),
        ('hw4-simple-envelope', memory.SIMPLE_ENVELOPE_BASE, 'simple_envelope', 1024, False),
        ('hw4-noise-waves', memory.NOISE_WAVES_BASE, 'noise_waves', 1024, True),
    ):
        index = banks[bank] - 0x7a5
        values = tables.unpack_u16(low[index:], count)
        if signed:
            values = [v if v < 0x8000 else v - 0x10000 for v in values]
        rows.append({'base_word': base, **emit_words(out / (name + '.bin'), values),
                     'purpose': name + ', one exact sample per DSP word'})

    def reader(label, base):
        return (f'{label}:\n        move x0,n1\n'
                f'        move #>${base:06x},r1\n'
                '        lua (r1+n1),r2\n        move y:(r2),a\n        rts\n')

    source = replace_routine(source, 'pksdo_read_s16', 'pk_simple_delta_at',
                             reader('pksdo_read_s16', memory.SIMPLE_WAVES_BASE))
    source = replace_routine(source, 'pksde_read_u16', 'pk_simple_frequency',
                             reader('pksde_read_u16', memory.SIMPLE_ENVELOPE_BASE))
    source = replace_routine(source, 'pkon_read_next', '; ===== END noise_tone_oscillator_packed.asm =====',
                             'pkon_read_next:\n        move y:(r2+1),a\n        rts\n' +
                             reader('pkop_read_s16', memory.NOISE_WAVES_BASE))
    source = replace_routine(source, 'pk_rng_step', 'pk_noise_step', rng_source())
    source = oscillator(source, 'pk_simple_oscillator', 'hso',
                        'pksdo_read_s16:', memory.SIMPLE_WAVES_BASE)
    source = oscillator(source, 'pk_osc_packed_probe', 'hno',
                        'pkon_read_next:', memory.NOISE_WAVES_BASE, noise=True)
    # The HW4 Noise/Tone profile always uses the exact analytic shape-1
    # curve. Decode its 2048 knots once rather than divide every sample.
    values = [32*i + (31*i + 1023)//2047 for i in range(2048)]
    rows.append({'base_word': memory.NOISE_ENVELOPE_BASE,
                 **emit_words(out / 'hw4-noise-envelope.bin', values),
                 'purpose': 'HW4 Noise/Tone analytic shape-1 knots, exact u16'})
    source = replace_routine(source, 'pk_envelope_packed7_cached',
                             'pk_envelope_probe',
                             'pk_envelope_packed7_cached:\n        bra pk_envelope_probe\n')
    start = source.index('\npkne_output:')
    end = source.index('\n; ===== END noise_tone_envelope.asm =====', start)
    source = source[:start] + noise_envelope_source() + source[end:]
    source = replace_routine(source, 'pksde_shape1', 'pksde_read_u16', simple_envelope_source().lstrip())
    source = replace_routine(source, 'pk_simple_frequency', 'pk_simple_oscillator', simple_frequency_source().lstrip())
    values = [(i*0x57619f1)//(1<<22) for i in range(2049)]
    rows.append({'base_word': memory.SIMPLE_FREQUENCY_BASE,
                 **emit_words(out / 'hw4-simple-frequency.bin', values),
                 'purpose': 'HW4 exact odd oscillator frequency law, absolute indices 0..2048'})
    # Signed oscillator results stay in signed24 scratch through the mixer.
    # The renderer consumes only the mixer's signed return, not probe debug.
    source = source.replace('        and #>$ffff,a\n        move a1,x:(r5+$48)\n        rts\n\npkon_read_next:',
                            '        move a1,x:(r5+$48)\n        rts\n\npkon_read_next:', 1)
    for label in ('pknm_osc1_sign:', 'pknm_osc2_sign:'):
        at = source.index('\n'+label)
        start = source.rfind('        asl #$8,a,a', 0, at)
        source = source[:start] + source[at:]
    at = source.index('\npknm_amp_sign:')
    begin = source.index('move a1,b', at)
    end = source.index('cmp #>$007fff,a', begin)
    source = source[:begin] + source[end:]
    at = source.index('\npknm_clamp_ok:')
    end = source.index('\n; ===== END noise_tone_mix.asm =====', at)
    source = source[:at] + '\npknm_clamp_ok:\n rts\n' + source[end:]
    source = source.replace("""        move x:(r5+$47),a
        asl #$8,a,a
        move a1,a
        asr #$8,a,a
pkvx_sample_ready:""", 'pkvx_sample_ready:')
    source = fold2_pointers(source)
    # Use the established address-update + plain Y-load forms. There is no
    # indexed Y load in either stock payload; the existing packed readers
    # already use LUA with this addressing mode on the hardware.
    source = source.replace('move y:(r1+n1),', 'lua (r1+n1),r2\n        move y:(r2),')
    # Eight one-bit shifts and one eight-bit shift produce identical full
    # accumulator bits here; no intermediate flags are consumed.
    old = '\n'.join(['        asl     a'] * 8)
    assert source.count(old) == 1
    source = source.replace(old, '        asl     #$8,a,a', 1)
    return source, rows


def oscillator(source, label, prefix, end, base, noise=False):
    begin = source.index('\n' + label + ':')
    ready = source.index('\n' + ('pkop' if noise else 'pksdo') + '_phase_ready:', begin)
    # Retain the proven u32 phase update/wrap and deferred switch.
    phase = source[begin:ready]
    phase_prefix = 'pkop' if noise else 'pksdo'
    phase = phase.replace(phase_prefix + '_phase_ready', prefix + '_ready')
    text = phase + '\n' + prefix + '_ready:\n'
    if noise:
        text += f'''        move x:(r7+$4),a
        lsr a
        and #>$300,a
        add #>${base:06x},a
        move a1,r1
'''
    else:
        text += f'''        move x:(r7+$5),a
        cmp #>$802,a
        bne {prefix}_invalid
        move x:(r7+$4),a
        cmp #>$22a0,a
        beq {prefix}_bank_a
        cmp #>$26a0,a
        beq {prefix}_bank_b
        cmp #>$28a0,a
        bne {prefix}_invalid
        move #>${base+512:06x},r1
        bra {prefix}_lookup
{prefix}_bank_a:
        move #>${base:06x},r1
        bra {prefix}_lookup
{prefix}_bank_b:
        move #>${base+256:06x},r1
'''
    text += f'''{prefix}_lookup:
        move x:(r7+$0),a
        move a1,b
        and #>$fff,b
        move b1,y0
        lsr #$c,a
        move a1,x0
        move x:(r7+$1),a
        and #>$f,a
        asl #$4,a,a
        add x0,a
        move a1,n1
        move y:(r1+n1),y1
        add #>$1,a
        and #>$ff,a
        move a1,n1
        move y:(r1+n1),a
        sub y1,a
        move a1,x0
        mpy y0,x0,a
        asr #$d,a,a
        move a0,a
        add y1,a
'''
    if noise:
        text += '        and #>$ffff,a\n        move a1,x:(r5+$48)\n        rts\n'
    else:
        text += f'''        and #>$ffff,a
        asl #$8,a,a
        move a1,a
        asr #$8,a,a
        rts
{prefix}_invalid:
        clr a
        rts
'''
    finish = source.index('\n' + end, ready)
    return source[:begin] + text + source[finish:]



def noise_envelope_source():
    return f"""
pkne_output:
        move x:(r6+$7),a
        asl #$6,a,a
        move x:(r6+$6),x0
        move x0,b
        lsr #$a,b
        add b,a
        and #>$7ff,a
        move a1,n1
        move #>${memory.NOISE_ENVELOPE_BASE:06x},r1
        move y:(r1+n1),y1
        add #>$1,a
        and #>$7ff,a
        move a1,n1
        move y:(r1+n1),a
        sub y1,a
        move a1,y0
        move x0,a
        and #>$3ff,a
        move a1,x0
        mpy y0,x0,a
        asr #$b,a,a
        move a0,a
        add y1,a
        and #>$ffff,a
        move a1,x:(r5+$51)
        rts
"""


def simple_envelope_source():
    return f'''
pksde_shape1:
        move a1,b
        and #>$3ff,b
        move b1,y0
        lsr #$a,a
        move a1,n1
        move #>${memory.SIMPLE_ENVELOPE_BASE:06x},r1
        move y:(r1+n1),y1
        cmp #>$3ff,a
        beq hse_last_knot
        add #>$1,a
hse_last_knot:
        move a1,n1
        move y:(r1+n1),a
        sub y1,a
        move a1,x0
        mpy y0,x0,a
        asr #$b,a,a
        move a0,a
        add y1,a
        and #>$ffff,a
        rts
'''


def simple_frequency_source():
    return f'''
pk_simple_frequency:
        move x0,a
        and #>$fff,a
        btst #11,a1
        bcc hsf_positive_input
        sub #>$1000,a
hsf_positive_input:
        move a1,y1
        abs a
        move a1,n1
        move #>${memory.SIMPLE_FREQUENCY_BASE:06x},r1
        move y:(r1+n1),a
        move y1,b
        tst b
        bpl hsf_return
        neg a
hsf_return:
        rts
'''



def fold2_pointers(source):
    # Raw triggers can swap the primary, but neither renderer changes it.
    # Select both bases once per prefix/suffix call. n4/n6 are untouched by
    # every helper reachable from this loop (envelope/frequency/oscillator/RNG).
    start = source.index('\npk_fold2_voice:')
    loop = source.index('        do      n7,pkf2_samples_done', start)
    setup = """        move x:(r6+$32),a
        tst a
        bne hfp_primary_b
        lua (r6+$2),r7
        move r7,n6
        lua (r6+$22),r7
        move r7,n4
        bra hfp_pair_ready
hfp_primary_b:
        lua (r6+$22),r7
        move r7,n6
        lua (r6+$2),r7
        move r7,n4
hfp_pair_ready:
"""
    source = source[:loop] + setup + source[loop:]
    begin = source.index('        ; Keep the returned 32-bit oscillator increment', start)
    end = source.index('        ; Render p1.', begin)
    source = source[:begin] + """        move n6,r7
        move a1,b
        and #>$ffff,b
        move b1,x:(r7+$2)
        asr #$10,a,a
        and #>$ffff,a
        move a1,x:(r7+$3)

""" + source[end:]
    begin = source.index('        ; Render p2 (the other fixed oscillator).', start)
    end = source.index('        jsrl     pk_simple_oscillator', begin)
    source = source[:begin] + '        move n4,r7\n' + source[end:]
    return source

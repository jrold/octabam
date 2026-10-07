"""Compose Slap from the renderer and the exact shared Noise Hat primitives.

Only field addresses and the final delay return width differ from Noise Hat's
wrapper delay. Keep its source as the single implementation of the five taps.
"""
from pathlib import Path
import re
from dsp_source_layout import center_scratch

ROOT = Path(__file__).resolve().parents[2]
PERKY = ROOT / 'modules/perky'


def delay_source():
    source = (PERKY / 'noise_hat_classic_delay.asm').read_text()
    source = source.replace('pk_noise_hat_classic_delay', 'pk_slap_delay').replace('pknhcd_', 'pksld_')
    fields = {'6d': '1c', '72': '21', '77': '26', '78': '27'}
    source = re.sub(r'(r6\+\$)([0-9a-f]+)',
                    lambda m: m[1] + fields.get(m[2], m[2]), source)
    source = source.replace('move    #>$6d,n1', 'move    #>$1c,n1')
    source = source.replace('move    #>$72,n2', 'move    #>$21,n2')
    # Slap returns signed32 >>12, whereas Noise Hat narrows that result to
    # int16. Wrap the sum first: discarded overflow is visible to Slap.
    old = '''        asr     #$c,a,a
        move    a0,a
        asl     #$8,a,a
        move    a1,a
        asr     #$8,a,a
        rts'''
    new = '''        asl     #$18,a,a
        asr     #$c,a,a
        move    a1,a
        rts'''
    assert source.count(old) == 1
    source = source.replace(old, new)
    # Replace the inherited header with this composed routine's actual ABI.
    source = source[source.index('\npk_slap_delay:'):]
    return '; Slap five-tap delay: compact fields +$1c..$27; signed32 output.\n' + source


def source():
    text = '\n'.join([
        (PERKY / 'slap_voice.asm').read_text(), delay_source(),
        *((PERKY / name).read_text() for name in (
            'noise_hat_filter.asm', 'noise_hat_envelope.asm', 'noise_tone_math.asm')),
    ])
    return center_scratch(text, 'pk_slap_voice', delay=True)

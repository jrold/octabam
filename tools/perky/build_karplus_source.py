"""Compose Karplus with the qualified common envelope, RNG and filter."""
from pathlib import Path
import re
from dsp_source_layout import center_scratch
ROOT = Path(__file__).resolve().parents[2]
PERKY = ROOT / 'modules/perky'


def source(*, include_math=True):
    noise = (PERKY / 'slap_voice.asm').read_text().split('\npk_slap_noise:', 1)[1]
    noise = ('\npk_karplus_noise:' + noise).replace('pkslv_noise_refresh', 'pkkv_noise_refresh')
    fields = {'d': 'e', 'e': 'f', 'f': '10'}
    noise = re.sub(r'(r6\+\$)([0-9a-f]+)', lambda m: m[1] + fields.get(m[2], m[2]), noise)
    filt = (PERKY / 'noise_hat_filter.asm').read_text()
    old = '''        move    x:(r5+$61),a
        asl     #$8,a,a
        move    a1,a
        asr     #$8,a,a
        move    a1,r1'''
    assert filt.count(old) == 1
    filt = filt.replace(old, '        move    x:(r5+$61),r1')
    filt = filt[filt.index('\npk_noise_hat_filter:'):]
    filt = filt.replace('pk_noise_hat_filter', 'pk_karplus_filter').replace('pknhf_', 'pkkf_')
    pieces = [
        (PERKY / 'karplus_voice.asm').read_text(), noise,
        '; Karplus filter input is signed24 (unsigned ring + signed excitation).\n' + filt,
        (PERKY / 'noise_hat_envelope.asm').read_text(),
    ]
    # Multi-engine production compositions already carry the common u32 math
    # helpers through Noise/Tone.  Standalone Karplus gates keep the historical
    # self-contained source by leaving this default enabled.
    if include_math:
        pieces.append((PERKY / 'noise_tone_math.asm').read_text())
    return center_scratch('\n'.join(pieces), 'pk_karplus_voice')

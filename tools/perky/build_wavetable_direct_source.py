"""Constant-time direct packed Wavetable asset candidate.

One directory entry supplies each physical wave base. The proven three-u16 in
two-DSP-word reader performs at most two reads, without a decoded-block cache.
Placement/stock init/retirement/transport remain independent production gates.
"""
from pathlib import Path
import build_wavetable_cached_source as cached

PERKY = Path(__file__).resolve().parents[2] / 'modules/perky'


def source():
    text = cached.source()
    # Keep the renderer and pointer-directory lookup, replace only the backend.
    start = text.index('; Lossless second-difference32 block decoder.')
    end = text.index('\npk_simple_envelope:', start)
    reader = (PERKY / 'simple_drum_oscillator.asm').read_text().split('\npksdo_read_s16:', 1)[1]
    reader = '\npkwt_direct_s16:' + reader.replace('pksdo_read_', 'pkwtd_')
    reader = reader.replace('move    #>$0007a5,r1', 'move    n4,r1')
    text = text[:start] + reader + text[end:]
    text = text.replace('jsr pk_wavetable_asset_at', 'jsr pkwt_direct_s16')
    text = text.replace('        move y:(r1+$2),r2\n', '').replace('        move r2,r1\n', '')
    text = text.replace(f'        move #>${cached.CACHE_A:06x},r4\n', '')
    text = text.replace(f'        move #>${cached.CACHE_B:06x},r4\n', '')
    return text

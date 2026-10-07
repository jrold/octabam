"""Compose a Wavetable candidate with two exact compressed-asset caches.

The directory supplies physical DSP pointers. This does not install uploads,
retire stock effects or change stock initialization. Gate all of those before
shipping. r5 scratch/decoder ABI, r4 one of two shared 33-word decode caches.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PERKY = ROOT / 'modules/perky'
DIRECTORY = 0x7A5
CACHE_A, CACHE_B = 0x3975, 0x3996


def source():
    voice = (PERKY / 'wavetable_drum_voice.asm').read_text()
    voice = voice[:voice.index('\npkwt_fetch_wave:')]
    voice = voice.replace('pkwto_targets_ready:', f'pkwto_targets_ready:\n        move #>${CACHE_A:06x},r4')
    old = '        move x:(r5+$52),x0\n        move x:(r6+$22),y0'
    assert voice.count(old) == 1
    voice = voice.replace(old, f'        move #>${CACHE_B:06x},r4\n' + old)
    fetch = f'''
pkwt_fetch_wave:
        move x0,x:(r5+$5b)
        move y1,a
        and #>$ff,a
        asl #$10,a,a
        add y0,a
        cmp #>$0222a0,a
        beq pkwtc_initial_wave
        sub #>$0327cc,a
        lsr #$c,a
        add #>$1,a
        bra pkwtc_index_ready
pkwtc_initial_wave:
        clr a
pkwtc_index_ready:
        asl #$2,a,a
        move a1,n1
        move #>${DIRECTORY:06x},r1
        move (r1)+n1
        move y:(r1+$2),r2
        move y:(r1+$3),n4
        move r2,r1
        move x:(r5+$5b),x0
        jsr pk_wavetable_asset_at
        rts
'''
    decoder = (PERKY / 'wavetable_asset_decode.asm').read_text()
    # Shared-window headers produce negative 24-bit cache tags. Normalize B
    # before comparing to the sign-extended stored tag, otherwise every hit
    # becomes a miss despite identical bits. Header addresses < 2^18 make the
    # 24-bit (header << 6) | block identity collision-free across this map.
    old = '        add a,b\n        move x:(r4),x0'
    assert decoder.count(old) == 1
    decoder = decoder.replace(old, '        add a,b\n        move b1,b\n        move x:(r4),x0')
    parts = [voice, fetch, decoder]
    for name, label in (('envelope', 'pk_simple_envelope'), ('frequency', 'pk_simple_frequency')):
        text = (PERKY / f'simple_drum_{name}.asm').read_text()
        parts.append(text[text.index('\n' + label + ':'):].replace('#>$0009a5,r1', '#>$000c50,r1'))
    parts.append((PERKY / 'simple_drum_delta.asm').read_text())
    return '\n'.join(parts)

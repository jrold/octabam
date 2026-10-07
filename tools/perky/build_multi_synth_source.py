#!/usr/bin/env python3
"""PERKY3 shipping composition: authentic Simple Drum + unchanged live Noise/Tone.

Noise/Tone's exposed control path always initializes/restores shape 1, whose
lookup is analytic in PERKY2. Remove unreachable curve variants and their Y
assets only in this explicit shipping profile; original generic probes remain.
"""
from pathlib import Path
import re
import build_noise_tone_synth_source as noise
ROOT=Path(__file__).resolve().parents[2];PERKY=ROOT/'modules/perky'

def generate(noise_layout):
    source=noise.generate(noise_layout)
    begin=source.index('; ===== BEGIN noise_tone_envelope_packed7.asm =====')
    end=source.index('; ===== END noise_tone_envelope_packed7.asm =====',begin)
    section=source[begin:end];linear=section[section.index('\npken_linear:'):]
    wrapper='''pk_envelope_packed7_cached:
        clr a
        move a1,x:(r6+$2)
        jsrl pk_envelope_probe
        move #>$1,a
        move a1,x:(r6+$2)
        bra pken_linear
'''
    source=source[:begin]+wrapper+linear+source[end:]
    # Standalone math dispatcher and unused SUB/ASR are not reachable by RNG.
    start=source.index('\npk_math_probe:');stop=source.index('\npk_u32_add:',start)
    source=source[:start]+source[stop:]
    start=source.index('\npk_u32_sub:');stop=source.index('\npk_u32_mul_low:',start)
    source=source[:start]+source[stop:]
    # Dispatch precedes Noise/Tone control/voice entry; all admission/stock
    # continuation behavior is retained from the working PERKY2 source.
    source=source.replace('pks_voice_ready:\n','''pks_voice_ready:
        move x:(r4+$13),a
        and #>$ff,a
        cmp #>$2,a
        beq pks_simple_entry
        cmp #>$a,a
        bne pks_silence
        jsrl pk_multi_noise_init
''',1)
    source=source.replace('pks_silence:',(PERKY/'simple_drum_seam.asm').read_text()+'\npks_silence:',1)
    extras=(PERKY/'simple_drum_voice.asm').read_text()
    for name,label in [('envelope','pk_simple_envelope'),('frequency','pk_simple_frequency'),('oscillator','pk_simple_oscillator')]:
        text=(PERKY/f'simple_drum_{name}.asm').read_text();text=text[text.index('\n'+label+':'):]
        if name=='envelope':text=text.replace('#>$0009a5,r1','#>$000c50,r1')
        if name=='oscillator':text=text.replace('#>$0007a5,r1','#>$000a50,r1')
        extras+='\n'+text
    extras+='\n'+(PERKY/'simple_drum_delta.asm').read_text()
    source=noise.force_long_local_jsr(noise.relativize_local_conditionals(source+'\n'+extras))
    labels=re.findall(r'(?m)^([A-Za-z0-9_]+):',source)
    for a in labels:
        for b in labels:
            if a!=b and b.startswith(a):raise ValueError(f'prefix collision {a}/{b}')
    return source

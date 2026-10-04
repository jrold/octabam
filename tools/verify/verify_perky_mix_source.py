#!/usr/bin/env python3
"""Static invariants for PERKY's standalone final Noise/Tone mixer probe."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
p = (ROOT / 'modules/perky/noise_tone_mix.asm').read_text()


def need(s: str) -> None:
    if s not in p:
        raise SystemExit(f'verify-perky-mix-source: missing {s!r}')


for s in (
    'pk_mix_probe:',
    'pkm_s16_to_b:',
    'pkm_add:',
    'pkm_sub:',
    'pkm_asr:',
    'pkm_mul_low:',
    'pkm_clamp_i16:',
    'move    #>$d,a',
    'move    #>$4,a',
    'move    #>$000fff,a',
    'move    #>$9,a',
    'move    #>$10,a',
    'move    #>$8,a',
    'move    #>$007fff,a',
    'move    #>$008000,a',
    'move    a1,x:(r5+$47)',
    'move    a1,x:(r5+$48)',
    'move    a1,x:(r5+$49)',
):
    need(s)

if p.count('jsr     pkm_mul_low') != 4:
    raise SystemExit(
        'verify-perky-mix-source: expected noise/tonal/amplitude/velocity multiplies'
    )
if p.count('jsr     pkm_asr') != 5:
    raise SystemExit(
        'verify-perky-mix-source: expected five arithmetic shifts in mixer chain'
    )
if p.count('jsr     pkm_s16_to_b') != 3:
    raise SystemExit(
        'verify-perky-mix-source: noise and both oscillators must be sign-extended'
    )
if 'bset    #17,sr' in p or 'SA_MODE' in p:
    raise SystemExit('verify-perky-mix-source: SA mode is forbidden')

print('PERKY Noise/Tone mixer source gate: OK')

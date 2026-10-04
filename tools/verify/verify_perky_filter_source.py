#!/usr/bin/env python3
"""Static invariants for the standalone PERKY Noise/Tone filter probe."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
p = (ROOT / 'modules/perky/noise_tone_filter.asm').read_text()


def need(s: str) -> None:
    if s not in p:
        raise SystemExit(f'verify-perky-filter-source: missing {s!r}')


for s in (
    'pk_filter_probe:',
    'pkf_add:',
    'pkf_sub:',
    'pkf_asr:',
    'pkf_mul_low:',
    'pkf_clamp_s16ish:',
    'move    x:(r5+$44),a',
    'move    x:(r5+$45),a',
    'move    x:(r5+$46),a',
    'move    x:(r5+$48),a',
    'move    x:(r5+$50),a',
    'move    x:(r5+$52),a',
    'move    #>$00ffff,a',
    'move    #>$10,a',
    'move    #>$a,a',
    'move    #>$007fff,a',
    'move    #>$008001,a',
):
    need(s)

if p.count('jsr     pkf_mul_low') != 3:
    raise SystemExit(
        'verify-perky-filter-source: expected exactly three low32 multiplies'
    )
if p.count('jsr     pkf_clamp_s16ish') != 3:
    raise SystemExit(
        'verify-perky-filter-source: expected first/second/velocity clamps'
    )
if p.count('btst    #15,a1') < 4:
    raise SystemExit(
        'verify-perky-filter-source: signed product/clamp tests are incomplete'
    )
if 'mpyuu   x0,y0,a' not in p:
    raise SystemExit('verify-perky-filter-source: missing 16x16 multiply kernel')
if 'bset    #17,sr' in p or 'SA_MODE' in p:
    raise SystemExit('verify-perky-filter-source: SA mode is forbidden')

print('PERKY Noise/Tone filter source gate: OK')

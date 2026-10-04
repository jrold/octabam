#!/usr/bin/env python3
"""Static invariants for PERKY's table-free oscillator interpolation probe."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
p = (ROOT / 'modules/perky/noise_tone_oscillator.asm').read_text()


def need(s: str) -> None:
    if s not in p:
        raise SystemExit(f'verify-perky-oscillator-source: missing {s!r}')


for s in (
    'pk_osc_probe:',
    'pko_add:',
    'pko_asr:',
    'pko_mul_low:',
    'cmp     #>$0010,a',
    'sub     #>$0010,a',
    'cmp     #>$002222,a',
    'cmp     #>$001111,a',
    'cmp     #>$004444,a',
    'cmp     #>$003333,a',
    'move    #>$003000,r1',
    'move    #>$003100,r1',
    'and     #>$000fff,a',
    'and     #>$0000ff,a',
    'lsr     #$c,b,b',
    'asl     #$4,a,a',
    'move    x:(r1+n1),a',
    'move    #>$c,a',
    'move    a1,x:(r5+$48)',
):
    need(s)

if p.count('move    x:(r1+n1),a') != 2:
    raise SystemExit(
        'verify-perky-oscillator-source: expected exactly two table reads'
    )
if p.count('btst    #15,a1') < 4:
    raise SystemExit(
        'verify-perky-oscillator-source: signed phase/sample handling incomplete'
    )
if p.count('jsr     pko_mul_low') != 1:
    raise SystemExit(
        'verify-perky-oscillator-source: interpolation must use one low32 multiply'
    )
if 'bset    #17,sr' in p or 'SA_MODE' in p:
    raise SystemExit('verify-perky-oscillator-source: SA mode is forbidden')

print('PERKY Noise/Tone oscillator source gate: OK')

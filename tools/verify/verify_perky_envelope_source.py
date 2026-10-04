#!/usr/bin/env python3
"""Static invariants for PERKY's standalone Noise/Tone envelope probe."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
p = (ROOT / 'modules/perky/noise_tone_envelope.asm').read_text()


def need(s: str) -> None:
    if s not in p:
        raise SystemExit(f'verify-perky-envelope-source: missing {s!r}')


for s in (
    'pk_envelope_probe:',
    'pke_state0:',
    'pke_state1:',
    'pke_state3:',
    'pke_state4:',
    'pke_curve1:',
    'pke_curve2:',
    'pke_value_gt_peak:',
    'pke_value_ge_one:',
    'pke_value_le_zero:',
    'pke_add:',
    'pke_sub:',
    'pke_asr:',
    'pke_mul_low:',
    'move    #>$003200,r1',
    'move    #>$003a00,r1',
    'cmp     #>$00fffe,a',
    'cmp     #>$000010,a',
    'move    #>$00ffff,a',
    'move    #>$00000f,a',
    'and     #>$0007ff,a',
    'and     #>$0003ff,a',
    'move    #>$a,a',
    'move    a1,x:(r5+$51)',
):
    need(s)

if p.count('move    x:(r1+n1),a') != 2:
    raise SystemExit(
        'verify-perky-envelope-source: expected exactly two curve reads'
    )
if p.count('jsr     pke_value_gt_peak') != 1:
    raise SystemExit('verify-perky-envelope-source: peak test count drifted')
if p.count('jsr     pke_value_ge_one') != 1:
    raise SystemExit('verify-perky-envelope-source: clamp test count drifted')
if p.count('jsr     pke_value_le_zero') != 1:
    raise SystemExit('verify-perky-envelope-source: release zero test count drifted')
if 'bset    #17,sr' in p or 'SA_MODE' in p:
    raise SystemExit('verify-perky-envelope-source: SA mode is forbidden')

print('PERKY Noise/Tone envelope source gate: OK')

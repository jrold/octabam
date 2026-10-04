#!/usr/bin/env python3
"""Static gate for PERKY's standalone DSP56300 u32/RNG/noise kernel."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
p = (ROOT / 'modules/perky/noise_tone_math.asm').read_text()


def need(s):
    if s not in p:
        raise SystemExit(f'verify-perky-math-source: missing {s!r}')


for s in (
    'pk_math_probe:',
    'pk_u32_add:',
    'pk_u32_sub:',
    'pk_u32_asr:',
    'pk_u32_mul_low:',
    'pk_mul16:',
    'pk_u32_mul_full:',
    'pk_rng_step:',
    'pk_noise_step:',
    'pk_noise_refresh:',
    'btst    #16,a1',
    'jpl     pk_sub_no_borrow',
    'btst    #15,a1',
    'do      x0,pk_asr_loop_done',
    'add     y1,b ifcs',
    'mpyuu   x0,y0,a',
    'lsr     #$10,a,a',
    'move    #>$00f42d,a',
    'move    #>$005851,a',
    'move    #>$007f2d,a',
    'move    #>$004c95,a',
    'move    a1,x:(r5+$36)',
    'move    a1,x:(r5+$8)',
    'move    a1,x:(r5+$9)',
    'move    a1,x:(r5+$10)',
    'move    a1,x:(r5+$11)',
    'move    x:(r5+$40),a',
    'move    x:(r5+$41),a',
    'move    x:(r5+$42),a',
    'move    a1,x:(r5+$12)',
    'jsr     pk_rng_step',
):
    need(s)

if p.count('mpyuu   x0,y0,a') < 4:
    raise SystemExit(
        'verify-perky-math-source: low32/full64 multiply paths are incomplete'
    )
if p.count('jsr     pk_u32_mul_low') < 2:
    raise SystemExit(
        'verify-perky-math-source: RNG accumulator must use both low32 products'
    )
if 'jsr     pk_u32_mul_full' not in p:
    raise SystemExit(
        'verify-perky-math-source: RNG must use the exact full64 product path'
    )
if 'move    #>$7,x0' not in p or 'beq     pk_math_do_noise' not in p:
    raise SystemExit(
        'verify-perky-math-source: sample-and-hold noise op is not reachable'
    )
if 'bset    #17,sr' in p or 'SA_MODE' in p:
    raise SystemExit(
        'verify-perky-math-source: SA mode must stay out of emulator-tested kernel'
    )

print('PERKY DSP math/RNG/noise source gate: OK')

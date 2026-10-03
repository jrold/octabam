#!/usr/bin/env python3
"""Static gate for PERKY's standalone DSP56300 u32 kernel."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
p=(ROOT/'modules/perky/noise_tone_math.asm').read_text()
def need(s):
    if s not in p: raise SystemExit(f'verify-perky-math-source: missing {s!r}')
for s in ('pk_math_probe:','pk_u32_add:','pk_u32_sub:','pk_u32_asr:','pk_u32_mul_low:',
          'btst    #16,a1','jpl     pk_sub_no_borrow','btst    #15,a1',
          'do      x0,pk_asr_loop_done','add     y1,b ifcs','mpyuu   x0,y0,a',
          'lsr     #$10,a,a','move    a1,x:(r5+$8)','move    b1,x:(r5+$9)'):
    need(s)
if p.count('mpyuu   x0,y0,a') != 3:
    raise SystemExit('verify-perky-math-source: low32 multiply must use three 16x16 products')
if 'bset    #17,sr' in p or 'SA_MODE' in p:
    raise SystemExit('verify-perky-math-source: SA mode must stay out of emulator-tested kernel')
print('PERKY DSP math source gate: OK')

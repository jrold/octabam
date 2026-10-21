"""Exact rational source interpolation using one fractional EMAC product.

For p=1..146, C=ceil(p*32*2^26/147). Positive differences use C;
negative differences use C-1 and complement the quotient. The error bound
65535/2^26 < 1/147 preserves every noninteger quotient. At exact multiples,
ceil/floor coefficient selection preserves the two rounding directions.
For p=0 the negative coefficient is -1, whose negative fractional result
floors to -1; complementing yields the required zero correction.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def coefficients():
    return [(phase * 32 * (1 << 26) + 146) // 147 for phase in range(147)]


def generate(work):
    work = Path(work)
    text = (ROOT / 'modules/perky/production_resample.s').read_text()
    old = ''' lea (%a1,%d0.l),%a4
 move.l (%a3),%d0
 move.l #233739717,%d6
 cmp.l %a4,%a1'''
    new = ''' move.l %a1,%d6
 add.l %d0,%d6
 move.l (%a3),%d0
 lea .Lrs_exact_coeffs:l,%a4
 cmp.l %d6,%a1'''
    assert text.count(old) == 1
    text = text.replace(old, new, 1)
    begin = text.index('.Lnhbc_loop:\n')
    end = text.index('.Lnhbc_store:\n', begin)
    text = text[:begin] + '''.Lnhbc_loop:
 mvs.w (%a0),%d1
 mvs.w 2(%a0),%d2
 sub.l %d1,%d2
 smi %d3
 extb.l %d3
 eor.l %d3,%d2
 sub.l %d3,%d2
 lsl.l #5,%d2
 move.l (%a4,%d0.l*4),%d4
 add.l %d3,%d4
 mac.l %d2,%d4,%acc0
 movclr.l %acc0,%d2
 eor.l %d3,%d2
 lsl.l #5,%d1
 add.l %d2,%d1
''' + text[end:]
    assert text.count(' cmp.l %a4,%a1') == 1
    text = text.replace(' cmp.l %a4,%a1', ' cmp.l %d6,%a1')
    # The table stays in the same mapped unit as its caller. It contains only
    # computed rational coefficients, never firmware bytes.
    text += '\n.balign 4\n.Lrs_exact_coeffs:\n' + ''.join(
        f' .long {value}\n' for value in coefficients())
    target = work / 'source-resample-lut.s'
    target.write_text(text)
    return target

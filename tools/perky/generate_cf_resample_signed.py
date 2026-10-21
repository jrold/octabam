"""Exact signed interpolation, with the existing phase table and clock ABI.

For a negative difference use C-1 rather than C, where C=ceil(p*2^31/147).
Multiplying the signed difference directly then needs neither an absolute
value nor a complemented quotient. The coefficient error is less than 1/147
over all int16 differences, so flooring preserves the rational quotient.
The exhaustive proof also covers p=0, whose negative coefficient is -1.
"""
from pathlib import Path

import generate_cf_resample_lut as previous


def generate(work):
    work = Path(work)
    source = previous.generate(work)
    text = source.read_text()
    old = ''' smi %d3
 extb.l %d3
 eor.l %d3,%d2
 sub.l %d3,%d2
 lsl.l #5,%d2'''
    new = ''' smi %d3
 extb.l %d3
 lsl.l #5,%d2'''
    assert text.count(old) == 1
    text = text.replace(old, new, 1)
    old = ' movclr.l %acc0,%d2\n eor.l %d3,%d2\n'
    assert text.count(old) == 1
    text = text.replace(old, ' movclr.l %acc0,%d2\n', 1)
    target = work / 'source-resample-signed.s'
    target.write_text(text)
    return target

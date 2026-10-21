"""Opt-in Slap high-product EMAC path, retaining exact RNG and caller MAC state."""
import re
from pathlib import Path


def transform(work, source_path):
    text = Path(source_path).read_text()
    old = '#include "cf_math.h"'
    assert text.count(old) == 1
    text = text.replace(old, '#include "cf_render_math.h"', 1)
    old = 'ph=pk_cf_mul_hi_u32(ol,b)'
    assert text.count(old) == 1
    text = text.replace(old, 'ph=pk_cf_render_rng_hi(ol)', 1)
    marker = 'int pk_cf_slap_render('
    assert text.count(marker) == 2, 'Expected retained target and portable renderers'
    at = 0
    for _ in range(2):
        begin = text.index(marker, at)
        body = text.index('{', begin) + 1
        end, depth = body, 1
        while depth:
            depth += (text[end] == '{') - (text[end] == '}')
            end += 1
        value = text[body:end - 1]
        value, count = re.subn(r'\breturn\s+([^;]+);',
            r'{int result=(\1);pk_cf_render_math_end_saved(&math_context);return result;}', value)
        assert count >= 2
        value = '\n    volatile pk_cf_render_math_context math_context=pk_cf_render_math_begin();\n' + value
        text = text[:body] + value + text[end - 1:]
        at = body + len(value) + 1
    destination = Path(work) / 'slap-rng-emac.c'
    destination.write_text(text)
    return destination

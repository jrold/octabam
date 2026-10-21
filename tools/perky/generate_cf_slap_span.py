"""Candidate-only bounded generic Slap delay addressing on frozen PKFM20."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ASSEMBLY = ROOT / 'tools/harness/perky_cf/slap_span_delay.s'


def transform(work, source_path):
    text = Path(source_path).read_text()
    old = '    pk_cf_slap_delay_block(&ds,s+PK_CF_SLAP_RING_OFF,inner_block,n);'
    assert text.count(old) == 1
    text = text.replace(old, '    pk_cf_slap_delay_span(&ds,s+PK_CF_SLAP_RING_OFF,inner_block,n);', 1)
    marker = '#if defined(__mcoldfire__)\nint pk_cf_slap_render_c_delay('
    assert text.count(marker) == 1
    text = text.replace(marker,
        'extern void pk_cf_slap_delay_span(void*,uint8_t*,int32_t*,uint32_t);\n' + marker, 1)
    output = Path(work) / 'slap-generic-span.c'
    output.write_text(text)
    return output

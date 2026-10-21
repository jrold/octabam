"""Wavetable render in one assembly chunk (modules/perky/cf_wt_render.s).

The original C renderer stays, renamed pk_cf_wt_render_c, as the fallback the
assembly tail-calls for every case it does not prove up front (null tables,
an absent curve table, invalid wave views, n == 0 or n > 20). The C exports
its frequency factor table for the assembly; nothing else in it changes.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UNITS = (('pkenvblock', ROOT / 'modules/perky/cf_env_block.s'),
         ('pkwtfreq', ROOT / 'modules/perky/cf_wt_frequency_block.s'),
         ('pkwtrender', ROOT / 'modules/perky/cf_wt_render.s'))

ORIGINAL = 'int pk_cf_wt_render(uint8_t*s,int16_t*d,uint32_t n,const pk_cf_wt_tables*t){'
RENAMED = '''/* PKFM24: the assembly pk_cf_wt_render falls back to this original. */
const uint8_t *const pk_cf_wt_pe_factors=wt_pe_factors;
int pk_cf_wt_render_c(uint8_t*s,int16_t*d,uint32_t n,const pk_cf_wt_tables*t);
int pk_cf_wt_render_c(uint8_t*s,int16_t*d,uint32_t n,const pk_cf_wt_tables*t){'''


def transform(work, source_path):
    text = Path(source_path).read_text()
    assert text.count(ORIGINAL) == 1, 'WT render transform anchor changed'
    text = text.replace(ORIGINAL, RENAMED, 1)
    target = Path(work) / 'wavetable-render-asm.c'
    target.write_text(text)
    return target

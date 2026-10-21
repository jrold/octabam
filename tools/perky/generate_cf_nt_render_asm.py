"""Noise/Tone shared render in one assembly chunk (modules/perky/cf_nt_render.s).

The original C renderer stays, renamed pk_cf_nt_shared_render_c, as the
fallback the assembly tail-calls for every case it does not prove up front
(null pointers, n == 0 or n > 20, an absent curve table, a missing wave).
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UNITS = (('pkenvblock', ROOT / 'modules/perky/cf_env_block.s'),
         ('pkntrender', ROOT / 'modules/perky/cf_nt_render.s'))

ORIGINAL = 'int pk_cf_nt_shared_render(uint8_t*s,int16_t*d,uint32_t n,const pk_cf_nt_shared_tables*t,pk_cf_nt_rng*r){'
RENAMED = '''/* PKFM24: the assembly pk_cf_nt_shared_render falls back to this original. */
int pk_cf_nt_shared_render_c(uint8_t*s,int16_t*d,uint32_t n,const pk_cf_nt_shared_tables*t,pk_cf_nt_rng*r);
int pk_cf_nt_shared_render_c(uint8_t*s,int16_t*d,uint32_t n,const pk_cf_nt_shared_tables*t,pk_cf_nt_rng*r){'''


def transform(work, source_path):
    text = Path(source_path).read_text()
    assert text.count(ORIGINAL) == 1, 'NT render transform anchor changed'
    target = Path(work) / 'noise-tone-render-asm.c'
    target.write_text(text.replace(ORIGINAL, RENAMED, 1))
    return target

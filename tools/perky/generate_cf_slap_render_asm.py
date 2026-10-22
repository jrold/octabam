"""Slap chunk loops in assembly (modules/perky/cf_slap_render.s).

Applied after generate_cf_slap_env_asm. The ColdFire pk_cf_slap_render (the
span renderer with envelope segments) is renamed pk_cf_slap_render_c and
stays the fallback for every case the assembly does not take: more than 20 or
zero samples, a null argument or table, and a curve selector whose table is
absent. The assembly runs the same EMAC context, noise source and LCG,
filter block, envelope segments, envelope scale, delay span and velocity
saturation; filter, envelope block and delay span are the same callees.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UNITS = (('pkenvblock', ROOT / 'modules/perky/cf_env_block.s'),
         ('pkslaprender', ROOT / 'modules/perky/cf_slap_render.s'))

ORIGINAL = '''int pk_cf_slap_render(uint8_t*s,int16_t*d,uint32_t n,const pk_cf_fold_tables*t,pk_cf_fold_rng*rng){
    volatile pk_cf_render_math_context math_context=pk_cf_render_math_begin();

    uint32_t i,k;
    if(n>20u)'''
REPLACED = '''/* PKFM29: the exported pk_cf_slap_render is assembly (cf_slap_render.s), which
 * jumps here for every case it does not take. */
int pk_cf_slap_render_c(uint8_t*s,int16_t*d,uint32_t n,const pk_cf_fold_tables*t,pk_cf_fold_rng*rng);
int pk_cf_slap_render_c(uint8_t*s,int16_t*d,uint32_t n,const pk_cf_fold_tables*t,pk_cf_fold_rng*rng){
    volatile pk_cf_render_math_context math_context=pk_cf_render_math_begin();

    uint32_t i,k;
    if(n>20u)'''


def once(text, old, new):
    assert text.count(old) == 1, ('slap render transform anchor changed', old[:80])
    return text.replace(old, new, 1)


def transform(work, source_path):
    text = once(Path(source_path).read_text(), ORIGINAL, REPLACED)
    target = Path(work) / 'slap-render-asm.c'
    target.write_text(text)
    return target

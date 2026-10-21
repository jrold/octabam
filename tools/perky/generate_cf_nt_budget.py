"""Opt-in exact Noise/Tone block optimizations; original module stays pinned.

The filter consumes the same held noise twice per native sample. Its result
does not feed the oscillators or noise RNG, so it may run after filling the
noise block. Reuse the already qualified wrapping/clamping Slap assembly with
an explicit five-int32 temporary, rather than assuming the NT C struct ABI.
"""
import hashlib
from pathlib import Path

ORIGINAL_SHA256 = '7fd94294d0e3e41f74633da93def530927fcd3f96312191397f080ba09c3dfd4'


def generate(source, destination, *, assembly_filter=True, native20=True):
    source, destination = Path(source), Path(destination)
    assert hashlib.sha256(source.read_bytes()).hexdigest() == ORIGINAL_SHA256, 'Noise/Tone original drift'
    text = source.read_text()
    if native20:
        for before, after in (
            ('amplitudes[16];int16_t noise[16]', 'amplitudes[20];int16_t noise[20]'),
            ('n>16u?16u:n', 'n>20u?20u:n'),
        ):
            assert text.count(before) == 1, before
            text = text.replace(before, after, 1)
    if assembly_filter:
        start = text.index('static void __attribute__((noinline))\nnt_noise_filter_block(')
        end = text.index('\ntypedef struct{uint32_t phase,inc,cur,next;', start)
        original = text[start:end]
        fallback = original.replace('nt_noise_filter_block(', 'nt_noise_filter_block_c(', 1)
        replacement = '''/* Native temporary layout is deliberately independent of filt_fast. */
extern void pk_budget_slap_filter(void*,const int16_t*,int32_t*,unsigned);
static void __attribute__((noinline))
nt_noise_filter_block(uint8_t*s,int16_t*noise,uint32_t n,pk_cf_nt_rng*r){
    noise_fast nzs;
    int32_t filter[5],discard[20];
    if(n>20u){nt_noise_filter_block_c(s,noise,n,r);return;}
    noise_fast_init(s,0x60,&nzs);
    filter[0]=(int32_t)r16(s+0xaa);filter[1]=(int32_t)r16(s+0xa8);
    filter[2]=s32(r32(s+0xac));filter[3]=s32(r32(s+0xb0));filter[4]=s32(r32(s+0xb4));
    for(uint32_t i=0;i<n;i++)noise[i]=noise_fast_sample(&nzs,r);
    pk_budget_slap_filter(filter,noise,discard,n);
    noise_fast_store(s,0x60,&nzs);
    w32(s+0xac,u32(filter[2]));w32(s+0xb0,u32(filter[3]));w32(s+0xb4,u32(filter[4]));
}
'''
        text = text[:start] + '#if defined(__mcoldfire__)\n' + fallback + replacement + '#else\n' + original + '#endif\n' + text[end:]
    destination.write_text(text)
    return destination


def transform(work, source_path):
    """Build-hook API: existing retained budget transforms run first."""
    # The assembly-filter development variant regressed the combined layout.
    # Retain only native20 until a full-ISR measurement can justify another path.
    return generate(source_path, Path(work) / 'noise-tone-native20.c', assembly_filter=False)

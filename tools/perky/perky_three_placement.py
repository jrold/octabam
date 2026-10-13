"""Place hot kernels in private P and duplicate hot shared loops per core.

Cold init/control/pitch/RNG helpers have identical bytes in shared memory.
They never call private or core-specific P. Private P retains all stock FX
except the already-approved Plate/Compressor sacrifices. The geometry is
measured from the assembled program; failure to fit refuses the build.
"""
import all_fx_layout as L

COMMON = frozenset(('noise_tone_math.asm','simple_drum_delta.asm',
    'pk_multi_simple_init','pk_multi_fold_init','pk_multi_fold2_init',
    'fold_rng_glue','fold_drum2_seam.asm'))
PRIVATE_FAST = ('simple_drum_envelope.asm','simple_drum_oscillator.asm',
                'simple_drum_frequency.asm','pk_three_fold2_trigger')
PRIVATE_ENTRY = ('synth_seam_glue.asm','simple_drum_voice.asm')


def place(pieces, syms, tag, externals):
    size={n:b-a for n,a,b,_,_ in pieces}
    if 'pk_multi_complex_init' in size:
        import perky_four_placement
        return perky_four_placement.place(pieces, syms, tag, externals)
    common=COMMON | ({'pk_source_clock_prepare','pk_three_common_controls','pk_three_common_trigger'} if 'pk_source_clock_prepare' in size else set())
    private_fast=PRIVATE_FAST + (('pk_source_clock_finish',) if 'pk_source_clock_finish' in size else ())
    assert COMMON <= size.keys(), 'three-engine cold-helper census changed'
    owner=lambda a:next(n for n,lo,hi,_,_ in pieces if lo<=a<hi)
    for n,_,_,text,_ in pieces:
        if n in common:
            assert all(owner(syms[l]) in common for l in externals(text,syms)), ('shared helper calls core-owned P',n)
    # All cores are placed together so shared cold helpers cannot collide
    # with either core's copy of the renderer/control/return shards.
    dest={t:{} for t in ('A','B')}
    free=list(L.SAFE_SHARED_P_SPANS)
    for t in ('A','B'):
        local=L.local_p_spans(t)
        for names,span in ((private_fast,(local[0][0],local[0][1]-48)),(PRIVATE_ENTRY,local[1])):
            cursor=span[0]
            for name in names:
                assert cursor+size[name]<=span[1],(t,name,'private P overflow')
                dest[t][name]=cursor;cursor+=size[name]
        owned=[i for i,(lo,hi) in enumerate(free) if (lo<0x38000)==(t=='A')]
        remaining=set(size)-common-set(private_fast)-set(PRIVATE_ENTRY)
        for name in sorted(remaining,key=lambda n:(-size[n],n)):
            i=next((i for i in owned if free[i][0]+size[name]<=free[i][1]),None)
            if i is None:raise ValueError(f'{t} {name}: no owned P extent')
            lo,hi=free[i];dest[t][name]=lo;free[i]=(lo+size[name],hi)
    for name in sorted(common,key=lambda n:(-size[n],n)):
        i=next((i for i,(lo,hi) in enumerate(free) if lo+size[name]<=hi),None)
        if i is None:raise ValueError(f'{name}: common cold helpers do not fit')
        lo,hi=free[i]
        for t in ('A','B'):dest[t][name]=lo
        free[i]=(lo+size[name],hi)
    return dest[tag]

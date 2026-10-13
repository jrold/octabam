"""Place the four-engine profile within the existing PERKY3R donors.

Shared P is one physical memory: a common helper is one item, while each
core-owned renderer is a separate item restricted to that core's safe tails.
Use a deterministic exhaustive packer rather than treating gaps as contiguous.
"""
import all_fx_layout as L


def place(pieces, syms, tag, externals):
    import perky_three_placement as three
    size = {n:b-a for n,a,b,_,_ in pieces}
    common = three.COMMON | {'pk_source_clock_prepare', 'pk_three_common_controls',
                             'pk_three_common_trigger', 'pk_multi_complex_init'}
    fast = three.PRIVATE_FAST + ('pk_source_clock_finish',)
    entry = three.PRIVATE_ENTRY + ('pk_three_finish',)
    owner = lambda a: next(n for n,lo,hi,_,_ in pieces if lo<=a<hi)
    for n,_,_,text,_ in pieces:
        if n in common:
            assert all(owner(syms[x]) in common for x in externals(text,syms)), n
    dest = {t:{} for t in ('A','B')}
    for t in dest:
        local = L.local_p_spans(t)
        for names, (lo,hi) in ((fast,(local[0][0],local[0][1]-48)), (entry,local[1])):
            for n in names:
                assert lo+size[n]<=hi, (t,n,'private overflow')
                dest[t][n] = lo; lo += size[n]
    spans = L.SAFE_SHARED_P_SPANS
    owned = set(size)-common-set(fast)-set(entry)
    items = [(n,t,size[n]) for t in ('A','B') for n in owned]
    items += [(n,None,size[n]) for n in common]
    items.sort(key=lambda item:(-item[2], item[0], item[1] or ''))
    failed = set()
    def solve(k, cursors):
        if k == len(items): return []
        key = (k,tuple(cursors))
        if key in failed: return None
        name, core, words = items[k]
        options = [i for i,(a,b) in enumerate(spans) if cursors[i]+words<=b
                   and (core is None or (a<0x38000)==(core=='A'))]
        options.sort(key=lambda i:(spans[i][1]-cursors[i]-words,i))
        for i in options:
            lo = cursors[i]; trial = list(cursors); trial[i] += words
            suffix = solve(k+1,trial)
            if suffix is not None: return [(name,core,lo)]+suffix
        failed.add(key)
        return None
    answer = solve(0,[a for a,b in spans])
    if answer is None:
        raise ValueError(f'PERKY4 physical P placement failed: {sum(w for n,t,w in items)} words across {[b-a for a,b in spans]}')
    for name,core,lo in answer:
        for t in ((core,) if core else ('A','B')): dest[t][name] = lo
    return dest[tag]

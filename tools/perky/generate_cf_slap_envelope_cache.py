"""Probe-local Slap envelope-cache and rejected compiler experiments."""
from pathlib import Path

def slap_compiler_transform(work, source_path):
    text = Path(source_path).read_text()
    assert text.count('int pk_cf_slap_render(') == 2
    assert text.count('pk_budget_slap_filter(&fs,noise,filtered,n)') == 1
    text = ('#if defined(__mcoldfire__)\n'
            '#pragma GCC optimize ("no-unroll-loops", "no-split-loops", '
            '"no-tree-loop-distribute-patterns")\n'
            '#endif\n' + text)
    destination = Path(work) / 'slap-bounded-loops.c'
    destination.write_text(text)
    return destination


def slap_transform(work, source_path):
    """Cache only the bounded target renderer's envelope fields.

    Internal retriggers update the cached gate/value at the same sample. The
    long-block C fallback and its original per-sample envelope are retained.
    """
    text = Path(source_path).read_text()
    begin = text.index('static uint16_t slap_env(')
    end = text.index('/* --- shared 32-bit PRNG', begin)
    cached = text[begin:end]
    cached = cached.replace('static uint16_t slap_env(uint8_t*s,size_t b,',
                            'static uint16_t slap_env_cached(slap_env_cache*q,')
    cached = cached.replace('uint8_t st=s[b];int32_t v=s32(r32(s,b+0xc));',
                            'uint8_t st=q->st;int32_t v=q->value;')
    for offset, field in [('0x20', 'rate_up'), ('0x22', 'rate_dn')]:
        cached = cached.replace('r16(s,b+' + offset + ')', 'q->' + field)
    cached = cached.replace('w32(s,b+0xc,u32(v));', '')
    cached = cached.replace('w32(s,b+0xc,0);', '')
    for offset, field in [('0x10', 'f10'), ('7', 'f7'), ('6', 'f6'),
                          ('4', 'f4'), ('1', 'curve')]:
        cached = cached.replace('s[b+' + offset + ']', 'q->' + field)
    cached = cached.replace('s[b]', 'q->st')
    cached = cached.replace('    if(q->curve!=1',
                            '    q->value=v;\n    if(q->curve!=1', 1)
    assert 's[b' not in cached and 'w32(' not in cached and 'r16(' not in cached
    declaration = '''typedef struct {
    int32_t value;uint32_t hold;
    uint16_t rate_up,rate_dn;
    uint8_t st,curve,f4,f6,f7,f10,reset;
} slap_env_cache;
'''
    text = text[:end] + declaration + cached + text[end:]
    begin = text.index('int pk_cf_slap_render(', text.index('#if defined(__mcoldfire__)\nint pk_cf_slap_render_c_delay'))
    end = text.index('\n#else\nint pk_cf_slap_render(', begin)
    body = text[begin:end]
    marker = '    ns.count=r16(s,0x60);'
    assert body.count(marker) == 1
    body = body.replace(marker, '''    slap_env_cache env;
    env.value=s32(r32(s,0x80));env.hold=r32(s,0x84);
    env.rate_up=r16(s,0x94);env.rate_dn=r16(s,0x96);
    env.st=s[0x74];env.curve=s[0x75];env.f4=s[0x78];env.f6=s[0x7a];
    env.f7=s[0x7b];env.f10=s[0x84];env.reset=s[0x7c];
''' + marker, 1)
    assert body.count('            slap_retrigger(s);') == 1
    body = body.replace('            slap_retrigger(s);', '''            env.hold=(env.hold&0xffffff00u)|1u;env.f10=1u;env.st=1u;
            if(env.reset)env.value=0;''', 1)
    assert body.count('a=slap_env(s,0x74,t);') == 1
    body = body.replace('a=slap_env(s,0x74,t);', 'a=slap_env_cached(&env,t);', 1)
    marker = '    w16(s,0x60,ns.count);'
    assert body.count(marker) == 1
    body = body.replace(marker, '''    s[0x74]=env.st;w32(s,0x80,u32(env.value));w32(s,0x84,env.hold);
''' + marker, 1)
    destination = Path(work) / 'slap-envelope-cache.c'
    destination.write_text(text[:begin] + body + text[end:])
    return destination

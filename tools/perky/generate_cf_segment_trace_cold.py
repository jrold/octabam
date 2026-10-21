"""Keep diagnostic trace loops out of the normal segment register frame.

The diagnostic flag remains live and the original trace contents remain
available. Only enabled tracing calls the separate out-of-line helpers.
"""
from pathlib import Path


def transform(work, source_path):
    text = Path(source_path).read_text()
    marker = 'int placement_segment(unsigned tr,uint32_t start,uint32_t end,unsigned trace_half)\n'
    assert text.count(marker) == 1
    helpers = '''static void __attribute__((noinline)) placement_trace_empty(unsigned tr,unsigned half)
{
    for(unsigned i=0;i<24;i++)placement_trace[tr][half][i]=0;
}
static void __attribute__((noinline)) placement_trace_native(unsigned tr,unsigned half,
    const pk_cf_native_clock*c,unsigned have,unsigned need,unsigned n,const int16_t*data)
{
    placement_trace[tr][half][0]=(int32_t)c->phase;
    placement_trace[tr][half][1]=(int32_t)have;
    placement_trace[tr][half][2]=(int32_t)need;
    placement_trace[tr][half][3]=(int32_t)n;
    for(unsigned i=0;i<20;i++)placement_trace[tr][half][4+i]=i<need+have?data[i]:0;
}

'''
    text = text.replace(marker, helpers + marker, 1)
    old = 'if(!n){if(placement_trace_enabled)for(i=0;i<24;i++)placement_trace[tr][trace_half][i]=0;return 1;}'
    assert text.count(old) == 1
    text = text.replace(old, 'if(!n){if(placement_trace_enabled)placement_trace_empty(tr,trace_half);return 1;}', 1)
    old = '''    if(placement_trace_enabled) {
        placement_trace[tr][trace_half][0]=(int32_t)c->phase;
        placement_trace[tr][trace_half][1]=(int32_t)have;
        placement_trace[tr][trace_half][2]=(int32_t)need;
        placement_trace[tr][trace_half][3]=(int32_t)n;
        for(i=0;i<20;i++)placement_trace[tr][trace_half][4+i]=i<need+have?data[i]:0;
    }'''
    assert text.count(old) == 1
    text = text.replace(old, '    if(placement_trace_enabled)placement_trace_native(tr,trace_half,c,have,need,n,data);', 1)
    target = Path(work) / 'placement-cold-trace.c'
    target.write_text(text)
    return target

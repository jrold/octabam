"""Candidate-only exact WT oscillator assembly and pitch-envelope factor map."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ASSEMBLY = ROOT / 'tools/harness/perky_cf/wt_oscillator_block.s'


def once(text, old, new):
    assert text.count(old) == 1, (old, text.count(old))
    return text.replace(old, new, 1)


def factors():
    """All original u16 envelope values; low six bits cannot affect factor."""
    values = []
    for index in range(1024):
        pe = index << 6
        factor = (((pe & 8191) + 8192) >> (13 - (pe >> 13))) - 1
        assert 0 <= factor <= 255
        for remainder in range(64):
            value = pe + remainder
            assert factor == ((((value & 8191) + 8192) >> (13 - (value >> 13))) - 1)
        values.append(factor)
    return bytes(values)


def transform_text(text, *, oscillator=True, factor=True):
    if factor:
        table = 'static const uint8_t wt_pe_factors[1024]={\n' + ','.join(map(str, factors())) + '\n};\n'
        marker = 'static uint32_t wt_frequency_step(uint32_t f){'
        text = once(text, marker, table + marker)
        text = once(text, 'const uint32_t factor=((lo+0x2000u)>>sh)-1u;',
                    'const uint32_t factor=wt_pe_factors[pe>>6];')
        text = once(text, '        const uint32_t lo=pe&0x1fffu,sh=13u-(pe>>13);\n', '')
    if oscillator:
        marker = 'static int wt_render_chunk('
        helper = '''typedef struct {
    uint32_t phase,mix,velocity,target_mix;
    const uint8_t *wave,*secondary,*target_wave,*target_secondary;
    uint32_t changed,mute;
    int16_t *destination;
    const uint32_t *steps;
    const uint16_t *amplitudes;
    uint32_t count;
} wt_oscillator_context;
extern void pk_cf_wt_oscillator_block(wt_oscillator_context*);
'''
        text = once(text, marker, helper + marker)
        marker = '    wc=pk_cf_wt_wave(t,cur);sc=pk_cf_wt_wave(t,sec);\n    for(i=0;i<n;i++){'
        fast = '''    wc=pk_cf_wt_wave(t,cur);sc=pk_cf_wt_wave(t,sec);
    /* Prove every view valid before using the assembly block. Invalid target
     * views retain the original sample-by-sample partial-failure semantics. */
    if(n&&wc&&sc){
        const uint8_t *tw=wc,*ts=sc;
        if(cur!=target_cur){tw=pk_cf_wt_wave(t,target_cur);ts=pk_cf_wt_wave(t,target_sec);}
        if(tw&&ts){
            wt_oscillator_context c={phase,mix,velocity,target_mix,wc,sc,tw,ts,
                                     0,mute,d,steps,amplitudes,n};
            pk_cf_wt_oscillator_block(&c);
            phase=c.phase;mix=(uint16_t)c.mix;step=steps[n-1];
            if(c.changed&&cur!=target_cur){cur=target_cur;sec=target_sec;}
            goto wt_block_commit;
        }
    }
    for(i=0;i<n;i++){'''
        text = once(text, marker, fast)
        marker = '    w32(s,0xf4,phase);w32(s,0xf8,step);\n    w32(s,0x100,cur);'
        text = once(text, marker, 'wt_block_commit:\n' + marker)
    return text


def transform(work, source_path):
    """Apply after the admitted native20 transform; assembly must be linked."""
    target = Path(work) / 'wavetable-block-asm.c'
    target.write_text(transform_text(Path(source_path).read_text()))
    return target

"""Opt-in guarded fixed-tap delay after retained Slap block/filter transforms."""
from pathlib import Path


def transform(work, source_path):
    text = Path(source_path).read_text()
    before = '    pk_cf_slap_delay_block(&ds,s+PK_CF_SLAP_RING_OFF,inner_block,n);'
    assert text.count(before) == 1, 'Expected retained Slap block delay'
    assert text.count('    if(n)pk_budget_slap_filter(&fs,noise,filtered,n);') == 1, 'Expected retained filter clamp before envelope'
    text = text.replace(before, '    pk_cf_slap_delay_fixed_dispatch(&ds,s+PK_CF_SLAP_RING_OFF,inner_block,n);', 1)
    marker = '#if defined(__mcoldfire__)\nint pk_cf_slap_render_c_delay('
    assert text.count(marker) == 1, 'Expected retained bounded Slap fallback'
    helper = '''#if defined(__mcoldfire__)
/* Each input is (clamped_filter_first * uint16_envelope)>>16. It is in
 * [-32767,32766] for every history/control, including the first sample.
 * The assembly dispatcher reloads every tap pair before its tail call. */
extern void pk_cf_slap_delay_fixed_dispatch(void*,uint8_t*,int32_t*,uint32_t);
#endif
'''
    text = text.replace(marker, helper + marker, 1)
    destination = Path(work) / 'slap-guarded-fixed-delay.c'
    destination.write_text(text)
    return destination

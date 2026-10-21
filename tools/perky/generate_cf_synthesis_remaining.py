"""Probe-local remaining CF synthesis candidates; no frozen inputs are changed.

The native 48-to-44.1 kHz adapter can request nineteen samples per OT block.
Resonant's sixteen-sample internal chunks then repeat cached-state setup.
Changing only the bounded temporary capacity retains every recurrence's order.
"""
from pathlib import Path


def resonant_transform(work, source_path):
    text = Path(source_path).read_text()
    old = 'int32_t drive[16],acc[16],level[16];'
    assert text.count(old) == 2, 'Expected both frozen Resonant chunk buffers'
    text = text.replace(old, 'int32_t drive[20],acc[20],level[20];')
    old = 'uint32_t count=n>16u?16u:n;'
    assert text.count(old) == 2, 'Expected both frozen Resonant chunk limits'
    text = text.replace(old, 'uint32_t count=n>20u?20u:n;')
    destination = Path(work) / 'resonant-native20.c'
    destination.write_text(text)
    return destination

"""Emit the exact update for HW4's explicitly frozen Karplus controls.

The audition has no live Karplus control transport. This specialization is valid
only when all four captured histories are fixed points for the captured targets,
and first/active original objects agree with the complete update model. Changing
that policy requires a runtime smoother/transport, not more constants here.
"""
from pathlib import Path
import hashlib
import json
import os
import struct
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'modules/perky'), str(ROOT/'tools/perky')]
import hw4_control_update as update
import karplus_compact as compact
from extract_noise_tone_tables import find_m7, parse_container

CONTROL_WORDS = (7, 12, 13, 18, 25, 27, 28)
FIRMWARE_SHA = 'adcdbc4a2c660ffb6477f202211ae3cb70170bfe6ddfaecc3df0e4cb7db398c6'


def context_values(case, phase, firmware=None):
    firmware = Path(firmware or os.environ.get('PERKONS_FIRMWARE',
        str(Path.home()/'Downloads/perkons_both_v1.2.1-0-gbcccfd0.img')))
    blob = firmware.read_bytes()
    if hashlib.sha256(blob).hexdigest() != FIRMWARE_SHA:
        raise RuntimeError('Karplus prepared update requires pinned v1.2.1 firmware')
    manifest = json.loads((case.parent/'manifest.json').read_text())
    if manifest['firmware_sha256'] != FIRMWARE_SHA:
        raise RuntimeError('Karplus update fixture firmware drift')
    m7 = find_m7(parse_container(blob)[1])
    pitch, chromatic = m7.read(0x080202a0, 8192), m7.read(0x08030ecc, 24)
    pre, post = {
        'first_trigger': ('wrapper-window-trigger-only.bin', 'wrapper-window-before.bin'),
        'active_retrigger': ('wrapper-window-retrigger-only.bin', 'wrapper-window-retrigger-before.bin'),
    }[phase]
    paths = (case/pre, case/post, case/(pre+'.targets.bin'))
    for path in paths:
        if hashlib.sha256(path.read_bytes()).hexdigest() != manifest['files'][str(path.relative_to(case.parent))]:
            raise RuntimeError(f'Karplus prepared update capture drift: {path}')
    raw = paths[0].read_bytes()[0x2908:0x39e8]
    want = paths[1].read_bytes()[0x2908:0x39e8]
    targets = struct.unpack('<4I', paths[2].read_bytes())
    got = update.karplus_update(raw, targets, pitch, chromatic)
    if got != want:
        raise RuntimeError('Karplus complete update does not match ARM')
    fixed = all(update.u32(got, 0x1c+4*i) == update.u32(raw, 0x1c+4*i) for i in range(4))
    before = compact.Karplus.from_arm(raw)
    after = compact.Karplus.from_arm(got)
    changed = {i for i, (a, b) in enumerate(zip(before.words, after.words)) if a != b}
    if changed - set(CONTROL_WORDS) or before.ring != after.ring:
        raise RuntimeError('Karplus prepared update writes outside proven control fields')
    return tuple(after.words[i] for i in CONTROL_WORDS), fixed


def prepared_values(case, firmware=None):
    """Shipping specialization: reject any unsettled history or phase drift."""
    first, fixed_first = context_values(case, 'first_trigger', firmware)
    active, fixed_active = context_values(case, 'active_retrigger', firmware)
    if not fixed_first or not fixed_active:
        raise RuntimeError('Karplus audition requires frozen, settled control history')
    if first != active:
        raise RuntimeError('Karplus frozen control values differ at retrigger')
    return first


def emit_routine(values, label='pk_karplus_apply_prepared'):
    if len(values) != len(CONTROL_WORDS) or any(not 0 <= v <= 0xffff for v in values):
        raise ValueError('invalid prepared Karplus controls')
    lines = [label+':']
    for word, value in zip(CONTROL_WORDS, values):
        lines += [f'        move #>${value:06x},a', f'        move a1,x:(r6+${word:x})']
    return '\n'.join(lines)+'\n        rts\n'

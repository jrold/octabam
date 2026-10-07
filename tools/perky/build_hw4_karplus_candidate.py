#!/usr/bin/env python3
"""Add an exact fixed-state Karplus V3 path to the static HW4 audition source.

The first hardware audition deliberately freezes V3's live knobs at one real
v1.2.1 ARM control state.  Its renderer, first trigger and active retrigger are
still exact.  No Karplus browser row is exposed yet.

Requires local, ignored qualification inputs:
  out/perky/karplus-trigger-plan.json
  out/perky/engine-fixtures/engine-9-mode-2-corner-1/...

The selected fixture is panel mode 2 / mid controls.  The production builder
accepts only a zero-initialized 2K delay ring and an AMP envelope shape that can
use the authentic envelope-1 table already carried by the PERKY4 payload.
"""
from pathlib import Path
import json
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'modules/perky'), str(ROOT / 'tools/perky')]

import build_hw4_candidate as hw4
import build_karplus_source as karplus_source
import build_noise_tone_synth_source as noise
import hw4_memory as memory
import karplus_compact as compact
import karplus_trigger_plan_source as trigger

OUT = ROOT / 'out/perky/hw4-karplus-candidate'
PLAN = ROOT / 'out/perky/karplus-trigger-plan.json'
CASE = ROOT / 'out/perky/engine-fixtures/engine-9-mode-2-corner-1'
ARM_OFFSET = 0x2908
ARM_SIZE = 0x10E0
RING_Y = 0x1000
ENGINE = 8
ENGINE_MARKER = 0x0E
TRIGGERED_WORD = 0x20              # first free overlay word after 32-word state
RNG_X = 0x38E8
SCRATCH = memory.SCRATCH_BASE
RNG_SCRATCH = SCRATCH + 0x72


def once(text, old, new, what):
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f'{what}: expected one anchor, found {count}')
    return text.replace(old, new, 1)


def fixture_voice():
    path = CASE / 'wrapper-window-pre-trigger.bin'
    if not path.exists():
        raise FileNotFoundError(
            f'Karplus ARM fixture missing: {path}; regenerate the pinned v1.2.1 engine corpus'
        )
    blob = path.read_bytes()[ARM_OFFSET:ARM_OFFSET + ARM_SIZE]
    if len(blob) != ARM_SIZE:
        raise RuntimeError(f'short Karplus state in {path}')
    voice = compact.Karplus.from_arm(blob)
    if any(voice.ring):
        changed = [i for i, value in enumerate(voice.ring) if value][:16]
        raise RuntimeError(
            'Karplus first-audition ring is not zero-initialized; boot-time zero-fill is not exact '
            f'(first nonzero indices {changed})'
        )
    shape = voice.words[compact.AMP_ENV + 1]
    if shape not in (0, 1):
        raise RuntimeError(
            f'Karplus audition AMP envelope shape is {shape}; HW4 currently carries exact linear/envelope-1 only'
        )
    return voice


def sync_rng_in():
    lines = ['pk_hw4_karplus_rng_in:']
    for i in range(4):
        lines += [f'        move x:>${RNG_X+i:04x},a', f'        move a1,x:>${RNG_SCRATCH+i:04x}']
    lines += ['        rts']
    return '\n'.join(lines) + '\n'


def sync_rng_out():
    lines = ['pk_hw4_karplus_rng_out:']
    for i in range(4):
        lines += [f'        move x:>${RNG_SCRATCH+i:04x},a', f'        move a1,x:>${RNG_X+i:04x}']
    lines += ['        rts']
    return '\n'.join(lines) + '\n'


def init_source(words):
    lines = [
        'pk_hw4_karplus_init:',
        '        move x:>$418,a',
        '        lsr #$5,a',
        '        move a1,n1',
        '        move #>$38ee,r1',
        '        move x:(r1+n1),b',
        f'        cmp #>${ENGINE_MARKER:x},b',
        '        beq pkh4k_initialized',
        f'        move #>${ENGINE_MARKER:x},a',
        '        move a1,x:(r1+n1)',
        '        move r6,r1',
        '        clr a',
        '        do #>$3a,pkh4k_zero',
        '        move a1,x:(r1)+',
        'pkh4k_zero:',
        '        nop',
    ]
    for i, value in enumerate(words):
        if value:
            lines += [f'        move #>${value & 0xffff:06x},a', f'        move a1,x:(r6+${i:x})']
    lines += [
        f'        clr a',
        f'        move a1,x:(r6+${TRIGGERED_WORD:x})',
        'pkh4k_initialized:',
        '        rts',
    ]
    return '\n'.join(lines) + '\n'


def entry_source():
    return f'''pks_karplus_entry:
        jsrl pk_hw4_karplus_init
        move #>$10,a
        move a1,x:>$38ec
        move x:(r4+$3),a
        and #>$ffff,a
        tst a
        beq pkh4k_event_ready
        move x:>$20c,a
        tst a
        blt pkh4k_event_ready
        cmp #>$10,a
        bge pkh4k_event_ready
        move a1,x:>$38ec
pkh4k_event_ready:
        move x:>$38ec,a
        cmp #>$10,a
        beq pkh4k_full
        tst a
        beq pkh4k_retrigger
        move a1,n7
        jsrl pk_hw4_karplus_render
pkh4k_retrigger:
        move x:(r6+${TRIGGERED_WORD:x}),a
        tst a
        bne pkh4k_active_trigger
        move #>${SCRATCH:04x},r5
        jsrl pk_karplus_trigger_first
        move #>$1,a
        move a1,x:(r6+${TRIGGERED_WORD:x})
        bra pkh4k_after_trigger
pkh4k_active_trigger:
        move #>${SCRATCH:04x},r5
        jsrl pk_karplus_trigger_active
pkh4k_after_trigger:
        move #>$10,a
        move x:>$38ec,x0
        sub x0,a
        move a1,n7
        jsrl pk_hw4_karplus_render
        bra pks_continue
pkh4k_full:
        move #>$10,n7
        jsrl pk_hw4_karplus_render
        bra pks_continue

pk_hw4_karplus_render:
        move n7,x:>${SCRATCH+0x7d:04x}
        jsrl pk_hw4_karplus_rng_in
        move #>${SCRATCH:04x},r5
        move #>${RING_Y:04x},r4
        move x:>${SCRATCH+0x7d:04x},n7
        jsrl pk_karplus_voice
        jsrl pk_hw4_karplus_rng_out
        rts
'''


def build(out: Path = OUT):
    voice = fixture_voice()
    _plan, plans = trigger.load_plan(PLAN)
    source, _ = hw4.build(out)

    # Exact engine 8 dispatch; hidden from the stable browser for this audition.
    anchor = '''        cmp #>$3,a
        beq pks_fold2_entry
        cmp #>$2,a'''
    replacement = '''        cmp #>$3,a
        beq pks_fold2_entry
        cmp #>$8,a
        beq pks_karplus_entry
        cmp #>$2,a'''
    source = once(source, anchor, replacement, 'Karplus dispatcher')
    source = once(source, 'pks_fold2_entry:\n', entry_source() + 'pks_fold2_entry:\n', 'Karplus production entry')

    # Production Karplus shares the common u32 math helpers already present in
    # the PERKY source.  Its captured AMP shape is restricted above to 0/1, so
    # repoint envelope-1 at the authentic direct-packed table carried at C50.
    karplus = karplus_source.source(include_math=False)
    karplus = karplus.replace('#>$0009a5,r1', '#>$000c50,r1')
    source += '\n' + karplus
    source += '\n' + sync_rng_in() + sync_rng_out()
    source += '\n' + init_source(voice.words)
    source += '\n' + trigger.emit_routine(
        plans['first_trigger'], label='pk_karplus_trigger_first',
        snapshot_reg='r5', snapshot_address=SCRATCH, prefix='kh4f')
    source += '\n' + trigger.emit_routine(
        plans['active_retrigger'], label='pk_karplus_trigger_active',
        snapshot_reg='r5', snapshot_address=SCRATCH, prefix='kh4a')

    source = noise.force_long_local_jsr(noise.relativize_local_conditionals(source))
    labels = re.findall(r'(?m)^([A-Za-z0-9_]+):', source)
    dup = sorted({name for name in labels if labels.count(name) > 1})
    if dup:
        raise RuntimeError('duplicate DSP labels: ' + ', '.join(dup))
    for i, left in enumerate(labels):
        for right in labels[i+1:]:
            if left.startswith(right) or right.startswith(left):
                raise RuntimeError(f'DSP assembler prefix collision: {left}/{right}')

    # Tell the image injector to seed the exact zero ring at boot.  This is only
    # emitted after the ARM fixture above proved the selected pre-trigger ring is zero.
    layout_path = out / 'layout.json'
    layout = json.loads(layout_path.read_text())
    layout['extra_y_init'] = [{
        'name': 'karplus-ring', 'base_word': RING_Y,
        'words': compact.RING_LEN, 'fill': 0,
    }]
    layout['hw4_fixed_engines'] = {'T1': 0, 'T2': 8, 'T5': 3, 'T6': 10}
    layout['karplus_fixture'] = {
        'engine': 9, 'panel_mode': 2, 'corner': 1,
        'amp_shape': voice.words[compact.AMP_ENV + 1],
        'ring_initialization': 'zero verified against local ARM fixture',
    }
    layout_path.write_text(json.dumps(layout, indent=2) + '\n')

    out.mkdir(parents=True, exist_ok=True)
    (out / 'hw4-karplus.asm').write_text(source)
    print('HW4 Karplus production candidate: composed')
    print('  T2/V3 engine 8; exact first/retrigger plans; fixed authentic mid-control state')
    print(f'  ring Y:${RING_Y:04x}..${RING_Y + compact.RING_LEN - 1:04x}; boot zero verified by ARM fixture')
    return source


if __name__ == '__main__':
    build()

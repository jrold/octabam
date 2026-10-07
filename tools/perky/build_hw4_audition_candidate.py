#!/usr/bin/env python3
"""Compose the first four-voice HW4 hardware-audition DSP candidate.

Audition engines are deliberately one authentic family per logical PĒRKONS
voice before we attempt the complete 12-algorithm browser:

  T1 / V1 -> Fold Drum 1
  T2 / V3 -> Karplus
  T5 / V2 -> Fold Drum 2
  T6 / V4 -> Noise / Tone

The HW4 ColdFire profile forces those engine ids.  Fold1/Fold2/Noise-Tone keep
their existing production paths.  Karplus adds its exact renderer, separate
ARM-derived first/active trigger plans, an authentic pre-trigger compact state,
the two firmware envelope curves and one 2K delay ring.

This builder emits source/assets only.  It does not make a flashable updater;
image placement and hardware gates remain separate and must consume the layout
metadata written here.
"""
from __future__ import annotations

from pathlib import Path
import hashlib
import json
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'modules/perky'), str(ROOT / 'tools/perky')]

import build_hw4_candidate as base
import build_karplus_source as karplus_source
import build_noise_tone_payload as packed
import build_noise_tone_synth_source as synth
import hw4_memory as memory
import karplus_compact as karplus
import karplus_trigger_plan_source as trigger
import karplus_prepared_update_source as control_update
import simple_drum_tables as tables

OUT = ROOT / 'out/perky/hw4-audition'
PLAN = ROOT / 'out/perky/karplus-trigger-plan.json'
FIX = ROOT / 'out/perky/engine-fixtures'
ASSETS = ROOT / 'out/perky/simple-drum-assets'
KARPLUS_CASE = FIX / 'engine-9-mode-1-corner-1'
STATE_FILE = KARPLUS_CASE / 'wrapper-window-pre-trigger.bin'
ARM_STATE_OFFSET = 0x2908
ARM_STATE_SIZE = 0x10E0


def once(source: str, old: str, new: str, what: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f'{what}: expected one anchor, found {count}')
    return source.replace(old, new, 1)


def words24(path: Path, values: list[int]) -> dict:
    values = [int(v) & 0xFFFFFF for v in values]
    path.write_bytes(packed.words24_bytes(values))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {'file': path.name, 'words': len(values), 'sha256': digest}


def authentic_karplus() -> karplus.Karplus:
    if not STATE_FILE.exists():
        raise FileNotFoundError(
            f'{STATE_FILE} missing; regenerate the pinned v1.2.1 all-engine fixture corpus'
        )
    blob = STATE_FILE.read_bytes()
    raw = blob[ARM_STATE_OFFSET:ARM_STATE_OFFSET + ARM_STATE_SIZE]
    if len(raw) != ARM_STATE_SIZE:
        raise RuntimeError(f'{STATE_FILE}: short Karplus state slice')
    return karplus.Karplus.from_arm(raw)


def emit_init(words: list[int]) -> str:
    if len(words) != karplus.WORDS:
        raise RuntimeError(f'Karplus compact init has {len(words)} words')
    source = '''
pk_multi_karplus_init:
        move    x:>$418,a
        lsr     #$5,a
        move    a1,n1
        move    #>$38ee,r1
        move    x:(r1+n1),b
        cmp     #>$8,b
        beq     pkk_init_done
        move    #>$8,a
        move    a1,x:(r1+n1)
        move    r6,r1
        clr     a
        do      #>$3a,pkk_init_zero
        move    a1,x:(r1)+
pkk_init_zero:
        nop
'''
    for i, value in enumerate(words):
        if value:
            source += (
                f'        move    #>${value & 0xffff:06x},a\n'
                f'        move    a1,x:(r6+${i:x})\n'
            )
    source += 'pkk_init_done:\n        rts\n'
    return source


def build(out: Path = OUT, assets: Path = ASSETS):
    memory.validate()
    _plan, plans = trigger.load_plan(PLAN)
    voice = authentic_karplus()

    for name in ('envelope1.bin', 'envelope2.bin'):
        if not (assets / name).exists():
            raise FileNotFoundError(
                f'{assets / name} missing; run the authentic Simple Drum asset extractor first'
            )

    source, fold2_words = base.build(out)

    source = once(
        source,
        '        cmp #>$3,a\n        beq pks_fold2_entry\n        cmp #>$2,a',
        '        cmp #>$3,a\n        beq pks_fold2_entry\n'
        '        cmp #>$8,a\n        beq pks_karplus_entry\n'
        '        cmp #>$2,a',
        'HW4 Karplus dispatcher',
    )

    ksource = karplus_source.source(include_math=False)
    ksource = ksource.replace(
        '#>$0009a5,r1', f'#>${memory.KARPLUS_ENV1_BASE:06x},r1'
    ).replace(
        '#>$000c51,r1', f'#>${memory.KARPLUS_ENV2_BASE:06x},r1'
    )
    source += '\n' + control_update.emit_routine(control_update.prepared_values(KARPLUS_CASE))
    # Keep the return branch near pks_continue; long negative BRA literals
    # are not accepted by this assembler. Use the established relative form.
    source = once(source, 'pks_fold2_entry:\n',
                  (ROOT / 'modules/perky/karplus_seam.asm').read_text() + '\npks_fold2_entry:\n',
                  'HW4 Karplus entry placement')
    source += '\n' + ksource
    source += '\n' + trigger.emit_routine(
        plans['first_trigger'],
        label='pk_karplus_trigger_first',
        frozen='r5',
        snapshot_address=memory.KARPLUS_SHADOW_BASE,
        prefix='kh4f',
    )
    source += '\n' + trigger.emit_routine(
        plans['active_retrigger'],
        label='pk_karplus_trigger_active',
        frozen='r5',
        snapshot_address=memory.KARPLUS_SHADOW_BASE,
        prefix='kh4a',
    )
    source += '\n' + emit_init(voice.words)
    source = synth.force_long_local_jsr(synth.relativize_local_conditionals(source))

    out.mkdir(parents=True, exist_ok=True)
    (out / 'hw4-audition.asm').write_text(source)

    env1 = list(struct.unpack('<1025H', (assets / 'envelope1.bin').read_bytes()[:2050]))
    env2 = list(struct.unpack('<1025H', (assets / 'envelope2.bin').read_bytes()[:2050]))
    env1_words = tables.pack_u16(env1)
    env2_words = tables.pack_u16(env2)
    if len(env1_words) != memory.KARPLUS_ENV_PACKED_WORDS:
        raise RuntimeError(f'Karplus env1 packed to {len(env1_words)} words')
    if len(env2_words) != memory.KARPLUS_ENV_PACKED_WORDS:
        raise RuntimeError(f'Karplus env2 packed to {len(env2_words)} words')

    e1 = words24(out / 'karplus-envelope1.bin', env1_words)
    e2 = words24(out / 'karplus-envelope2.bin', env2_words)
    ring = words24(out / 'karplus-ring.bin', voice.ring)
    if ring['words'] != memory.KARPLUS_RING_WORDS:
        raise RuntimeError(f'Karplus ring has {ring["words"]} words')

    layout_path = out / 'layout.json'
    layout = json.loads(layout_path.read_text())
    layout['hw4_audition'] = {
        'engines': {'T1': 0, 'T2': 8, 'T5': 3, 'T6': 10},
        'karplus_fixture': str(STATE_FILE.relative_to(ROOT)),
        'karplus_state_words': karplus.WORDS,
        'karplus_triggered_overlay_word': memory.KARPLUS_TRIGGERED_WORD,
        'karplus_trigger_snapshot': {
            'base_word': memory.KARPLUS_SHADOW_BASE,
            'words': memory.KARPLUS_SHADOW_WORDS,
        },
    }
    layout['extra_y_init'] = [
        {'base_word': memory.KARPLUS_ENV1_BASE, **e1,
         'purpose': 'Karplus envelope curve 1, direct packed u16'},
        {'base_word': memory.KARPLUS_ENV2_BASE, **e2,
         'purpose': 'Karplus envelope curve 2, direct packed u16'},
        {'base_word': memory.KARPLUS_RING_BASE, **ring,
         'purpose': 'Karplus authentic pre-trigger 2K delay ring'},
    ]
    layout_path.write_text(json.dumps(layout, indent=2) + '\n')

    print('HW4 audition DSP: T1 Fold1; T2 Karplus; T5 Fold2; T6 Noise/Tone')
    print(
        f'Karplus Y: env1 ${memory.KARPLUS_ENV1_BASE:04x}, '
        f'env2 ${memory.KARPLUS_ENV2_BASE:04x}, '
        f'ring ${memory.KARPLUS_RING_BASE:04x}..${memory.KARPLUS_RING_END - 1:04x}'
    )
    print('Karplus controls: authentic fixed middle-corner fixture for first audition')
    return source, fold2_words


if __name__ == '__main__':
    build()

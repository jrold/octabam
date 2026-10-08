#!/usr/bin/env python3
"""Compose the four-voice HW4 hardware-audition DSP candidate.

Audition engines remain one authentic family per logical PĒRKONS voice:

  T1 / V1 -> Fold Drum 1
  T2 / V3 -> Karplus
  T5 / V2 -> Fold Drum 2
  T6 / V4 -> Noise / Tone

The HW4 ColdFire profile forces those engine ids. Fold1/Fold2 keep their
qualified production paths. Karplus combines its exact renderer, separate
ARM-derived first/active trigger plans, authentic compact/ring state and live
TUNE/DECAY/EDGE/TWANG/MODE transport. Its nonlinear transforms are exact
128-position Octatrack-domain tables generated from the recovered original
v1.2.1 update law; control changes are endpoint-exact and immediate for p-locks.

Noise/Tone is the remaining control/asset transport target. Its authentic
shared and Waveform2 renderers are already separately ARM-qualified.

This builder emits source/assets only. It does not by itself make a flashable
updater; image placement and hardware gates consume the layout metadata here.
"""
from __future__ import annotations

from pathlib import Path
import hashlib
import json
import os
import shutil
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'modules/perky'), str(ROOT / 'tools/perky')]

import build_hw4_candidate as base
import build_karplus_control_tables as karplus_controls
import build_karplus_source as karplus_source
import build_noise_tone_payload as packed
import build_noise_tone_synth_source as synth
import hw4_memory as memory
import karplus_compact as karplus
import karplus_trigger_plan_source as trigger
import simple_drum_tables as tables

OUT = ROOT / 'out/perky/hw4-audition'
PLAN = ROOT / 'out/perky/karplus-trigger-plan.json'
FIX = ROOT / 'out/perky/engine-fixtures'
ASSETS = ROOT / 'out/perky/simple-drum-assets'
CONTROL_ASSETS = ROOT / 'out/perky/karplus-live-control'
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


def _regenerate_control_assets() -> None:
    firmware = Path(os.environ.get(
        'PERKONS_FIRMWARE',
        str(Path.home() / 'Downloads/perkons_both_v1.2.1-0-gbcccfd0.img'),
    )).expanduser()
    if not firmware.exists():
        raise FileNotFoundError(
            f'pinned firmware not found at {firmware}; run '
            'tools/perky/build_karplus_control_tables.py --firmware <v1.2.1.img>'
        )
    karplus_controls.build(firmware, CONTROL_ASSETS, FIX)


def ensure_control_assets() -> dict:
    """Load or locally regenerate exact OT-domain Karplus control LUTs."""
    manifest_path = CONTROL_ASSETS / 'manifest.json'
    if not manifest_path.exists():
        _regenerate_control_assets()

    report = json.loads(manifest_path.read_text())
    if report.get('schema') != 'octabam.perky.karplus-live-control.v2':
        # An older local v1 manifest is expected after the 4096->128 compaction.
        # Regenerate from pinned evidence rather than asking the user to clean out/.
        _regenerate_control_assets()
        report = json.loads(manifest_path.read_text())
    if report.get('schema') != 'octabam.perky.karplus-live-control.v2':
        raise RuntimeError('Karplus control-table manifest schema drift')
    if report.get('mode_map') != [1, 0, 2]:
        raise RuntimeError('Karplus physical MODE map drift')
    if report.get('lookup_index') != 'prepared >> 5':
        raise RuntimeError('Karplus OT-domain lookup-index contract drift')

    expected = {
        'tune-delay': memory.KARPLUS_TUNE_DELAY_BASE,
        'decay-rate': memory.KARPLUS_DECAY_RATE_BASE,
        'edge-coeff': memory.KARPLUS_EDGE_COEFF_BASE,
    }
    tables_by_name = {row['name']: row for row in report.get('tables', [])}
    if set(tables_by_name) != set(expected):
        raise RuntimeError(f'Karplus control-table set drift: {sorted(tables_by_name)}')
    for name, base in expected.items():
        row = tables_by_name[name]
        if int(row['base_word']) != base:
            raise RuntimeError(
                f'Karplus {name} base ${int(row["base_word"]):04x} != ${base:04x}'
            )
        if int(row['entries']) != memory.KARPLUS_CONTROL_LUT_ENTRIES:
            raise RuntimeError(f'Karplus {name} entry-count drift')
        if int(row['words']) != memory.KARPLUS_CONTROL_LUT_WORDS:
            raise RuntimeError(f'Karplus {name} packed-word geometry drift')
        path = CONTROL_ASSETS / row['file']
        raw = path.read_bytes()
        if len(raw) != int(row['words']) * 3:
            raise RuntimeError(f'Karplus {name} packed payload size drift')
        if hashlib.sha256(raw).hexdigest() != row['sha256']:
            raise RuntimeError(f'Karplus {name} payload hash drift')

    if int(report.get('y_end_exclusive', -1)) != memory.HW4_Y_END:
        raise RuntimeError('Karplus control-table Y end disagrees with HW4 memory plan')
    return report


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
    control_report = ensure_control_assets()
    control_rows = {row['name']: row for row in control_report['tables']}

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

    control_source = (ROOT / 'modules/perky/karplus_control_seam.asm').read_text()
    control_source = control_source.replace(
        '@K_TUNE_LUT@', f'${memory.KARPLUS_TUNE_DELAY_BASE:06x}'
    ).replace(
        '@K_DECAY_LUT@', f'${memory.KARPLUS_DECAY_RATE_BASE:06x}'
    ).replace(
        '@K_EDGE_LUT@', f'${memory.KARPLUS_EDGE_COEFF_BASE:06x}'
    ).replace(
        '@K_GATE_THRESHOLD@', f'${int(control_report["gate_threshold"]):06x}'
    )
    if '@K_' in control_source:
        raise RuntimeError('unresolved Karplus live-control source placeholder')

    source += '\n' + (ROOT / 'modules/perky/karplus_seam.asm').read_text()
    source += '\n' + control_source
    source += '\n' + ksource
    source += '\n' + trigger.emit_routine(
        plans['first_trigger'],
        label='pk_karplus_trigger_first',
        snapshot_reg='r5',
        snapshot_address=memory.KARPLUS_SHADOW_BASE,
        prefix='kh4f',
    )
    source += '\n' + trigger.emit_routine(
        plans['active_retrigger'],
        label='pk_karplus_trigger_active',
        snapshot_reg='r5',
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

    live_assets: list[dict] = []
    for name in ('tune-delay', 'decay-rate', 'edge-coeff'):
        row = dict(control_rows[name])
        src = CONTROL_ASSETS / row['file']
        dst = out / row['file']
        shutil.copyfile(src, dst)
        if hashlib.sha256(dst.read_bytes()).hexdigest() != row['sha256']:
            raise RuntimeError(f'copied Karplus {name} payload hash drift')
        live_assets.append(row)

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
        'karplus_controls': {
            'status': 'live exact OT-domain controls; immediate p-lock changes',
            'parameters': ['TUNE', 'DECAY', 'EDGE', 'TWANG', 'MODE'],
            'mode_map': control_report['mode_map'],
            'lookup_entries': memory.KARPLUS_CONTROL_LUT_ENTRIES,
            'lookup_index': control_report['lookup_index'],
            'gate_threshold': control_report['gate_threshold'],
            'attack_rate': control_report['attack_rate'],
            'transition_smoothing': 'not emulated; exact final state applied immediately',
        },
    }
    layout['extra_y_init'] = [
        {'base_word': memory.KARPLUS_ENV1_BASE, **e1,
         'purpose': 'Karplus envelope curve 1, direct packed u16'},
        {'base_word': memory.KARPLUS_ENV2_BASE, **e2,
         'purpose': 'Karplus envelope curve 2, direct packed u16'},
        {'base_word': memory.KARPLUS_RING_BASE, **ring,
         'purpose': 'Karplus authentic pre-trigger 2K delay ring'},
        {'base_word': memory.KARPLUS_TUNE_DELAY_BASE, **live_assets[0],
         'purpose': 'Karplus exact OT TUNE -> delay lookup'},
        {'base_word': memory.KARPLUS_DECAY_RATE_BASE, **live_assets[1],
         'purpose': 'Karplus exact OT DECAY -> envelope rate lookup'},
        {'base_word': memory.KARPLUS_EDGE_COEFF_BASE, **live_assets[2],
         'purpose': 'Karplus exact OT EDGE -> filter coefficient lookup'},
    ]
    layout_path.write_text(json.dumps(layout, indent=2) + '\n')

    print('HW4 audition DSP: T1 Fold1; T2 Karplus; T5 Fold2; T6 Noise/Tone')
    print(
        f'Karplus Y: env1 ${memory.KARPLUS_ENV1_BASE:04x}, '
        f'env2 ${memory.KARPLUS_ENV2_BASE:04x}, '
        f'ring ${memory.KARPLUS_RING_BASE:04x}..${memory.KARPLUS_RING_END - 1:04x}'
    )
    print(
        f'Karplus exact OT-domain LUTs: ${memory.KARPLUS_TUNE_DELAY_BASE:04x}..'
        f'${memory.HW4_Y_END - 1:04x}; '
        f'{memory.KARPLUS_CONTROL_LUT_ENTRIES} entries each; '
        'TUNE/DECAY/EDGE/TWANG/MODE active'
    )
    print(
        f'HW4 Y free before stock boot clear: '
        f'{memory.HW4_Y_BOOT_CLEAR - memory.HW4_Y_END} words'
    )
    return source, fold2_words


if __name__ == '__main__':
    build()

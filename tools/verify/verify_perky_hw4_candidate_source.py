#!/usr/bin/env python3
"""Assemble/structurally gate the actual four-engine HW4 audition source.

Requires the local evidence-derived Fold2/Karplus trigger plans, pinned ARM
fixtures, authentic v1.2.1 static assets and generated Karplus control tables.
The final full-image placer is authoritative for usable harvested P words; this
gate proves the complete Fold1/Karplus/Fold2/Noise-Tone composition assembles,
contains no label hazards, carries the live Karplus control contract and fits
inside the audition remix's 5,431-word gross stock-effect donor run.

This is also the release choke point used by ``build_hw4_machine_canary.py``:
a successful source gate must additionally pass the explicit stock-FX harvest
audit, live Karplus audible-control A/B gate, and two-voices-per-core realtime
budget. A failure in any gate is fatal before firmware packaging.
"""
from pathlib import Path
import json
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'tools/perky'), str(ROOT / 'modules/perky')]

import build_hw4_audition_candidate as candidate
import build_noise_tone_synth_source as synth
import hw4_memory as memory
import hw4_profile as profile

OUT = ROOT / 'out/perky/hw4-production-candidate'
GROSS_HW4_DONOR = 5431
FOLD2_PLAN = ROOT / 'out/perky/fold2-trigger-plan.json'
KARPLUS_PLAN = ROOT / 'out/perky/karplus-trigger-plan.json'
KARPLUS_CONTROL = ROOT / 'out/perky/karplus-live-control/manifest.json'


def run_release_gate(script: str) -> None:
    path = ROOT / 'tools/verify' / script
    if not path.exists():
        raise AssertionError(f'missing mandatory HW4 release gate: {path}')
    print('+ ' + ' '.join((sys.executable, str(path))), flush=True)
    subprocess.run([sys.executable, str(path)], cwd=ROOT, check=True)


def main():
    profile.validate()
    memory.validate()
    for path, name in ((FOLD2_PLAN, 'Fold2'), (KARPLUS_PLAN, 'Karplus')):
        if not path.exists():
            print(
                f'PERKY HW4 candidate: SKIP (qualified local {name} trigger plan missing)',
                file=sys.stderr,
            )
            raise SystemExit(2)
    if not KARPLUS_CONTROL.exists():
        print(
            'PERKY HW4 candidate: SKIP (Karplus live-control tables missing; run '
            'tools/perky/build_karplus_control_tables.py first)',
            file=sys.stderr,
        )
        raise SystemExit(2)

    source, _fold2_words = candidate.build(OUT)

    # HW4 scheduling: exactly two local slots per DSP core and no first-wins latch.
    assert 'cmp     #>$40,a\n        bge     pks_silence' in source
    assert 'move    a1,x:>$38ed' not in source
    assert 'move    #>$003800,r6' in source
    assert 'move    #>$00383a,r6' in source
    assert 'move    #>$003874,r6' not in source
    assert 'move    #>$0038ae,r6' not in source

    # All four authentic audition render paths, exact Karplus trigger contracts,
    # and the live post-trigger control layer must coexist in one shipping hook.
    for needle in (
        'pk_fold_voice:',
        'pk_fold2_voice:',
        'pk_fold2_candidate_trigger:',
        'pks_karplus_entry:',
        'pk_karplus_voice:',
        'pk_karplus_trigger_first:',
        'pk_karplus_trigger_active:',
        'pk_karplus_apply_controls:',
        'pk_karplus_shadow_controls:',
        'pk_karplus_restore_controls:',
        'pk_karplus_lut_u16:',
        'pk_probe_source:',
        'pks_continue:',
    ):
        assert needle in source, needle
    assert 'pk_synth_source:' not in source, (
        'shipping generator must expose pk_probe_source hook'
    )

    # Preserve original trigger -> update -> render semantics. Controls are
    # applied/shadowed at block entry, generated first/active trigger runs, then
    # the seven live compact words are restored before the triggered suffix.
    entry_order = (
        'pks_karplus_entry:\n'
        '        jsrl    pk_multi_karplus_init\n'
        '        jsrl    pk_karplus_apply_controls\n'
        '        jsrl    pk_karplus_shadow_controls'
    )
    assert entry_order in source, 'Karplus entry does not apply/shadow live controls'
    trigger_restore = (
        'pkk_trigger_done:\n'
        '        ; Original trigger is followed by update(). Generated plans may restore\n'
    )
    assert trigger_restore in source, 'Karplus trigger/update ordering comment/anchor missing'
    restore_at = source.find('pkk_trigger_done:')
    render_at = source.find('jsrl    pk_karplus_voice', restore_at)
    restore_call = source.find('jsrl    pk_karplus_restore_controls', restore_at)
    assert restore_at >= 0 and restore_at < restore_call < render_at, (
        'Karplus live controls must be restored after trigger and before suffix render'
    )

    # Pin the exact live-control ABI and authentic physical MODE map.
    for needle in (
        'move    x:(r4+$8),a',   # TUNE
        'move    x:(r4+$a),a',   # DECAY
        'move    x:(r4+$c),a',   # EDGE
        'move    x:(r4+$e),a',   # TWANG
        'move    x:(r4+$10),a',  # MODE
        f'move    #>${memory.KARPLUS_TUNE_DELAY_BASE:06x},r1',
        f'move    #>${memory.KARPLUS_DECAY_RATE_BASE:06x},r1',
        f'move    #>${memory.KARPLUS_EDGE_COEFF_BASE:06x},r1',
        'move    a1,x:(r6+$1b)',
        'move    a1,x:(r6+$d)',
        'move    a1,x:(r6+$12)',
        'move    a1,x:(r6+$19)',
        'pkk_control_mode0:',
        'pkk_control_mode1:',
        'move    a1,x:(r6+$2)',
    ):
        assert needle in source, f'Karplus live-control source missing {needle!r}'
    for placeholder in ('@K_TUNE_LUT@', '@K_DECAY_LUT@', '@K_EDGE_LUT@',
                        '@K_GATE_THRESHOLD@'):
        assert placeholder not in source, f'unresolved Karplus placeholder {placeholder}'

    # Shadow must be exactly seven words in spare per-track overlay space. The
    # generated trigger plans operate on compact words 0..31 and cannot corrupt
    # +$21..+$27 while the live values are parked there.
    for compact_word, shadow_word in (
        (0x02, 0x21), (0x07, 0x22), (0x0d, 0x23), (0x12, 0x24),
        (0x19, 0x25), (0x1b, 0x26), (0x1c, 0x27),
    ):
        save = (
            f'move    x:(r6+${compact_word:x}),a\n'
            f'        move    a1,x:(r6+${shadow_word:x})'
        )
        restore = (
            f'move    x:(r6+${shadow_word:x}),a\n'
            f'        move    a1,x:(r6+${compact_word:x})'
        )
        assert save in source, f'Karplus shadow save missing {compact_word:x}->{shadow_word:x}'
        assert restore in source, f'Karplus shadow restore missing {shadow_word:x}->{compact_word:x}'

    # The production record writer pins one hardware family to each physical
    # audition track. Karplus receives four full prepared u16 controls and MODE,
    # not the old four raw bytes/frozen state.
    control = (ROOT / 'modules/perky/control_hw4_candidate.c').read_text()
    for needle in (
        'if (track == 0u) return 0u;',
        'if (track == 1u) return 8u;',
        'if (track == 4u) return 3u;',
        'if (track == 5u) return 10u;',
        'value == 127u ? 4095u : value << 5',
        'pk_hw4_karplus_prepare(p);',
        'p[8] = (uint8_t)mode;',
        'p[11] = 8u;',
        'p[11] = (uint8_t)pk_hw4_engine(track);',
    ):
        assert needle in control, needle

    # The repo assembler performs simple symbol substitution. Exact duplicate
    # labels and prefix-related labels are therefore both fatal hazards.
    labels = re.findall(r'(?m)^([A-Za-z0-9_]+):', source)
    duplicates = sorted({label for label in labels if labels.count(label) > 1})
    if duplicates:
        raise AssertionError('duplicate DSP labels: ' + ', '.join(duplicates))
    for i, left in enumerate(labels):
        for right in labels[i + 1:]:
            if left.startswith(right) or right.startswith(left):
                raise AssertionError(f'DSP assembler prefix collision: {left}/{right}')

    OUT.mkdir(parents=True, exist_ok=True)
    asm, binary = OUT / 'candidate-full.asm', OUT / 'candidate-full.bin'
    asm.write_text(source.replace('@CONT@', '$000426'))
    result = subprocess.run(
        [str(synth.ASM), '-in', str(asm), '-org', '1000', '-out', str(binary)],
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise AssertionError(
            'HW4 candidate assembler failed:\n'
            + result.stdout[-6000:] + result.stderr[-3000:]
        )
    if binary.stat().st_size % 3:
        raise AssertionError('candidate binary is not whole DSP words')

    words = binary.stat().st_size // 3
    if words > GROSS_HW4_DONOR:
        raise AssertionError(
            f'HW4 source needs {words} P words, larger than the '
            f'{GROSS_HW4_DONOR}-word gross audition donor'
        )

    layout = json.loads((OUT / 'layout.json').read_text())
    hw4 = layout['hw4_audition']
    assert hw4['engines'] == {'T1': 0, 'T2': 8, 'T5': 3, 'T6': 10}
    assert hw4['karplus_trigger_snapshot'] == {
        'base_word': memory.KARPLUS_SHADOW_BASE,
        'words': memory.KARPLUS_SHADOW_WORDS,
    }
    controls = hw4['karplus_controls']
    assert controls['parameters'] == ['TUNE', 'DECAY', 'EDGE', 'TWANG', 'MODE']
    assert controls['mode_map'] == [1, 0, 2]
    assert 'immediate' in controls['transition_smoothing']

    extra = layout['extra_y_init']
    assert [row['base_word'] for row in extra] == [
        memory.KARPLUS_ENV1_BASE,
        memory.KARPLUS_ENV2_BASE,
        memory.KARPLUS_RING_BASE,
        memory.KARPLUS_TUNE_DELAY_BASE,
        memory.KARPLUS_DECAY_RATE_BASE,
        memory.KARPLUS_EDGE_COEFF_BASE,
    ]
    assert [row['words'] for row in extra] == [
        memory.KARPLUS_ENV_PACKED_WORDS,
        memory.KARPLUS_ENV_PACKED_WORDS,
        memory.KARPLUS_RING_WORDS,
        memory.KARPLUS_CONTROL_LUT_WORDS,
        memory.KARPLUS_CONTROL_LUT_WORDS,
        memory.KARPLUS_CONTROL_LUT_WORDS,
    ]
    for row in extra:
        assert row['sha256'] and len(row['sha256']) == 64
        path = OUT / row['file']
        assert path.exists(), row['file']
        assert path.stat().st_size == row['words'] * 3, row['file']

    # Compact 128-position Karplus LUTs replaced the former full-domain tables.
    # Validate the active memory contract instead of the obsolete $3e01 layout.
    assert memory.HW4_Y_END == 0x1F02
    assert memory.HW4_Y_BOOT_CLEAR - memory.HW4_Y_END == 0x1FFE

    # Mandatory release gates: reclaimed-stock audit, direct audible A/B for all
    # five Karplus controls (including live no-retrigger changes), then exact
    # composed-source cycle accounting for both two-voice DSP-core pairings.
    run_release_gate('verify_perky_hw4_harvest.py')
    run_release_gate('verify_perky_karplus_live_control_exec.py')
    run_release_gate('verify_perky_hw4_realtime_budget.py')

    print(
        f'PERKY HW4 four-engine composition: PASS '
        f'({words} P words; gross audition donor {GROSS_HW4_DONOR})'
    )
    print('  T1 Fold1 / T2 Karplus / T5 Fold2 / T6 Noise-Tone')
    print('  Karplus: live TUNE/DECAY/EDGE/TWANG/MODE; physical M1/M2/M3 -> 1/0/2')
    print('  Karplus: every control passed fresh-trigger + live no-retrigger PCM A/B')
    print('  Karplus trigger order: trigger -> live-control restore -> render')
    print(
        f'  Karplus Y: env/ring/LUTs ${memory.KARPLUS_ENV1_BASE:04x}..'
        f'${memory.HW4_Y_END - 1:04x}; '
        f'{memory.HW4_Y_BOOT_CLEAR - memory.HW4_Y_END} words free before boot clear'
    )
    print('  actual stock-pinned donor fit remains a full-image placer gate')


if __name__ == '__main__':
    main()

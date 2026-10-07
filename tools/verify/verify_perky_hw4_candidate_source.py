#!/usr/bin/env python3
"""Assemble/structurally gate the actual four-engine HW4 audition source.

Requires the local evidence-derived Fold2/Karplus trigger plans, pinned ARM
fixtures and authentic v1.2.1 static assets.  The final full-image placer is
authoritative for usable harvested P words; this gate proves the complete
Fold1/Karplus/Fold2/Noise-Tone composition assembles, contains no label hazards,
and fits inside the audition remix's 5,431-word gross stock-effect donor run.
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


def main():
    profile.validate()
    memory.validate()
    for path, name in ((FOLD2_PLAN, 'Fold2'), (KARPLUS_PLAN, 'Karplus')):
        if not path.exists():
            print(f'PERKY HW4 candidate: SKIP (qualified local {name} trigger plan missing)', file=sys.stderr)
            raise SystemExit(2)

    source, _fold2_words = candidate.build(OUT)

    # HW4 scheduling: exactly two local slots per DSP core and no first-wins latch.
    assert 'cmp     #>$40,a\n        bge     pks_silence' in source
    assert 'move    a1,x:>$38ed' not in source
    assert 'move    #>$003800,r6' in source
    assert 'move    #>$00383a,r6' in source
    assert 'move    #>$003874,r6' not in source
    assert 'move    #>$0038ae,r6' not in source

    # All four authentic audition render paths plus the two exact Karplus
    # trigger contracts must be present in the one shipping-hook source image.
    for needle in (
        'pk_fold_voice:',
        'pk_fold2_voice:',
        'pk_fold2_candidate_trigger:',
        'pks_karplus_entry:',
        'pk_karplus_voice:',
        'pk_karplus_trigger_first:',
        'pk_karplus_trigger_active:',
        'pk_probe_source:',
        'pks_continue:',
    ):
        assert needle in source, needle
    assert 'pk_synth_source:' not in source, 'shipping generator must expose pk_probe_source hook'

    # The production record writer pins one hardware family to each physical
    # audition track so stale Part/browser bytes cannot change this test.
    control = (ROOT / 'modules/perky/control_hw4_candidate.c').read_text()
    for needle in (
        'if (track == 0u) return 0u;',
        'if (track == 1u) return 8u;',
        'if (track == 4u) return 3u;',
        'if (track == 5u) return 10u;',
        'p[11] = (uint8_t)pk_hw4_engine(track);',
    ):
        assert needle in control, needle

    # The repo assembler performs simple symbol substitution.  Exact duplicate
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
    assert layout['hw4_audition']['engines'] == {
        'T1': 0, 'T2': 8, 'T5': 3, 'T6': 10,
    }
    assert layout['hw4_audition']['karplus_trigger_snapshot'] == {
        'base_word': memory.KARPLUS_SHADOW_BASE,
        'words': memory.KARPLUS_SHADOW_WORDS,
    }

    extra = layout['extra_y_init']
    assert [row['base_word'] for row in extra] == [
        memory.KARPLUS_ENV1_BASE,
        memory.KARPLUS_ENV2_BASE,
        memory.KARPLUS_RING_BASE,
    ]
    assert [row['words'] for row in extra] == [
        memory.KARPLUS_ENV_PACKED_WORDS,
        memory.KARPLUS_ENV_PACKED_WORDS,
        memory.KARPLUS_RING_WORDS,
    ]
    for row in extra:
        assert row['sha256'] and len(row['sha256']) == 64
        assert (OUT / row['file']).exists(), row['file']

    print(
        f'PERKY HW4 four-engine composition: PASS '
        f'({words} P words; gross audition donor {GROSS_HW4_DONOR})'
    )
    print('  T1 Fold1 / T2 Karplus / T5 Fold2 / T6 Noise-Tone')
    print(
        f'  Karplus envs/ring: Y:${memory.KARPLUS_ENV1_BASE:04x}, '
        f'${memory.KARPLUS_ENV2_BASE:04x}, '
        f'${memory.KARPLUS_RING_BASE:04x}..${memory.KARPLUS_RING_END - 1:04x}'
    )
    print('  actual stock-pinned donor fit remains a full-image placer gate')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Assemble/structurally gate the actual four-engine HW4 audition source.

Requires both local evidence-derived trigger plans plus the pinned ARM fixtures.
The final build placer remains authoritative for usable harvested P words, but
this gate proves the complete Fold1/Karplus/Fold2/Noise-Tone composition
assembles and is smaller than the audition remix's 5,431-word gross donor run.
"""
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'tools/perky'), str(ROOT / 'modules/perky')]

import build_hw4_karplus_candidate as candidate
import build_noise_tone_synth_source as synth
import hw4_profile as profile

OUT = ROOT / 'out/perky/hw4-production-candidate'
GROSS_HW4_DONOR = 5431


def main():
    profile.validate()
    if not candidate.hw4.fold2.PLAN.exists():
        print('PERKY HW4 candidate: SKIP (qualified local Fold2 trigger plan missing)', file=sys.stderr)
        raise SystemExit(2)
    if not candidate.PLAN.exists():
        print('PERKY HW4 candidate: SKIP (qualified local Karplus trigger plan missing)', file=sys.stderr)
        raise SystemExit(2)

    source = candidate.build(OUT)

    assert 'cmp     #>$40,a\n        bge     pks_silence' in source
    assert 'move    a1,x:>$38ed' not in source
    assert 'move    #>$003800,r6' in source
    assert 'move    #>$00383a,r6' in source
    assert 'move    #>$003874,r6' not in source
    assert 'move    #>$0038ae,r6' not in source

    for needle in (
        'pk_fold_voice:', 'pk_fold2_voice:', 'pk_fold2_candidate_trigger:',
        'pk_karplus_voice:', 'pk_karplus_trigger_first:',
        'pk_karplus_trigger_active:', 'pk_synth_source:', 'pks_continue:',
    ):
        assert needle in source, needle

    control = (ROOT / 'modules/perky/control_hw4_candidate.c').read_text()
    for needle in (
        'if (track == 0u) return 0u;',
        'if (track == 1u) return 8u;',
        'if (track == 4u) return 3u;',
        'if (track == 5u) return 10u;',
        'p[11] = (uint8_t)pk_hw4_engine(track);',
    ):
        assert needle in control, needle

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
        capture_output=True, text=True,
    )
    if result.returncode:
        raise AssertionError('HW4 candidate assembler failed:\n' + result.stdout[-6000:] + result.stderr[-3000:])
    if binary.stat().st_size % 3:
        raise AssertionError('candidate binary is not whole DSP words')

    words = binary.stat().st_size // 3
    if words > GROSS_HW4_DONOR:
        raise AssertionError(
            f'HW4 source needs {words} P words, larger than even the {GROSS_HW4_DONOR}-word gross audition donor'
        )
    layout = __import__('json').loads((OUT / 'layout.json').read_text())
    assert layout['extra_y_init'] == [
        {'name': 'karplus-ring', 'base_word': 0x1000, 'words': 0x800, 'fill': 0}
    ]
    assert layout['hw4_fixed_engines'] == {'T1': 0, 'T2': 8, 'T5': 3, 'T6': 10}

    print(f'PERKY HW4 four-engine composition: PASS ({words} P words; gross audition donor {GROSS_HW4_DONOR})')
    print('  T1 Fold1 / T2 Karplus / T5 Fold2 / T6 Noise-Tone')
    print('  two fixed local slots per core; Karplus 2K ring boot-zero contract present')
    print('  actual stock-pinned donor fit remains a full-image placer gate')


if __name__ == '__main__':
    main()

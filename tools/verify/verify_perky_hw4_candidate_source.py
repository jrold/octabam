#!/usr/bin/env python3
"""Assemble and structurally gate the static two-voices/core HW4 candidate.

Requires the same local ARM Fold2 trigger plan and fixture used by the hidden
Fold2 production candidate.  This gate deliberately permits P-memory overflow:
the user approved temporary stock-FX reclamation for the first four-voice
hardware audition.  It emits no firmware updater.
"""
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/perky'))
sys.path.insert(0, str(ROOT / 'modules/perky'))

import build_hw4_candidate as candidate
import build_noise_tone_synth_source as synth
import hw4_profile as profile

OUT = ROOT / 'out/perky/hw4-production-candidate'
CURRENT_DONOR = 2724


def main():
    profile.validate()
    if not candidate.fold2.PLAN.exists():
        print('PERKY HW4 candidate: SKIP (qualified local Fold2 trigger plan missing)', file=sys.stderr)
        raise SystemExit(2)
    fixture = candidate.fold2.FIX / 'engine-4-mode-1-corner-0/wrapper-window-before.bin'
    if not fixture.exists():
        print('PERKY HW4 candidate: SKIP (local ARM Fold2 fixture missing)', file=sys.stderr)
        raise SystemExit(2)

    source, _ = candidate.build(OUT)

    # Admission must be positional, not first-come/first-served.
    assert 'cmp     #>$40,a\n        bge     pks_silence' in source
    assert 'move    a1,x:>$38ed' not in source
    assert 'move    #>$003800,r6' in source
    assert 'move    #>$00383a,r6' in source
    assert 'move    #>$003874,r6' not in source
    assert 'move    #>$0038ae,r6' not in source

    # Existing production renderers remain present; Fold2 stays hidden from the
    # stable browser even though the DSP production-form path is composed.
    for needle in (
        'pk_fold_voice:',
        'pk_simple_voice:',
        'pk_fold2_voice:',
        'pk_fold2_candidate_trigger:',
        'pk_synth_source:',
        'pks_continue:',
    ):
        assert needle in source, needle
    control = (ROOT / 'modules/perky/control_hw4_candidate.c').read_text()
    assert '#include "control_fold2_candidate.c"' in control
    assert 'FOLD DRUM 2' not in control

    # Catch exact duplicates as well as the assembler's prefix-label hazard.
    labels = re.findall(r'(?m)^([A-Za-z0-9_]+):', source)
    duplicates = sorted({label for label in labels if labels.count(label) > 1})
    if duplicates:
        raise AssertionError('duplicate DSP labels: ' + ', '.join(duplicates))
    for i, a in enumerate(labels):
        for b in labels[i + 1:]:
            if a.startswith(b) or b.startswith(a):
                raise AssertionError(f'DSP assembler prefix collision: {a}/{b}')

    OUT.mkdir(parents=True, exist_ok=True)
    asm = OUT / 'candidate-full.asm'
    binary = OUT / 'candidate-full.bin'
    asm.write_text(source.replace('@CONT@', '$000426'))
    result = subprocess.run(
        [str(synth.ASM), '-in', str(asm), '-org', '1000', '-out', str(binary)],
        capture_output=True, text=True,
    )
    if result.returncode:
        raise AssertionError(
            'HW4 candidate assembler failed:\n' + result.stdout[-5000:] + result.stderr[-3000:]
        )
    if binary.stat().st_size % 3:
        raise AssertionError('candidate binary is not whole DSP words')

    words = binary.stat().st_size // 3
    overflow = max(0, words - CURRENT_DONOR)
    print(f'PERKY HW4 production composition: PASS ({words} P words; current donor {CURRENT_DONOR}; overflow {overflow})')
    print('admission: two fixed local slots/core; global T1/T2/T5/T6 only')
    print('browser: unchanged; no unqualified engine rows exposed')
    if overflow:
        print('P placement requires the already-approved temporary stock-FX reclamation before an updater can be emitted.')


if __name__ == '__main__':
    main()

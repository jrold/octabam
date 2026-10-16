#!/usr/bin/env python3
"""Reject GCC option-scope mismatches that outline CF sample-loop helpers."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'modules/perky'))
import generate_cf_final as generator


def mismatches(text):
    return [line for line in text.splitlines() if 'optimization level attribute mismatch' in line]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--work', type=Path, required=True)
    args = ap.parse_args()
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    result = dict(status='RUNNING', commands=[], sources={}, mismatches={})
    path = work / 'INLINE.json'
    try:
        # A deliberately conflicting scope calibrates the actual compiler and
        # diagnostic parser; a compiler that stops reporting it cannot pass.
        probe = work / 'negative.c'
        probe.write_text('#pragma GCC optimize ("no-unroll-loops")\n'
                         'static inline int twice(int x){return x+x;}\n'
                         '#pragma GCC optimize ("no-unswitch-loops")\n'
                         'int outer(int x){return twice(x);}\n')
        for source in [probe, ROOT / 'modules/perky/cf_wavetable.c', ROOT / 'modules/perky/cf_resonant.c']:
            info = work / (source.stem + '-missed.txt')
            info.unlink(missing_ok=True)
            command = ['m68k-elf-gcc', *generator.FLAGS,
                       '-fopt-info-inline-missed=' + str(info), '-c', str(source),
                       '-o', str(work / (source.stem + '.o'))]
            result['commands'].append(command)
            result['sources'][str(source)] = hashlib.sha256(source.read_bytes()).hexdigest()
            subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
            found = mismatches(info.read_text() if info.exists() else '')
            result['mismatches'][source.name] = found
            if source == probe:
                assert found, 'negative control did not expose an inlining mismatch'
            else:
                assert not found, f'{source.name}: option scopes block helper inlining'
        result['status'] = 'PASS_CALIBRATED_INLINE_OPTIONS'
        print(result['status'])
    except Exception as error:
        result.update(status='FAIL', error=str(error))
        raise
    finally:
        path.write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()

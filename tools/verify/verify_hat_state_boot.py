#!/usr/bin/env python3
"""Keep complete boot/read-back checks with the explicit A snapshot initializer.

Only candidate expectations differ from the existing resident boot wrapper:
A reclaims part of its retired waveform Y record; B keeps the original table.
The common loader, cookie, preblob and live upload read-back checks all run.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/perky'))
import generate_hat_state_dsp as snapshot


def main():
    common = ROOT / 'tools/verify/verify_perky_machine_boot.py'
    source = common.read_text()
    first = source.index('        raw, _ = perky_image.extend_upload(')
    last = source.index('        expected_blob = (', first)
    source = source[:first] + '''        raw=(packed.parent / f'dsp-{tag}.upload.bin').read_bytes()
        records=parse_upload(raw)
        for addr, words in p_records.get(tag, []):
            exact_record(records, 0, addr, words, tag)
        expected_y = snapshot.snapshot_initial_y(ywords) if tag == 'A' else ywords
        exact_record(records, 2, perky_image.Y_BASE, expected_y, tag)
        for base, values, purpose in extra_y:
            exact_record(records, 2, base, values, f'{tag}:{purpose}')

''' + source[last:]
    scope = {'__name__': '__main__', '__file__': str(common), 'snapshot': snapshot}
    exec(compile(source, str(common), 'exec'), scope)


if __name__ == '__main__':
    main()

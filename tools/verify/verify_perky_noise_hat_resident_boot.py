#!/usr/bin/env python3
"""Run the common byte-exact boot gate with candidate per-core init records.

The shared verifier assumes identical X initializers on both cores. The
resident experiment deliberately replaces A's initializer. Its complete
expected A/B uploads are supplied instead; runtime/loader/cookie/read-back
checks remain those of the common gate. No shipping verifier is changed.
"""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def main():
    common=ROOT/'tools/verify/verify_perky_machine_boot.py'
    source=common.read_text()
    first=source.index('        raw, _ = perky_image.extend_upload(')
    last=source.index('        expected_blob = (',first)
    source=source[:first]+'''        raw=(packed.parent / f'dsp-{tag}.upload.bin').read_bytes()
        records=parse_upload(raw)
        for addr, words in p_records.get(tag, []):
            exact_record(records, 0, addr, words, tag)
        exact_record(records, 2, perky_image.Y_BASE, ywords, tag)
        for base, values, purpose in extra_y:
            exact_record(records, 2, base, values, f'{tag}:{purpose}')

'''+source[last:]
    # Retain the common module's repository-root discovery and CLI behavior.
    scope={'__name__':'__main__','__file__':str(common)}
    exec(compile(source,str(common),'exec'),scope)
if __name__=='__main__':main()

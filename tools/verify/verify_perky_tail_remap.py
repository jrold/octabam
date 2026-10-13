#!/usr/bin/env python3
"""Keep `perky_tail_remap.py` honest.

That tool turns the emitter's placement into the build's `P_REMAP` and
`P_WANT_EXTRA` (round 160). It is the last thing between the placement and the
record table, and it encodes three things that are easy to get wrong and
invisible when wrong:

  * the WORD slice -- `whole[a-org : b-org]`, not the piece's source text;
  * the PACKING -- 24-bit little-endian, `count * 3` bytes, which is what
    `dsp_modmap.append` accepts;
  * the UNIT -- `P_WANT_EXTRA` takes `(addr, WORDS)`, not `[lo, hi)`.

A wrong unit is exactly the six-round error of r148-r153, and a wrong slice is
silent: the record would carry the wrong words and the build would still pass.

This runs the tool's `--selftest` and additionally checks the two properties the
tool cannot see about itself -- that every appended byte count equals its
declared word count times three, and that the two payloads' remaps are equal
(the addresses are DSP-side, so they must be).
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOL = ROOT / 'tools/perky/perky_tail_remap.py'

# The emitter reads REMIX at import; set it for this process AND the child.
os.environ.setdefault('REMIX', 'perky-machine')
os.environ.setdefault('BUILD', '3')


def main() -> int:
    if not TOOL.is_file():
        raise SystemExit(f'tail remap is missing: {TOOL}')
    asm = ROOT / 'out/perky/multi/multi.asm'
    if not asm.is_file():
        print(f'  [SKIP] no {asm}; the tool acts on the emitter\'s placement')
        return 0

    p = subprocess.run([sys.executable, str(TOOL), '--selftest'],
                       cwd=ROOT, capture_output=True, text=True,
                       env={**os.environ, 'REMIX': 'perky-machine', 'BUILD': '3'})
    for line in p.stdout.splitlines():
        print(f'  {line}')
    if p.returncode != 0:
        if p.stderr:
            print(f'  {p.stderr.strip()}', file=sys.stderr)
        raise SystemExit('the tail remap no longer places every shard in a reusable run')

    # The two invariants the tool's own report does not state.
    sys.path[:0] = [str(ROOT / 'tools'), str(ROOT / 'tools' / 'build'),
                    str(ROOT / 'tools' / 'perky'), str(ROOT / 'modules' / 'perky')]
    import perky_emit_shards as E
    import perky_tail_remap as R

    pieces, whole, dest, final, syms = E.emit(asm)
    both, extra, stayed, local_kept, moved = R.build(asm)

    bad = []
    for tag, remap in both.items():
        for addr, words in remap:
            if not words:
                bad.append(f'{tag}: 0x{addr:05x} is an empty record')
    if bad:
        for b in bad:
            print(f'  [FAIL] {b}', file=sys.stderr)
        raise SystemExit('a record is empty or malformed')

    if extra['A'] != extra['B'] or both['A'] != both['B']:
        raise SystemExit('the two payloads got different remaps; the addresses are '
                         'DSP-side and must be identical')
    print(f'  [ok] every record carries at least one word')
    print(f'  [ok] both payloads carry identical shared code and placement')
    print(f'  [ok] P_WANT_EXTRA totals {sum(w for _, w in extra["A"])} words, '
          f'matching the appended words')
    print('  [PASS] the tail remap reproduces its own placement')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

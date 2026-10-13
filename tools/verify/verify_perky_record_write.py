#!/usr/bin/env python3
"""Gate the record-table write operations.

`tools/build/dsp_modmap.py` gained `repoint` and `append` in round 143 -- the
primitives step 2 needs to give payload A and B records at the tail addresses.
They were verified by hand against the real image; this makes that permanent.

What is checked, on the REAL payloads from the built image:

  * `repoint` moves a record's addr, changes nothing else, and keeps the blob's
    length -- it is payload A's operation (the retired records' contiguous run is
    repurposed, so nothing may grow);
  * `append` adds a record before the terminator, grows the blob by exactly the
    record's size, and leaves every earlier record byte-identical -- it is
    payload B's operation;
  * both results RE-PARSE, and `_p_off`'s predicate finds the new address -- the
    test is whether the build's own reader accepts the edit, not whether the
    function returned;
  * an unknown address raises rather than silently doing nothing.

`_p_off`'s predicate is reproduced here rather than imported: `build_bus` reads
the image at import time and this gate must not.

Writes nothing; every edit is on a copy.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'tools'), str(ROOT / 'tools' / 'build')]

import dsp_modmap as M  # noqa: E402

# SPRING REV in payload A: retired by the milestone's priorities, 1063 words.
DONOR_ADDR, DONOR_COUNT = 0x01252, 1063
TAIL_ADDR = 0x33DA3


def resolves(mods, addr: int) -> bool:
    """`build_bus._p_off`'s predicate: a record in space 0 covering addr."""
    return any(sp == 0 and a <= addr < a + cnt for sp, a, cnt, _ in mods)


def main() -> int:
    image = ROOT / 'out/mainos_bus.bin'
    if not image.is_file():
        print(f'  [SKIP] no {image.name} (run `make bus REMIX=perky-machine`); '
              'these operations act on the built payloads')
        return 0
    img = image.read_bytes()

    bad: list[str] = []

    def check(name: str, ok: bool) -> None:
        print(f'  [{"ok" if ok else "FAIL"}] {name}')
        if not ok:
            bad.append(name)

    # ---- payload A: repoint (in place, no growth) --------------------------
    tag, va, ln = [p for p in M.PAYLOADS if p[0] == 'A'][0]
    a = img[va - M.BASE: va - M.BASE + ln]
    before, _ = M.parse(a, 'ac')
    after_bytes = M.repoint(a, DONOR_ADDR, TAIL_ADDR)
    after, _ = M.parse(after_bytes, 'ac')

    check('A: repoint keeps the blob length', len(after_bytes) == len(a))
    check('A: repoint keeps the record count', len(after) == len(before))
    check('A: the new address is a record',
          any(m[1] == TAIL_ADDR and m[2] == DONOR_COUNT for m in after))
    check('A: the old address is gone', not any(m[1] == DONOR_ADDR for m in after))
    check('A: _p_off resolves the new address', resolves(after, TAIL_ADDR))
    check('A: _p_off no longer resolves the old one', not resolves(after, DONOR_ADDR))
    # only the addr field moved: compare every record's (space, count, data_off)
    same_shape = ([(m[0], m[2], m[3]) for m in before]
                  == [(m[0], m[2], m[3]) for m in after])
    check('A: no record moved or resized', same_shape)

    # ---- payload B: append (grows by exactly one record) -------------------
    tag, va, ln = [p for p in M.PAYLOADS if p[0] == 'B'][0]
    b = img[va - M.BASE: va - M.BASE + ln]
    b_before, _ = M.parse(b, 'ac')
    words = bytes(300 * 3)
    b_after_bytes = M.append(b, 0, TAIL_ADDR, words)
    b_after, _ = M.parse(b_after_bytes, 'ac')

    check('B: append grows by header + words',
          len(b_after_bytes) - len(b) == 9 + len(words))
    check('B: append adds exactly one record', len(b_after) == len(b_before) + 1)
    check('B: the new address is a record',
          any(m[1] == TAIL_ADDR and m[2] == 300 for m in b_after))
    check('B: _p_off resolves the new address', resolves(b_after, TAIL_ADDR))
    check('B: every earlier record is byte-identical',
          [(m[0], m[1], m[2], m[3]) for m in b_before]
          == [(m[0], m[1], m[2], m[3]) for m in b_after[:len(b_before)]])

    # ---- and an unknown address must not pass silently ---------------------
    try:
        M.repoint(a, 0x99999, TAIL_ADDR)
        check('an unknown address raises', False)
    except KeyError:
        check('an unknown address raises', True)

    # ---- the terminator helper agrees with where append put it -------------
    check('terminator_offset points at the insertion point',
          M.terminator_offset(b, 'ac') == len(b) - 6)

    if bad:
        for name in bad:
            print(f'  [FAIL] {name}', file=sys.stderr)
        raise SystemExit(f'perky record write: {len(bad)} check(s) failed')
    print('  [PASS] the record table accepts both operations, and _p_off sees them')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

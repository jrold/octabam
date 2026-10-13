#!/usr/bin/env python3
"""Turn the emitter's placement into the build's P_REMAP / P_WANT_EXTRA.

THE PROBLEM THIS SOLVES
    `perky_emit_shards.emit()` already places every shard correctly: it returns
    `dest = {shard: DSP P address}` and all 16 shards land inside
    `all_fx_layout.SAFE_LOCAL_P_SPANS + SAFE_SHARED_P_SPANS` (measured, r148).
    But `build_bus` cannot WRITE there: the P record table comes from the stock
    payload, and no stock record covers the shared runs, so `_p_off` refuses
    (r152). The records have to exist first.

WHAT IT BUILDS
    For every shard that MOVES (dest[name] != its old address):

        P_REMAP[tag]      += (None, (dest[name], packed_words))   -- append a record
        P_WANT_EXTRA[tag] += (dest[name], len(words))             -- name the same ground

    `build_bus` applies the first before it reads `mods`, and adds the second to
    `_want`; its pre-existing `_have != sum(n for _a, n in _want)` guard then
    proves the two agree -- no new check is needed (r152, r157).

WHY BOTH, AND WHY THE WORDS ARE COUNTED TWICE
    The five donor records stay in `region`, holding their old stock code, so
    `_have` counts them AND the appended records. `_want` must therefore count
    both too. The duplication costs accounting, not space: `region` is only a
    write target, and the donors are effects this milestone has given up.

    Re-pointing the donors instead cannot work: their extents and the shards'
    extents do not correspond (Plate alone feeds four shards going to four
    different runs, r151), and `repoint` moves one record to one address.

UNITS -- THE TRAP THAT COST SIX ROUNDS (r148-r153)
    `dest`, `whole`'s slice indices and this module's addresses are all ordinary
    P addresses. `P_WANT_EXTRA` takes `(addr, WORDS)`, the convention
    `stock.p_spans` and `build_bus`'s `region` line use (`a <= m[1] < a + n`).
    `all_fx_layout.SAFE_*_SPANS` is `[lo, hi)`; nothing here consumes it.

SELF-TEST
    `--selftest` runs the whole thing against the real build and prints what it
    would hand the build: per-tag append counts, word totals, and the run each
    appended extent falls in. It writes nothing.
"""
from __future__ import annotations

import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'tools'), str(ROOT / 'tools' / 'build'),
                str(ROOT / 'tools' / 'perky'), str(ROOT / 'modules' / 'perky')]

MONOLITH_ORG = None          # filled from perky_emit_shards, which knows it


def pack(words) -> bytes:
    """24-bit little-endian, the order dsp_modmap.parse reads."""
    return b"".join(int(w).to_bytes(3, "little") for w in words)


def build(pieces, whole, dest, org):
    """Return ({tag: remap}, {tag: extra}) for payloads A and B.

    `pieces` and `whole` come from `emit()`; `org` is the monolith's load
    address, so piece words are `whole[a-org : b-org]`.
    """
    remap, extra, stayed, moved = [], [], [], 0
    for (name, a, b, _text, _i) in pieces:
        new = dest[name]
        if new == a:
            stayed.append((name, a, b - a))       # an existing record already covers it
            continue
        words = whole[a - org: b - org]
        if len(words) != b - a:
            raise SystemExit(f"{name}: got {len(words)} words, expected {b - a}")
        remap.append((None, (new, pack(words))))
        extra.append((new, len(words)))
        moved += len(words)

    # dest holds DSP P addresses, which are payload-INDEPENDENT -- only the stock
    # RECORD addresses differ between A and B (r149), and append names none.
    both = {"A": list(remap), "B": list(remap)}
    extra_both = {"A": list(extra), "B": list(extra)}
    return both, extra_both, stayed, moved


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--selftest', action='store_true')
    args = ap.parse_args()

    import perky_emit_shards as E
    import all_fx_layout as L

    asm = ROOT / 'out/perky/multi/multi.asm'
    if not asm.is_file():
        print(f'  [SKIP] no {asm} (run REMIX=perky-machine BUILD=3 '
              'python3 tools/perky/perky_emit_shards.py first)')
        return 0

    org = E.MONOLITH_ORG
    pieces, whole, dest, final, syms = E.emit(asm)
    both, extra_both, stayed, moved = build(pieces, whole, dest, org)

    runs = [(a, b, 'LOCAL') for a, b in L.SAFE_LOCAL_P_SPANS] + \
           [(a, b, 'SHARED') for a, b in L.SAFE_SHARED_P_SPANS]
    bad = []
    print(f'  emit(): {len(pieces)} pieces, {len(whole)} words; monolith org 0x{org:x}')
    print(f'  staying put : {len(stayed)} shard(s): '
          f'{[(n, hex(a), w) for n, a, w in stayed]}')
    print(f'  appending   : {len(both["A"])} record(s), {moved} words')
    for r in both['A']:
        addr, packed = r[1]
        w = len(packed) // 3
        hit = [f'{k}' for a, b, k in runs if a <= addr and addr + w <= b]
        if not hit:
            bad.append((addr, w))
        print(f'    0x{addr:05x}  {w:5d}w  {hit[0] if hit else "*** NOT IN A RUN ***"}')
    print(f'  P_WANT_EXTRA total: {sum(w for _, w in extra_both["A"])} words')

    if bad:
        for addr, w in bad:
            print(f'  [FAIL] appended record at 0x{addr:05x} ({w}w) is not inside a '
                  f'SAFE run', file=sys.stderr)
        raise SystemExit('perky tail remap: a shard lands outside every reusable run')
    print(f'  [PASS] all {len(both["A"])} appended extents fall inside one reusable run')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

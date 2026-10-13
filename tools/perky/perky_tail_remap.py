#!/usr/bin/env python3
"""Emit relocated shared-P records for PERKY's extended preboot uploads.

The current canary installs private Plate/Compressor shards through existing
records, then extends both uploads with identical shared shards. This tool's
JSON adapter preserves the old analysis interface; growing stock uploads in
place is not the production path. Addresses and lengths are ordinary P words.
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


def build(asm):
    """Return payload-specific relocated shared records and their word extents.

    Local Plate/Compressor shards are installed by perky_fragmented_image;
    shared shards extend the upload. Both payloads have the same placement
    geometry. Shared code never calls into payload-private P and is identical.
    """
    import perky_fragmented_image as F
    import all_fx_layout as L
    both, extra = {}, {}
    local_kept=[]
    for tag in ('A','B'):
        records, ledger, _ = F.plan(asm,tag)
        shared=[]
        for item,(addr,words) in zip(ledger,records):
            if any(lo <= addr and addr+len(words) <= hi for lo,hi in L.local_p_spans(tag)):
                if tag=='A':local_kept.append((item['name'],addr,len(words)))
            else:
                shared.append((addr,words))
        both[tag]=shared
        extra[tag]=[(addr,len(words)) for addr,words in shared]
    return both, extra, [], local_kept, sum(len(w) for _,w in both['A'])


def to_json(both, extra) -> dict:
    """The shape `build_bus._load_p_spans_from_env` reads.

    remap entries are [null, [addr, "hex"]] for an append (or [old, new] for a
    re-point); want entries are [addr, words].
    """
    out = {}
    for tag in sorted(both):
        remap = []
        for addr, words in both[tag]:
            remap.append([None, [addr, pack(words).hex()]])
        out[tag] = {"remap": remap, "want": [[a, w] for a, w in extra[tag]]}
    return out


def write_spec(path, both, extra) -> None:
    import json
    with open(path, 'w') as f:
        json.dump(to_json(both, extra), f)
    print(f'  wrote {path}')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--selftest', action='store_true')
    ap.add_argument('--write', type=pathlib.Path, default=None,
                    help='write the JSON that PERKY_P_SPANS names')
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
    both, extra_both, stayed, local_kept, moved = build(asm)

    runs = [(a, b, 'LOCAL') for a, b in L.SAFE_LOCAL_P_SPANS] + \
           [(a, b, 'SHARED') for a, b in L.SAFE_SHARED_P_SPANS]
    bad = []
    print(f'  emit(): {len(pieces)} pieces, {len(whole)} words; monolith org 0x{org:x}')
    print(f'  staying put : {len(stayed)} shard(s): '
          f'{[(n, hex(a), w) for n, a, w in stayed]}')
    print(f'  appending   : {len(both["A"])} record(s), {moved} words')
    for addr, words in both['A']:
        w = len(words)
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

    # Only now -- after every check above has passed -- write what the build reads.
    if args.write:
        write_spec(args.write, both, extra_both)
        print(f'  build with:  PERKY_P_SPANS={args.write} '
              f'REMIX=perky-machine make bus')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

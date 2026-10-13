#!/usr/bin/env python3
"""Round-trip fragmented P uploads, with stock parser controls and bad-record gates.

ab_records.records expects a full MAIN OS indexed from BASE. Standalone uploads
must be parsed with va=BASE and their exact length. The interrupted verifier
used the original payload VA for a standalone buffer; stock bytes fail the same
way. This gate checks record bodies, not just header counts.
"""
from __future__ import annotations

import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'tools'), str(ROOT / 'tools' / 'build'),
                str(ROOT / 'tools' / 'perky'), str(ROOT / 'modules' / 'perky')]

os.environ.setdefault('REMIX', 'perky-machine')
os.environ.setdefault('BUILD', '3')


def main() -> int:
    asm = ROOT / 'out/perky/multi/multi.asm'
    if not asm.is_file():
        print(f'  [SKIP] no {asm} (run REMIX=perky-machine BUILD=3 '
              'python3 tools/perky/perky_emit_shards.py first)')
        return 0

    import perky_emit_shards as E
    import perky_tail_remap as R
    import perky_image as PI
    import ab_records as AR
    import dsp_modmap as M

    bad: list[str] = []

    def check(name: str, ok: bool) -> None:
        print(f'  [{"ok" if ok else "FAIL"}] {name}')
        if not ok:
            bad.append(name)

    pieces, whole, dest, final, syms = E.emit(asm)
    recs, extra, stayed, kept, moved = R.build(asm)
    print(f'  emit(): {len(pieces)} pieces, {len(whole)} words')
    print(f'  build(): {len(recs["A"])} P record(s), {moved} words; '
          f'{len(stayed)}+{len(kept)} shard(s) already covered')

    check('build() found records to append', len(recs['A']) > 0)
    check('both payloads carry identical shared code', recs['A'] == recs['B'])
    check('every record has words', all(words for _a, words in recs['A']))

    img = (ROOT / 'out/mainos_bus.bin').read_bytes()
    va, ln = [(v, l) for t, v, l in M.PAYLOADS if t == 'A'][0]
    for tag in ('A', 'B'):
        v_, l_ = [(v, l) for t, v, l in M.PAYLOADS if t == tag][0]
        stock, stock_term = AR.records(img, v_, l_)
        stock_raw = img[v_ - AR.BASE:v_ - AR.BASE + l_]
        control, control_term = AR.records(stock_raw, AR.BASE, len(stock_raw))
        check(f'{tag}: stock full-image and standalone parser controls agree',
              [(sp,a,c,o-(v_-AR.BASE)) for sp,a,c,o in stock] == control
              and stock_term-(v_-AR.BASE) == control_term)
        raw, term = PI.extend_upload(img, tag, [], None, None, None, recs[tag])
        grow = len(raw) - l_
        want_grow = 9 + sum(9 + len(w) * 3 for _a, w in recs[tag])
        check(f'{tag}: upload grew by exactly the headers + words '
              f'({grow} == {want_grow})', grow == want_grow)

        # (4) -- read the bytes back the way the loader will.
        parsed, parsed_term = AR.records(raw, AR.BASE, len(raw))
        check(f"{tag}: terminator preserved", raw[parsed_term:] == img[term:v_ - AR.BASE + l_])
        at = {a: c for sp, a, c, _off in parsed if sp == 0}
        for addr, words in recs[tag]:
            check(f'{tag}: P:0x{addr:05x} is a record of {len(words)} words',
                  at.get(addr) == len(words))
            off = AR.word_at(parsed, 0, addr)
            check(f"{tag}: P:0x{addr:05x} words round-trip",
                  [AR.rd(raw, off + 3*i) for i in range(len(words))] == words)

        addr, words = recs[tag][0]
        for name, malformed in (
            ('empty', [(addr, [])]),
            ('duplicate', [(addr,words),(addr,words)]),
            ('outside P', [(0x40000,[1])]),
            ('overflow word', [(addr,[0x1000000])]),
            ('protected stock', [(0x40,[1])]),
        ):
            refused=False
            try:PI.extend_upload(img,tag,[],p_records=malformed)
            except SystemExit:refused=True
            check(f'{tag}: rejects {name} P record',refused)

    if bad:
        for name in bad:
            print(f'  [FAIL] {name}', file=sys.stderr)
        raise SystemExit(f'perky P records: {len(bad)} check(s) failed')
    print('  [PASS] emit -> build -> extend_upload, re-parsed from the built bytes')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

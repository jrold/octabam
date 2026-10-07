#!/usr/bin/env python3
"""Derive the v1.2.1 Karplus first-trigger/retrigger compact-state contract.

Consumes the existing all-engine ARM fixture corpus.  Karplus is Voice 3 / A3
(catalog engine 9 one-based).  The wrapper's Karplus object begins at +0x2908
and is 0x10e0 bytes.  Every observation is normalized through the exact
32-word compact renderer model plus its external 2,048-word ring.

For the first HW4 audition the raw trigger must leave the delay ring untouched.
The separate complete-object update gate also checks every ring byte.  If any ring word changes,
the analyzer records the evidence and the compiler refuses to emit a shipping
plan rather than guessing a bulk-ring operation.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import argparse
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'modules/perky'))
import karplus_compact as compact

FIX_DEFAULT = ROOT / 'out/perky/engine-fixtures'
OUT_DEFAULT = ROOT / 'out/perky/karplus-trigger-contract.json'
ENGINE = 9
ARM_STATE_OFFSET = 0x2908
ARM_STATE_SIZE = 0x10E0

NAMES = {
    compact.VELOCITY: 'velocity',
    compact.MUTE: 'mute',
    compact.MODE: 'mode',
    compact.EXCITE_TARGET: 'excite_target',
    compact.EXCITE_COUNT: 'excite_count',
    compact.DELAY + 0: 'delay.lo',
    compact.DELAY + 1: 'delay.hi',
    compact.WRITE_INDEX: 'write_index',
    compact.AGE + 0: 'age.lo',
    compact.AGE + 1: 'age.hi',
}
for i in range(compact.WORDS):
    NAMES.setdefault(i, f'word[{i}]')


def _state(path: Path) -> compact.Karplus:
    blob = path.read_bytes()
    raw = blob[ARM_STATE_OFFSET:ARM_STATE_OFFSET + ARM_STATE_SIZE]
    if len(raw) != ARM_STATE_SIZE:
        raise RuntimeError(f'short Karplus wrapper snapshot: {path}')
    return compact.Karplus.from_arm(raw)


def _missing(path: Path):
    print('Karplus trigger analysis needs the regenerated all-engine fixture corpus.', file=sys.stderr)
    print(f'First missing file: {path}', file=sys.stderr)
    print('Run tools/perky/capture_engine_fixtures.py with the pinned v1.2.1 firmware/PerkyBits inputs.', file=sys.stderr)
    raise SystemExit(2)


def _cases(fix: Path, pre_name: str, post_name: str):
    out = []
    for mode in range(3):
        for corner in range(3):
            case = fix / f'engine-{ENGINE}-mode-{mode + 1}-corner-{corner}'
            a, b = case / pre_name, case / post_name
            if not a.exists(): _missing(a)
            if not b.exists(): _missing(b)
            out.append((f'm{mode + 1}/c{corner}', _state(a), _state(b)))
    return out


def _ring_delta(pre, post):
    return [
        {'index': i, 'before': a, 'after': b}
        for i, (a, b) in enumerate(zip(pre.ring, post.ring)) if a != b
    ]


def _sha16(values):
    raw = bytearray()
    for v in values:
        raw += int(v & 0xffff).to_bytes(2, 'little')
    return hashlib.sha256(raw).hexdigest()


def _phase(title, cases):
    by_word = defaultdict(list)
    normalized = []
    changed = set()
    ring_changed_cases = 0
    ring_changed_words = set()
    for label, pre, post in cases:
        for i, pair in enumerate(zip(pre.words, post.words)):
            by_word[i].append(pair)
            if pair[0] != pair[1]: changed.add(i)
        delta = _ring_delta(pre, post)
        if delta:
            ring_changed_cases += 1
            ring_changed_words |= {x['index'] for x in delta}
        normalized.append({
            'case': label,
            'pre': pre.words,
            'post': post.words,
            'ring_pre_sha256': _sha16(pre.ring),
            'ring_post_sha256': _sha16(post.ring),
            'ring_changes': delta,
        })

    print(title)
    print('=' * len(title))
    print(f'changed compact words: {len(changed)} / {compact.WORDS}: {sorted(changed)}')
    print(f'ring-mutating cases: {ring_changed_cases} / {len(cases)}; unique changed ring words: {len(ring_changed_words)}')
    if ring_changed_words:
        print('ring indices:', ','.join(map(str, sorted(ring_changed_words)[:64])) + (' ...' if len(ring_changed_words) > 64 else ''))
    print()
    return {
        'title': title,
        'case_count': len(cases),
        'changed_indices': sorted(changed),
        'ring_changed_cases': ring_changed_cases,
        'ring_changed_indices': sorted(ring_changed_words),
        'cases': normalized,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--fixtures', type=Path, default=FIX_DEFAULT)
    ap.add_argument('--json', type=Path, default=OUT_DEFAULT)
    a = ap.parse_args()

    first = _cases(a.fixtures, 'wrapper-window-pre-trigger.bin', 'wrapper-window-trigger-only.bin')
    retrig = _cases(a.fixtures, 'wrapper-window-retrigger-pre.bin', 'wrapper-window-retrigger-only.bin')
    first_c = _phase('Karplus original ARM first-trigger delta', first)
    retrig_c = _phase('Karplus original ARM active-retrigger delta', retrig)

    contract = {
        'schema': 'octabam.perky.karplus-trigger.v2',
        'engine_zero_based': 8,
        'engine_one_based': ENGINE,
        'arm_state_offset': ARM_STATE_OFFSET,
        'arm_state_size': ARM_STATE_SIZE,
        'compact_words': compact.WORDS,
        'ring_words': compact.RING_LEN,
        'first_trigger': first_c,
        'active_retrigger': retrig_c,
        'notes': [
            'Derived from original v1.2.1 ARM snapshots only.',
            'Raw trigger only; mandatory update has a separate complete-object oracle gate.',
            'The first HW4 shipping compiler requires the 2K Karplus ring to remain unchanged by trigger/update.',
        ],
    }
    a.json.parent.mkdir(parents=True, exist_ok=True)
    a.json.write_text(json.dumps(contract, indent=2) + '\n')
    print('contract:', a.json)


if __name__ == '__main__':
    main()

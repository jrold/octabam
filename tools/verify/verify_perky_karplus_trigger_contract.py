#!/usr/bin/env python3
"""Validate/compile the evidence-derived Karplus trigger/retrigger contract.

The contract contains nine original ARM first-trigger observations and nine
active-retrigger observations.  Each phase gets its own deterministic compact
state plan because the first hardware trigger is allowed to differ from a
retrigger.  Reads are from a frozen 32-word pre-trigger snapshot.

For the first HW4 audition, any trigger-time mutation of the external 2K ring is
a hard blocker.  The exact renderer already owns ring evolution sample-by-sample;
this compiler will not invent an unobserved bulk ring law.
"""
from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / 'out/perky/karplus-trigger-contract.json'
PLAN = ROOT / 'out/perky/karplus-trigger-plan.json'
WORDS = 32
MODE = 2
PHASES = ('first_trigger', 'active_retrigger')


def infer(cases, dst):
    pre = [c['pre'] for c in cases]
    post = [c['post'] for c in cases]
    if all(a[dst] == b[dst] for a, b in zip(pre, post)):
        return {'op': 'SAME'}
    values = {b[dst] for b in post}
    if len(values) == 1:
        return {'op': 'CONST', 'value': next(iter(values))}
    values = {(b[dst] ^ a[dst]) & 0xffff for a, b in zip(pre, post)}
    if len(values) == 1 and next(iter(values)):
        return {'op': 'XOR', 'mask': next(iter(values))}
    values = {(b[dst] - a[dst]) & 0xffff for a, b in zip(pre, post)}
    if len(values) == 1 and next(iter(values)):
        return {'op': 'ADD16', 'delta': next(iter(values))}
    sources = [
        src for src in range(WORDS) if src != dst and
        all(b[dst] == a[src] for a, b in zip(pre, post))
    ]
    if len(sources) == 1:
        return {'op': 'COPY', 'src': sources[0]}
    return None


def apply_primitive(op, pre, dst):
    kind = op['op']
    if kind == 'SAME': return pre[dst]
    if kind == 'CONST': return op['value'] & 0xffff
    if kind == 'XOR': return (pre[dst] ^ op['mask']) & 0xffff
    if kind == 'ADD16': return (pre[dst] + op['delta']) & 0xffff
    if kind == 'COPY': return pre[op['src']] & 0xffff
    raise ValueError(kind)


def exact(op, cases, dst):
    return op is not None and all(
        apply_primitive(op, c['pre'], dst) == c['post'][dst] for c in cases
    )


def resolve(cases, dst):
    op = infer(cases, dst)
    if exact(op, cases, dst):
        return op
    modes = sorted({c['pre'][MODE] & 0xff for c in cases})
    if modes != [0, 1, 2]:
        return None
    branches = {}
    for mode in modes:
        subset = [c for c in cases if (c['pre'][MODE] & 0xff) == mode]
        op = infer(subset, dst)
        if not exact(op, subset, dst):
            return None
        branches[str(mode)] = op
    if branches['0'] == branches['1'] == branches['2']:
        return branches['0']
    return {'op': 'BY_MODE', 'branches': branches}


def matches(op, case, dst):
    selected = op
    if op['op'] == 'BY_MODE':
        selected = op['branches'][str(case['pre'][MODE] & 0xff)]
    return apply_primitive(selected, case['pre'], dst) == case['post'][dst]


def validate_case(case):
    pre, post = case.get('pre'), case.get('post')
    assert len(pre) == len(post) == WORDS
    assert all(isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 0xffff for v in pre + post)
    changes = case.get('ring_changes')
    assert isinstance(changes, list)
    for change in changes:
        assert 0 <= change['index'] < 0x800
        assert 0 <= change['before'] <= 0xffff and 0 <= change['after'] <= 0xffff


def compile_phase(name, phase):
    cases = phase['cases']
    assert len(cases) == 9
    for case in cases: validate_case(case)
    if phase.get('ring_changed_cases') != sum(bool(c['ring_changes']) for c in cases):
        raise AssertionError(f'{name}: ring change summary drifted')
    ring_indices = sorted({x['index'] for c in cases for x in c['ring_changes']})
    if ring_indices != phase.get('ring_changed_indices'):
        raise AssertionError(f'{name}: ring change index summary drifted')
    if ring_indices:
        raise RuntimeError(
            f'{name}: Karplus trigger/update mutates {len(ring_indices)} delay-ring words; '
            'HW4 first-audition compiler intentionally refuses bulk ring mutation'
        )

    changed = sorted({
        i for c in cases for i, (a, b) in enumerate(zip(c['pre'], c['post'])) if a != b
    })
    assert changed == phase['changed_indices']
    ops, bad = [], []
    for dst in changed:
        op = resolve(cases, dst)
        if op is None or not all(matches(op, c, dst) for c in cases):
            bad.append(dst)
        else:
            ops.append({'dst': dst, **op})
    if bad:
        raise RuntimeError(f'{name}: unresolved compact trigger words: ' + ','.join(map(str, bad)))
    return {'observations': 9, 'changed_words': changed, 'operations': ops}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--contract', type=Path, default=CONTRACT)
    ap.add_argument('--plan', type=Path, default=PLAN)
    a = ap.parse_args()
    if a.plan.exists(): a.plan.unlink()
    if not a.contract.exists():
        print('Karplus trigger contract missing; run tools/perky/analyze_karplus_trigger.py first.', file=sys.stderr)
        raise SystemExit(2)
    contract = json.loads(a.contract.read_text())
    assert contract.get('schema') == 'octabam.perky.karplus-trigger.v2'
    assert contract.get('engine_zero_based') == 8
    assert contract.get('compact_words') == WORDS
    assert contract.get('ring_words') == 0x800

    phases = {name: compile_phase(name, contract[name]) for name in PHASES}
    plan = {
        'schema': 'octabam.perky.karplus-trigger-plan.v2',
        'source_contract': contract['schema'],
        'engine_zero_based': 8,
        'compact_words': WORDS,
        'ring_words': 0x800,
        'mode_word': MODE,
        'ring_trigger_mutation': 'none in all 18 ARM observations',
        'semantics': [
            'all COPY/XOR/ADD reads use a frozen pre-trigger compact-state snapshot',
            'first trigger and active retrigger retain separate plans',
            'post snapshots stop before the separately verified mandatory update',
        ],
        **phases,
    }
    a.plan.parent.mkdir(parents=True, exist_ok=True)
    a.plan.write_text(json.dumps(plan, indent=2) + '\n')
    conditional = sum(
        op['op'] == 'BY_MODE' for phase in phases.values() for op in phase['operations']
    )
    writes = sum(len(phase['operations']) for phase in phases.values())
    print(f'Karplus trigger contract: PASS (18 ARM observations; {writes} phase-writes; {conditional} MODE-conditioned)')
    print('ring trigger mutation: none')
    print('plan:', a.plan)


if __name__ == '__main__':
    main()

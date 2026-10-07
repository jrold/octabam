#!/usr/bin/env python3
"""Validate/apply/emit DSP56300 source for the qualified Karplus trigger plan."""
from __future__ import annotations
from pathlib import Path
import json

WORDS = 32
MODE = 2
PLAN_SCHEMA = 'octabam.perky.karplus-trigger-plan.v1'
CONTRACT_SCHEMA = 'octabam.perky.karplus-trigger.v1'


def fail(message):
    raise AssertionError('Karplus trigger plan: ' + message)


def u16(value, where):
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 0xffff:
        fail(f'{where}: invalid u16 {value!r}')
    return value


def validate_primitive(op, where):
    kind = op.get('op')
    if kind == 'SAME': return
    if kind == 'CONST': u16(op.get('value'), where + '.value'); return
    if kind == 'COPY':
        src = op.get('src')
        if not isinstance(src, int) or isinstance(src, bool) or not 0 <= src < WORDS:
            fail(f'{where}: invalid COPY source {src!r}')
        return
    if kind == 'XOR': u16(op.get('mask'), where + '.mask'); return
    if kind == 'ADD16': u16(op.get('delta'), where + '.delta'); return
    fail(f'{where}: unsupported primitive {kind!r}')


def validate_phase(phase, where):
    if phase.get('observations') != 9:
        fail(f'{where}: expected 9 observations')
    changed, ops = phase.get('changed_words'), phase.get('operations')
    if not isinstance(changed, list) or not isinstance(ops, list):
        fail(f'{where}: missing changed/operations')
    if len(changed) != len(ops) or [x.get('dst') for x in ops] != changed:
        fail(f'{where}: operation destinations mismatch')
    for i, op in enumerate(ops):
        dst = op.get('dst')
        if not isinstance(dst, int) or isinstance(dst, bool) or not 0 <= dst < WORDS:
            fail(f'{where}/{i}: bad destination {dst!r}')
        if op.get('op') == 'BY_MODE':
            branches = op.get('branches')
            if not isinstance(branches, dict) or set(branches) != {'0', '1', '2'}:
                fail(f'{where}/{i}: BY_MODE needs exact 0/1/2 branches')
            for mode in ('0', '1', '2'):
                validate_primitive(branches[mode], f'{where}/{i}/mode{mode}')
        else:
            validate_primitive(op, f'{where}/{i}')
    return ops


def validate_plan(plan):
    if plan.get('schema') != PLAN_SCHEMA: fail('unexpected schema')
    if plan.get('source_contract') != CONTRACT_SCHEMA: fail('unexpected source contract')
    if plan.get('engine_zero_based') != 8: fail('wrong engine')
    if plan.get('compact_words') != WORDS or plan.get('ring_words') != 0x800: fail('geometry drifted')
    if plan.get('mode_word') != MODE: fail('mode word drifted')
    if plan.get('ring_trigger_mutation') != 'none in all 18 ARM observations': fail('ring mutation not qualified absent')
    return {
        'first_trigger': validate_phase(plan['first_trigger'], 'first_trigger'),
        'active_retrigger': validate_phase(plan['active_retrigger'], 'active_retrigger'),
    }


def load_plan(path: Path):
    if not path.exists():
        raise FileNotFoundError(
            f'qualified Karplus trigger plan missing: {path}; run analyze_karplus_trigger.py then verify_perky_karplus_trigger_contract.py'
        )
    plan = json.loads(path.read_text())
    return plan, validate_plan(plan)


def apply_primitive(op, pre, dst):
    kind = op['op']
    if kind == 'SAME': return pre[dst]
    if kind == 'CONST': return op['value'] & 0xffff
    if kind == 'COPY': return pre[op['src']] & 0xffff
    if kind == 'XOR': return (pre[dst] ^ op['mask']) & 0xffff
    if kind == 'ADD16': return (pre[dst] + op['delta']) & 0xffff
    fail(f'cannot apply {kind!r}')


def apply_plan(pre, ops):
    if len(pre) != WORDS: fail(f'pre-state has {len(pre)} words')
    mode = pre[MODE] & 0xff
    if mode not in (0, 1, 2): fail(f'mode is {mode}, expected 0/1/2')
    out = list(pre)
    for op in ops:
        chosen = op['branches'][str(mode)] if op['op'] == 'BY_MODE' else op
        out[op['dst']] = apply_primitive(chosen, pre, op['dst'])
    return out


def hx(value):
    return f'{u16(value, "immediate"):06x}'


def emit_primitive(op, dst, live='r6', frozen='r5'):
    kind = op['op']
    live_dst = f'x:({live}+${dst:x})'
    frozen_dst = f'x:({frozen}+${dst:x})'
    if kind == 'SAME': return []
    if kind == 'CONST': return [f'        move #>${hx(op["value"])},a', f'        move a1,{live_dst}']
    if kind == 'COPY': return [f'        move x:({frozen}+${op["src"]:x}),a', f'        move a1,{live_dst}']
    if kind == 'XOR': return [f'        move {frozen_dst},a', f'        eor #>${hx(op["mask"])},a', '        and #>$00ffff,a', f'        move a1,{live_dst}']
    if kind == 'ADD16': return [f'        move {frozen_dst},a', f'        add #>${hx(op["delta"])},a', '        and #>$00ffff,a', f'        move a1,{live_dst}']
    fail(f'cannot emit {kind!r}')


def emit_snapshot(*, live='r6', frozen='r5'):
    lines = []
    for i in range(WORDS):
        lines += [f'        move x:({live}+${i:x}),a', f'        move a1,x:({frozen}+${i:x})']
    return '\n'.join(lines) + '\n'


def emit_apply(ops, *, live='r6', frozen='r5', prefix='ktp'):
    lines = []
    for i, op in enumerate(ops):
        dst = op['dst']
        if op['op'] != 'BY_MODE':
            lines += emit_primitive(op, dst, live, frozen)
            continue
        m0, m1, done = f'{prefix}_{i}m0', f'{prefix}_{i}m1', f'{prefix}_{i}d'
        lines += [
            f'        move x:({frozen}+${MODE:x}),a',
            '        and #>$ff,a',
            '        tst a',
            f'        beq {m0}',
            '        cmp #>$1,a',
            f'        beq {m1}',
        ]
        lines += emit_primitive(op['branches']['2'], dst, live, frozen) + [f'        bra {done}', m1 + ':']
        lines += emit_primitive(op['branches']['1'], dst, live, frozen) + [f'        bra {done}', m0 + ':']
        lines += emit_primitive(op['branches']['0'], dst, live, frozen) + [done + ':', '        nop']
    return '\n'.join(lines) + ('\n' if lines else '')


def emit_routine(ops, *, label, live='r6', frozen='r5', snapshot_address=None, prefix='ktp'):
    if prefix.startswith(label) or label.startswith(prefix): fail('unsafe label prefix relation')
    lines = [label + ':']
    if snapshot_address is not None:
        if not 0 <= snapshot_address <= 0xffff: fail('snapshot address outside X')
        lines.append(f'        move #>${snapshot_address:06x},{frozen}')
    text = '\n'.join(lines) + '\n'
    text += emit_snapshot(live=live, frozen=frozen)
    text += emit_apply(ops, live=live, frozen=frozen, prefix=prefix)
    return text + '        rts\n'

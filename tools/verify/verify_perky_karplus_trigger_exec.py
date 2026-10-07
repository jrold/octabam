#!/usr/bin/env python3
"""Execute both evidence-derived Karplus trigger plans on DSP56300."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'out/perky/karplus-trigger-exec'
CONTRACT = ROOT / 'out/perky/karplus-trigger-contract.json'
PLAN = ROOT / 'out/perky/karplus-trigger-plan.json'
sys.path[:0] = [str(ROOT / 'tools/verify'), str(ROOT / 'tools/perky')]

import verify_perky_controlled_voice_exec as host
import karplus_trigger_plan_source as trigger

WORDS = trigger.WORDS
VISIBLE = 64
VOICE_X = 0x200
SNAPSHOT_X = 0x300
PHASE_X = 0x280
PHASES = (('first_trigger', 0), ('active_retrigger', 1))


def fail(message):
    raise AssertionError('Karplus trigger DSP gate: ' + message)


def rows(contract, plans):
    out = []
    assert contract.get('schema') == trigger.CONTRACT_SCHEMA
    assert contract.get('compact_words') == WORDS
    assert contract.get('ring_words') == 0x800
    for phase, flag in PHASES:
        cases = contract[phase]['cases']
        assert len(cases) == 9
        ops = plans[phase]
        for n, row in enumerate(cases):
            if row.get('ring_changes'):
                fail(f'{phase}[{n}]: ring changed in contract')
            pre, post = row['pre'], row['post']
            got = trigger.apply_plan(pre, ops)
            if got != post:
                fail(f'{phase}[{n}]: host plan does not reproduce ARM post-state')
            out.append((f'{phase}-{n}-{row.get("case", "case")}', flag, pre, post))
    return out


def main():
    if not PLAN.exists() or not CONTRACT.exists():
        print('Karplus trigger DSP gate: SKIP (run analyzer + contract compiler first)', file=sys.stderr)
        raise SystemExit(2)
    _plan, plans = trigger.load_plan(PLAN)
    contract = json.loads(CONTRACT.read_text())
    cases = rows(contract, plans)

    host.OUT = OUT
    OUT.mkdir(parents=True, exist_ok=True)
    host.HOST.parent.mkdir(parents=True, exist_ok=True)
    host.build_host()

    source = f'''pk_controlled_voice_exec:
        move #>${VOICE_X:06x},r6
        move x:>${PHASE_X:06x},a
        tst a
        bne pkkt_active_entry
        jsr pk_karplus_trigger_first
        rts
pkkt_active_entry:
        jsr pk_karplus_trigger_active
        rts
'''
    source += trigger.emit_routine(
        plans['first_trigger'], label='pk_karplus_trigger_first',
        frozen='r5', snapshot_address=SNAPSHOT_X, prefix='ktf')
    source += trigger.emit_routine(
        plans['active_retrigger'], label='pk_karplus_trigger_active',
        frozen='r5', snapshot_address=SNAPSHOT_X, prefix='kta')
    binary, entry = host.assemble(host.source_builder.force_long_local_jsr(host.source_builder.relativize_local_conditionals(source)))

    phase_flag = 0
    def write_data(path, state_words, _tables):
        if len(state_words) != VISIBLE: fail('bad visible state size')
        path.write_text(
            'X 100 ' + ' '.join(['000000'] * 13) + '\n' +
            f'X {VOICE_X:x} ' + ' '.join(f'{v & 0xffff:06x}' for v in state_words) + '\n' +
            f'X {PHASE_X:x} {phase_flag:06x}\n' +
            f'X {SNAPSHOT_X:x} ' + ' '.join(['000000'] * 64) + '\n'
        )
        return []

    host.write_data = write_data
    record = tuple([0] * 12)
    for tag, flag, pre, want in cases:
        tag = tag.replace("/", "-")
        phase_flag = flag
        initial = list(pre) + [0] * (VISIBLE - WORDS)
        _audio, states, _rng = host.run(binary, entry, tag, initial, [], [(record, -1)])
        got = states[0][:WORDS]
        if got != want: fail(f'{tag}: executable state mismatch')
        if states[0][WORDS:VISIBLE] != [0] * (VISIBLE - WORDS):
            fail(f'{tag}: trigger write escaped 32-word compact state')

    print(f'Karplus trigger DSP executable gate: PASS ({len(cases)} ARM observations; first + active plans)')


if __name__ == '__main__':
    main()

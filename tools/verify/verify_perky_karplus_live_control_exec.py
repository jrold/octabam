#!/usr/bin/env python3
"""Execute the actual HW4 Karplus live-control path and require audible deltas.

This is the regression gate for the physical complaint that Karplus sounded like
a short impulse and its knobs did not meaningfully change the sound. It uses
the exact composed HW4 DSP source and the exact generated boot assets, enters at
the production ``pk_probe_source`` seam, and feeds the same 12-word PK/Y1 payload
ABI produced by ``control_hw4_candidate.c``.

For each of TUNE, DECAY, EDGE, TWANG and MODE the gate proves two things:

* fresh-trigger low/high settings do not produce bit-identical PCM;
* an untriggered parameter change on an already sounding Karplus voice changes
  subsequent PCM while the pre-change history stays identical.

The nonlinear TUNE/DECAY/EDGE transforms therefore exercise the three real
4096-entry LUTs. TWANG exercises the exact prepared>>1 law. MODE exercises the
physical M1/M2/M3 -> firmware 1/0/2 mapping. The generated original first
trigger runs before the live-control restore in the same source under test.
"""
from __future__ import annotations

from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [
    str(ROOT / 'modules/perky'),
    str(ROOT / 'tools/perky'),
    str(ROOT / 'tools/build'),
    str(ROOT / 'tools/verify'),
]

import build_hw4_audition_candidate as candidate
import perky_image
import verify_perky_controlled_voice_exec as c

OUT = ROOT / 'out/perky/karplus-live-control-exec'
WORK = ROOT / 'out/perky/hw4-production-candidate'
SLOT = 0x20                         # local slot 1 => physical OT T2 on DSP core 1
BLOCKS = 48

WRAPPER = r'''
; Keep the entry label expected by verify_perky_controlled_voice_exec. The body
; enters the real composed HW4 source seam, not the synthetic controlled voice.
pk_controlled_voice_exec:
        ; The harness writes twelve PK/Y1 payload words at X:$100..$10b and
        ; event offset at X:$10c. Point r4 at $f8 so payload words are +8..+19.
        move    #>$0000f8,r4
        move    r4,x:>$209

        ; Reproduce the production trigger flag from a valid event offset.
        move    x:>$10c,a
        clr     b
        tst     a
        blt     pkkve_flag_ready
        cmp     #>$10,a
        bge     pkkve_flag_ready
        move    #>$1,b
pkkve_flag_ready:
        move    b1,x:(r4+$3)
        jsrl    pk_probe_source
        rts

pkkve_finish:
        move    #>$1234,a
        move    a1,x:>$23f
        rts
'''


def fail(message: str) -> "NoReturn":
    raise SystemExit('verify-perky-karplus-live-control-exec: ' + message)


def target(raw: int) -> int:
    raw &= 0x7F
    return 4095 if raw == 127 else raw << 5


def split(value: int) -> tuple[int, int]:
    return ((value >> 8) & 0xFF, value & 0xFF)


def row(*, tune: int = 64, decay: int = 64, edge: int = 64,
        twang: int = 64, mode: int = 1) -> tuple[int, ...]:
    values = [target(tune), target(decay), target(edge), target(twang)]
    payload: list[int] = []
    for value in values:
        payload.extend(split(value))
    payload.extend((max(0, min(2, mode)), 0, 0, 8))
    if len(payload) != 12:
        raise AssertionError(payload)
    return tuple(payload)


def flatten(audio: list[list[int]]) -> list[int]:
    return [sample for block in audio for sample in block]


def different(name: str, left: list[list[int]], right: list[list[int]]) -> None:
    a, b = flatten(left), flatten(right)
    if a == b:
        fail(f'{name}: control change produced bit-identical PCM')
    changed = sum(x != y for x, y in zip(a, b))
    if changed < 8:
        fail(f'{name}: only {changed} samples changed across {len(a)} samples')


def audible(name: str, audio: list[list[int]]) -> None:
    samples = flatten(audio)
    significant = [sample for sample in samples if abs(sample) > 100]
    if len(significant) < 16:
        fail(f'{name}: only {len(significant)} significant samples')
    if len(set(significant)) < 5:
        fail(f'{name}: only {len(set(significant))} distinct significant values')


def main() -> None:
    c.build_host()
    c.OUT = OUT
    c.CYCLE_METER = False
    OUT.mkdir(parents=True, exist_ok=True)

    source, _ = candidate.build(WORK)
    source = WRAPPER + '\n' + source.replace('@CONT@', '$000400')
    binary, entry = c.assemble(source)

    symbols = binary.with_suffix('.sym')
    labels = {
        fields[0]: int(fields[1], 16)
        for line in symbols.read_text().splitlines()
        if len(fields := line.split()) == 2
    }
    finish = labels.get('pkkve_finish')
    if finish is None:
        fail('assembler emitted no pkkve_finish symbol')

    state_init = perky_image.read_words24(WORK / 'state_init.bin')
    low_y = perky_image.read_words24(WORK / 'tables.bin')
    layout = json.loads((WORK / 'layout.json').read_text())
    extra_y = perky_image.load_extra_y_init(WORK, layout)
    extra_x = perky_image.extra_state_init(layout)
    if len(extra_y) != 6:
        fail(f'expected six HW4 extra-Y assets, got {len(extra_y)}')
    purposes = ' '.join(purpose.lower() for _base, _values, purpose in extra_y)
    for token in ('tune', 'decay', 'edge'):
        if token not in purposes:
            fail(f'extra-Y assets do not identify the Karplus {token} lookup')

    # Header occupies X:$f8..$ff; the harness writes the 12 payload words at
    # X:$100..$10b before every invocation, enabling true live/no-retrigger A/B.
    def write_data(path, _state, _tables):
        header = [0x504B, 0, 0x5931, 0, 0, 0, 0, 0]
        lines = [
            'X 3800 ' + ' '.join(f'{value:06x}' for value in state_init),
            'X 3900 ' + ' '.join(['000000'] * (0x39E4 - 0x3900)),
            'X f8 ' + ' '.join(f'{value:06x}' for value in header),
            f'X 418 {SLOT:06x}',
            'X 20b 004080',
            f'P 400 0bf080 {finish:06x} 00000c',
            f'Y {perky_image.Y_BASE:x} ' + ' '.join(f'{value:06x}' for value in low_y),
        ]
        for base, values in extra_x:
            lines.append(f'X {base:x} ' + ' '.join(f'{value:06x}' for value in values))
        for base, values, _purpose in extra_y:
            lines.append(f'Y {base:x} ' + ' '.join(f'{value:06x}' for value in values))
        path.write_text('\n'.join(lines) + '\n')
        return state_init[-4:]

    c.write_data = write_data

    def run(tag: str, script: list[tuple[tuple[int, ...], int]]) -> list[list[int]]:
        audio, _state, _rng = c.run(binary, entry, tag, [], [], script)
        return audio

    baseline = row()
    base_script = [(baseline, 0)] + [(baseline, -1)] * (BLOCKS - 1)
    base_audio = run('baseline', base_script)
    audible('baseline', base_audio)

    axes = (
        ('TUNE', row(tune=0), row(tune=127), row(tune=104)),
        ('DECAY', row(decay=0), row(decay=127), row(decay=112)),
        ('EDGE', row(edge=0), row(edge=127), row(edge=112)),
        ('TWANG', row(twang=0), row(twang=127), row(twang=112)),
        ('MODE', row(mode=0), row(mode=2), row(mode=2)),
    )

    report = {
        'schema': 'perky-karplus-live-control-exec-v1',
        'blocks': BLOCKS,
        'baseline': list(baseline),
        'controls': {},
    }

    for name, low, high, changed in axes:
        lo = run(
            f'{name.lower()}-low',
            [(low, 0)] + [(low, -1)] * (BLOCKS - 1),
        )
        hi = run(
            f'{name.lower()}-high',
            [(high, 0)] + [(high, -1)] * (BLOCKS - 1),
        )
        different(name + ' fresh-trigger low/high', lo, hi)

        # Change early enough that even the shortest authentic Karplus cases are
        # still sounding. The histories must match through block 1, then diverge
        # on block 2 without a new trigger.
        change_at = 2
        fixed_script = [(baseline, 0)] + [(baseline, -1)] * (BLOCKS - 1)
        changed_script = (
            [(baseline, 0)]
            + [(baseline, -1)] * (change_at - 1)
            + [(changed, -1)] * (BLOCKS - change_at)
        )
        fixed_audio = run(f'{name.lower()}-live-fixed', fixed_script)
        changed_audio = run(f'{name.lower()}-live-changed', changed_script)
        if fixed_audio[:change_at] != changed_audio[:change_at]:
            fail(f'{name}: live A/B diverged before the untriggered control change')
        different(
            name + ' untriggered live change',
            fixed_audio[change_at:],
            changed_audio[change_at:],
        )

        fresh_changed = sum(
            a != b for a, b in zip(flatten(lo), flatten(hi))
        )
        live_changed = sum(
            a != b
            for a, b in zip(
                flatten(fixed_audio[change_at:]),
                flatten(changed_audio[change_at:]),
            )
        )
        report['controls'][name] = {
            'low': list(low),
            'high': list(high),
            'live_change': list(changed),
            'fresh_changed_samples': fresh_changed,
            'live_changed_samples': live_changed,
        }
        print(
            f'PASS Karplus {name}: fresh A/B changed {fresh_changed} samples; '
            f'live no-retrigger change altered {live_changed} samples'
        )

    (OUT / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(
        'PERKY Karplus live-control executable gate: PASS '
        '(TUNE/DECAY/EDGE/TWANG/MODE all alter actual composed DSP PCM on fresh '
        'trigger and while already sounding; six HW4 Y assets loaded)'
    )


if __name__ == '__main__':
    main()

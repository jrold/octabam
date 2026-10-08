#!/usr/bin/env python3
"""Measure the final HW4 audition source with two voices per DSP core.

This uses the exact composed shipping source, authentic boot assets and the same
DSP56300 cycle model as the existing one-voice PERKY deadline gate. Each of the
four fixed audition engines runs a persistent 256-block sequence with first
trigger, release tails and active retriggers at all 16 sample offsets. The two
tracks assigned to each core are then summed block-for-block.

Karplus is fed the same full-width prepared PK/Y1 ABI as the real HW4 ColdFire
writer (four 0x0800 middle controls plus physical MODE). This ensures the three
live lookup-table decodes, TWANG mapping and trigger control restore are all in
the measured source path; an obsolete four-raw-byte fixture would index outside
the 4096-entry control tables and would not be a meaningful realtime proof.

Hardware-safety rule is intentionally unchanged from the existing gate:
  2 * modeled PERKY source cycles + stock reserve <= 72,512 cycles / 16 samples
where the stock reserve is the measured 1,410 cycles/sample. The factor of two
covers the emulator model's optimistic MOVE timings. A failing gate blocks the
HW4 firmware packager; it is not converted into a warning.
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
import fold_drum_transport as fold1_transport
import fold_drum2_transport as fold2_transport
import perky_image
import verify_perky_controlled_voice_exec as c

OUT = ROOT / 'out/perky/hw4-realtime-budget'
WORK = ROOT / 'out/perky/hw4-production-candidate'
DEADLINE = 16 * 4532
STOCK_PER_SAMPLE = 1410
STOCK_RESERVED = 16 * STOCK_PER_SAMPLE
MODEL_MARGIN = 2
SOURCE_BUDGET = (DEADLINE - STOCK_RESERVED) // MODEL_MARGIN
PRIVATE_X_WORDS_FROM_3900 = 0x39E4 - 0x3900
SLOT = 0
RECORD = [0] * 12

WRAPPER = r'''
pk_controlled_voice_exec:
        move #>$000500,r4
        move r4,x:>$209
        move x:>$10c,a
        move a1,x:>$20c
        clr b
        tst a
        blt pkh4b_flag_ready
        cmp #>$10,a
        bge pkh4b_flag_ready
        move #>$1,b
pkh4b_flag_ready:
        move b1,x:(r4+$3)
        jsrl pk_probe_source
        rts

pkh4b_finish:
        move #>$1234,a
        move a1,x:>$23f
        rts
'''


def words24(path: Path) -> list[int]:
    return perky_image.read_words24(path)


def prepared_records():
    raw = (64, 64, 64, 64)
    fold1 = fold1_transport.State().prepare(raw, 0, trigger=True)
    fold2 = fold2_transport.State().prepare(raw, 0, trigger=True)
    noise = bytearray([64, 64, 64, 64, 0, 0, 0, 0, 0, 0, 0, 10])

    # Real control_hw4_candidate.c ABI for four middle Karplus controls:
    # raw 64 -> prepared 2048 -> big-endian 0x0800. Physical MODE 1 exercises
    # the M2 -> firmware-mode-0 branch, which includes both comparisons.
    karplus = bytearray([
        0x08, 0x00,  # TUNE
        0x08, 0x00,  # DECAY
        0x08, 0x00,  # EDGE
        0x08, 0x00,  # TWANG
        1,           # physical MODE M2
        0,
        0,
        8,           # engine id
    ])
    assert len(fold1) == len(fold2) == len(noise) == len(karplus) == 12
    return {0: list(fold1), 8: list(karplus), 3: list(fold2), 10: list(noise)}


def main():
    c.build_host()
    c.CYCLE_METER = True
    c.OUT = OUT
    OUT.mkdir(parents=True, exist_ok=True)

    source, _ = candidate.build(WORK)
    source = WRAPPER + '\n' + source.replace('@CONT@', '$000400')
    binary, entry = c.assemble(source)
    labels = {
        f[0]: int(f[1], 16)
        for line in binary.with_suffix('.sym').read_text().splitlines()
        if len(f := line.split()) == 2
    }
    finish = labels['pkh4b_finish']

    state_init = words24(WORK / 'state_init.bin')
    low_y = words24(WORK / 'tables.bin')
    layout = json.loads((WORK / 'layout.json').read_text())
    extra_y = perky_image.load_extra_y_init(WORK, layout)
    extra_x = perky_image.extra_state_init(layout)
    if len(extra_y) != 10:
        raise AssertionError(
            f'HW4 timing expected 10 extra Y assets (6 Karplus + 4 T6), '
            f'got {len(extra_y)}'
        )

    def write_data(path, _state, _tables):
        record_words = [0x504B, 0, 0x5931, 0, 0, 0, 0, 0] + list(RECORD)
        lines = [
            'X 3800 ' + ' '.join(f'{v:06x}' for v in state_init),
            'X 3900 ' + ' '.join(['000000'] * PRIVATE_X_WORDS_FROM_3900),
            'X 500 ' + ' '.join(f'{v & 0xffffff:06x}' for v in record_words),
            f'X 418 {SLOT:06x}',
            'X 20b 004080',
            f'P 400 0bf080 {finish:06x} 00000c',
            f'Y {perky_image.Y_BASE:x} ' + ' '.join(f'{v:06x}' for v in low_y),
        ]
        for base, values in extra_x:
            lines.append(f'X {base:x} ' + ' '.join(f'{v:06x}' for v in values))
        for base, values, _purpose in extra_y:
            lines.append(f'Y {base:x} ' + ' '.join(f'{v:06x}' for v in values))
        path.write_text('\n'.join(lines) + '\n')
        return state_init[-4:]

    c.write_data = write_data
    events = [((block // 16) % 16) if block % 16 == 0 else -1 for block in range(256)]
    dummy = tuple([0] * 12)
    records = prepared_records()
    meters = {}

    global SLOT, RECORD
    for engine, slot in ((0, 0x00), (8, 0x20), (3, 0x00), (10, 0x20)):
        SLOT = slot
        RECORD = records[engine]
        tag = f'engine-{engine}-slot-{slot:02x}'
        c.run(binary, entry, tag, [], [], [(dummy, event) for event in events])
        values = list(map(int, (OUT / f'{tag}.meter').read_text().split()))
        if len(values) != len(events):
            raise AssertionError(f'{tag}: {len(values)} meter rows for {len(events)} blocks')
        meters[engine] = values
        print(f'HW4 timing engine {engine}: max {max(values)} modeled cycles/source block')

    # Physical core grouping is the fixed HW4 map: local slot0+slot1 on each.
    core1 = [a + b for a, b in zip(meters[0], meters[8])]   # T1 Fold1 + T2 Karplus
    core0 = [a + b for a, b in zip(meters[3], meters[10])] # T5 Fold2 + T6 Noise/Tone
    worst1, worst0 = max(core1), max(core0)
    guarded1 = MODEL_MARGIN * worst1 + STOCK_RESERVED
    guarded0 = MODEL_MARGIN * worst0 + STOCK_RESERVED

    report = {
        'schema': 'perky-hw4-realtime-budget-v2',
        'deadline_cycles_per_16': DEADLINE,
        'stock_reserved_cycles_per_16': STOCK_RESERVED,
        'stock_cycles_per_sample': STOCK_PER_SAMPLE,
        'model_margin': MODEL_MARGIN,
        'combined_modeled_source_budget_per_core': SOURCE_BUDGET,
        'blocks_per_engine': len(events),
        'karplus_record': records[8],
        'extra_y_assets': len(extra_y),
        'karplus_live_control_assets': 6,
        'noise_tone_authentic_assets': 4,
        'engine_max_modeled': {str(k): max(v) for k, v in meters.items()},
        'core1_T1_fold1_T2_karplus': {
            'modeled_max': worst1,
            'guarded_total': guarded1,
        },
        'core0_T5_fold2_T6_noise_tone': {
            'modeled_max': worst0,
            'guarded_total': guarded0,
        },
    }
    (OUT / 'report.json').write_text(json.dumps(report, indent=2) + '\n')

    if guarded1 > DEADLINE or guarded0 > DEADLINE:
        raise AssertionError(
            'HW4 realtime budget failed: '
            f'core1 modeled {worst1}, guarded {guarded1}/{DEADLINE}; '
            f'core0 modeled {worst0}, guarded {guarded0}/{DEADLINE}; '
            f'combined modeled source budget is {SOURCE_BUDGET}. '
            'Optimize/rebalance before packaging firmware.'
        )

    print(
        'PERKY HW4 realtime budget: PASS '
        f'(core1 {worst1} modeled -> {guarded1}/{DEADLINE} guarded; '
        f'core0 {worst0} modeled -> {guarded0}/{DEADLINE} guarded; '
        'live Karplus LUT/control restore included; '
        '2x model margin + measured stock reserve)'
    )


if __name__ == '__main__':
    main()

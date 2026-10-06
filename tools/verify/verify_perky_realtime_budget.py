#!/usr/bin/env python3
"""Bound the actual shipping seam's development voice cost, including splits.

The interpreter host counts decoded opcode cycles rather than instructions.
Use a 2x margin on that model (hardware MOVE timings exceed its nominal
counts), and reserve stock's measured 1410 cycles/sample. Only one PERKY voice
per core is admitted, with FX1/FX2 NONE for this hardware canary.
"""
from pathlib import Path
import itertools
import json
import verify_perky_controlled_voice_exec as c
import verify_perky_synth_seam_exec as seam

ROOT = c.ROOT
MAX_MODELED_BLOCK = 23040  # 2x + stock = 68,640 / 72,512 cycles, >5% headroom


def main():
    c.build_host()
    c.CYCLE_METER = True
    c.OUT = ROOT / 'out/perky/realtime-budget'
    c.OUT.mkdir(parents=True, exist_ok=True)
    c.WRAPPER = seam.WRAPPER
    source, init, tables = c.build_source_and_assets()
    source = source.replace('jmp     $000426', 'jmp     $000400')
    binary, entry = c.assemble(source)
    labels = {f[0]: int(f[1], 16) for line in binary.with_suffix('.sym').read_text().splitlines()
              if len(f := line.split()) == 2}
    finish = labels['pkse_finish']

    def write_data(path, state_init, table_words):
        path.write_text(
            'X 3800 ' + ' '.join(f'{v:06x}' for v in state_init) + '\n'
            + 'X 3900 ' + ' '.join(['000000'] * 100) + '\n'
            + 'X 500 00504b 000000 005931 000000\n'
            + 'X 418 000000\nX 20b 004080\nX 38ed 000000\n'
            + f'P 400 0bf080 {finish:06x} 00000c\n'
            + f'Y {c.TABLE_Y:x} ' + ' '.join(f'{v:06x}' for v in table_words) + '\n')
        return state_init[-4:]
    c.write_data = write_data
    cases = list(itertools.product((0, 127), (0, 127), (0, 127), (0, 127), range(3)))
    cases.append((64, 64, 64, 64, 0))
    worst = (0, None)
    total_blocks = 0
    for i, (tune, decay, env, mix, mode) in enumerate(cases):
        knobs = list(c.knob_row())
        knobs[0:4] = tune, decay, env, mix
        knobs[6] = mode
        # Sustain, retrigger at every possible sample offset, and decay to idle.
        blocks = [(tuple(knobs), (block // 16) % 16 if block % 16 == 0 else -1)
                  for block in range(256)]
        c.run(binary, entry, f'corner-{i}', init, tables, blocks)
        values = list(map(int, (c.OUT / f'corner-{i}.meter').read_text().split()))
        n = max(values)
        if n > worst[0]: worst = (n, (tune, decay, env, mix, mode))
        total_blocks += len(values)
    report = dict(modeled_cycles_max=worst[0], worst_controls=worst[1],
                  blocks=total_blocks, block_limit=MAX_MODELED_BLOCK,
                  model_margin=2, stock_reserved=16 * 1410,
                  deadline=16 * 4532, max_voices_per_core=1)
    (c.OUT / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    assert worst[0] <= MAX_MODELED_BLOCK, report
    print(f'PERKY realtime budget: PASS ({total_blocks} seam blocks; max {worst[0]} '
          f'modeled cycles <= {MAX_MODELED_BLOCK}; 2x model + stock reserve; '
          'one admitted voice per core, FX NONE)')

if __name__ == '__main__':
    main()

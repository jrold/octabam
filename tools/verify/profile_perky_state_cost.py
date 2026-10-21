#!/usr/bin/env python3
"""Attribute the current state-handoff candidate without changing its budget.

An identical unprofiled workload is mandatory. Full ISR/whole-CPU statistics,
raw comparison dumps and all stock audio witnesses must remain identical.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess

import calibrate_perky_hybrid_budget as c
import measure_perky_state_handoff as state
import profile_perky_full_map_cost as cost


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--control-row', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    control = args.control_row.resolve()
    old = json.loads(control.read_text())
    source = args.candidate.resolve()
    version = old['configuration']['version']
    image = source / 'probe' / f'mainos_{version}.bin'
    assert c.sha(image) == old['image_sha256']
    c.CURRENT = source
    c.PINNED[version] = old['image_sha256']
    c.cases = lambda: {old['case']: old['configuration']}
    cost.build(work)
    elf = source / 'probe/platform/runtime.elf'
    lines = subprocess.check_output(['m68k-elf-nm', '-n', '-S', str(elf)], text=True)
    symbols = work / 'symbols.txt'
    symbols.write_text(''.join(
        f'{int(v[0],16):x} {int(v[0],16)+int(v[1],16):x} {v[3]}\n'
        for line in lines.splitlines()
        if len(v := line.split()) == 4 and v[2] in ('t', 'T')))
    os.environ.update(CF_COST_SYMBOLS=str(symbols), CF_COST_REPORT=str(work / 'cost.json'))
    run, adapted = state.measurement_function()
    row = run(work, old['case'], old['requested_transport_frames'])
    (work / 'MEASUREMENT_ADAPTER.py').write_text(adapted)
    for key in ('frames', 'image_sha256', 'full_ISR', 'comparison_dumps', 'whole_CPU', 'stock_audio', 'transport'):
        assert old[key] == row[key], ('Profiling perturbed execution', key)
    profile = json.loads((work / 'cost.json').read_text())
    count = profile['completed_ISR'] - 512
    top = {key: sorted(((name, cycles / count / 264) for name, cycles in profile[key].items()),
                       key=lambda item: item[1], reverse=True)[:32]
           for key in ('ISR', 'background')}
    c.save(work / 'PROFILE.json', dict(
        status='PASS_UNCHANGED_AUDIO_STATE_AND_CYCLES',
        control_receipt=str(control), control_sha256=c.sha(control),
        row=row, profile=profile, per_frame_us=top,
        source_sha256={str(p): c.sha(p) for p in
                       (Path(__file__), Path(state.__file__), Path(cost.__file__),
                        c.ROOT / 'tools/harness/perky_cf/full_map_cost_observer.h')}))
    print(json.dumps(top, indent=2))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Attribute corrected Resonant workloads without changing their execution.

Build the isolated read-only cost observer once with --build-observer, then
profile control rows in separate processes. A profile is valid only when its
cycles, source oracle, stock activity and raw target/audio hashes match the
existing 32768-frame unprofiled row exactly.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess

import calibrate_perky_hybrid_budget as calibration
import measure_perky_resonant_workload as resonant
import measure_perky_state_handoff as state
import profile_perky_full_map_cost as cost

ROOT = calibration.ROOT
DEFAULT_BUILD = ROOT / 'out/perky/hybrid/full-map-packet-reserve-v2'
DEFAULT_WORK = ROOT / 'out/perky/hybrid/resonant-cf-optimization/profiles'
FRAMES = 32768
MATCH = ('frames', 'image_sha256', 'full_ISR', 'steady_ISR', 'all_ISR',
         'whole_CPU', 'stock_audio', 'exact_source', 'comparison_dumps', 'transport')


def read(path):
    return json.loads(path.read_text())


def prepare(work, source):
    """Only this explicit preparation phase writes shared observer artifacts."""
    work.mkdir(parents=True, exist_ok=True)
    assert not (work / 'observer').exists(), 'Reuse an existing observer; do not replace a profile instrument'
    cost.build(work)
    elf = source / 'probe/platform/runtime.elf'
    lines = subprocess.check_output(['m68k-elf-nm', '-n', '-S', str(elf)], text=True)
    symbols = work / 'symbols.txt'
    symbols.write_text(''.join(
        f'{int(fields[0], 16):x} {int(fields[0], 16) + int(fields[1], 16):x} {fields[3]}\n'
        for line in lines.splitlines()
        if len(fields := line.split()) == 4 and fields[2] in ('t', 'T')))
    calibration.save(work / 'PROFILE_OBSERVER.json', dict(
        status='BUILT_READ_ONLY_COST_OBSERVER',
        elf_sha256=calibration.sha(elf), symbols_sha256=calibration.sha(symbols),
        observer_sha256=calibration.sha(work / 'observer/ot_emu_safety'),
        parent_observer_sha256=calibration.sha(calibration.DEFAULT_WORK / 'observer/ot_emu_safety'),
        source_sha256={str(path): calibration.sha(path) for path in
                       (Path(cost.__file__), ROOT / 'tools/harness/perky_cf/full_map_cost_observer.h')}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, default=DEFAULT_BUILD)
    parser.add_argument('--control-row', type=Path)
    parser.add_argument('--work', type=Path, default=DEFAULT_WORK)
    parser.add_argument('--build-observer', action='store_true')
    args = parser.parse_args()
    source, work = args.candidate.resolve(), args.work.resolve()
    if args.build_observer:
        prepare(work, source)
        assert args.control_row is None, 'Prepare once before launching isolated profile rows'
        return
    assert args.control_row, 'An existing matching unprofiled control row is required'
    control = args.control_row.resolve()
    old = read(control)
    configuration = old['configuration']
    kind, fourth = configuration['v3_case'], configuration['voice4_case']
    assert kind in resonant.V3 and fourth in resonant.V4
    assert old['frames'] == old['requested_transport_frames'] == FRAMES
    build = read(source / 'BUILD.json')
    assert build['version'] == configuration['version'] == 'PKFM17'
    image = source / 'probe/mainos_PKFM17.bin'
    elf = source / 'probe/platform/runtime.elf'
    assert calibration.sha(image) == build['main_sha256'] == old['image_sha256']
    assert calibration.sha(elf) == build['runtime_sha256'] == old['elf_sha256']
    observer_receipt = read(work / 'PROFILE_OBSERVER.json')
    observer_build = read(work / 'observer/BUILD.json')
    observer = work / 'observer/ot_emu_safety'
    assert calibration.sha(observer) == observer_receipt['observer_sha256'] == observer_build['binary_sha256']
    assert observer_receipt['parent_observer_sha256'] == old['observer_sha256'] == observer_build['parent_sha256']
    assert observer_receipt['elf_sha256'] == calibration.sha(elf)
    symbols = work / 'symbols.txt'
    assert calibration.sha(symbols) == observer_receipt['symbols_sha256']
    for name, expected in observer_receipt['source_sha256'].items():
        assert calibration.sha(Path(name)) == expected, ('Profile source changed', name)
    directory = work / old['case']
    assert not directory.exists(), 'Use a new isolated row directory'
    calibration.CURRENT = source
    calibration.PINNED[build['version']] = old['image_sha256']
    calibration.cases = lambda: {old['case']: configuration}
    os.environ.update(CF_COST_SYMBOLS=str(symbols), CF_COST_REPORT=str(directory / 'cost.json'))
    original_stage = calibration.full.stage
    calibration.full.stage = resonant.project_stage(original_stage, kind, build, configuration)
    run, adapted = state.measurement_function()
    marker = 'Path(_calibration_source))}'
    assert adapted.count(marker) == 1
    adapted = adapted.replace(marker,
        'Path(_calibration_source), Path(_resonant_driver), Path(_profile_driver))}', 1)
    namespace = dict(run.__globals__)
    namespace.update(_resonant_driver=str(Path(resonant.__file__).resolve()),
                     _profile_driver=str(Path(__file__).resolve()))
    exec(compile(adapted, str(Path(__file__).resolve()), 'exec'), namespace)
    try:
        row = namespace['run'](work, old['case'], FRAMES)
    finally:
        calibration.full.stage = original_stage
    (directory / 'MEASUREMENT_ADAPTER.py').write_text(adapted)
    assert read(directory / 'full-map-exact.json') == row['exact_source']
    for key in MATCH:
        assert old[key] == row[key], ('Profiling perturbed execution', key)
    old_fixture = read(control.parent / 'RESONANT_FIXTURE.json')
    fixture = read(directory / 'RESONANT_FIXTURE.json')
    assert old_fixture == fixture, 'Profiling changed final card bytes or MODE locks'
    profile = read(directory / 'cost.json')
    assert profile['completed_ISR'] == FRAMES and profile['exclude_first_ISR'] == 512
    count = FRAMES - 512
    top = {key: sorted(((name, cycles / count / 264) for name, cycles in profile[key].items()),
                       key=lambda item: item[1], reverse=True)[:32]
           for key in ('ISR', 'background')}
    calibration.save(directory / 'PROFILE.json', dict(
        status='PASS_UNCHANGED_AUDIO_STATE_AND_CYCLES',
        control_receipt=str(control), control_sha256=calibration.sha(control),
        matched_fields=MATCH, row=row, profile=profile, per_frame_us=top,
        profiled_observer=observer_receipt,
        final_card_fixture_sha256=calibration.sha(directory / 'RESONANT_FIXTURE.json'),
        source_sha256={str(path): calibration.sha(path) for path in
                       (Path(__file__), Path(state.__file__), Path(resonant.__file__), Path(cost.__file__),
                        ROOT / 'tools/harness/perky_cf/full_map_cost_observer.h')},
        limits=['Symbol buckets are exclusive attribution of modeled cycles after the first 512 ISR completions.',
                'The profile observer is valid for this row only after exact equality of all matched audio/cycle fields and final-card fixture.',
                'Stock functions without runtime ELF symbols share the stock bucket; retained top PC samples locate that work.']))
    print(json.dumps(dict(case=old['case'], per_frame_us=top), indent=2), flush=True)


if __name__ == '__main__':
    main()

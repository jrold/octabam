#!/usr/bin/env python3
"""Diagnostic: a sustained row with some PĒRKONS voices taken off the CF placement.

  placement_mask_variant.py --build BUILD --work WORK --v3 slap-control --voice4 hat --mask 0xc

Runs the frozen row (measure_perky_resonant_workload's card, observer, clocks,
oracle and budget) with one change: `placement_mask` is poked to MASK instead
of 15. A cleared bit sends that voice's chunks where pk_render sends them:
T1 and T5 (voices 0 and 2) to the original DSP-voice control path
(pk_dsp_render_orig), T2 and T6 (voices 1 and 3) to the stock source routine.
It prices the CF side of moving voices off the CF; it does not run a DSP
renderer for them (this image's DSP-B upload has none), so the moved voices
are silent and their exactness checks are reported, not asserted. The audio,
exactness and V4-transport asserts the variant must fail are relaxed for the
unplaced tracks only; every other check of the frozen run body stays.

Writes WORK/<case>-mask<M>/ROW.json and DIAGNOSTIC.json (the seven budget
metrics). Not an admission instrument.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / 'tools/verify'))
import measure_perky_resonant_workload as rw  # noqa: E402

calibration, budget = rw.calibration, rw.budget
TRACKS = (0, 1, 4, 5)


def once(text, old, new):
    assert text.count(old) == 1, ('frozen run body changed', old[:70])
    return text.replace(old, new, 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--v3', choices=rw.V3, required=True)
    parser.add_argument('--voice4', choices=rw.V4, required=True)
    parser.add_argument('--mask', type=lambda s: int(s, 0), required=True)
    parser.add_argument('--frames', type=int, default=32768)
    args = parser.parse_args()
    assert 0 <= args.mask < 15, 'use the ordinary row runner for mask 15'
    source, work = args.build.resolve(), args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    build = json.loads((source / 'BUILD.json').read_text())
    version = build['version']
    frozen = json.loads((calibration.ROOT / 'modules/perky/hybrid/EMULATOR_BUDGET.json').read_text())
    observer = work / 'observer'
    try:  # parallel variants share one link
        observer.symlink_to(calibration.DEFAULT_WORK / 'observer', target_is_directory=True)
    except FileExistsError:
        pass
    assert calibration.sha(observer / 'ot_emu_safety') == frozen['observer_sha256']
    configuration = dict(version=version, role='diagnostic',
                         algos=[9, 9, rw.V3[args.v3][0], rw.V4[args.voice4][0]],
                         modes=[1, 2, rw.V3[args.v3][1], 1], FX='all14',
                         v3_case=args.v3, voice4_case=args.voice4, placement_mask=args.mask)
    name = f'{version}-WTWT-{rw.V3[args.v3][2]}-{rw.V4[args.voice4][2]}-all14-mask{args.mask:x}'
    unplaced = [track for voice, track in enumerate(TRACKS) if not args.mask & (1 << voice)]
    calibration.CURRENT = source
    calibration.PINNED[version] = build['main_sha256']
    calibration.cases = lambda: {name: configuration}
    original_stage = calibration.full.stage
    calibration.full.stage = rw.project_stage(original_stage, args.v3, build, configuration)
    run, adapted = rw.state.measurement_function()
    adapted = once(adapted, 'Path(_calibration_source))}', 'Path(_calibration_source), Path(_variant_driver))}')
    adapted = once(adapted, "        poke('placement_mask', 15)", "        poke('placement_mask', _mask)")
    adapted = once(adapted, "        assert counts['post_FX_significant'] > 64, (name, track, counts)",
                   "        assert track in _unplaced or counts['post_FX_significant'] > 64, (name, track, counts)")
    adapted = once(adapted, "            assert counts['source_significant'] > 64, (name, track, counts)",
                   "            assert track in _unplaced or counts['source_significant'] > 64, (name, track, counts)")
    adapted = once(adapted, "        assert full.exact(exact), exact", "        _exact.append(full.exact(exact))")
    if 5 in unplaced:
        adapted = once(adapted, "        assert transport['pk_nhr_sequence'] > 0\n        assert transport['pk_nhr_consumed'] > 0\n", '')
    namespace = dict(run.__globals__)
    namespace.update(_variant_driver=str(Path(__file__).resolve()), _mask=args.mask,
                     _unplaced=unplaced, _exact=[])
    exec(compile(adapted, str(Path(__file__).resolve()), 'exec'), namespace)
    try:
        row = namespace['run'](work, name, args.frames)
    finally:
        calibration.full.stage = original_stage
    directory = work / name
    row['requested_transport_frames'] = args.frames
    assessment = budget.evaluate(row, frozen['budgets_us'])
    exact = row['exact_source']
    result = dict(status='DIAGNOSTIC_PLACEMENT_MASK_VARIANT_NOT_ADMISSION', case=name, configuration=configuration,
                  unplaced_tracks=[t + 1 for t in unplaced], image_sha256=row['image_sha256'],
                  observer_sha256=row['observer_sha256'], all_voices_exact=namespace['_exact'][0],
                  source_frames=exact['source_frames'], PCM_mismatches=exact['PCM_mismatches'],
                  transport=row['transport'], stock_audio=row['stock_audio'],
                  checks={k: round(v['measured_us'], 3) for k, v in assessment['checks'].items()},
                  pass_budget={k: v['pass_budget'] for k, v in assessment['checks'].items()})
    (directory / 'DIAGNOSTIC.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(case=name, checks=result['checks'], source_frames=result['source_frames']), indent=1), flush=True)


if __name__ == '__main__':
    main()

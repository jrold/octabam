#!/usr/bin/env python3
"""Reuse the frozen cost observer for an isolated new stock-CF candidate.

Prepare symbols once with --build-observer, then supply a completed matching
32768-frame candidate ROW. No firmware or frozen instrument is rebuilt.
"""
import inspect
from pathlib import Path

import measure_perky_stock_cf as measurement
import profile_perky_remaining_cf_cost as previous

ROOT = previous.ROOT
WORK = ROOT / 'out/perky/hybrid/stock-cf-optimization/final-profile'
HELPER_SHA256 = 'ae84ac9c304876dc26d4d4f61bc96594fe4f12a877397cb120102d5e2490ea05'


def replace_once(source, before, after):
    assert source.count(before) == 1, ('Frozen profile template changed', before)
    return source.replace(before, after, 1)


def prepare_reused(work, candidate):
    assert previous.calibration.sha(Path(previous.__file__)) == HELPER_SHA256
    source = inspect.getsource(previous.prepare_reused)
    source = replace_once(source, "assert metadata['version'] == 'PKFM20'",
                          "assert metadata['version'] != 'PKFM20'")
    source = replace_once(source, "candidate / 'probe/mainos_PKFM20.bin'",
                          "candidate / 'probe' / f\"mainos_{metadata['version']}.bin\"")
    namespace = dict(vars(previous))
    namespace.update(__file__=str(Path(__file__).resolve()), remaining=measurement)
    exec(compile(source, str(Path(__file__).resolve()), 'exec'), namespace)
    namespace['prepare_reused'](work, candidate)
    path = work / 'PROFILE_OBSERVER.json'
    receipt = previous.profile.read(path)
    for helper in (Path(previous.__file__), Path(measurement.remaining.__file__)):
        receipt['source_sha256'][str(helper)] = previous.calibration.sha(helper)
    previous.calibration.save(path, receipt)


def adapted_main():
    assert previous.calibration.sha(Path(previous.__file__)) == HELPER_SHA256
    source = previous.adapted_main()
    replacements = {
        "parser.add_argument('--candidate', type=Path, default=DEFAULT_BUILD)":
            "parser.add_argument('--candidate', type=Path, required=True)",
        "assert build['version'] == configuration['version'] == 'PKFM20'":
            "assert build['version'] == configuration['version'] and build['version'] != 'PKFM20'",
        "'Path(_calibration_source), Path(_resonant_driver), Path(_profile_driver), Path(_profile_helper), Path(_remaining_driver))}'":
            "'Path(_calibration_source), Path(_resonant_driver), Path(_profile_driver), Path(_profile_helper), Path(_remaining_driver), Path(_stock_profile_helpers), Path(_remaining_measure_helpers))}'",
        "                     _remaining_driver=str(Path(remaining.__file__).resolve()))":
            "                     _remaining_driver=str(Path(remaining.__file__).resolve()),\n"
            "                     _stock_profile_helpers=str(Path(_profile_adapter.__file__).resolve()),\n"
            "                     _remaining_measure_helpers=str(Path(_measurement_ancestor.__file__).resolve()))",
        "(Path(__file__), Path(_profile_module.__file__), Path(remaining.__file__), Path(state.__file__), Path(resonant.__file__), Path(cost.__file__),":
            "(Path(__file__), Path(_profile_module.__file__), Path(_profile_adapter.__file__), Path(_measurement_ancestor.__file__), Path(remaining.__file__), Path(state.__file__), Path(resonant.__file__), Path(cost.__file__),",
    }
    for before, after in replacements.items():
        source = replace_once(source, before, after)
    return source


def main():
    source = adapted_main()
    namespace = dict(vars(previous.profile))
    namespace.update(__file__=str(Path(__file__).resolve()), remaining=measurement,
                     _profile_module=previous.profile, _profile_adapter=previous,
                     _measurement_ancestor=measurement.remaining,
                     DEFAULT_WORK=WORK, prepare=prepare_reused)
    exec(compile(source, str(Path(__file__).resolve()), 'exec'), namespace)
    namespace['main']()


if __name__ == '__main__':
    main()

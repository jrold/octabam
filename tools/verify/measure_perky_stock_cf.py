#!/usr/bin/env python3
"""Measure a stock-CF candidate with frozen PKFM20-matched voice fixtures.

Only source binding/provenance text changes. The old measurement, oracle,
clock, transport length and final-card selection witnesses are retained.
"""
import hashlib
import inspect
from pathlib import Path

import measure_perky_remaining_cf as remaining

HELPER_SHA256 = 'bbabd353c70ce9f3a6829c34bac474bfd397db9180ca658ad151328c56df36ec'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def adapted_main():
    assert sha(remaining.__file__) == HELPER_SHA256, 'Frozen measurement helper changed'
    source = inspect.getsource(remaining.main)
    replacements = {
        "    namespace['_resonant_helpers'] = str(Path(resonant.__file__).resolve())":
            "    namespace['_resonant_helpers'] = str(Path(resonant.__file__).resolve())\n"
            "    namespace['_remaining_helpers'] = str(Path(remaining.__file__).resolve())",
        "'Path(_resonant_driver), Path(_resonant_helpers))}'":
            "'Path(_resonant_driver), Path(_resonant_helpers), Path(_remaining_helpers))}'",
        "namespace.update(__file__=str(Path(__file__).resolve()), resonant=resonant)":
            "namespace.update(__file__=str(Path(__file__).resolve()), resonant=resonant, remaining=remaining)",
        'Candidate image and ELF are pinned separately; original-source oracle, frozen observer, native clocks, calibrated budget and matched 32768-block fixtures are unchanged from PKFM17.':
            'Candidate image and ELF are pinned separately; original-source oracle, frozen observer, native clocks and calibrated budget remain fixed. These 32768-block fixtures match the immediate PKFM20 controls and retain the frozen PKFM17 ancestry.',
    }
    for before, after in replacements.items():
        assert source.count(before) == 1, ('Frozen measurement template changed', before)
        source = source.replace(before, after, 1)
    return source


def expected_run_source():
    """Reconstruct the exact saved adapter without executing a measurement."""
    _, source = remaining.resonant.state.measurement_function()
    marker = 'Path(_calibration_source))}'
    assert source.count(marker) == 1
    return source.replace(marker,
        'Path(_calibration_source), Path(_resonant_driver), Path(_resonant_helpers), Path(_remaining_helpers))}', 1)


def main():
    source = adapted_main()
    namespace = dict(vars(remaining))
    namespace.update(__file__=str(Path(__file__).resolve()), remaining=remaining)
    exec(compile(source, str(Path(__file__).resolve()), 'exec'), namespace)
    namespace['main']()


if __name__ == '__main__':
    main()

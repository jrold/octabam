#!/usr/bin/env python3
"""Measure the CF candidate with unchanged matched Resonant/Slap fixtures.

Retain the frozen benchmark implementation and bind both its source and this
adapter. Only the candidate image/ELF changes; workload, oracle and budget stay
fixed. Actual final-card selections and runtime combinations remain required.
"""
import inspect
from pathlib import Path

import measure_perky_resonant_workload as resonant


def main():
    source = inspect.getsource(resonant.main)
    marker = "    namespace['_resonant_driver'] = str(Path(__file__).resolve())"
    assert source.count(marker) == 1
    source = source.replace(marker, marker + '''
    namespace['_resonant_helpers'] = str(Path(resonant.__file__).resolve())
    extra = 'Path(_resonant_driver))}'
    assert adapted.count(extra) == 1
    adapted = adapted.replace(extra, 'Path(_resonant_driver), Path(_resonant_helpers))}', 1)
''')
    old = 'Same firmware, measuring binary, clocks and calibrated budget as PKFM17; new fixtures and longer matched Slap controls replace the prior missing Resonant screen.'
    assert source.count(old) == 1
    source = source.replace(old, 'Candidate image and ELF are pinned separately; original-source oracle, frozen observer, native clocks, calibrated budget and matched 32768-block fixtures are unchanged from PKFM17.')
    namespace = dict(vars(resonant))
    namespace.update(__file__=str(Path(__file__).resolve()), resonant=resonant)
    exec(compile(source, __file__, 'exec'), namespace)
    namespace['main']()


if __name__ == '__main__':
    main()

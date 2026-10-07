#!/usr/bin/env python3
"""Verify the intentionally aggressive stock-FX harvest for PERKY HW4.

This is an audition profile, not the eventual product mix.  FILTER is the only
stock DSP effect retained on either chooser; stock DELAY is also retained but
runs on ColdFire and consumes no DSP P words.  Every other stock DSP effect is
therefore legal donor ground.  The stock-image reachability analysis remains
the authority for any pinned words the placer must preserve.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))

from remix import registry, stock


def main():
    remix = registry.remix('perky-hw4')
    assert remix.modules == ('PERKY PROBE', 'FILTER', 'DELAY')
    assert remix.fx1 == ('FILTER',)
    assert remix.fallback == 'NONE'

    listed = set(remix.modules) | set(remix.fx1)
    harvest = stock.harvested(listed)
    expected = set(stock.p_spans('A')) - {'FILTER'}
    assert harvest == expected, (sorted(harvest), sorted(expected))

    runs = stock.regions_of(harvest)
    assert len(runs) == 1, runs
    assert runs[0][0] == 'SPATIALIZER'
    assert runs[0][-1] == 'COMB FILTER'

    gross = sum(stock.WORDS[k] for k in harvest)
    assert gross == 5431, gross
    net = stock.region_words(harvest)
    assert 0 < net <= gross

    print('PERKY HW4 harvest: PASS')
    print('  retained stock DSP FX: FILTER')
    print('  retained stock ColdFire FX: DELAY')
    print(f'  contiguous gross donor: {gross} P words')
    print(f'  placeable after preserved/pinned stock routines: {net} P words')
    if net < gross:
        print(f'  pinned stock routines preserved inside donor: {gross-net} P words')


if __name__ == '__main__':
    main()

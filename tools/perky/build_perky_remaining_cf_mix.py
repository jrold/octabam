#!/usr/bin/env python3
"""Add the exact fixed stock source mixer to the remaining-CF candidate."""
import dataclasses
import json
import os
from pathlib import Path

import build_perky_remaining_cf as base
import generate_stock_source_mix_block as stock
from remix.schema import Detour

ROOT = base.ROOT
WORK = Path(os.environ.get('PERKY_REMAINING_MIX_WORK', str(ROOT / 'out/perky/hybrid/full-map-remaining-cf-mix-v1'))).resolve()
VERSION = os.environ.get('PERKY_REMAINING_MIX_VERSION', 'PKFM20')


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    base.WORK = WORK
    base.VERSION = VERSION
    platform = base.baseline.synthesis.state.budget.card.a.b.G.h.CF
    h = base.baseline.synthesis.state.budget.card.a.b.G.h
    original = platform.base.build_hybrid_module
    spec = stock.generate(WORK)

    def module(*args, **kwargs):
        result = original(*args, **kwargs)
        unit = h.Linked('pkstockmix', str(Path(spec['path']).relative_to(ROOT)), dram=True)
        detours = tuple(Detour(site['address'], stock.expected_span(site),
                               'pkstockmix', site['entry'],
                               'Exact stock16-group source mixer; original data/MAC order',
                               pad_to=site['pad_to']) for site in spec['sites'])
        return dataclasses.replace(result, linked=result.linked + (unit,),
                                   detours=result.detours + detours)

    platform.base.build_hybrid_module = module
    try:
        base.main()
    finally:
        platform.base.build_hybrid_module = original
    path = WORK / 'BUILD.json'
    result = json.loads(path.read_text())
    sha = base.baseline.synthesis.state.budget.card.a.b.sha
    sources = [Path(__file__).resolve(), Path(stock.__file__).resolve(), Path(spec['path'])]
    result['source_sha256'].update({str(p.relative_to(ROOT)): sha(p) for p in sources})
    result['remaining_cf_options']['stock_source_mix'] = True
    result['stock_source_mix_contract'] = spec
    path.write_text(json.dumps(result, indent=2) + '\n')
    print(result['status'], VERSION, 'exact fixed stock source mixer')


if __name__ == '__main__':
    main()

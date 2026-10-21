#!/usr/bin/env python3
"""Opt-in direct-dispatch candidate layered on the PKFM22 merged-segment builder.

Adds one change: the exported pk_render handles the V1-V3 deferred prefix and
merged continuation directly (generate_cf_dispatch_fast.py) and otherwise
tail-calls the unchanged general dispatcher. Synthesis, clocks, DSP uploads,
packets and the stock path are unchanged.
"""
import json
import os
from pathlib import Path

import build_perky_merge_cf as base
import generate_cf_dispatch_fast as fast

ROOT = base.ROOT
WORK = Path(os.environ.get('PERKY_DISPATCH_CF_WORK', str(ROOT / 'out/perky/hybrid/full-map-dispatch-v1'))).resolve()
VERSION = os.environ.get('PERKY_DISPATCH_CF_VERSION', 'PKFM23')


def main():
    assert WORK != base.WORK, 'Never overwrite the PKFM22 outputs'
    WORK.mkdir(parents=True, exist_ok=True)
    base.WORK, base.VERSION = WORK, VERSION
    platform = base.base.base.base.baseline.synthesis.state.budget.card.a.b.G.h.CF
    original_build = platform.build
    generated = []

    def build(work, **kwargs):
        previous = kwargs.get('source_transform')

        def source(name, path):
            prior = previous(name, path) if previous else None
            actual = prior or path
            if name == 'pkplacement':
                actual = fast.transform_placement(WORK, actual)
            elif name == 'pkcontrol':
                actual = fast.transform_control(WORK, actual)
            else:
                return prior
            generated.append(Path(actual))
            return actual

        kwargs['source_transform'] = source
        return original_build(work, **kwargs)

    platform.build = build
    try:
        base.main()
    finally:
        platform.build = original_build
    path = WORK / 'BUILD.json'
    result = json.loads(path.read_text())
    sha = base.base.base.base.baseline.synthesis.state.budget.card.a.b.sha
    sources = [Path(__file__).resolve(), Path(fast.__file__).resolve(), *generated]
    result['source_sha256'].update({str(p.relative_to(ROOT)): sha(p) for p in sources})
    result.update(status='BUILT_DIRECT_DISPATCH_CANDIDATE_NOT_QUALIFIED',
                  optimization_baseline='PKFM22; same fixed seven-ceiling budget, oracle, algorithms and clocks',
                  direct_dispatch=dict(voices=[0, 1, 2], fallback='unchanged PKFM22 general dispatcher'))
    path.write_text(json.dumps(result, indent=2) + '\n')
    print(result['status'], VERSION)


if __name__ == '__main__':
    main()

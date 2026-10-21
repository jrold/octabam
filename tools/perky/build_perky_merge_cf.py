#!/usr/bin/env python3
"""Opt-in merged-segment candidate layered on the immutable PKFM21 builder.

Adds one change: V1-V3 render a frame in one native segment when the stock
event boundary is a rendering no-op (generate_cf_merged_segments.py).
Synthesis, clocks, DSP uploads, packets and the stock path are unchanged.
"""
import json
import os
from pathlib import Path

import build_perky_stock_cf as base
import generate_cf_merged_segments as merged

ROOT = base.ROOT
WORK = Path(os.environ.get('PERKY_MERGE_CF_WORK', str(ROOT / 'out/perky/hybrid/full-map-merge-v1'))).resolve()
VERSION = os.environ.get('PERKY_MERGE_CF_VERSION', 'PKFM22')


def main():
    assert WORK != base.WORK, 'Never overwrite the admitted PKFM21 outputs'
    WORK.mkdir(parents=True, exist_ok=True)
    base.WORK, base.VERSION = WORK, VERSION
    platform = base.base.base.baseline.synthesis.state.budget.card.a.b.G.h.CF
    original_build = platform.build
    generated = []

    def build(work, **kwargs):
        previous = kwargs.get('source_transform')

        def source(name, path):
            prior = previous(name, path) if previous else None
            actual = prior or path
            if name == 'pkplacement':
                actual = merged.transform_placement(WORK, actual)
            elif name == 'pkcontrol':
                actual = merged.transform_control(WORK, actual)
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
    sha = base.base.base.baseline.synthesis.state.budget.card.a.b.sha
    sources = [Path(__file__).resolve(), Path(merged.__file__).resolve(), *generated]
    result['source_sha256'].update({str(p.relative_to(ROOT)): sha(p) for p in sources})
    result.update(status='BUILT_MERGED_SEGMENT_CANDIDATE_NOT_QUALIFIED',
                  optimization_baseline='PKFM21; same fixed seven-ceiling budget, oracle, algorithms and clocks',
                  merged_segments=dict(voices=[0, 1, 2],
                                       excluded=['V4 external halves publish per-half side words',
                                                 'diagnostic tracing keeps two segments',
                                                 'Acoustic Hats (algorithm 10) is V4-only']))
    path.write_text(json.dumps(result, indent=2) + '\n')
    print(result['status'], VERSION)


if __name__ == '__main__':
    main()

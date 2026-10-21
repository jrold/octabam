#!/usr/bin/env python3
"""Opt-in CF candidate layered over immutable PKFM17 source generators."""
import json
import os
from pathlib import Path

import build_perky_packet_reserve_probe as baseline
import generate_cf_prepare_fast as prepare
import generate_cf_synthesis_remaining as synthesis

ROOT = baseline.synthesis.ROOT
WORK = Path(os.environ.get('PERKY_REMAINING_WORK', str(ROOT / 'out/perky/hybrid/full-map-remaining-cf-v1'))).resolve()
VERSION = os.environ.get('PERKY_REMAINING_VERSION', 'PKFM18')


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    baseline.synthesis.WORK = WORK
    baseline.synthesis.VERSION = VERSION
    platform = baseline.synthesis.state.budget.card.a.b.G.h.CF
    original = platform.build
    generated = []
    options = {name: os.environ.get('PERKY_REMAINING_' + name.upper(), '1') == '1'
               for name in ('prepare', 'resonant')}

    def build(work, **kwargs):
        previous = kwargs.get('source_transform')

        def source(name, path):
            prior = previous(name, path) if previous else None
            actual = prior or path
            if name == 'pkplacement' and options['prepare']:
                actual = prepare.transform(WORK, actual)
                generated.append(actual)
                return actual
            if name == 'pkresonant' and options['resonant']:
                actual = synthesis.resonant_transform(WORK, actual)
                generated.append(actual)
                return actual
            return prior

        kwargs['source_transform'] = source
        return original(work, **kwargs)

    platform.build = build
    try:
        baseline.main()
    finally:
        platform.build = original
    path = WORK / 'BUILD.json'
    result = json.loads(path.read_text())
    sources = [Path(__file__).resolve(), Path(prepare.__file__).resolve(),
               Path(synthesis.__file__).resolve(), *generated]
    sha = baseline.synthesis.state.budget.card.a.b.sha
    result['source_sha256'].update({str(p.relative_to(ROOT)): sha(p) for p in sources})
    result.update(status='BUILT_REMAINING_CF_CANDIDATE_NOT_QUALIFIED',
                  remaining_cf_options=options,
                  optimization_baseline='PKFM17; unchanged fixed budget and original algorithms')
    path.write_text(json.dumps(result, indent=2) + '\n')
    print(result['status'], VERSION)


if __name__ == '__main__':
    main()

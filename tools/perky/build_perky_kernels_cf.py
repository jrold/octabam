#!/usr/bin/env python3
"""Opt-in assembly-kernel candidate layered on the PKFM22 merged-segment builder.

Adds exact assembly kernels behind the original C renderers, which remain as
their fallbacks. Each kernel is a source transform of its compiled unit plus
linked assembly units; enable them with PERKY_KERNELS (comma list, default
"wt"). Synthesis arithmetic, clocks, DSP uploads, packets and the stock path
are unchanged.
"""
import dataclasses
import json
import os
from pathlib import Path

import build_perky_merge_cf as base
import generate_cf_dispatch_lean as lean
import generate_cf_nt_render_asm as nt
import generate_cf_slap_env_asm as slap
import generate_cf_v4_merge as v4merge
import generate_cf_wt_render_asm as wt

ROOT = base.ROOT
WORK = Path(os.environ.get('PERKY_KERNELS_CF_WORK', str(ROOT / 'out/perky/hybrid/full-map-kernels-v1'))).resolve()
VERSION = os.environ.get('PERKY_KERNELS_CF_VERSION', 'PKFM24')
KERNELS = {'wt': ('pkwavetable', wt), 'slap': ('pkslap', slap), 'nt': ('pknoise', nt),
           'v4merge': ('pkplacement', v4merge), 'lean': ('pkcontrol', lean)}


def main():
    selected = [k for k in os.environ.get('PERKY_KERNELS', 'wt').split(',') if k]
    assert selected and all(k in KERNELS for k in selected), selected
    assert WORK != base.WORK and WORK != base.base.WORK, 'Never overwrite earlier candidates'
    WORK.mkdir(parents=True, exist_ok=True)
    base.WORK, base.VERSION = WORK, VERSION
    stage = base.base.base.base.baseline.synthesis.state.budget.card.a.b
    chain = stage.G.h
    platform = chain.CF
    original_build, original_module = platform.build, platform.base.build_hybrid_module
    generated = []
    units = list(dict.fromkeys(u for k in selected for u in KERNELS[k][1].UNITS))

    def module(*args, **kwargs):
        result = original_module(*args, **kwargs)
        linked = tuple(chain.Linked(name, str(path.relative_to(ROOT)), dram=True) for name, path in units)
        return dataclasses.replace(result, linked=result.linked + linked)

    def build(work, **kwargs):
        previous = kwargs.get('source_transform')

        def source(name, path):
            prior = previous(name, path) if previous else None
            for kernel in selected:
                unit, generator = KERNELS[kernel]
                if name == unit:
                    actual = generator.transform(WORK, prior or path)
                    generated.append(Path(actual))
                    return actual
            return prior

        kwargs['source_transform'] = source
        return original_build(work, **kwargs)

    platform.build, platform.base.build_hybrid_module = build, module
    try:
        base.main()
    finally:
        platform.build, platform.base.build_hybrid_module = original_build, original_module
    path = WORK / 'BUILD.json'
    result = json.loads(path.read_text())
    sha = stage.sha
    sources = [Path(__file__).resolve(), *[Path(KERNELS[k][1].__file__).resolve() for k in selected],
               *generated, *[p for _, p in units]]
    result['source_sha256'].update({str(p.relative_to(ROOT)): sha(p) for p in sources})
    result.update(status='BUILT_ASSEMBLY_KERNEL_CANDIDATE_NOT_QUALIFIED',
                  optimization_baseline='PKFM22; same fixed seven-ceiling budget, oracle, algorithms and clocks',
                  assembly_kernels=selected)
    path.write_text(json.dumps(result, indent=2) + '\n')
    print(result['status'], VERSION, selected)


if __name__ == '__main__':
    main()

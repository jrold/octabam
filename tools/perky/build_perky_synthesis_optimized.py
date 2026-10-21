#!/usr/bin/env python3
"""Opt-in exact CF synthesis/ISR candidate on the resident-state Hat image.

The PKFM15 builder and its receipts remain unchanged. Candidate switches are
recorded so complete-image measurements can reject isolated timing regressions.
No precision, algorithm, sample clock, feedback, or fixed-budget change.
"""
import dataclasses
import json
import os
from pathlib import Path

import build_perky_state_handoff as state
import generate_cf_ah_budget as ah
import generate_cf_control_batches as controls
import generate_cf_nt_budget as nt
import generate_cf_resample_lut as resample
import generate_cf_slap_rng as slap
import generate_fast_transport as transport
import generate_stock_position_fast as stock
import generate_wt_block_asm as wt
from remix.schema import Detour

ROOT = state.ROOT
WORK = Path(os.environ.get('PERKY_SYNTHESIS_WORK', str(ROOT / 'out/perky/hybrid/full-map-synthesis-v1'))).resolve()
VERSION = os.environ.get('PERKY_SYNTHESIS_VERSION', 'PKFM16')


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    state.WORK = WORK
    state.VERSION = VERSION
    enabled = {key: os.environ.get('PERKY_SYNTHESIS_' + key.upper(), '1') == '1'
               for key in ('wt', 'nt', 'ah', 'slap', 'controls', 'resample', 'transport', 'stock')}
    h = state.budget.card.a.b.G.h
    cf = h.CF
    original_build = cf.build
    original_module = cf.base.build_hybrid_module
    original_linked = h.Linked
    generated = []
    transforms = dict(pkwavetable=('wt', wt.transform), pknoise=('nt', nt.transform),
                      pkacoustic=('ah', ah.transform), pkslap=('slap', slap.transform),
                      pkplacement=('controls', controls.transform))
    asm_paths = {}
    if enabled['resample']:
        asm_paths['pknhbclock'] = resample.generate(WORK)
    if enabled['transport']:
        asm_paths['pkbudget'] = Path(transport.generate(WORK)['path'])
    stock_spec = stock.generate(WORK) if enabled['stock'] else None
    generated.extend(asm_paths.values())
    if stock_spec:
        generated.append(Path(stock_spec['path']))

    def linked(name, path, **kwargs):
        if name in asm_paths:
            path = str(asm_paths[name].relative_to(ROOT))
        return original_linked(name, path, **kwargs)

    def module(*args, **kwargs):
        result = original_module(*args, **kwargs)
        units = []
        detours = []
        if enabled['wt']:
            units.append(original_linked('pkwtblock', str(wt.ASSEMBLY.relative_to(ROOT)), dram=True))
        if stock_spec:
            units.append(original_linked('pkstockpos', str(Path(stock_spec['path']).relative_to(ROOT)), dram=True))
            detours.extend(Detour(site['address'], stock.expected_span(site), 'pkstockpos', site['entry'],
                                  'Exact guarded unity sample-position recurrence; retain original generic fallback',
                                  pad_to=site['pad_to']) for site in stock_spec['sites'])
        return dataclasses.replace(result, linked=result.linked + tuple(units), detours=result.detours + tuple(detours))

    def build(work, **kwargs):
        previous = kwargs.get('source_transform')

        def source(name, path):
            prior = previous(name, path) if previous else None
            actual = prior or path
            if name in transforms:
                option, transform = transforms[name]
                if enabled[option]:
                    actual = transform(WORK, actual)
                    generated.append(Path(actual))
                    return actual
            return prior

        kwargs['source_transform'] = source
        return original_build(work, **kwargs)

    h.Linked = linked
    cf.base.build_hybrid_module = module
    cf.build = build
    try:
        state.main()
    finally:
        h.Linked = original_linked
        cf.base.build_hybrid_module = original_module
        cf.build = original_build
    path = WORK / 'BUILD.json'
    result = json.loads(path.read_text())
    inputs = [Path(__file__).resolve(), wt.ASSEMBLY, *generated]
    inputs += [Path(module.__file__) for module in (wt, nt, ah, slap, controls, resample, transport, stock)]
    control_engine = WORK / 'cf-perky4-control-batches.c'
    if control_engine.exists():
        inputs.append(control_engine)
    result['source_sha256'].update({str(p.relative_to(ROOT)): state.budget.card.a.b.sha(p) for p in inputs})
    result.update(status='BUILT_EXACT_CF_SYNTHESIS_CANDIDATE_NOT_QUALIFIED',
                  synthesis_options=enabled, stock_position_contract=stock_spec,
                  optimization_baseline='PKFM15 full-map-state-v4; no normal CF Hat shadow')
    path.write_text(json.dumps(result, indent=2) + '\n')
    print(result['status'], VERSION, json.dumps(enabled, sort_keys=True))


if __name__ == '__main__':
    main()

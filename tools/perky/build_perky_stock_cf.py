#!/usr/bin/env python3
"""Opt-in stock/CF candidate on the immutable PKFM20 generators."""
import dataclasses
import json
import os
from pathlib import Path

import build_perky_remaining_cf_mix as base
import generate_cf_publish_unrolled as publish
import generate_cf_resample_signed as resample
import generate_cf_segment_trace_cold as trace
import generate_cf_slap_span as slap
import generate_stock_delay_steady_mix as stock
from remix.schema import Detour

ROOT = base.ROOT
WORK = Path(os.environ.get('PERKY_STOCK_CF_WORK', str(ROOT / 'out/perky/hybrid/full-map-stock-cf-v1'))).resolve()
VERSION = os.environ.get('PERKY_STOCK_CF_VERSION', 'PKFM21')


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    base.WORK, base.VERSION = WORK, VERSION
    platform = base.base.baseline.synthesis.state.budget.card.a.b.G.h.CF
    h = base.base.baseline.synthesis.state.budget.card.a.b.G.h
    options = {key: os.environ.get('PERKY_STOCK_CF_' + key.upper(), '1') == '1'
               for key in ('resample', 'publish', 'trace', 'slap', 'stock_delay')}
    original_build, original_module, original_linked = platform.build, platform.base.build_hybrid_module, h.Linked
    assembly = {}
    if options['resample']:
        assembly['pknhbclock'] = resample.generate(WORK)
    if options['publish']:
        assembly['pkprpub'] = publish.generate(WORK)
    specification = stock.generate(WORK) if options['stock_delay'] else None
    generated = list(assembly.values())

    def linked(name, path, **kwargs):
        if name in assembly:
            path = str(assembly[name].relative_to(ROOT))
        return original_linked(name, path, **kwargs)

    def module(*args, **kwargs):
        result = original_module(*args, **kwargs)
        units, detours = [], []
        if options['slap']:
            units.append(original_linked('pkslapspan', str(slap.ASSEMBLY.relative_to(ROOT)), dram=True))
        if specification:
            units.append(original_linked('pkstockdelay', str(Path(specification['path']).relative_to(ROOT)), dram=True))
            detours.extend(Detour(site['address'], stock.expected_span(site),
                                  'pkstockdelay', site['entry'],
                                  'Exact zero-ramp stock DELAY mixer; original generic fallback',
                                  pad_to=site['pad_to']) for site in specification['sites'])
        return dataclasses.replace(result, linked=result.linked + tuple(units), detours=result.detours + tuple(detours))

    def build(work, **kwargs):
        previous = kwargs.get('source_transform')

        def source(name, path):
            prior = previous(name, path) if previous else None
            actual = prior or path
            if name == 'pkplacement' and options['trace']:
                actual = trace.transform(WORK, actual)
            elif name == 'pkslap' and options['slap']:
                actual = slap.transform(WORK, actual)
            else:
                return prior
            generated.append(Path(actual))
            return actual

        kwargs['source_transform'] = source
        return original_build(work, **kwargs)

    h.Linked, platform.base.build_hybrid_module, platform.build = linked, module, build
    try:
        base.main()
    finally:
        h.Linked, platform.base.build_hybrid_module, platform.build = original_linked, original_module, original_build
    path = WORK / 'BUILD.json'
    result = json.loads(path.read_text())
    sha = base.base.baseline.synthesis.state.budget.card.a.b.sha
    sources = [Path(__file__).resolve(), *generated,
               *[Path(m.__file__) for m in (publish, resample, trace, slap, stock)]]
    if options['slap']:
        sources.append(slap.ASSEMBLY)
    if specification:
        sources.append(Path(specification['path']))
    result['source_sha256'].update({str(p.relative_to(ROOT)): sha(p) for p in sources})
    result.update(status='BUILT_STOCK_CF_CANDIDATE_NOT_QUALIFIED', stock_cf_options=options,
                  optimization_baseline='PKFM20; same fixed seven-ceiling budget, oracle, algorithms and clocks',
                  stock_cf_delay_contract=specification,
                  stock_cf_required_proofs=['stock_delay_mix'] if specification else [],
                  stock_cf_proof_contracts={'stock_delay_mix': dict(minimum_cases=4096, required_symbols=['pk_stock_delay_steady_mix'])} if specification else {},
                  stock_cf_required_direct_proofs=[name for name, option in (('resample_linked', 'resample'), ('publish_binding', 'publish')) if options[option]])
    path.write_text(json.dumps(result, indent=2) + '\n')
    print(result['status'], VERSION, json.dumps(options, sort_keys=True))


if __name__ == '__main__':
    main()

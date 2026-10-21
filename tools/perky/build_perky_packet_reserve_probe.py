#!/usr/bin/env python3
"""Isolated PKFM16-derived reservation experiment; retained builders unchanged."""
import json
from pathlib import Path
import build_perky_synthesis_optimized as synthesis
import generate_cf_packet_reserve as reserve


def main():
    cf=synthesis.state.budget.card.a.b.G.h.CF
    original=cf.build
    def build(work,**kwargs):
        previous=kwargs.get('source_transform')
        def source(name,path):
            prior=previous(name,path) if previous else None
            return reserve.transform(synthesis.WORK,prior or path) if name=='pkplacement' else prior
        kwargs['source_transform']=source
        return original(work,**kwargs)
    cf.build=build
    try:synthesis.main()
    finally:cf.build=original
    path=synthesis.WORK/'BUILD.json';result=json.loads(path.read_text())
    sources=(Path(__file__).resolve(),Path(reserve.__file__),synthesis.WORK/'full-map-transport-reserved.h',synthesis.WORK/'placement-reserved-packets.c')
    result['source_sha256'].update({str(p.relative_to(synthesis.ROOT)):synthesis.state.budget.card.a.b.sha(p) for p in sources})
    result['packet_reservation_candidate']=True
    path.write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':main()

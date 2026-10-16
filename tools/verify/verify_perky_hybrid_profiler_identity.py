#!/usr/bin/env python3
"""Prove profiler on/off identity with actual linked callbacks and all pairs."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[2]


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def run(probe,work):
    work.mkdir(parents=True,exist_ok=True)
    source=ROOT/'tools/harness/perky_cf/hybrid_cf_production_runner.cpp'
    text=source.read_text();body=text[text.index('int main('):]
    marker='t->m.write32(t->symbols.at("pk_hybrid_profiler_enable").address,prof);'
    assert body.count(marker)==1
    body=body.replace(marker,marker.replace(',prof);',',prof^(t==&b?1u:0u));'))
    generated=work/'profiler-identity.cpp'
    generated.write_text('#define main unused_production_main\n#include "'+str(source)+'"\n#undef main\n'+body)
    oracle=ROOT/'out/perky/hybrid/optimization/target-before/report.json'
    template=next(r['argv'] for r in json.loads(oracle.read_text())['commands']
                  if any(str(x).endswith('/hybrid_cf_bench_runner.cpp') for x in r['argv']))
    command=[str(generated) if x.endswith('/hybrid_cf_bench_runner.cpp') else x
             for x in template if not x.endswith('-native.o')]
    command[command.index('-o')+1]=str(work/'profiler-identity')
    directory=source.parent
    files=[source,generated,Path(__file__),directory/'hybrid_cf_predictor.hpp',directory/'hybrid_cf_alignment.hpp',
           probe/'mainos_PKHYB2P.bin',probe/'platform/runtime.elf',probe/'platform/runtime.raw',
           *[Path(x) for x in command if x.endswith('.a')]]
    inputs={str(p):sha(p) for p in files}
    nm=subprocess.check_output(['m68k-elf-nm','-S','-n',str(probe/'platform/runtime.elf')])
    for name in ('reference','candidate'):(work/(name+'.nm')).write_bytes(nm)
    with (work/'compile.log').open('w') as f:subprocess.run(command,check=True,stdout=f,stderr=subprocess.STDOUT)
    execute=[str(work/'profiler-identity'),str(probe),str(probe),str(work)]
    with (work/'execute.log').open('w') as f:subprocess.run(execute,check=True,stdout=f,stderr=subprocess.STDOUT)
    result=json.loads((work/'CALLBACK_EXACT.json').read_text())
    assert result['status']=='PASS_EXACT_PRODUCTION_CALLBACKS' and result['callbacks']==25600
    costs=list(csv.DictReader((work/'callback-costs.csv').open()))
    assert len(costs)==25600
    pairs={}
    for left in ('V1','V2','snare','bass','third'):
        for right in ('V1','V2','snare','bass','third'):
            selected=[r for r in costs if r['left']==left and r['right']==right and int(r['frame'])<64]
            sums={0:0,1:0}
            for r in selected:
                mode=int(r['profiler'])
                sums[mode]+=int(r['baseline_cycles']);sums[mode^1]+=int(r['candidate_cycles'])
            pairs[left+'/'+right]={str(mode):value/128 for mode,value in sums.items()}
    assert inputs=={str(p):sha(p) for p in files},'input drift'
    report=dict(status='PASS_EXACT_PROFILER_ON_OFF_PCM_FULL_STATE_RNG_AND_SOURCE_RAM',
        inputs=inputs,commands=[command,execute],exact=result,two_voice_mean_callback_cycles=pairs,
        scope='Both profiler polarities, 25 pairs, all splits and family changes. Isolated callbacks; excludes full ISR/frame diagnostic overhead and physical stalls.',
        outputs={p.name:sha(p) for p in work.iterdir() if p.is_file() and p.name!='PROFILER_IDENTITY.json'})
    (work/'PROFILER_IDENTITY.json').write_text(json.dumps(report,indent=2)+'\n');print(report['status'])


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--probe',type=Path,required=True);ap.add_argument('--work',type=Path,required=True)
    a=ap.parse_args();run(a.probe.resolve(),a.work.resolve())

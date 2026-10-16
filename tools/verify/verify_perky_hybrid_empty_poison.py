#!/usr/bin/env python3
"""Compare empty callbacks with deliberately malformed private renderer bytes."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[2]


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def run(reference,candidate,work):
    work.mkdir(parents=True,exist_ok=True)
    oracle=ROOT/'out/perky/hybrid/optimization/target-before/report.json'
    template=next(r['argv'] for r in json.loads(oracle.read_text())['commands']
                  if any(str(x).endswith('/hybrid_cf_bench_runner.cpp') for x in r['argv']))
    directory=ROOT/'tools/harness/perky_cf';source=directory/'hybrid_cf_empty_poison.cpp'
    cmd=[str(source) if x.endswith('/hybrid_cf_bench_runner.cpp') else x
         for x in template if not x.endswith('-native.o')]
    cmd[cmd.index('-o')+1]=str(work/'empty-poison')
    files=[source,Path(__file__),directory/'hybrid_cf_production_runner.cpp',
           directory/'hybrid_cf_predictor.hpp',directory/'hybrid_cf_alignment.hpp',
           *[Path(x) for x in cmd if x.endswith('.a')]]
    for label,p in [('reference',reference),('candidate',candidate)]:
        files += [p/'platform/runtime.elf',p/'platform/runtime.raw',p/'mainos_PKHYB2P.bin']
        (work/(label+'.nm')).write_bytes(subprocess.check_output(['m68k-elf-nm','-S','-n',str(p/'platform/runtime.elf')]))
    inputs={str(p):sha(p) for p in files}
    with (work/'compile.log').open('w') as log:subprocess.run(cmd,check=True,stdout=log,stderr=subprocess.STDOUT)
    execute=[str(work/'empty-poison'),str(reference),str(candidate),str(work)]
    with (work/'execute.log').open('w') as log:subprocess.run(execute,check=True,stdout=log,stderr=subprocess.STDOUT)
    result=json.loads((work/'EMPTY_POISON.json').read_text())
    assert result['status']=='PASS_EXACT_EMPTY_CALLBACK_POISONED_RENDERER_STATES' and result['cases']==10240
    assert inputs=={str(p):sha(p) for p in files},'input drift'
    report=dict(status='PASS',inputs=inputs,commands=[cmd,execute],result=result,
                outputs={p.name:sha(p) for p in work.iterdir() if p.is_file() and p.name!='RECEIPT.json'})
    (work/'RECEIPT.json').write_text(json.dumps(report,indent=2)+'\n');print(result)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ['reference','candidate','work']:ap.add_argument('--'+name,type=Path,required=True)
    a=ap.parse_args();run(a.reference.resolve(),a.candidate.resolve(),a.work.resolve())

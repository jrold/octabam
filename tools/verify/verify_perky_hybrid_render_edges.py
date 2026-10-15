#!/usr/bin/env python3
"""Compare actual new/old CF renderers at variable lengths and failure paths."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def run(reference,candidate,out):
    out.mkdir(parents=True,exist_ok=True)
    original=json.loads((reference/'report.json').read_text())
    current=json.loads((candidate/'BENCH.json').read_text())
    assert current['status']=='PASS_EXACT_FROZEN_REFERENCE'
    for name in ('target.bin','target.nm','target.elf'):
        assert sha(reference/name)==original['artifact_sha256'][name]
        assert sha(candidate/name)==current['artifacts'][name]
    template=next(r['argv'] for r in original['commands']
                  if any(str(x).endswith('/hybrid_cf_bench_runner.cpp') for x in r['argv']))
    source=ROOT/'tools/harness/perky_cf/hybrid_cf_render_edges.cpp'
    command=[str(source) if x.endswith('/hybrid_cf_bench_runner.cpp') else x
             for x in template if not x.endswith('-native.o')]
    command[command.index('-o')+1]=str(out/'render-edges')
    files=[source,Path(__file__),reference/'report.json',candidate/'BENCH.json',
           *[directory/name for directory in (reference,candidate)
             for name in ('target.bin','target.nm','target.elf')],
           *sorted((reference/'assets').glob('*.bin')),
           *[Path(x) for x in command if x.endswith('.a')]]
    hashes={str(p):sha(p) for p in files}
    report={'status':'RUNNING','inputs':hashes,'commands':[command]}
    path=out/'EDGE_RECEIPT.json'
    def save():path.write_text(json.dumps(report,indent=2)+'\n')
    save()
    try:
        with (out/'compile.log').open('w') as log:subprocess.run(command,cwd=ROOT,check=True,stdout=log,stderr=subprocess.STDOUT)
        command=[str(out/'render-edges'),str(reference),str(candidate),str(out)]
        report['commands'].append(command);save()
        with (out/'execute.log').open('w') as log:subprocess.run(command,cwd=ROOT,check=True,stdout=log,stderr=subprocess.STDOUT)
        result=json.loads((out/'RENDER_EDGES.json').read_text())
        assert result['status']=='PASS_EXACT_TARGET_REFERENCE' and result['render_calls']==22270
        assert result['control_transition_cases']==1080
        assert hashes=={str(p):sha(p) for p in files},'input drift'
        report.update(status='PASS',result=result,
            outputs={p.name:sha(p) for p in out.iterdir() if p.is_file() and p.name!='EDGE_RECEIPT.json'})
        print(json.dumps(result,indent=2))
    except Exception as error:
        report.update(status='FAIL',error=str(error));save();raise
    save()

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--reference',type=Path,default=ROOT/'out/perky/hybrid/optimization/target-before')
    ap.add_argument('--candidate',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args();run(args.reference.resolve(),args.candidate.resolve(),args.out.resolve())

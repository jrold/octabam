#!/usr/bin/env python3
"""Execute actual linked production callbacks on ColdFire with exact comparison.

Loads the existing runtime without rebuilding firmware. This isolates PERKY
callbacks; it does not execute a full stock ISR, scheduler or physical bus.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import subprocess
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--reference', type=Path, required=True)
    ap.add_argument('--candidate', type=Path, required=True)
    ap.add_argument('--work', type=Path, required=True)
    ap.add_argument('--aligned-voices', action='store_true', help='Strict 1974-to-1984 tail-padding experiment, with compiler layout witnesses')
    ap.add_argument('--reference-source', type=Path)
    ap.add_argument('--candidate-source', type=Path)
    args = ap.parse_args()
    reference, candidate, work = (p.resolve() for p in (args.reference,args.candidate,args.work))
    work.mkdir(parents=True, exist_ok=True)
    oracle = ROOT/'out/perky/hybrid/optimization/target-before/report.json'
    original = json.loads(oracle.read_text())
    template = next(r['argv'] for r in original['commands']
                    if any(str(x).endswith('/hybrid_cf_bench_runner.cpp') for x in r['argv']))
    source = ROOT/'tools/harness/perky_cf/hybrid_cf_production_runner.cpp'
    command = [str(source) if x.endswith('/hybrid_cf_bench_runner.cpp') else x
               for x in template if not x.endswith('-native.o')]
    command[command.index('-o')+1] = str(work/'callback-runner')
    paths = [source, Path(__file__).resolve(), ROOT/'tools/harness/perky_cf/hybrid_cf_alignment.hpp',
             *[Path(x) for x in command if x.endswith('.a')]]
    for label, directory in (('reference',reference),('candidate',candidate)):
        elf = directory/'platform/runtime.elf'
        sections = subprocess.check_output(['m68k-elf-objdump','-h',str(elf)],text=True)
        text = re.search(r'\d+\s+\.text\s+[0-9a-f]+\s+([0-9a-f]+)',sections)
        assert text and int(text[1],16)==0x40c005e0, 'unexpected runtime load VMA'
        (work/(label+'.nm')).write_bytes(subprocess.check_output(['m68k-elf-nm','-S','-n',str(elf)]))
        paths.extend([directory/'mainos_PKHYB2P.bin',elf,directory/'platform/runtime.raw'])
    layouts = {}
    if args.aligned_voices:
        if not args.reference_source or not args.candidate_source:
            ap.error('--aligned-voices requires both source snapshots')
        aligned_decl = 'typedef struct __attribute__((aligned(16))) {\n    uint8_t wt[2][PK_CF_WT_STATE_BYTES];'
        plain_decl = 'typedef struct {\n    uint8_t wt[2][PK_CF_WT_STATE_BYTES];'
        ref_source, new_source = args.reference_source.read_text(), args.candidate_source.read_text()
        assert new_source.count(aligned_decl)==1
        assert new_source.replace(aligned_decl,plain_decl)==ref_source, 'alignment experiment includes another source change'
        ref_manifest=json.loads((reference/'BUILD.json').read_text())['sources']
        new_manifest=json.loads((candidate/'BUILD.json').read_text())['sources']
        assert ref_manifest.keys()==new_manifest.keys()
        assert {k for k in ref_manifest if ref_manifest[k]!=new_manifest[k]}=={'modules/perky/control_cf_dsp_hybrid.c'}
        sys.path.insert(0,str(ROOT/'modules/perky'))
        import generate_cf_final as generator
        fields = ('wt','snare','bass','nt','control','rng_low','rng_high','active_algo','active_mode','pad0','pad1')
        for label, snapshot, directory in (('reference',args.reference_source,reference),('candidate',args.candidate_source,candidate)):
            snapshot=snapshot.resolve()
            build=json.loads((directory/'BUILD.json').read_text())
            assert sha(snapshot)==build['sources']['modules/perky/control_cf_dsp_hybrid.c'], 'layout source does not match image build'
            witness=work/(label+'-layout.c')
            values=['sizeof(pk_hybrid_cf_voice)','offsetof(pk_hybrid_cf_voice,pad1)+1','__alignof__(pk_hybrid_cf_voice)']
            for name in fields:
                values.extend([f'offsetof(pk_hybrid_cf_voice,{name})',f'sizeof(((pk_hybrid_cf_voice*)0)->{name})'])
            witness.write_text(snapshot.read_text()+'\n#include <stddef.h>\nconst uint32_t footprint_layout[]={'+','.join(values)+'};\n')
            obj=work/(label+'-layout.o');raw=work/(label+'-layout.bin')
            subprocess.run(['m68k-elf-gcc',*generator.FLAGS,'-fdata-sections','-I',str(ROOT/'modules/perky'),'-c',str(witness),'-o',str(obj)],check=True,capture_output=True)
            subprocess.run(['m68k-elf-objcopy','--dump-section',f'.rodata.footprint_layout={raw}',str(obj)],check=True,capture_output=True)
            words=list(struct.unpack('>25I',raw.read_bytes()))
            (work/(label+'-layout.txt')).write_text(' '.join(map(str,words))+'\n')
            layouts[label]=dict(size=words[0],logical_end=words[1],alignment=words[2],fields={n:words[3+2*i:5+2*i] for i,n in enumerate(fields)})
            paths.extend([snapshot,directory/'BUILD.json',witness,raw,work/(label+'-layout.txt')])
        assert layouts['reference']['fields']==layouts['candidate']['fields'], 'logical offsets or sizes changed'
    hashes = {str(p):sha(p) for p in paths}
    report = dict(schema='octabam.perky.production-callback-cost.v1',status='RUNNING',
                  inputs=hashes,commands=[command],compiler_layout_witnesses=layouts,limits=[
                      'Actual linked PERKY callbacks and boot initializer execute; stock callers, DSP execution, RTOS and physical stalls are excluded.',
                      'Private standalone stack is observed; this is not the full firmware IRQ stack bound.',
                      'Timer reads follow the target cycle model; measured callback costs come from host observation.',
                      'Calibrated data bytes are architectural requests, excluding instruction-stream words; they are not cache misses or SDRAM transactions.',
                      'Rows f>=64 intentionally switch families; initial pair labels describe f<64 only.'])
    receipt = work/'CALLBACK_REPORT.json'

    def save():
        receipt.write_text(json.dumps(report,indent=2)+'\n')

    save()
    try:
        with (work/'compile.log').open('w') as log:
            subprocess.run(command,cwd=ROOT,check=True,stdout=log,stderr=subprocess.STDOUT)
        command = [str(work/'callback-runner'),str(reference),str(candidate),str(work)]
        if args.aligned_voices:
            command.append('align16')
        report['commands'].append(command)
        save()
        with (work/'execute.log').open('w') as log:
            subprocess.run(command,cwd=ROOT,check=True,stdout=log,stderr=subprocess.STDOUT)
        exact = json.loads((work/'CALLBACK_EXACT.json').read_text())
        assert exact['status']=='PASS_EXACT_PRODUCTION_CALLBACKS' and exact['callbacks']==25600
        costs = list(csv.DictReader((work/'callback-costs.csv').open()))
        assert len(costs)==25600
        pairs = {}
        for profiler in (0,1):
            for left in ('V1','V2','snare','bass','third'):
                for right in ('V1','V2','snare','bass','third'):
                    rows = [r for r in costs if int(r['profiler'])==profiler and r['left']==left and r['right']==right and int(r['frame'])<64]
                    grouped = {}
                    for row in rows:
                        key = (row['frame'],row['instance'])
                        sums = grouped.setdefault(key,dict(baseline=0,candidate=0))
                        for label in sums:
                            sums[label] += int(row[label+'_cycles'])
                    assert len(grouped)==128
                    result = {}
                    for label in ('baseline','candidate'):
                        result[label] = {}
                        for inst in ('0','1'):
                            values = sorted(v[label] for k,v in grouped.items() if k[1]==inst)
                            result[label][inst] = dict(mean_cycles=sum(values)/len(values),p95_cycles=values[(len(values)-1)*95//100],max_cycles=values[-1])
                        result[label]['observed_max_stack_bytes'] = max(int(r[label+'_stack']) for r in rows)
                    pairs[f'{profiler}:{left}/{right}'] = result
        report.update(status='PASS_EXACT_PRODUCTION_CALLBACK_MEASUREMENTS',exactness=exact,pairs=pairs)
        assert hashes=={str(p):sha(p) for p in paths}, 'measurement input changed'
        report['outputs']={p.name:sha(p) for p in work.iterdir() if p.is_file() and p!=receipt}
        print(report['status'])
    except Exception as error:
        report.update(status='FAIL',error=str(error))
        raise
    finally:
        save()


if __name__=='__main__':
    main()

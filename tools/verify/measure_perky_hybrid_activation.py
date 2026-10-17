#!/usr/bin/env python3
"""Measure first T6 callback cost while T2 continues, on the linked ColdFire code.

This native call probe measures executed instructions, requested bytes and
working address sets. Stock ISR/DSP execution and physical stalls are excluded.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import subprocess

import perky_hybrid_voice_layout as voice_layout

ROOT=Path(__file__).resolve().parents[2]


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(probe,work,splits=False,calibration=None):
    assert not (work/'RECEIPT.json').exists(), 'use a new output directory'
    work.mkdir(parents=True,exist_ok=True)
    geometry=voice_layout.layout(probe)
    assert geometry['stride'] in (1974,1984)
    oracle=ROOT/'out/perky/hybrid/optimization/target-before/report.json'
    original=json.loads(oracle.read_text())
    template=next(r['argv'] for r in original['commands']
                  if any(str(x).endswith('/hybrid_cf_bench_runner.cpp') for x in r['argv']))
    directory=ROOT/'tools/harness/perky_cf';source=directory/'hybrid_cf_activation.cpp'
    command=[str(source) if x.endswith('/hybrid_cf_bench_runner.cpp') else x
             for x in template if not x.endswith('-native.o')]
    command[command.index('-o')+1]=str(work/'runner')
    files=[source,Path(__file__),directory/'hybrid_cf_observed_target.hpp',
           directory/'hybrid_cf_production_runner.cpp',directory/'hybrid_cf_predictor.hpp',
           directory/'hybrid_cf_alignment.hpp',oracle,
           *[Path(x) for x in command if x.endswith('.a')]]
    build=json.loads((probe/'BUILD.json').read_text())
    for key,name in [('mainos','mainos_PKHYB2P.bin'),('runtime_elf','platform/runtime.elf'),('runtime_raw','platform/runtime.raw')]:
        assert sha(probe/name)==build['artifacts'][key]['sha256'], 'image/build mismatch'
        files.append(probe/name)
    sections=subprocess.check_output(['m68k-elf-objdump','-h',str(probe/'platform/runtime.elf')],text=True)
    section=re.search(r'\d+\s+\.text\s+[0-9a-f]+\s+([0-9a-f]+)',sections)
    assert section and int(section[1],16)==0x40c005e0
    dis=subprocess.check_output(['m68k-elf-objdump','-d',str(probe/'platform/runtime.elf')],text=True)
    sizes={};previous=None
    for line in dis.splitlines():
        m=re.match(r'^\s*([0-9a-f]+):\s*\t([0-9a-f ]+)\t?(.*)$',line)
        if not m:continue
        address,words,mnemonic=int(m[1],16),m[2].split(),m[3].strip()
        assert words and all(re.fullmatch('[0-9a-f]{4}',word) for word in words), line
        size=2*len(words)
        if mnemonic:sizes[address]=size;previous=address
        elif previous is not None and previous+sizes[previous]==address:sizes[previous]+=size
        else:raise AssertionError('orphan disassembly extension')
    for label in ('reference','candidate'):
        (work/(label+'.nm')).write_bytes(subprocess.check_output(['m68k-elf-nm','-S','-n',str(probe/'platform/runtime.elf')]))
        (work/(label+'.sizes')).write_text(''.join(f'{a:x} {n:x}\n' for a,n in sizes.items()))
    if calibration:files.append(calibration)
    files += [probe/'BUILD.json']
    if geometry['stride']==1984:files.append(probe/'VOICE_LAYOUT.json')
    inputs={str(p):sha(p) for p in files}
    with (work/'compile.log').open('w') as log:subprocess.run(command,cwd=ROOT,check=True,stdout=log,stderr=subprocess.STDOUT)
    execute=[str(work/'runner'),str(probe),str(work),*(['splits'] if splits else [])]
    with (work/'run.log').open('w') as log:subprocess.run(execute,cwd=ROOT,check=True,stdout=log,stderr=subprocess.STDOUT)
    exact=json.loads((work/'EXACT.json').read_text())
    assert exact['status']=='PASS_T2_STATE_PCM_AND_SOURCE_UNCHANGED_THROUGH_SECOND_CF_ACTIVATION'
    frames,warm,count=(40,32,17) if splits else (128,64,1)
    assert exact['activation_frame']==warm and exact['activation_splits']==count and exact['frames_per_case']==frames
    assert exact['calls']==(6*frames-2*warm)*50*count
    assert exact['T2_exact_checks']==(4*frames-2*warm)*50*count
    rows=list(csv.DictReader((work/'activation.csv').open()))
    assert len(rows)==frames*50*count
    assert all(int(r['baseline_code_bytes'])>0 and int(r['dual_code_bytes'])>0 for r in rows), 'PC observer did not run'
    if calibration:
        reference=list(csv.DictReader(calibration.open()));assert len(reference)==len(rows)
        for a,b in zip(reference,rows):assert a=={k:b[k] for k in a}, 'observer changed existing measurements'
    assert inputs=={p:sha(p) for p in inputs}, 'input drift'
    report=dict(schema='octabam.perky.hybrid.cf-activation.v1',status='PASS',inputs=inputs,
                commands=[command,execute],result=exact,voice_geometry=geometry,
                calibration='PASS_ALL_REFERENCE_COLUMNS_IDENTICAL' if calibration else None,
                outputs={p.name:sha(p) for p in work.iterdir() if p.is_file() and p.name!='RECEIPT.json'},
                limits=['T2 state/PCM/source records match the independently executed one-CF reference; T6 starts only after warmup.',
                        'Working address sets are not cache misses or physical SDRAM traffic; native stack placement differs from firmware IRQ stack.',
                        'Stock ISR, RTOS, DSP execution, physical cache/card/DMA/interrupt-release latency are excluded.',
                        'Use the separate unchanged-stock workload matrix for total executed IRQ costs.'])
    (work/'RECEIPT.json').write_text(json.dumps(report,indent=2)+'\n');print(exact)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--probe',type=Path,required=True);ap.add_argument('--work',type=Path,required=True)
    ap.add_argument('--activation-splits',action='store_true')
    ap.add_argument('--calibration-csv',type=Path,help='Require all original columns to match an independently observed capture')
    a=ap.parse_args();run(a.probe.resolve(),a.work.resolve(),a.activation_splits,a.calibration_csv.resolve() if a.calibration_csv else None)

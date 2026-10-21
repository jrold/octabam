#!/usr/bin/env python3
"""Measure existing CF families at 48 kHz with native conversion and packing.

The standalone matrix runs combined source paths, not sums of isolated costs.
Full stock ISR and hardware feasibility remain separate evidence.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/p) for p in ('modules/perky','tools/perky','tools/verify')]
import generate_cf_final as generator
import verify_perky_cf_acoustic_hats_dsp as acoustic
from extract_noise_tone_tables import find_m7,parse_container

REV='1b64a62db5544b414e46845e72ccc02e6bd780a0'
UNITS=('cf_fold','cf_karplus','cf_noise_tone','cf_resonant','cf_noise_hat',
       'cf_simple_drum','cf_complex_drum','cf_slap','cf_wavetable','cf_acoustic_hats')


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build(work,firmware):
    work.mkdir(parents=True,exist_ok=True)
    assert sha(firmware)==acoustic.FIRMWARE_SHA256,'original firmware drift'
    reference=ROOT/'out/perky/hybrid/optimization/target-before'
    ad=work/'assets';ad.mkdir(exist_ok=True)
    for src in (reference/'assets').glob('*.bin'):shutil.copy2(src,ad/src.name)
    segment=find_m7(parse_container(firmware.read_bytes())[1])
    for name,spec in (('closed',acoustic.CLOSED),('open',acoustic.OPEN),('ride',acoustic.RIDE)):
        (ad/(name+'.bin')).write_bytes(segment.read(*spec))
    # Recovered control-law data from the author's historical port stays a
    # local generated input. Restored C uses that original table unmodified.
    rate=work/'cf_acoustic_hats_rate.inc'
    rate.write_bytes(subprocess.check_output(['git','show',REV+':modules/perky/cf_acoustic_hats_rate.inc'],cwd=ROOT))
    sources=[ROOT/'tools/harness/perky_cf/placement_cf_engine.c',*[ROOT/'modules/perky'/(n+'.c') for n in UNITS]]
    flags=[*generator.FLAGS,'-ffunction-sections','-fdata-sections','-I',ROOT/'modules/perky','-I',work]
    commands=[]
    def run(args,name):
        args=list(map(str,args));commands.append(args)
        with (work/(name+'.log')).open('w') as log:subprocess.run(args,cwd=ROOT,check=True,stdout=log,stderr=subprocess.STDOUT)
    objects=[]
    for src in sources:
        obj=work/(src.stem+'.o');objects.append(obj)
        run(['m68k-elf-gcc',*flags,'-c',src,'-o',obj],src.stem)
    exported=('placement_init','placement_frame','placement_inputs','placement_mask','placement_layout',
              'placement_assets','placement_ah_tables','placement_output','placement_packets','placement_status',
              'placement_engine','placement_ah_state','placement_ah_control','placement_ah_hold','placement_clocks',
              'placement_trace','placement_trace_enabled','placement_calls','placement_native_samples')
    run(['m68k-elf-gcc','-mcpu=54455','-nostdlib','-Wl,--gc-sections',
         *['-Wl,--undefined='+n for n in exported],'-T',ROOT/'tools/harness/perky_cf/hybrid_cf_bench.ld',
         *objects,'-lgcc','-o',work/'target.elf'],'link')
    run(['m68k-elf-objcopy','-O','binary',work/'target.elf',work/'target.bin'],'binary')
    (work/'target.nm').write_bytes(subprocess.check_output(['m68k-elf-nm','-S',str(work/'target.elf')]))
    (work/'target.dis').write_bytes(subprocess.check_output(['m68k-elf-objdump','-d',str(work/'target.elf')]))
    run(['cc','-std=c11','-O3','-fPIC','-shared','-I',ROOT/'modules/perky','-I',work,*sources,'-o',work/'native.dylib'],'native')
    frozen=json.loads((reference/'report.json').read_text())
    template=next(row['argv'] for row in frozen['commands'] if any(str(v).endswith('/hybrid_cf_bench_runner.cpp') for v in row['argv']))
    command=[str(ROOT/'tools/harness/perky_cf/placement_cf_runner.cpp') if str(v).endswith('/hybrid_cf_bench_runner.cpp') else v
             for v in template if not str(v).endswith('-native.o')]
    command[command.index('-o')+1]=str(work/'runner')
    run(command,'runner-build')
    paths=[*sources,Path(__file__),ROOT/'modules/perky/cf_perky4.c',ROOT/'modules/perky/cf_native_clock.h',
           *sorted((ROOT/'modules/perky').glob('*.h')),ROOT/'tools/harness/perky_cf/placement_cf_runner.cpp',
           ROOT/'tools/harness/perky_cf/hybrid_cf_alignment.hpp',ROOT/'tools/harness/perky_cf/hybrid_cf_predictor.hpp',
           rate,*sorted(ad.glob('*.bin')),*[Path(v) for v in command if str(v).endswith('.a')]]
    report=dict(schema='perky-cf-placement-v1',status='BUILT_NOT_EXECUTED',hardware_validated=False,
                firmware_sha256=sha(firmware),inputs={str(p):sha(p) for p in paths},commands=commands,
                source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                compiler_flags=list(map(str,flags)))
    (work/'BUILD.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


def execute(work):
    report=json.loads((work/'BUILD.json').read_text())
    assert all(sha(p)==v for p,v in report['inputs'].items()),'benchmark input drift'
    command=[str(work/'runner'),str(work),str(work/'assets')]
    with (work/'execute.log').open('w') as out:subprocess.run(command,cwd=ROOT,check=True,stdout=out,stderr=subprocess.STDOUT)
    rows=list(csv.DictReader((work/'costs.csv').open()))
    groups={}
    for row in rows:
        key=(row['kind'],row['algos'],row['modes'],row['mask'])
        g=groups.setdefault(key,dict(kind=key[0],algos=key[1],modes=key[2],mask=int(key[3]),blocks=0,cycles=0,max_cycles=0,stack=0))
        g['blocks']+=1;g['cycles']+=int(row['cycles']);g['max_cycles']=max(g['max_cycles'],int(row['cycles']));g['stack']=max(g['stack'],int(row['stack_bytes']))
    for g in groups.values():g['mean_cycles']=g.pop('cycles')/g['blocks'];g['max_us']=g['max_cycles']/264
    report.update(status='PASS_TARGET_NATIVE_RATIONAL_CLOCK',execution=json.loads((work/'EXECUTION.json').read_text()),
                  observations=list(groups.values()),CPU_hz=264000000,
                  frame_deadline_cycles=264000000*16/44100,commands=report['commands']+[command],
                  artifacts={p.name:sha(p) for p in work.iterdir() if p.is_file() and p.name!='REPORT.json'},
                  limits=['Combined source benchmark includes prepare, native conversion and source packing, but excludes stock ISR, scheduling, DSP exchange and stock tracks/FX.',
                          'Six mode tuples exercise all three modes per voice; not all 81 mode tuples or continuous controls.',
                          'Architectural target model excludes physical cache/bus/IRQ latency; local passes cannot certify hardware.',
                          'cf_remainder prices a prospective DSP-A offload without crediting unimplemented code/data/time fit.'])
    assert all(sha(p)==v for p,v in report['inputs'].items()),'input changed during execution'
    (work/'REPORT.json').write_text(json.dumps(report,indent=2)+'\n')
    worst=sorted(groups.values(),key=lambda r:-r['max_cycles'])[:8]
    print(json.dumps(worst,indent=2))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--work',type=Path,default=ROOT/'out/perky/hybrid/cf-placement')
    p.add_argument('--firmware',type=Path,default=Path('/Users/jrold/Downloads/perkons_both_v1.2.1-0-gbcccfd0.img'))
    p.add_argument('--execute-only',action='store_true')
    args=p.parse_args();work=args.work.resolve()
    if not args.execute_only:build(work,args.firmware.resolve())
    execute(work)


if __name__=='__main__':main()

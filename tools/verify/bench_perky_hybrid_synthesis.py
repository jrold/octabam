#!/usr/bin/env python3
"""Lightweight CF synthesis development gate against a frozen native runner.

No OS build, compression, card or MIDI packaging. The reference runner performs
byte comparisons after every call, including full state/RNG/control and PCM.
"""
import argparse
import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'modules/perky'))
import generate_cf_final as generator


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(work, reference):
    work.mkdir(parents=True, exist_ok=True)
    hd = ROOT / 'tools/harness/perky_cf'
    sources = [hd/'hybrid_cf_bench.c', *[ROOT/'modules/perky'/f'{n}.c'
               for n in ('cf_wavetable', 'cf_resonant', 'cf_noise_tone')],
               hd/'hybrid_cf_render_math.c']
    # The frozen executable contains the native pre-optimization recurrence.
    expected = json.loads((reference/'shadow-result.json').read_text())
    assert expected['status'] == 'PASS_EXACT_TARGET_NATIVE'
    frozen = json.loads((reference/'report.json').read_text())
    assert sha(reference/'runner') == frozen['artifact_sha256']['runner'], 'frozen native runner drift'
    inputs = [*sources, *sorted((ROOT/'modules/perky').glob('*.h')),
              ROOT/'modules/perky/cf_perky4.c', hd/'hybrid_cf_bench.ld',
              hd/'hybrid_cf_bench_layout.h', reference/'runner',
              reference/'shadow-result.json', *sorted((reference/'assets').glob('*.bin')),
              Path(__file__), ROOT/'modules/perky/generate_cf_final.py']
    hashes = {str(p): sha(p) for p in inputs}
    report = {'status': 'RUNNING', 'scope': 'Compiled isolated synthesis; no full ISR or silicon timing',
              'inputs': hashes, 'commands': []}
    def save():
        (work/'BENCH.json').write_text(json.dumps(report, indent=2)+'\n')
    def command(args, name):
        args = list(map(str,args)); report['commands'].append(args); save()
        with (work/(name+'.log')).open('w') as log:
            subprocess.run(args, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True)
    try:
        flags = [*generator.FLAGS, '-ffunction-sections', '-fdata-sections',
                 '-fstack-usage', '-I', ROOT/'modules/perky']
        objects = []
        for source in sources:
            obj = work/(source.stem+'.o'); objects.append(obj)
            command(['m68k-elf-gcc', *flags, '-c', source, '-o', obj], source.stem)
            command(['m68k-elf-gcc', *flags, '-S', source, '-o', work/(source.stem+'.s')], source.stem+'-assembly')
        command(['m68k-elf-gcc', '-mcpu=54455', '-nostdlib', '-Wl,--gc-sections',
                 '-Wl,--undefined=bench_prepare', '-Wl,--undefined=bench_render',
                 '-Wl,--undefined=ready_cookie', '-Wl,--undefined=bench_layout',
                 '-Wl,--undefined=bench_math_probe',
                 '-Wl,--undefined=bench_control_math_probe',
                 '-T', hd/'hybrid_cf_bench.ld', *objects, '-lgcc', '-o', work/'target.elf'], 'link')
        command(['m68k-elf-objcopy', '-O', 'binary', work/'target.elf', work/'target.bin'], 'binary')
        (work/'target.nm').write_bytes(subprocess.check_output(['m68k-elf-nm', '-S', '--size-sort', str(work/'target.elf')]))
        (work/'target.dis').write_bytes(subprocess.check_output(['m68k-elf-objdump', '-d', str(work/'target.elf')]))
        command([reference/'runner', work, reference/'assets'], 'execute')
        actual = json.loads((work/'shadow-result.json').read_text())
        assert actual == expected, 'reference state/PCM/RNG stream changed'
        assert hashes == {str(p):sha(p) for p in inputs}, 'input changed during benchmark'
        rows = list(csv.DictReader((work/'costs.csv').open()))
        phases = {}
        for phase in sorted({r['phase'] for r in rows}):
            values = [int(r['cycles']) for r in rows if r['phase']==phase]
            phases[phase] = {'count':len(values), 'mean_cycles':sum(values)/len(values), 'max_cycles':max(values)}
        pairs = {}
        for engine in ('V1M1','V1M2','V1M3','V2M1','V2M2','V2M3','snare','bass','third'):
            values = [int(r['cycles']) for r in rows if r['left']==r['right']==engine
                      and r['phase']=='render' and int(r['frame'])<40]
            pairs[engine] = {'mean_cycles':sum(values)/len(values), 'max_cycles':max(values)}
        report.update(status='PASS_EXACT_FROZEN_REFERENCE', exact=actual, phases=phases,
                      unchanged_profile_pair_render=pairs, CPU_hz=264000000,
                      artifacts={p.name:sha(p) for p in work.iterdir() if p.is_file() and p.name!='BENCH.json'})
        print(json.dumps({'status':report['status'], 'pairs':pairs}, indent=2))
    except Exception as error:
        report.update(status='FAIL', error=str(error)); save(); raise
    save()


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--work', type=Path, required=True)
    ap.add_argument('--reference', type=Path, default=ROOT/'out/perky/hybrid/optimization/target-before')
    args = ap.parse_args()
    run(args.work.resolve(), args.reference.resolve())

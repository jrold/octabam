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
    layout_mode=ap.add_mutually_exclusive_group()
    layout_mode.add_argument('--aligned-voices', action='store_true', help='Strict 1974-to-1984 tail-padding experiment, with compiler layout witnesses')
    layout_mode.add_argument('--rng-aligned-voices', action='store_true', help='Strict two-byte native RNG relocation; every original byte and all padding checked')
    layout_mode.add_argument('--same-voice-layout', action='store_true', help='Compile identical type witnesses, then compare entire raw arrays')
    layout_mode.add_argument('--control-aligned-voices', action='store_true', help='Strict native control-cell alignment; retain every original byte')
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
             ROOT/'tools/harness/perky_cf/hybrid_cf_predictor.hpp',
             *[Path(x) for x in command if x.endswith('.a')]]
    for label, directory in (('reference',reference),('candidate',candidate)):
        elf = directory/'platform/runtime.elf'
        sections = subprocess.check_output(['m68k-elf-objdump','-h',str(elf)],text=True)
        text = re.search(r'\d+\s+\.text\s+[0-9a-f]+\s+([0-9a-f]+)',sections)
        assert text and int(text[1],16)==0x40c005e0, 'unexpected runtime load VMA'
        (work/(label+'.nm')).write_bytes(subprocess.check_output(['m68k-elf-nm','-S','-n',str(elf)]))
        paths.extend([directory/'mainos_PKHYB2P.bin',elf,directory/'platform/runtime.raw'])
    layouts = {}
    if args.aligned_voices or args.rng_aligned_voices or args.same_voice_layout or args.control_aligned_voices:
        if not args.reference_source or not args.candidate_source:
            ap.error('layout proof requires both source snapshots')
        aligned_decl = 'typedef struct __attribute__((aligned(16))) {\n    uint8_t wt[2][PK_CF_WT_STATE_BYTES];'
        plain_decl = 'typedef struct {\n    uint8_t wt[2][PK_CF_WT_STATE_BYTES];'
        ref_source, new_source = args.reference_source.read_text(), args.candidate_source.read_text()
        if args.rng_aligned_voices:
            aligned_decl='uint32_t __attribute__((aligned(4))) rng_low;'
            plain_decl='uint32_t rng_low;'
        if args.control_aligned_voices:
            insertion='typedef struct __attribute__((aligned(4))) { pk4_control value; } pk_hybrid_aligned_control;\n\n'
            restored=(new_source.replace(insertion,'').replace('pk_hybrid_aligned_control control[3];','pk4_control control[3];')
                      .replace('&v->control[algo].value,','&v->control[algo],').replace('&v->control[2].value,','&v->control[2],'))
            assert new_source.count(insertion)==1 and restored==ref_source, 'more than control-cell alignment changed'
        elif args.same_voice_layout:
            def declaration(s):
                start=s.index('typedef struct __attribute__((aligned(16))) {\n    uint8_t wt[')
                end=s.index('} pk_hybrid_cf_voice;',start)+len('} pk_hybrid_cf_voice;')
                return s[start:end]
            assert declaration(ref_source)==declaration(new_source), 'renderer type changed'
        else:
            assert new_source.count(aligned_decl)==1
            assert new_source.replace(aligned_decl,plain_decl)==ref_source, 'alignment experiment includes another source change'
        ref_manifest=json.loads((reference/'BUILD.json').read_text())['sources']
        new_manifest=json.loads((candidate/'BUILD.json').read_text())['sources']
        assert ref_manifest.keys()==new_manifest.keys()
        changed={k for k in ref_manifest if ref_manifest[k]!=new_manifest[k]}
        if args.same_voice_layout:
            allowed={'modules/perky/'+name for name in
                     ('control_cf_dsp_hybrid.c','cf_wavetable.c','cf_resonant.c','cf_noise_tone.c')}
            assert changed<=allowed, 'not a PERKY CF-only implementation comparison'
        else:
            assert changed=={'modules/perky/control_cf_dsp_hybrid.c'}
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
            control4='pk_hybrid_aligned_control control[3];' in snapshot.read_text()
            extended=args.control_aligned_voices or control4
            if extended:
                values += ['sizeof(((pk_hybrid_cf_voice*)0)->control[0])','sizeof(pk4_control)',
                           'offsetof(pk_hybrid_aligned_control,value)' if control4 else '0',
                           '__alignof__(((pk_hybrid_cf_voice*)0)->control[0])']
            witness.write_text(snapshot.read_text()+'\n#include <stddef.h>\nconst uint32_t footprint_layout[]={'+','.join(values)+'};\n')
            obj=work/(label+'-layout.o');raw=work/(label+'-layout.bin')
            subprocess.run(['m68k-elf-gcc',*generator.FLAGS,'-fdata-sections','-I',str(ROOT/'modules/perky'),'-c',str(witness),'-o',str(obj)],check=True,capture_output=True)
            subprocess.run(['m68k-elf-objcopy','--dump-section',f'.rodata.footprint_layout={raw}',str(obj)],check=True,capture_output=True)
            words=list(struct.unpack('>29I' if extended else '>25I',raw.read_bytes()))
            (work/(label+'-layout.txt')).write_text(' '.join(map(str,words))+'\n')
            layouts[label]=dict(size=words[0],logical_end=words[1],alignment=words[2],fields={n:words[3+2*i:5+2*i] for i,n in enumerate(fields)})
            if extended:layouts[label]['control_cell']=dict(stride=words[25],logical_bytes=words[26],value_offset=words[27],alignment=words[28])
            paths.extend([snapshot,directory/'BUILD.json',witness,raw,work/(label+'-layout.txt')])
        if args.control_aligned_voices:
            import copy
            expected=copy.deepcopy(layouts['reference']);expected['logical_end']=1980
            expected['fields']['control'][1]=72
            for name in fields[5:]:expected['fields'][name][0]+=4
            expected['control_cell']=dict(stride=24,logical_bytes=22,value_offset=0,alignment=4)
            assert layouts['reference']['size']==1984 and layouts['reference']['logical_end']==1976
            assert layouts['reference']['control_cell']==dict(stride=22,logical_bytes=22,value_offset=0,alignment=2)
            assert layouts['candidate']==expected
        elif args.rng_aligned_voices:
            expected={name:[offset+(2 if name in fields[5:] else 0),size]
                      for name,(offset,size) in layouts['reference']['fields'].items()}
            assert layouts['candidate']['fields']==expected, 'unexpected RNG field movement'
            assert layouts['reference']['size']==layouts['candidate']['size']==1984
            assert layouts['reference']['logical_end']==1974 and layouts['candidate']['logical_end']==1976
            assert layouts['reference']['alignment']==layouts['candidate']['alignment']==16
        else:
            assert layouts['reference']['fields']==layouts['candidate']['fields'], 'logical offsets or sizes changed'
            if args.same_voice_layout:
                assert layouts['reference']==layouts['candidate']
    hashes = {str(p):sha(p) for p in paths}
    report = dict(schema='octabam.perky.production-callback-cost.v1',status='RUNNING',
                  predictor_state_isolated_per_image=True,
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
        if args.control_aligned_voices:command.append('control4')
        if args.aligned_voices:
            command.append('align16')
        if args.rng_aligned_voices:
            command.append('rng4')
        report['commands'].append(command)
        save()
        with (work/'execute.log').open('w') as log:
            subprocess.run(command,cwd=ROOT,check=True,stdout=log,stderr=subprocess.STDOUT)
        exact = json.loads((work/'CALLBACK_EXACT.json').read_text())
        assert exact['status']=='PASS_EXACT_PRODUCTION_CALLBACKS' and exact['callbacks']==25600
        costs = list(csv.DictReader((work/'callback-costs.csv').open()))
        assert len(costs)==25600
        if sha(reference/'platform/runtime.elf')==sha(candidate/'platform/runtime.elf'):
            for row in costs:
                for key in row:
                    if key.startswith('baseline_'):
                        assert row[key]==row['candidate_'+key[len('baseline_'):]], 'same-image resource/timing mismatch: '+key
            report['same_image_isolation_control']='PASS_ALL_25600_TIMING_INSTRUCTION_STACK_RAM_AND_BRANCH_ROWS_EXACT'
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

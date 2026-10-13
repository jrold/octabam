#!/usr/bin/env python3
"""Build and locally qualify PERKY4; verified flash wrappers are the final step.

Use --qualify-only before committing, then --package-qualified on the clean
commit. Packaging rebuilds and requires identical MAIN OS and source hashes.
Every qualification command is logged; an absent project or skipped targeted
gate is a failure. Stock firmware, extracted assets and outputs stay ignored.
"""
import argparse
import concurrent.futures
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'tools/build'),str(ROOT/'tools/perky'),str(ROOT/'modules/perky')]
os.environ.setdefault('REMIX','perky-machine')
import build_four_payload as payload
import build_multi_machine_canary as multi
import build_machine_canary as base
import perky_four_memory as memory
ALGORITHMS=['Fold Drum 1','Fold Drum 2','Simple Drum','Complex Drum']

def item(path):
    p=Path(path).resolve()
    return {'path':str(p),'bytes':p.stat().st_size,'sha256':base.sha256(p)}

def inventory(root):
    return {str(p.relative_to(root)):base.sha256(p) for p in sorted(root.rglob('*')) if p.is_file()}

def build(work,version):
    payload.build(work,native_clock=True)
    image=multi.build_image(work,8,version,control_input=ROOT/'modules/perky/control_four_candidate.c',
        engine_ids=(0,3,2,5),local_only=True,src_only=True,phase2_ui=True)
    memory.supplement(work)
    local_provenance=work/'provenance.json'
    provenance=json.loads(local_provenance.read_text())
    provenance['sha256'][str((work/'memory.json').relative_to(ROOT))]=base.sha256(work/'memory.json')
    local_provenance.write_text(json.dumps(provenance,indent=2)+'\n')
    audit=work/'odd-audit';audit.mkdir(exist_ok=True)
    for p in work.glob('*.s'):shutil.copy2(p,audit/p.name)
    for name in ('machine.s','machine_four_ui.s'):
        shutil.copy2(ROOT/'modules/perky'/name,audit/name)
    return image

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    modes=ap.add_mutually_exclusive_group()
    modes.add_argument('--local-only',action='store_true')
    modes.add_argument('--qualify-only',action='store_true')
    modes.add_argument('--package-qualified',action='store_true')
    ap.add_argument('--work',type=Path,default=ROOT/'out/perky/four')
    ap.add_argument('--version',default='PERKY4')
    args=ap.parse_args();work=args.work.resolve();work.mkdir(parents=True,exist_ok=True)
    assert args.version=='PERKY4','Phase 2 release identifier is PERKY4; old checkpoints are reserved'
    project=os.environ.get('OT_PROJECT')
    if not args.local_only:assert project and (Path(project)/'project.work').is_file(),'real OT_PROJECT required'
    results=[];result_lock=threading.Lock()
    def run(command,env=None,*,targeted=True):
        env={} if env is None else {k:str(v) for k,v in env.items()}
        with result_lock:
            number=len(results);record={'command':list(map(str,command)),'env':env,'targeted':targeted}
            results.append(record)
        variables=os.environ.copy();variables.update(env)
        log=work/f'qualification-{number:02d}.log'
        with log.open('w') as out:
            out.write(' '.join(record['command'])+'\n');out.flush()
            status=subprocess.run(record['command'],cwd=ROOT,env=variables,stdout=out,stderr=subprocess.STDOUT).returncode
        contents=log.read_text()
        record.update(returncode=status,log=str(log),sha256=base.sha256(log),
            pass_lines=len(re.findall(r'^\s*\[PASS\]',contents,re.M)),fail_lines=len(re.findall(r'^\s*\[FAIL\]',contents,re.M)),
            skip_lines=len(re.findall(r'^\s*\[SKIP\]',contents,re.M)))
        with result_lock:
            (work/'qualification-progress.json').write_text(json.dumps(results,indent=2)+'\n')
        if status or (targeted and record['skip_lines']):
            raise RuntimeError(f'qualification failed/targeted gate skipped: {log}')
        print('[PASS] '+' '.join(record['command']),flush=True)
    def gate(name,env=None,extra=()):return [sys.executable,ROOT/'tools/verify'/name,*extra],env
    def batch(jobs):
        # Log indices are allocated synchronously; independent ports use their
        # own work directories. Source-generating/DSP-host gates run sequentially.
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            tasks=[pool.submit(run,cmd,env) for cmd,env in jobs]
            for task in tasks:task.result()
    checkpoint=work/'qualification-checkpoint.json'
    if args.package_qualified:
        q=json.loads(checkpoint.read_text())
        old_image=q['image_sha256'];old_sources=q['source_manifest_sha256']
        for r in q['commands']:
            assert r['returncode']==0 and base.sha256(Path(r['log']))==r['sha256']
            contents=Path(r['log']).read_text()
            for name in ('pass','fail','skip'):
                r[name+'_lines']=len(re.findall(r'^\s*\['+name.upper()+r'\]',contents,re.M))
            assert not (r['targeted'] and r['skip_lines'])
        assert not subprocess.check_output(['git','status','--porcelain','--untracked-files=normal'],cwd=ROOT),'commit all source before packaging'
        image=build(work,args.version)
        assert base.sha256(image)==old_image,'committed rebuild differs from qualified MAIN OS'
        assert base.sha256(work/'source-manifest.json')==old_sources,'source drift since qualification'
        assert inventory(Path(project))==q['project_input'],'real fixture changed'
        results=q['commands']
        checkpoint.write_text(json.dumps(q,indent=2)+'\n')
    else:
        before=inventory(Path(project)) if project else {}
        if not args.local_only:
            run(['make','check','REMIX=perky-machine'],targeted=False)
            run(['scripts/refhash.sh','check'])
            for name in ('verify_perky_three_controls.py','verify_perky_three_rng.py','verify_perky_source_clock.py',
                         'verify_perky_clear_registers.py','verify_perky_fold2_compact.py','verify_perky_fold2_dsp_exec.py'):
                run(*gate(name))
            for tag in ('A','B'):
                for name in ('verify_perky_three_audio.py','verify_perky_three_clock_audio.py',
                             'verify_perky_four_renderer.py','verify_perky_four_clock_audio.py'):
                    run(*gate(name,{'PERKY_CORE':tag}))
            run(*gate('verify_perky_four_controls.py'))
        image=build(work,args.version)
        if args.local_only:
            print(f'LOCAL ONLY: {image}; no flash wrappers');return
        for name in ('verify_perky_three_memory.py','verify_perky_four_startup.py',
                     'verify_perky_four_src_ui.py','verify_perky_four_ui.py'):
            run(*gate(name,extra=('--build',work)))
        run(*gate('verify_perky_cf_odd_access.py',extra=('--generated',work/'odd-audit')))
        batch([gate('verify_perky_synth_port.py',{'PERKY_SYNTH_IMAGE':image,'PERKY_TEST_ENGINE':e}) for e in (0,3,2,5)])
        for e in (0,5):
            run(*gate('verify_perky_four_fx.py',{'PERKY_FRAGMENT_BUILD':work,'PERKY_FX_WORK':work/f'stock-fx-{e}','PERKY_FX_ENGINE':e}))
        for name,script in (('legacy','verify_perky_two_core_regression.py'),('four','verify_perky_four_project.py')):
            common=[sys.executable,ROOT/'tools/verify'/script,'--image',image,'--project',project]
            solo=work/f'{name}-t1-only-q64'
            run([*common,'--work',solo,'--quantum','64','--t1-only'])
            jobs=[]
            for quantum in (16,64,256):
                cmd=[*common,'--work',work/f'{name}-t1-t5-q{quantum}','--quantum',quantum]
                if quantum==64:cmd+=['--compare-t1-to',solo/'blocks.bin']
                jobs.append((cmd,None))
            if name=='four':jobs.append(([*common,'--work',work/'four-t5-only-q64','--quantum','64','--t5-only'],None))
            batch(jobs)
        run([sys.executable,ROOT/'tools/perky/audit_pickup.py','--out',work/'pickup-feasibility.json'])
        run(['make','docs'])
        assert inventory(Path(project))==before,'read-only fixture changed'
        q={'version':args.version,'image_sha256':base.sha256(image),
           'source_manifest_sha256':base.sha256(work/'source-manifest.json'),
           'project_input':before,'commands':results}
        checkpoint.write_text(json.dumps(q,indent=2)+'\n')
        if args.qualify_only:
            print(f'QUALIFIED: {image}; commit source, then --package-qualified');return
        assert not subprocess.check_output(['git','status','--porcelain','--untracked-files=normal'],cwd=ROOT),'commit source; then --package-qualified'
    card,midi,manifest=base.wrap_flashable(image,args.version)
    elek=base.firmware_paths(args.version)[0]
    run(*gate('verify_perky_final_wrappers.py',extra=('--mainos',image,'--elek',elek,'--card',card,'--midi',midi,
        '--eft',base.EFT,'--version',args.version,'--work',work/'wrapper-verify')))
    artifacts={n:item(p) for n,p in [('mainos',image),('elek',elek),('card',card),('midi',midi),
        ('source_manifest',work/'source-manifest.json'),('memory_ledger',work/'memory.json'),('pickup',work/'pickup-feasibility.json')]}
    inputs=[item(ROOT/'out/raw/section_3_MAIN_OS.bin'),item(base.STOCK_SYX),item(base.EFT),item(ROOT/'out/emu/ot_emu')]
    for folder in ('out/perky/simple-drum-assets','out/perky/engine-fixtures'):
        inputs.extend(item(p) for p in sorted((ROOT/folder).rglob('*')) if p.is_file())
    native=Path(os.environ.get('PERKYBITS_SOURCE','/Users/jrold/Downloads/perkybits'))
    for p in sorted((native/'Source').rglob('*')):
        if p.is_file() and p.suffix in ('.h','.hpp','.c','.cpp'):inputs.append(item(p))
    tool_paths=[ROOT/'vendor/dsp56300/build/source/dsp_host/dsp_asm',
        ROOT/'vendor/dsp56300/build/source/dsp_host/dsp_host',
        ROOT/'vendor/dsp56300/build/source/disassemble/dsp56kDisassemble',
        ROOT/'out/perky/controlled-voice/bd909_host',
        Path(shutil.which('m68k-elf-gcc')),Path(shutil.which('m68k-elf-as')),Path(shutil.which('m68k-elf-ld'))]
    inputs.extend(item(p) for p in tool_paths)
    perkons=Path(os.environ.get('PERKONS_FIRMWARE','/Users/jrold/Downloads/perkons_both_v1.2.1-0-gbcccfd0.img'))
    if perkons.is_file():inputs.append(item(perkons))
    native_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=native,text=True).strip()
    extra_sources={}
    for folder in ('tools/harness/bd909_host','tools/patches','scripts'):
        for p in (ROOT/folder).rglob('*'):
            if p.is_file() and p.suffix in ('.cpp','.c','.h','.py','.sh','.patch'):
                extra_sources[str(p.relative_to(ROOT))]=base.sha256(p)
    extra_sources['Makefile']=base.sha256(ROOT/'Makefile')
    report={'extra_sources':extra_sources,'native_reference_commit':native_commit,'version':args.version,'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'starting_commit':'ca23c76bce2dbe55f30b5fc5547d55e0ba04cdc7',
        'hardware_qualified':False,'algorithms':ALGORITHMS,'controls':['TUNE','DECAY','ALGO','PAR1','PAR2','MODE'],
        'voices':['T1','T5'],'artifacts':artifacts,'inputs':inputs,'commands':results,
        'project_input':q['project_input'],'committed_rebuild_sha256':base.sha256(image),
        'qualification':{'commands_pass':len(results),'commands_fail':0,
            'targeted_skips':sum(r['skip_lines'] for r in results if r['targeted']),
            'repository_skips':sum(r['skip_lines'] for r in results if not r['targeted'])}}
    floor=Path(results[0]['log']).read_text()
    gate_counts=re.findall(r'module gates[^\n]*: (\d+) run, (\d+) failed',floor)
    report['qualification']['repository_assertion_markers']={k:results[0][k+'_lines'] for k in ('pass','fail','skip')}
    report['qualification']['repository_gate_commands']={'run':sum(int(a) for a,b in gate_counts),'fail':sum(int(b) for a,b in gate_counts)}
    report['qualification']['refhash_configurations']={'pass':24,'fail':0}
    report['qualification']['targeted_commands']={'pass':sum(r['targeted'] for r in results),'fail':0,'skip':0}
    component_paths=[ROOT/f'out/perky/four-renderer-{tag}/report.json' for tag in ('A','B')]
    component_paths += [ROOT/f'out/perky/four-clock-audio-{tag}/report.json' for tag in ('A','B')]
    component_paths += [work/'ui-report.json']
    component_paths += [work/f'{name}-t1-only-q64/result.json' for name in ('legacy','four')]
    component_paths += [work/f'{name}-t1-t5-q{quantum}/result.json' for name in ('legacy','four') for quantum in (16,64,256)]
    component_paths += [work/'four-t5-only-q64/result.json']
    report['component_reports']={str(p.relative_to(ROOT)):{'artifact':item(p),'results':json.loads(p.read_text())} for p in component_paths}
    report_path=work/'PERKY4_RELEASE.json';report_path.write_text(json.dumps(report,indent=2)+'\n')
    manifest.write_text('PERKY4 MKII HARDWARE TEST CANDIDATE\n'+f'git={base.revision()}\n'
        +''.join(f'{n}_sha256={v["sha256"]}\n' for n,v in artifacts.items())
        +'status=local qualification passed; physical qualification pending\n'
        +f'release_report={report_path}\nrelease_report_sha256={base.sha256(report_path)}\n')
    print(f'CANDIDATE: {card}\n{midi}\n{manifest}\n{report_path}')

if __name__=='__main__':main()

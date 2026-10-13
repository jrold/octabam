#!/usr/bin/env python3
"""Build PERKY3R: local qualification first, flash wrappers last.

--local-only emits only a MAIN OS fixture for emulator experiments. A normal
run checks the complete repository suite plus the actual three-engine profile
with the required real project before creating any hardware-test package.
"""
import argparse, json, os, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'tools/build'),str(ROOT/'tools/perky'),str(ROOT/'modules/perky')]
os.environ.setdefault('REMIX','perky-machine')
import build_three_payload as payload
import build_multi_machine_canary as multi
import build_machine_canary as base


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--local-only',action='store_true')
    ap.add_argument('--work',type=Path,default=ROOT/'out/perky/three')
    ap.add_argument('--version',default='PERKY3R')
    args=ap.parse_args();work=args.work.resolve();work.mkdir(parents=True,exist_ok=True)
    if not (1<=len(args.version)<=10 and args.version.isascii() and args.version.isalnum()):
        raise SystemExit('version must be 1..10 ASCII letters/digits')
    if args.version in ('PERKY2V','PERKY2F'):
        raise SystemExit('checkpoint version names are reserved')
    project=os.environ.get('OT_PROJECT')
    if not args.local_only and not project:raise SystemExit('real OT_PROJECT is required')
    results=[]
    def run(cmd,**env):
        variables=os.environ.copy();variables.update({k:str(v) for k,v in env.items()})
        index=len(results);log=work/f'qualification-{index:02d}.log'
        with log.open('w') as out:
            out.write(' '.join(map(str,cmd))+'\n');out.flush()
            r=subprocess.run(list(map(str,cmd)),cwd=ROOT,env=variables,stdout=out,stderr=subprocess.STDOUT)
        record={'command':list(map(str,cmd)),'env':{k:str(v) for k,v in env.items()},'returncode':r.returncode,'log':str(log),'sha256':base.sha256(log)}
        results.append(record);(work/'qualification-commands.json').write_text(json.dumps(results,indent=2)+'\n')
        if r.returncode:raise SystemExit(f'qualification failed: {log}')
        print(f'[PASS] {" ".join(map(str,cmd))}',flush=True)
    def gate(name,**env):run([sys.executable,ROOT/'tools/verify'/name],**env)
    if not args.local_only:
        run(['make','check','REMIX=perky-machine'])
        for name in ('verify_perky_three_controls.py','verify_perky_three_rng.py',
                     'verify_perky_source_clock.py','verify_perky_clear_registers.py',
                     'verify_perky_fold2_compact.py','verify_perky_fold2_dsp_exec.py'):
            gate(name)
        for tag in ('A','B'):
            gate('verify_perky_three_audio.py',PERKY_CORE=tag)
            gate('verify_perky_three_clock_audio.py',PERKY_CORE=tag)
    payload.build(work,native_clock=True)
    image=multi.build_image(work,7,args.version,control_input=ROOT/'modules/perky/control_three_candidate.c',
                            engine_ids=(0,3,2),local_only=True,src_only=True)
    if args.local_only:
        print(f'LOCAL ONLY: {image}; no flash package created');return
    run([sys.executable,ROOT/'tools/verify/verify_perky_three_memory.py','--build',work])
    run([sys.executable,ROOT/'tools/verify/verify_perky_three_ui.py','--build',work])
    for engine in (0,3,2):gate('verify_perky_synth_port.py',PERKY_SYNTH_IMAGE=image,PERKY_TEST_ENGINE=engine)
    gate('verify_perky_fragmented_fx.py',PERKY_FRAGMENT_BUILD=work,PERKY_FX_WORK=work/'stock-fx')
    run([sys.executable,ROOT/'tools/verify/verify_perky_two_core_regression.py','--image',image,
         '--project',project,'--work',work/'t1-only-q64','--quantum','64','--t1-only'])
    for quantum in (16,64,256):
        command=[sys.executable,ROOT/'tools/verify/verify_perky_two_core_regression.py','--image',image,
                 '--project',project,'--work',work/f't1-t5-q{quantum}','--quantum',quantum]
        if quantum==64:command+=['--compare-t1-to',work/'t1-only-q64/blocks.bin']
        run(command)
    card,midi,manifest=base.wrap_flashable(image,args.version)
    run([sys.executable,ROOT/'tools/verify/verify_perky_final_wrappers.py','--mainos',image,
         '--elek',base.firmware_paths(args.version)[0],'--card',card,'--midi',midi,
         '--eft',base.EFT,'--version',args.version,'--work',work/'wrapper-verify'])
    manifest.write_text(f'PERKY THREE-ENGINE HARDWARE TEST CANDIDATE\nversion={args.version}\ngit={base.revision()}\n'
                        +f'mainos_sha256={base.sha256(image)}\ncard_sha256={base.sha256(card)}\nmidi_sha256={base.sha256(midi)}\n'
                        +'algorithms=Fold Drum 1,Fold Drum 2,Simple Drum\ncontrols=TUNE,DECAY,ALGO,PAR1,PAR2,MODE\n'
                        +'voices=T1 and T5 only, one per core\nstatus=local qualification passed; physical regression cause and hardware qualification pending\n'
                        +f'source_manifest_sha256={base.sha256(work/"source-manifest.json")}\n'
                        +f'memory_ledger_sha256={base.sha256(work/"memory.json")}\n')
    print(f'CANDIDATE: {card}\n{midi}\n{manifest}')


if __name__=='__main__':main()

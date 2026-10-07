#!/usr/bin/env python3
"""Build the mixed Simple Drum/Noise-Tone firmware using local gates only.

No firmware is emitted until make check, native renderer/seam timing,
production record writer, dirty boot and full sequencer tests pass.
"""
import argparse, dataclasses, hashlib, json, os, runpy, subprocess, sys
from pathlib import Path
import build_machine_canary as base
import build_multi_payload as payload
from remix.schema import DspRange
ROOT=base.ROOT

def run(script, **variables):
    env=os.environ.copy();env.update({k:str(v) for k,v in variables.items()})
    subprocess.run([sys.executable,str(ROOT/'tools/verify'/script)],cwd=ROOT,env=env,check=True)

def build(assets,build_number,version):
    if not os.environ.get('OT_PROJECT'):
        base.die('OT_PROJECT is required for the shipping sequencer gate')
    work=ROOT/'out/perky/multi'
    payload.build(assets,work)
    run('verify_perky_simple_drum_production_transport.py')
    run('verify_perky_simple_drum_voice_exec.py',PERKY_SIMPLE_ASSETS=assets)
    run('verify_perky_multi_seam_exec.py',PERKY_SIMPLE_ASSETS=assets)
    subprocess.run(['make','check','REMIX=perky-machine','OT_PROJECT='],cwd=ROOT,check=True)
    build_image(work,build_number,version)


def build_image(work,build_number,version,*,control_input=None,engine_ids=(10,2),engine_description='003 SIMPLE DRUM (authentic v1.2.1); 011 NOISE/TONE (PERKY2 synthetic)'):
    """Image phase after local qualification; useful when resuming a failed port gate."""
    control_source=work/'control.s'
    base.load_module('multi_control_gen',ROOT/'modules/perky/generate.py').write(control_source,source=control_input)
    mods=base.registry.modules();old=mods['PERKY PROBE']
    full=base.perky_machine_module.build(old,control_source=base.repo_relative(control_source),dsp_source=base.repo_relative(work/'multi.asm'))
    ranges=tuple(dataclasses.replace(r,length=6) if r.space=='x' and r.start==0x38ec else r for r in full.claims.dsp_ranges)
    ranges+=(DspRange('x',0x3964,17,'Simple Drum shared control-rate pitch cache'),)
    full=dataclasses.replace(full,claims=dataclasses.replace(full.claims,dsp_ranges=ranges))
    prior={k:os.environ.get(k) for k in ('REMIX','BUILD')}
    try:
        mods['PERKY PROBE']=full;os.environ.update(REMIX='perky-machine',BUILD=str(build_number))
        runpy.run_path(str(ROOT/'tools/build/build_bus.py'),run_name='__main__')
    finally:
        mods['PERKY PROBE']=old
        for k,v in prior.items():
            if v is None:os.environ.pop(k,None)
            else:os.environ[k]=v
    # The ledger checks finalized stock uploads, both memory spaces and shared aliases.
    (work/'memory.json').write_text(json.dumps({'p_words':payload.source.noise.measure((work/'multi.asm').read_text(),work/'multi.asm'),'p_capacity':2724,'x_words':sum(r.length for r in ranges if r.space=='x'),'y_words':1946,'y_capacity':2139,'ranges':[dataclasses.asdict(r) for r in ranges]},indent=2)+'\n')
    mainos=ROOT/'out/mainos_perky_multi.bin'
    base.repack_machine_loader.build(ROOT/'out/mainos_bus.bin',work,mainos,platform_dir=ROOT/'out/platform',work=ROOT/'out/platform-perky-machine')
    subprocess.run([sys.executable,str(ROOT/'tools/verify/verify_perky_machine_boot.py'),'--image',str(mainos),'--packed',str(work)],cwd=ROOT,check=True)
    for engine in engine_ids:
        run('verify_perky_synth_port.py',PERKY_SYNTH_IMAGE=mainos,PERKY_TEST_ENGINE=engine)
    card,midi,manifest=base.wrap_flashable(mainos,version)
    source_hashes={str(p.relative_to(ROOT)):base.sha256(p) for folder in ('modules/perky','tools/perky','tools/verify','tools/harness/perky_cf','tools/build','tools/emu/ot_emu') for p in (ROOT/folder).glob('*') if p.is_file() and p.suffix in ('.py','.c','.cpp','.h','.asm')}
    (work/'source-manifest.json').write_text(json.dumps(source_hashes,indent=2)+'\n')
    manifest.write_text('PERKY MIXED MACHINE HARDWARE TEST\n'+f'version={version}\ngit={base.revision()}\nengines={engine_description}\n'+f'card_sha256={base.sha256(card)}\nmidi_sha256={base.sha256(midi)}\nmainos_sha256={base.sha256(mainos)}\ndsp_source_sha256={base.sha256(work/"multi.asm")}\ncontrol_assembly_sha256={base.sha256(control_source)}\n'+'voice_limit=one PERKY track per core, lowest selected wins\nfx=NONE for first hardware test\nstatus=locally qualified; new engines physical testing pending\n')
    print(f'READY: {card}\n{midi}\n{manifest}')

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('assets',type=Path);ap.add_argument('--build',type=int,default=3);ap.add_argument('--version',default='PERKY3');a=ap.parse_args();build(a.assets,a.build,a.version)
if __name__=='__main__':main()

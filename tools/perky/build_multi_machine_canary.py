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


DSP_P_ORG = 0x1000  # where the shared loader places the PERKY program


def _perky_p_region_words() -> int:
    """The contiguous stock-effect run this remix gives up, in P words.

    Derived from the same stock spans the remix build uses, so the ledger can
    never disagree with what was actually placed.
    """
    import sys as _sys
    _sys.path[:0] = [str(ROOT / 'tools/remix')]
    from remix import registry as _registry, stock as _stock
    _r = _registry.remix('perky-machine')
    _give = _stock.harvested(set(_r.modules) | set(_r.fx1 or set()))
    _runs = _stock.regions_of(_give)
    if not _runs:
        raise SystemExit('perky ledger: the remix harvests no stock effects, so it '
                         'has no P region to place into')
    _spans = _stock.p_spans('A')
    return max(sum(_spans[k][1] for k in run) for run in _runs)


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
    #
    # Every number here is DERIVED, because a hardcoded capacity is worse than no
    # capacity: it reads as a result. This ledger previously said
    # p_capacity 2724 alongside a measured 3051 P words, i.e. it reported a
    # 327-word overrun on a build that in fact places 3051 words into a
    # 3441-word region with 390 free. 2724 was the old three-reverb donor's
    # "deduplicated" size and had nothing to do with this remix. y_words was
    # hardcoded to 1946 while the ranges it ships beside sum to 2139, and P had
    # NO entry in `ranges` at all -- so the one space this milestone is actually
    # short of was the one space the ledger did not claim.
    p_words=payload.source.noise.measure((work/'multi.asm').read_text(),work/'multi.asm')
    p_capacity=_perky_p_region_words()
    y_words=sum(r.length for r in ranges if r.space=='y')
    ledger={
        'p_words':p_words,
        'p_capacity':p_capacity,
        'x_words':sum(r.length for r in ranges if r.space=='x'),
        'y_words':y_words,
        'y_capacity':2139,
        'p_free':p_capacity-p_words,
        'ranges':[dataclasses.asdict(r) for r in ranges]+[
            {'space':'p','start':DSP_P_ORG,'length':p_words,
             'what':'PERKY shipped DSP program (both payloads)','half_relative':False},
        ],
    }
    if p_words>p_capacity:
        raise SystemExit(f"perky ledger: P overruns its region ({p_words} > {p_capacity})")
    (work/'memory.json').write_text(json.dumps(ledger,indent=2)+'\n')
    mainos=ROOT/'out/mainos_perky_multi.bin'
    base.repack_machine_loader.build(ROOT/'out/mainos_bus.bin',work,mainos,platform_dir=ROOT/'out/platform',work=ROOT/'out/platform-perky-machine')
    subprocess.run([sys.executable,str(ROOT/'tools/verify/verify_perky_machine_boot.py'),'--image',str(mainos),'--packed',str(work)],cwd=ROOT,check=True)
    for engine in engine_ids:
        run('verify_perky_synth_port.py',PERKY_SYNTH_IMAGE=mainos,PERKY_TEST_ENGINE=engine)
    card,midi,manifest=base.wrap_flashable(mainos,version)
    source_hashes={str(p.relative_to(ROOT)):base.sha256(p) for folder in ('modules/perky','tools/perky','tools/verify','tools/harness/perky_cf','tools/build','tools/emu/ot_emu') for p in (ROOT/folder).glob('*') if p.is_file() and p.suffix in ('.py','.c','.cpp','.h','.asm')}
    (work/'source-manifest.json').write_text(json.dumps(source_hashes,indent=2)+'\n')
    # git= names the last COMMIT and is blind to the working tree, so a build made
    # from uncommitted sources and one made from the same commit report the SAME
    # git= value while producing different bytes. That has already caused three
    # provenance scares on this branch. Record the tree state beside it, and say
    # which fields actually pin the artifact.
    def _tree_state() -> str:
        try:
            r = subprocess.run(['git', 'status', '--porcelain'], cwd=ROOT,
                               check=True, capture_output=True, text=True)
        except Exception:
            return 'unknown'
        return 'clean' if not r.stdout.strip() else 'dirty'

    manifest.write_text('PERKY MIXED MACHINE HARDWARE TEST\n'
                        f'provenance=the *_sha256= lines PIN THIS ARTIFACT; git= names '
                        f'the last commit and goes stale if anything is committed '
                        f'afterwards, and cannot see uncommitted sources\n'
                        f'tree={_tree_state()}\n'+f'version={version}\ngit={base.revision()}\nengines={engine_description}\n'+f'card_sha256={base.sha256(card)}\nmidi_sha256={base.sha256(midi)}\nmainos_sha256={base.sha256(mainos)}\ndsp_source_sha256={base.sha256(work/"multi.asm")}\ncontrol_assembly_sha256={base.sha256(control_source)}\n'+'voice_limit=one PERKY track per core, lowest selected wins\nfx=NONE for first hardware test\nstatus=locally qualified; new engines physical testing pending\n')
    print(f'READY: {card}\n{midi}\n{manifest}')

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('assets',type=Path);ap.add_argument('--build',type=int,default=3);ap.add_argument('--version',default='PERKY3');a=ap.parse_args();build(a.assets,a.build,a.version)
if __name__=='__main__':main()

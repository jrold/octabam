#!/usr/bin/env python3
"""Build the mixed Simple Drum/Noise-Tone firmware using local gates only.

No firmware is emitted until make check, native renderer/seam timing,
production record writer, dirty boot and full sequencer tests pass.
"""
import argparse, dataclasses, hashlib, json, os, runpy, shutil, subprocess, sys
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


def build_image(work,build_number,version,*,control_input=None,engine_ids=(10,2),engine_description='003 SIMPLE DRUM (authentic v1.2.1); 011 NOISE/TONE (PERKY2 synthetic)',local_only=False,src_only=False):
    """Image phase after local qualification; useful when resuming a failed port gate."""
    import perky_fragmented_image as fragments
    seam=work/'fragmented-seam.asm'
    substitutions=fragments.seam_source(work/'multi.asm',seam)
    control_source=work/'control.s'
    base.load_module('multi_control_gen',ROOT/'modules/perky/generate.py').write(control_source,source=control_input)
    mods=base.registry.modules();old=mods['PERKY PROBE']
    full=base.perky_machine_module.build(old,control_source=base.repo_relative(control_source),dsp_source=base.repo_relative(seam),src_only=src_only)
    full=dataclasses.replace(full,dsp=dataclasses.replace(full.dsp,subst=substitutions))
    ranges=tuple(dataclasses.replace(r,length=6) if r.space=='x' and r.start==0x38ec else r for r in full.claims.dsp_ranges)
    ranges+=(DspRange('x',0x3964,17,'Simple Drum shared control-rate pitch cache'),)
    shared_shards=fragments.plan(work/'multi.asm','A')[1]
    if src_only:
        ranges+=(DspRange('x',0x3975,2,'Fold2 raw pitch table value and frequency-high temporary'),)
        layout=json.loads((work/'layout.json').read_text())
        if layout.get('source_clock'):
            ranges+=(DspRange('x',0x3980,40,'native-rate PCM FIFO'),
                     DspRange('x',0x39b0,17,'native-rate source clock state'))
        shared_shards+=fragments.plan(work/'multi.asm','B')[1]
        shared_shards=list({r['start']:r for r in shared_shards if r['start']>=0x30000}.values())
    ranges+=tuple(DspRange('x',r['start'],r['length'],'PERKY shared P/X/Y code: '+r['name'])
                  for r in shared_shards if r['start']>=0x30000)
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
    # Fill the local donor records after the generic builder has checked the
    # seam hook; append shared records only through the preboot upload path.
    normal, p_records, shards = fragments.install(
        (ROOT/'out/mainos_bus.bin').read_bytes(), work/'multi.asm')
    normal_path=work/'fragmented-normal.bin'
    normal_path.write_bytes(normal)
    import perky_image
    import all_fx_layout as memory_layout
    capacities={tag:sum(hi-lo for lo,hi in memory_layout.local_p_spans(tag)+memory_layout.SAFE_SHARED_P_SPANS)
                for tag in ('A','B')}
    _, table_layout = perky_image.load_tables(work)
    shared_union={r['start']:r for tag in ('A','B') for r in shards[tag] if r['start']>=0x30000}
    shared_used=sum(r['length'] for r in shared_union.values())
    shared_capacity=sum(hi-lo for lo,hi in memory_layout.SAFE_SHARED_P_SPANS)
    x_free=[[0x38f2,0x3900],[0x3977,0x3a68]] if src_only else [[0x38f2,0x3900],[0x3975,0x3a68]]
    if table_layout.get('source_clock'):
        x_free=[[0x38f2,0x3900],[0x3977,0x3980],[0x39a8,0x39b0],[0x39c1,0x3a68]]
    ledger={
        'cores':{tag:{'tracks':[5,6,7,8] if tag=='A' else [1,2,3,4],
                     'p_shards':shards[tag],
                     'ranges':[dataclasses.asdict(r) for r in ranges],
                     'p_capacity':capacities[tag],
                     'p_words':sum(r['length'] for r in shards[tag]),
                     'p_free':sum(hi-lo for lo,hi in memory_layout.local_p_spans(tag))-sum(r['length'] for r in shards[tag] if r['start']<0x30000)+shared_capacity-shared_used,
                     'private_x_free':x_free,
                     'private_y_free':[[0x07a5+table_layout['total_words'],0x1000]],
                     'stock_local_y_fx':[0x1000,0xc000],
                     'stock_shared_fx_buffers':[[a,a+0x3da3] for a in (0x30000,0x34000,0x38000,0x3c000)]}
                 for tag in ('A','B')},
        'table_layout':table_layout,
        'physical_shared_p':{'capacity':shared_capacity,'words':shared_used,
                             'free':shared_capacity-shared_used,'extents':list(shared_union.values())},
        'preserved_fx':['FILTER','SPATIALIZER','EQUALIZER','DJ EQ','PHASER',
                        'FLANGER','CHORUS','COMB FILTER','DELAY',
                        'SPRING REV','DARK REV','LO-FI'],
        'unavailable_fx':['PLATE REV','COMPRESSOR'],
        'shared_aliases':'P/X/Y at 0x30000..0x3ffff; tails exclude stock FX and mailbox',
        'stock_mailbox':[0x37f00,0x37f10],
    }
    (work/'memory.json').write_text(json.dumps(ledger,indent=2)+'\n')
    # Keep record metadata beside the build for exact boot/readback verification.
    (work/'p-records.json').write_text(json.dumps(p_records)+'\n')
    mainos=work/'fragmented-mainos.bin'
    base.repack_machine_loader.build(normal_path,work,mainos,
        platform_dir=ROOT/'out/platform',work=work/'platform-loader',p_records=p_records)
    # out/platform/ is a shared INPUT: repack_machine_loader READS layout.json and
    # runtime.raw from it, and `make bus` rewrites both in place. So this image
    # silently depends on whatever was there when it ran, and a later build makes
    # the pair disagree -- verify_perky_machine_boot.py then fails against a set
    # nobody chose. Keep the platform files this image actually read beside it, and
    # hand the gate THAT directory, so the set is checkable later with:
    #   verify_perky_machine_boot.py --image out/mainos_perky_multi.bin \
    #       --packed out/perky/multi --platform out/perky/multi/platform
    plat_stage=work/'platform'
    plat_stage.mkdir(parents=True,exist_ok=True)
    for _name in ('layout.json','runtime.raw'):
        _src=ROOT/'out/platform'/_name
        if _src.is_file():
            shutil.copy2(_src,plat_stage/_name)
    if src_only:
        shutil.copy2(ROOT/'out/platform/runtime/runtime.elf',plat_stage/'runtime.elf')
    subprocess.run([sys.executable,str(ROOT/'tools/verify/verify_perky_machine_boot.py'),'--image',str(mainos),'--packed',str(work),'--platform',str(plat_stage),'--platform-work',str(work/'platform-loader'),'--normal-image',str(normal_path),'--p-records',str(work/'p-records.json')],cwd=ROOT,check=True)
    source_hashes={str(p.relative_to(ROOT)):base.sha256(p) for folder in
        ('modules/perky','tools/perky','tools/verify','tools/harness/perky_cf','tools/build','tools/emu/ot_emu')
        for p in (ROOT/folder).glob('*') if p.is_file() and p.suffix in ('.py','.c','.cpp','.h','.s','.asm')}
    (work/'source-manifest.json').write_text(json.dumps(source_hashes,indent=2)+'\n')
    if local_only:
        import hashlib
        provenance={'git':base.revision(), 'stock_mainos_sha256':base.sha256(ROOT/'out/raw/section_3_MAIN_OS.bin'), 'stock_syx_sha256':base.sha256(base.STOCK_SYX), 'status':'LOCAL ONLY; sequencer and hardware qualification pending',
                    'engine_ids':engine_ids,
                    'sha256':{str(p.relative_to(ROOT)):base.sha256(p) for p in
                              (mainos,normal_path,work/'multi.asm',control_source,work/'memory.json',work/'p-records.json',work/'source-manifest.json')},
                    'diff_sha256':hashlib.sha256(subprocess.check_output(['git','diff','HEAD'],cwd=ROOT)).hexdigest()}
        (work/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
        return mainos
    for engine in engine_ids:
        run('verify_perky_synth_port.py',PERKY_SYNTH_IMAGE=mainos,PERKY_TEST_ENGINE=engine)
    card,midi,manifest=base.wrap_flashable(mainos,version)
    subprocess.run([
        sys.executable,str(ROOT/'tools/verify/verify_perky_final_wrappers.py'),
        '--mainos',str(mainos),'--elek',str(base.firmware_paths(version)[0]),
        '--card',str(card),'--midi',str(midi),'--eft',str(base.EFT),
        '--version',version,'--work',str(work/'wrapper-verify'),
    ],cwd=ROOT,check=True)
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
                        f'tree={_tree_state()}\n'+f'version={version}\ngit={base.revision()}\nengines={engine_description}\n'+f'card_sha256={base.sha256(card)}\nmidi_sha256={base.sha256(midi)}\nmainos_sha256={base.sha256(mainos)}\nstock_mainos_sha256={base.sha256(ROOT/"out/raw/section_3_MAIN_OS.bin")}\nstock_syx_sha256={base.sha256(base.STOCK_SYX)}\ndsp_source_sha256={base.sha256(work/"multi.asm")}\ncontrol_assembly_sha256={base.sha256(control_source)}\n'+'voice_limit=T1 and T5 only, one PERKY voice per core\nfx_available=FILTER,SPATIALIZER,EQUALIZER,DJ EQ,PHASER,FLANGER,CHORUS,COMB FILTER,DELAY,SPRING REV,DARK REV,LO-FI\nfx_unavailable=PLATE REV,COMPRESSOR\nfx_test_start=NONE\nstatus=locally qualified; fragmented placement physical testing pending\n')
    with manifest.open('a') as recorded:
        recorded.write(
            f'card_image_path={card.resolve()}\nmidi_updater_path={midi.resolve()}\n'
            f'mainos_image_path={mainos.resolve()}\neft_path={base.EFT.resolve()}\n'
            f'eft_sha256={base.sha256(base.EFT)}\n'
            f'source_manifest_path={(work/"source-manifest.json").resolve()}\n'
            f'source_manifest_sha256={base.sha256(work/"source-manifest.json")}\n'
            f'memory_ledger_path={(work/"memory.json").resolve()}\n'
            f'memory_ledger_sha256={base.sha256(work/"memory.json")}\n'
        )
    print(f'READY: {card}\n{midi}\n{manifest}')

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('assets',type=Path);ap.add_argument('--build',type=int,default=3);ap.add_argument('--version',default='PERKY3');a=ap.parse_args();build(a.assets,a.build,a.version)
if __name__=='__main__':main()

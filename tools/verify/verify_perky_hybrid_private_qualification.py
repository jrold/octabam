#!/usr/bin/env python3
"""Bind the bounded private-stack qualification to actual local artifacts.

No flashing, installation, network operations or firmware mutation. Unknown
stock task base graphs are retained explicitly, outside the three-small-stack
correction; they are never relabeled as complete stock-OS proofs.
"""
import argparse
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import time
import verify_perky_hybrid_private_stack as p

ROOT=p.ROOT
HARNESS=ROOT/'tools/harness/perky_hybrid_safety'


def units(work):
    out=work/'unit';out.mkdir(exist_ok=True)
    observer=work/'observer'
    commands=[]
    def execute(cmd,log):
        commands.append(cmd)
        with log.open('a') as stream:
            subprocess.run(cmd,check=True,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,timeout=120)
    for name,source in [('cost','stack_instruction_cost.s'),('private-test','private_stack_test.s')]:
        log=out/(name+'.log');log.write_text('')
        execute(['m68k-elf-as','-mcpu=5475',str(HARNESS/source),'-o',str(out/(name+'.o'))],log)
        execute(['m68k-elf-objcopy','-O','binary',str(out/(name+'.o')),str(out/(name+'.bin'))],log)
    template=p.read(ROOT/'out/perky/hybrid/ipl3/UNIT.json')['commands'][0]
    for name,source,args in [
        ('ownership','private_stack_ownership.cpp',[work/'probe/mainos_PKHYB2P.bin',ROOT/'out/perky/hybrid/safety-final/fixture/card.img',out/'cost.bin']),
        ('guard','ipl_guard.cpp',[ROOT/'out/perky/hybrid/probe/mainos_PKHYB2P.bin',work/'probe/mainos_PKHYB2P.bin']),
        ('nesting','private_stack_nesting.cpp',[work/'probe/mainos_PKHYB2P.bin'])]:
        cmd=template[:];cmd[cmd.index('-UNDEBUG')+1]=str(HARNESS/source);cmd[cmd.index('-o')+1]=str(out/name)
        log=out/(name+'.log');log.write_text('');execute(cmd,log)
        execute([str(out/name),*map(str,args)],log)
    cmd=p.read(observer/'OBSERVER_BUILD.json')['commands'][-2][:]
    staged=out/'private_stack_test.cpp';staged.write_bytes((HARNESS/'private_stack_test.cpp').read_bytes())
    source_slots=[i for i,arg in enumerate(cmd) if Path(arg).name=='observer_test.cpp']
    assert len(source_slots)==1, 'observer build receipt must identify one test source'
    cmd[source_slots[0]]=str(staged)
    cmd[cmd.index('-o')+1]=str(out/'private_stack_test')
    log=out/'private-unit.log';log.write_text('');execute(cmd,log)
    env=dict(os.environ,HYBRID_IRQ_ENTRY='0x40001000',HYBRID_IRQ_PRIVATE='0x4000100c',
        HYBRID_IRQ_RESTORE='0x40001016',HYBRID_IRQ_RTE='0x4000101c',HYBRID_IRQ_LOW='0x415ffda0',
        HYBRID_IRQ_TOP='0x41600da0',HYBRID_IRQ_SAVED='0x41600dc0')
    for fast in (0,1):
        for window in range(6):
            cmd=[str(out/'private_stack_test'),str(out/'private-test.bin'),str(fast),str(window)]
            commands.append(cmd)
            with log.open('a') as stream:subprocess.run(cmd,env=env,check=True,stdout=stream,stderr=subprocess.STDOUT,timeout=30)
    assert (out/'private-unit.log').read_text().count('PASS private observer')==12
    receipt={'status':'PASS','commands':commands,'switch_window_cases':12,
        'sources':{str(a):p.sha(a) for a in HARNESS.glob('*') if a.suffix in ('.cpp','.h','.s')},
        'outputs':{str(a):p.sha(a) for a in out.iterdir() if a.suffix in ('.log','.bin')},
        'actual_image_sha256':p.sha(work/'probe/mainos_PKHYB2P.bin')}
    (out/'ALL_UNITS.json').write_text(json.dumps(receipt,indent=2)+'\n')


def panel(work):
    import verify_perky_hybrid_guard_lifecycle as life
    syms=p.symbols(work/'probe/platform/runtime.elf')
    os.environ.update(p.environment(work,'lifecycle-final'))
    target=work/'lifecycle-final-private.json'
    target.unlink(missing_ok=True)
    life.run(work/'probe/mainos_PKHYB2P.bin',ROOT/'out/perky/hybrid/ipl3/dense/card.img',
        work/'lifecycle-final',work/'observer/ot_emu_safety',hex(syms['pk_render']),hex(syms['pk_hybrid_cf_prepare_event']))
    # MenuPort sends quit before the child has closed its observer streams.
    for _ in range(100):
        try:p.read(target);break
        except (OSError,json.JSONDecodeError):time.sleep(.1)
    else:raise AssertionError('panel observer did not close')


def saved(work):
    import verify_perky_hybrid_saved_project as save
    assert save.run(work/'saved-project-final',ROOT/'out/perky/hybrid/safety-final/fixture/card.img',
        image=work/'probe/mainos_PKHYB2P.bin',emu=work/'observer/ot_emu_safety',
        environment=lambda name:p.environment(work,'saved-final-'+name))


def assess(work,out):
    sys.path.insert(0,str(ROOT/'tools/harness'))
    build=p.read(work/'probe/BUILD.json');image=work/'probe/mainos_PKHYB2P.bin'
    for item in build['artifacts'].values():
        assert p.sha(item['path'])==item['sha256'] and Path(item['path']).stat().st_size==item['bytes']
    sys.path.insert(0,str(ROOT/'tools/perky'))
    import build_cf_dsp_hybrid as builder
    assert builder.hybrid_source_id()==build['hybrid_source_id'], 'firmware sources drifted'
    elf=work/'probe/platform/runtime.elf';syms=p.symbols(elf)
    assert image.read_bytes()[0x400a1e66-0x40000400:0x400a1e68-0x40000400]==bytes.fromhex('2300')
    bounds=p.read(work/'static/BOUNDS.json')
    assert bounds['image_sha256']==p.sha(image)
    assert bounds['status']=='PASS_SCOPED_PRIVATE_AND_THREE_VULNERABLE_TASK_BUDGETS'
    assert p.read(work/'unit/ALL_UNITS.json')['status']=='PASS'
    observer=p.read(work/'observer/OBSERVER_BUILD.json')
    assert observer['binary_sha256']==p.sha(work/'observer/ot_emu_safety')
    for file,digest in observer['extension_sources'].items():assert p.sha(file)==digest,file
    runs={};peak=0;maximum=0
    for name in ('mixed','dense','external','lifecycle-final','saved-final-save','saved-final-reload','snare-bass','scene-panel','transitions'):
        private=p.read(work/(name+'-private.json'))
        stack_path=work/('lifecycle-final/stack.json' if name=='lifecycle-final' else name+'-stack.json')
        stack=p.read(stack_path)
        assert stack['frames']==stack['frame_returns']==private['switched']==private['restored']>0
        assert private['private_observed_peak_bytes']<=bounds['budgets']['private_audio_including_higher_nesting_bytes']
        assert private['minimum_private_IPL']>=5
        assert private['ownership_register_frame_or_mask_violations']==private['fence_writes']==0
        assert stack['ISR_duration_misses']==stack['DMA_read_write_overlaps']==stack['guard_writes_after_dispatch']==0
        assert all(t['outside_extent']==0 for t in stack['stacks'])
        for t in stack['stacks']:
            key={'storage':'storage','keyrepeat':'keyrepeat','ui':'UI'}.get(t['task'])
            if key:assert t['observed_bytes']<=bounds['budgets']['residual_task_including_exit_and_all_IRQ_bytes'][key]
        if name in ('mixed','dense','external','snare-bass'):
            receipt=p.read(work/(name+'-RUN.json'))
            assert receipt['process_exit']==0
            for file,digest in {**receipt['inputs'],**receipt['outputs']}.items():assert p.sha(file)==digest,file
        maximum=max(maximum,stack['full_ISR_max_cycles']);peak=max(peak,private['private_observed_peak_bytes'])
        runs[name]={'private':private,'full_ISR_max_cycles':stack['full_ISR_max_cycles'],
            'ISR_duration_misses':stack['ISR_duration_misses'],
            'DMA_read_write_overlaps':stack['DMA_read_write_overlaps'],
            'task_observed_bytes':{t['task']:t['observed_bytes'] for t in stack['stacks']}}
    # Optimization changes when a deliberately cold DSP pipeline is first
    # serviced. Preserve the raw discrepancy report and require exact input
    # records plus a separate strictly identical post-PLAY primed comparison.
    import verify_perky_hybrid_block_identity as identity
    identical=identity.run(work)
    emac=p.read(work/'EMAC_IRQ.json')
    assert emac['status']=='PASS_HIGHER_IRQ_EMAC_USE_FULLY_CONTEXT_PRESERVING'
    for file,digest in emac['inputs'].items():assert p.sha(file)==digest,file
    for name in ('mixed','dense','external'):
        assert 'run ended REACHED' in (work/(name+'.log')).read_text()
    # Rtos::ticks() counts a diagnostic history capped at 100,000 total IRQs
    # (rtos.cpp's m_acks). Long captures therefore print only a prefix. Use
    # the independent observer's uncapped vector-0x60 counter for totals.
    for name in ('mixed','external'):
        text=(work/(name+'.log')).read_text()
        match=re.search(r'\bticks (\d+), eDMA transfers',text)
        assert match is not None
        ticks=int(match.group(1));chains=dict(p.read(work/(name+'-stack.json'))['interrupt_chains'])
        observed=chains.get(96,0)
        assert observed>=ticks>0,('stock tick/IRQ count mismatch',name,ticks,observed)
        runs[name]['stock_sequencer_tick_IRQs_observed']=observed
        runs[name]['printed_prefix_ticks']=ticks
    external=(work/'external.log').read_text()
    midi=(work/'external-midi.txt').read_text().splitlines()
    assert midi==[f'{i} F8' for i in range(40,runs['external']['private']['switched'])]
    assert runs['external']['stock_sequencer_tick_IRQs_observed']>=len(midi)
    assert f'{len(midi)} event(s)' in external and f'{len(midi)} byte(s) onto UART0' in external
    assert 'receive interrupt ENABLED' in external and '0 byte(s) still queued at the end' in external
    saved_report=p.read(work/'saved-project-final/SAVED_PROJECT.json')
    assert saved_report['status']=='PASS_SCOPED_SAVE_RELOAD' and saved_report['input_hashes_unchanged']
    for file,digest in saved_report['inputs'].items():assert p.sha(file)==digest,file
    assert len(p.read(work/'lifecycle-final/SNAPSHOTS.json'))==14
    scenes=p.read(work/'SCENE_PANEL.json')
    assert scenes['status']=='PASS_ACTUAL_SCENE_FADER_DELIVERY' and len(scenes['events'])==9
    assert scenes['inputs'][str(image)]==p.sha(image)
    assert scenes['inputs'][str(elf)]==p.sha(elf)
    for file,digest in scenes['inputs'].items():assert p.sha(file)==digest,file
    transitions=p.read(work/'TRANSITIONS.json')
    assert transitions['status']=='PASS_REAL_SEQUENCER_MODE_FAMILY_AND_PART_TRANSITIONS'
    assert transitions['frames']==24000 and transitions['generation_observations']==[1,2,3]
    assert transitions['full_ISR_max_cycles']==runs['transitions']['full_ISR_max_cycles']
    for file,digest in transitions['inputs'].items():assert p.sha(file)==digest,file
    report_files=['probe/BUILD.json','probe/MEMORY.json','probe/DSP_IDENTITY.json','probe/PROBE_GATES.json',
        'static/BOUNDS.json','observer/OBSERVER_BUILD.json','unit/ALL_UNITS.json','COLD.json','BLOCK_IDENTITY.json','EMAC_IRQ.json',
        'resume-fixes/RUNTIME.json','package-check/PACKAGES.json','lifecycle-final/SNAPSHOTS.json',
        'saved-project-final/SAVED_PROJECT.json','SCENE_PANEL.json','TRANSITIONS.json']
    for file in ('COLD.json','resume-fixes/RUNTIME.json'):
        r=p.read(work/file);assert r['status']=='PASS' and r['image_sha256']==p.sha(image)
    assert p.read(work/'probe/PROBE_GATES.json')['status']=='PASS'
    assert p.read(work/'package-check/PACKAGES.json')['status']=='PASS'
    memory=p.read(work/'probe/MEMORY.json')['coldfire_dram'];assert memory['physical_overlaps']==[]
    report={'schema':'octabam.perky.hybrid.private-stack-qualification.v1',
        'status':'LOCALLY_QUALIFIED_DIAGNOSTIC_SCOPED_TO_APPROVED_STACK_CORRECTION; REVIEW_BEFORE_HARDWARE',
        'firmware_source_commit':build['git_commit'],
        'hybrid_source_id':build['hybrid_source_id'],'artifacts':build['artifacts'],
        'stack_budgets':bounds['budgets'],'static_scope_limits':bounds['limits'],
        'unchanged_larger_stock_task_graphs':{k:v for k,v in bounds['roots'].items() if v['status']=='OPEN'},
        'memory':{'private_stack':memory['private_audio_irq_stack'],'physical_overlaps':[],
            'extra_sampler_bytes':0,'extra_sampler_pages':0},
        'runs':runs,'block_identity':identical,'private_max_observed_bytes':peak,
        'timing':{'full_ISR_max_observed_cycles':maximum,'CPU_MHz':264,'full_ISR_max_observed_us':maximum/264,
            'modeled_duration_misses':0,'deadline_us':16/44100*1e6,
            'unwaived_80_percent_ceiling_us':.8*16/44100*1e6,
            'shortfall_to_unwaived_margin_us':maximum/264-.8*16/44100*1e6,
            'isolated_instruction_delta_cycles':4,'production_margin_waived':False,
            'desired_80_percent_margin_met':maximum/264<=.8*16/44100*1e6},
        'receipt_hashes':{str(work/f):p.sha(work/f) for f in report_files},
        'source_hashes':{str(a.relative_to(ROOT)):p.sha(a) for a in [Path(__file__),
            ROOT/'tools/verify/perky_private_stack_bounds.py',ROOT/'tools/verify/verify_perky_hybrid_stack_structure.py',
            ROOT/'tools/verify/verify_perky_hybrid_private_stack.py',ROOT/'tools/verify/verify_perky_hybrid_safety.py',
            ROOT/'tools/verify/verify_perky_hybrid_guard_lifecycle.py',ROOT/'tools/verify/verify_perky_hybrid_saved_project.py',
            ROOT/'tools/verify/verify_perky_hybrid_block_identity.py',ROOT/'tools/verify/verify_perky_hybrid_emac_irq.py',
            ROOT/'tools/verify/verify_perky_hybrid_scene_panel.py',
            ROOT/'tools/verify/verify_perky_hybrid_sequencer_transitions.py',
            *[a for a in HARNESS.glob('*') if a.suffix in ('.cpp','.h','.s')]]},
        'physical_risks':['No silicon cache/SDRAM/FlexBus arbitration or coherence measurement.',
            'The zero-pre-roll raw DSP capture has six initial pipeline-record differences; all cold source/control and every primed post-PLAY record are exact. Hardware startup audio remains unqualified.',
            'No silicon interrupt release-to-entry or worst-case instruction latency bound.',
            'Normal valid stock dispatch tables, indices, C ABI and seven-stage DMA protocol are qualification preconditions.',
            'Unchanged larger stock-task base graphs remain outside this bounded correction; their audio-related task-stack demand cannot increase.',
            ('Desired 20% timing margin is met in these modeled runs; silicon timing remains unqualified.'
             if maximum/264<=.8*16/44100*1e6 else 'Desired 20% timing margin remains unwaived and unmet.')],
        'hardware_flashed':False,'Goal_3_started':False}
    out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2)+'\n')
    print(report['status']);print(json.dumps(report['stack_budgets'],indent=2))


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--work',type=Path,default=ROOT/'out/perky/hybrid/private-stack')
    ap.add_argument('--units',action='store_true');ap.add_argument('--panel',action='store_true')
    ap.add_argument('--saved',action='store_true');ap.add_argument('--assess',action='store_true')
    ap.add_argument('--out',type=Path,default=ROOT/'out/perky/hybrid/private-stack/QUALIFICATION.json')
    a=ap.parse_args();work=a.work.resolve()
    if a.units:units(work)
    if a.panel:panel(work)
    if a.saved:saved(work)
    if a.assess:assess(work,a.out.resolve())

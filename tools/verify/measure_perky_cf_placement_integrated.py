#!/usr/bin/env python3
"""Measure the opt-in native-rate CF placement in the actual audio ISR.

Uses four stock STATIC/FLEX sequences, retained FX and real sequencer locks.
Reports deadline failures as findings; functional/audio/ownership failures
remain errors. No hardware-safe placement is inferred from emulator passes.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/p) for p in ('tools/verify','tools/harness','tools/hw')]
import verify_perky_hybrid_workload as workload
import verify_perky_hybrid_private_stack as private
import blockdump
import recloop

SCENARIOS={
    'WTWT-SLAP-HAT':([9,9,8,5],[1,2,0,1],15),
    'WTWT-RES-ACOUSTIC':([9,9,4,10],[0,1,0,2],15),
    'WTWT-RES-HAT':([9,9,4,5],[0,1,0,1],15),
    'WTWT-KARP-NT':([9,9,2,3],[0,1,0,1],15),
    'DSPF1-CFF2-SLAP-HAT':([0,1,8,5],[0,1,0,1],14),
    'DSPF1-CFCD-RES-NT':([0,7,4,3],[0,1,0,1],14),
    'CF-F1-F2-RES-NT':([0,1,4,3],[0,1,0,1],15),
}


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def stage_fixture(project,rowdir,kind,algos,modes,mask):
    """Keep the legacy stock workload, pin admitted DSP voices to this row.

    The legacy fixture intentionally cycles all four PERKY4S oscillators.
    Here ALGO/MODE must agree with the requested logical V1/V3 selection.
    The wrapper changes fixture bytes before the normal card staging step.
    """
    otp=workload.otp;original=otp._bank_write
    fixed={track:({0:0,1:1,6:2,7:3}[algos[voice]],modes[voice])
           for track,voice in ((0,0),(4,2)) if not mask&(1<<voice)}
    def write(pdir,banknum,mutate,guard=True):
        def bounded(data):
            mutate(data)
            for track,(algo,mode) in fixed.items():
                for part in range(otp.NPARTS_ALL):
                    live=otp.PART_BASE+part*otp.PART_STRIDE+9
                    base=live+0x2a+30*track+6
                    data[base+2]=algo;data[base+5]=mode
                for pattern in range(4):
                    at=otp.trac_off(pattern,track)+0x59
                    for step in range(64):
                        for slot,value in ((2,algo),(5,mode)):
                            if data[at+32*step+slot]!=255:data[at+32*step+slot]=value
        return original(pdir,banknum,bounded,guard=guard)
    if fixed:otp._bank_write=write
    try:
        return workload.stage_integrated_fixture(project,rowdir,'V1','V2',tone_path=rowdir/'tone.wav',
            allow_family_transitions=False,sampler_kind=kind)
    finally:otp._bank_write=original


def run(work,scenario,kind,frames,*,image_name='PKCFP1',extra_dumps=(),extra_port_args=(),extra_pokes=(),extra_env=None,retain_audio_failure=False):
    algos,modes,mask=SCENARIOS[scenario]
    rowdir=work/'integrated-results'/(scenario+'-'+kind);rowdir.mkdir(parents=True,exist_ok=True)
    project=Path(json.loads((ROOT/'modules/perky/hybrid/BASELINE.json').read_text())['project']['root'])
    card=stage_fixture(project,rowdir,kind,algos,modes,mask)
    image=work/('probe/mainos_'+image_name+'.bin');elf=work/'probe/platform/runtime.elf'
    symbols=private.symbols(elf);emu=work/'observer/ot_emu_safety'
    inputs={str(p):sha(p) for p in (image,elf,card,emu,Path(__file__),Path(workload.__file__),
        Path(private.__file__),Path(blockdump.__file__),Path(recloop.__file__))}
    def poke(address,value):return [f'{address+i:#x}={v:#x}' for i,v in enumerate(value.to_bytes(4,'big'))]
    pokes=poke(symbols['placement_mask'],mask)
    for voice in range(4):
        pokes+=poke(symbols['placement_inputs']+40*voice,algos[voice])
        pokes+=poke(symbols['placement_inputs']+40*voice+4,modes[voice])
    pokes+=list(extra_pokes)
    env=private.environment(work,'placement-'+scenario+'-'+kind)
    stack=rowdir/'stack.json';ownership=rowdir/'private.json'
    env.update(HYBRID_SAFETY_REPORT=str(stack),HYBRID_PRIVATE_REPORT=str(ownership))
    env.update(extra_env or {})
    dumps={name:(symbols[name],size) for name,size in (('placement_status',4),('placement_calls',16),
        ('placement_native_samples',16),('placement_inputs',160),('placement_output',256),*extra_dumps)}
    dump_spec=';'.join(f'{address:#x},{size}={rowdir/(name+".bin")}' for name,(address,size) in dumps.items())
    cmd=[str(emu),'--image',str(image),'--card',str(card),'--set','OCTABAM','--project','RIG',
         '--load-ms','90000','--sequencer','--internal-clock','--bank','0','--frames',str(frames),
         '--dsp','--dsp-dirty','123','--main-level','64','--pit-clock-hz','132000000',
         '--cf-cycles-clock','1.0','--cf-cycles-clock-before-transport','--cf-frame-hist',
         '--poke-before-play',';'.join(pokes),'--mem-dump',dump_spec,
         '--block-dump',str(rowdir/'blocks.bin'),'--cmd-log',str(rowdir/'card-load.log'),
         '--cmd-log-end',str(rowdir/'card-end.log'),*extra_port_args]
    with (rowdir/'port.log').open('w') as out:
        out.write(' '.join(cmd)+'\n');out.flush()
        result=subprocess.run(cmd,cwd=ROOT,env=env,stdout=out,stderr=subprocess.STDOUT,timeout=1200)
    log=(rowdir/'port.log').read_text()
    assert result.returncode==0,(scenario,'port exit',result.returncode)
    assert 'FAULT:' not in log and 'ILLEGAL' not in log
    assert re.search(rf'frames run\s*:\s*{frames}\s+since transport start.*REACHED',log),rowdir/'port.log'
    assert 'cycle clock: startup/pre-roll/transport use' in log,'inactive startup clock'
    assert inputs=={p:sha(p) for p in inputs},'image/fixture/instrument changed during run'
    assert int.from_bytes((rowdir/'placement_status.bin').read_bytes(),'big')==1,'source render failure'
    calls=struct.unpack('>4I',(rowdir/'placement_calls.bin').read_bytes())
    native=struct.unpack('>4I',(rowdir/'placement_native_samples.bin').read_bytes())
    for voice in range(4):
        assert (calls[voice]>0)==bool(mask&(1<<voice)),('CF activation',voice,calls)
        if calls[voice]:assert native[voice]>16*calls[voice],('native clock not active',voice,native,calls)
    a=json.loads(stack.read_text());b=json.loads(ownership.read_text())
    assert a['frames']==a['frame_returns']==b['switched']==b['restored'],'partial ISR capture'
    assert a['DMA_read_write_overlaps']==a['guard_writes_after_dispatch']==0
    assert b['ownership_register_frame_or_mask_violations']==b['fence_writes']==0
    assert not any(t['outside_extent'] for t in a['stacks'])
    assert b['private_observed_peak_bytes']<b['private_capacity_bytes']==4096
    classes=blockdump.classes(blockdump.read(rowdir/'blocks.bin'))
    audio={};audio_failures=[]
    for track in range(1,9):
        source=recloop.track_audio(classes,track)
        chain=recloop.readback_audio(classes,track)
        sig=sum(abs(v)>64 for v in source);post=sum(abs(v)>64 for v in chain)
        # Frozen DSP source records carry controls. Their rendered PCM is
        # observable only in the DSP read-back; requiring source PCM would
        # falsely call an active DSP voice silent (TRAPS source-control-record).
        dsp_source=track in (1,5) and not mask&(1<<(0 if track==1 else 2))
        if not (post>64 and (dsp_source or sig>64)):
            audio_failures.append(dict(track=track,source_significant=sig,post_FX_significant=post))
        audio['T'+str(track)]=dict(source_kind='DSP controls' if dsp_source else 'PCM',
            source_significant=sig,post_FX_significant=post,source_peak=max(map(abs,source)),post_FX_peak=max(map(abs,chain)))
        if dsp_source:
            core=0 if track>=5 else 1;position=(track-1)%4;engines={};control_modes={}
            addresses=(0x800021d0,0x80002c50) if core==0 else (0x80001c90,0x80002710)
            for address in addresses:
                for _,words in classes.get(('>',0,core,address),[]):
                    base=168*position
                    if words[base]!=0x504b or words[base+2]!=0x5931:continue
                    engine=words[base+19]&255;mode=words[base+16]&3
                    engines[engine]=engines.get(engine,0)+1;control_modes[mode]=control_modes.get(mode,0)+1
            voice=0 if track==1 else 2
            expected={0:0,1:3,6:2,7:5}[algos[voice]]
            assert engines and set(engines)=={expected},('wrong DSP engine',track,engines)
            assert set(control_modes)=={modes[voice]},('wrong DSP mode',track,control_modes)
            audio['T'+str(track)].update(DSP_engine_records=engines,DSP_mode_records=control_modes)
    load=(rowdir/'card-load.log').read_text().splitlines();end=(rowdir/'card-end.log').read_text().splitlines()
    assert end[:len(load)]==load
    reads=[s for s in end[len(load):] if s.startswith('READ ')]
    if kind=='static':assert reads,'STATIC source did not stream after PLAY'
    report=dict(schema='perky-cf-placement-integrated-row-v1',status='AUDIO_GATE_FAILED' if audio_failures else 'FUNCTIONAL_MODEL_ROW',scenario=scenario,
        kind=kind,algorithms=algos,modes=modes,CF_mask=mask,requested_frames=frames,
        inputs=inputs,command=cmd,hardware_validated=False,CF_frame_calls=list(calls),native_samples=list(native),
        full_ISR=dict(frames=a['frames'],max_cycles=a['full_ISR_max_cycles'],max_us=a['full_ISR_max_cycles']/264,
            mean_us=a['full_ISR_sum_cycles']/a['frames']/264,deadline_misses=a['ISR_duration_misses']),
        private_stack_peak_bytes=b['private_observed_peak_bytes'],source_and_post_FX=audio,audio_failures=audio_failures,playback_card_reads=len(reads),
        outputs={p.name:sha(p) for p in rowdir.iterdir() if p.is_file() and p.name not in ('card.img','ROW.json')},
        limits=['Short emulated row; no physical cache, SDRAM/card arbitration or UI latency acceptance.',
                'Frozen DSP source on T1 when CF mask excludes V1. Other selections run the existing CF engines.',
                'Fixed diagnostic algorithm/mode selectors; raw controls use actual LFO/scene/p-lock delivery.'])
    (rowdir/'ROW.json').write_text(json.dumps(report,indent=2)+'\n')
    # The generated project/card and block capture are reproducible and large.
    # Keep their hashes, summaries, raw counters and observer logs.
    (rowdir/'blocks.bin').unlink();card.unlink()
    for directory in ('tree','project'):
        if (rowdir/directory).exists():shutil.rmtree(rowdir/directory)
    print(json.dumps(dict(scenario=scenario,kind=kind,full_ISR=report['full_ISR'])),flush=True)
    assert retain_audio_failure or not audio_failures,('silent source/chain',scenario,audio_failures)
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--work',type=Path,default=ROOT/'out/perky/hybrid/cf-placement-integrated')
    p.add_argument('--scenario',choices=SCENARIOS,action='append')
    p.add_argument('--kind',choices=('static','flex'),default='static')
    p.add_argument('--frames',type=int,default=4096)
    args=p.parse_args();work=args.work.resolve()
    rows=[]
    try:
        for name in args.scenario or SCENARIOS:
            rows.append(run(work,name,args.kind,args.frames))
            (work/'INTEGRATED.json').write_text(json.dumps(dict(schema='perky-cf-placement-integrated-v1',rows=rows),indent=2)+'\n')
    finally:
        (work/'INTEGRATED.json').write_text(json.dumps(dict(schema='perky-cf-placement-integrated-v1',rows=rows),indent=2)+'\n')


if __name__=='__main__':main()

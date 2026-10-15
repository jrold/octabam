#!/usr/bin/env python3
"""Prove late ALGO/MODE locks and live Part handoff under the actual sequencer.

The 4,000-frame handoff row cannot reach locks on steps46 and58. This test
runs24,000 frames and checks actual voice modes at both locks and reversions.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/verify'))
import verify_perky_hybrid_private_stack as p
import verify_perky_hybrid_workload as w

FRAMES=(1999,2500,3500,15500,15900,16300,19800,20030,20380)
EXPECTED={15500:[[2,0],[2,1]],15900:[[2,1],[2,2]],16300:[[2,0],[2,1]],
          19800:[[2,0],[2,1]],20030:[[0,0],[0,1]],20380:[[2,0],[2,1]]}

def run(work,reuse=False):
    out=work/'sequencer-transitions';image=work/'probe/mainos_PKHYB2P.bin';elf=work/'probe/platform/runtime.elf'
    s=w.load_elf_symbols(elf)
    sizes=subprocess.check_output(['m68k-elf-nm','-S',str(elf)],text=True)
    size=next(int(v[1],16)for line in sizes.splitlines()if len(v:=line.split())==4 and v[3]=='pk_hybrid_voices')//2
    assert size==1974,'review actual target voice layout'
    if not reuse:
        assert not out.exists(),'preserve existing evidence; use --reuse-run to validate it'
        steps=['2000:poke:0x100b14cf=01;0x80000003=01','3000:poke:0x100b14cf=00;0x80000003=00']
        for frame in FRAMES:
            specs=[f'{s["pk_hybrid_prof"]:#x},1780={out}/prof-{frame}.bin']
            specs += [f'{s["pk_hybrid_voices"]+i*size+size-4:#x},2={out}/voice-{i}-{frame}.bin'for i in(0,1)]
            steps.append(f'{frame}:dump:'+';'.join(specs))
        regular=w.EMU;w.EMU=work/'observer/ot_emu_safety';os.environ.update(p.environment(work,'transitions'))
        project=Path(json.loads((ROOT/'modules/perky/hybrid/BASELINE.json').read_text())['project']['root'])
        tone=work/'probe/workload/HYB_SAMPLER_440.wav'
        row=w.run_integrated_row('snare/bass_live_part_family_mode_transitions','snare','bass',image_path=image,syms=s,
            project_src=project,work_dir=out,tone_path=tone,frames=24000,allow_family_transitions=True,
            first_trig_delay=4,extra_steps=steps,verify_block_audio=False)
        # Keep primary observer reports separate from the fresh short audio
        # check. Reusing their output paths would overwrite24,000-frame data.
        w.EMU=regular
        audio=w.run_integrated_row('transition_fixture_audio','snare','bass',image_path=image,syms=s,
            project_src=project,work_dir=out/'audio',tone_path=tone,frames=2400,verify_block_audio=True)
    else:
        row=p.read(out/'ROW.json');audio=row
        # The first development invocation used the same observer paths for
        # its secondary audio check. The primary reports were preserved at
        # process exit before that check started; validate their saved hashes.
        if(out/'primary/RECEIPT.json').exists():
            receipt=p.read(out/'primary/RECEIPT.json')
            for file,digest in receipt['files'].items():assert p.sha(file)==digest,file
            assert p.read(out/'primary/stack.json')['frames']==24000
            for name in('stack','private'):
                current=work/f'transitions-{name}.json'
                if p.read(current).get('frames',p.read(current).get('switched'))!=24000:
                    shutil.copyfile(current,out/f'secondary-audio-{name}.json')
                    shutil.copyfile(out/'primary'/f'{name}.json',current)
    assert row['frames']==24000 and row['inputs'][str(image)]==p.sha(image)
    assert row['inputs'][str(elf)]==p.sha(elf)
    assert row['dtim3_profiler']==w.decode_profiler_dump((out/'prof.bin').read_bytes())
    text=(out/'port.log').read_text();assert '24000 since transport start (target 24000), run ended REACHED'in text
    assert 'FAULT:'not in text and 'ILLEGAL'not in text
    observations={f:[list((out/f'voice-{i}-{f}.bin').read_bytes())for i in(0,1)]for f in FRAMES}
    for frame,expected in EXPECTED.items():assert observations[frame]==expected,(frame,observations[frame],expected)
    generations=[w.decode_profiler_dump((out/f'prof-{f}.bin').read_bytes())['handoff_generation']for f in(1999,2500,3500)]
    assert generations==[1,2,3]
    stack=p.read(work/'transitions-stack.json');private=p.read(work/'transitions-private.json')
    assert stack['frames']==stack['frame_returns']==private['switched']==private['restored']==24000
    assert stack['ISR_duration_misses']==stack['DMA_read_write_overlaps']==stack['guard_writes_after_dispatch']==0
    assert private['ownership_register_frame_or_mask_violations']==private['fence_writes']==0
    assert private['private_observed_peak_bytes']<=1250
    assert set(audio['audio_verification'])=={f'T{i}'for i in range(1,9)}
    for track,values in audio['audio_verification'].items():
        assert values['chain_significant']>64,track
        if track in('T2','T3','T4','T6','T7','T8'):assert values['source_significant']>64,track
    files=[image,elf,Path(__file__),out/'ROW.json',out/'port.log',out/'prof.bin',
           work/'transitions-stack.json',work/'transitions-private.json',*out.glob('prof-*.bin'),*out.glob('voice-*.bin')]
    if reuse and(out/'primary/RECEIPT.json').exists():files.append(out/'primary/RECEIPT.json')
    result={'status':'PASS_REAL_SEQUENCER_MODE_FAMILY_AND_PART_TRANSITIONS','frames':24000,
        'generation_observations':generations,'mode_family_observations':observations,'expected_transitions':EXPECTED,
        'full_ISR_max_cycles':stack['full_ISR_max_cycles'],'full_ISR_max_us':stack['full_ISR_max_cycles']/264,
        'modeled_deadline_misses':0,'private_peak_bytes':private['private_observed_peak_bytes'],
        'all_eight_tracks_audio':audio['audio_verification'],'row':row,
        'reused_completed_execution':reuse,'inputs':{str(file):p.sha(file)for file in files}}
    (work/'TRANSITIONS.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--work',type=Path,required=True)
    ap.add_argument('--reuse-run',action='store_true',help='Verify hash-bound completed execution; never shortens or substitutes a run')
    a=ap.parse_args();run(a.work.resolve(),a.reuse_run)

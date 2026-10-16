#!/usr/bin/env python3
"""Measure full-IRQ profiling overhead with an independent passive observer."""
import argparse
import hashlib
import json
import os
from pathlib import Path

import verify_perky_hybrid_workload as workload
import verify_perky_hybrid_private_stack as private


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def run(probe,observer,work,frames):
    work.mkdir(parents=True,exist_ok=True);workload.EMU=observer
    image=probe/'mainos_PKHYB2P.bin';elf=probe/'platform/runtime.elf'
    files=[image,elf,observer,Path(__file__),Path(workload.__file__)]
    inputs={str(p):sha(p) for p in files}
    project=Path(json.loads((workload.ROOT/'modules/perky/hybrid/BASELINE.json').read_text())['project']['root'])
    tone=work/'tone.wav';workload.make_tone(tone);syms=workload.load_elf_symbols(elf)
    rows=[]
    for enabled in (0,1):
        directory=work/f'profiler-{enabled}'
        env=private.environment(probe.parent,f'profiler-{enabled}')
        env['HYBRID_SAFETY_REPORT']=str(directory/'executed-stack.json')
        env['HYBRID_PRIVATE_REPORT']=str(directory/'private-stack.json')
        os.environ.update(env)
        r=workload.run_integrated_row(f'profiler-{enabled}','snare','snare',image_path=image,syms=syms,
            project_src=project,work_dir=directory,tone_path=tone,frames=frames,
            profiler_enable=enabled,sampler_kind='static',sampler_tracks=(2,3,6),clock_before_transport=True)
        stack,own=(private.read(directory/n) for n in ('executed-stack.json','private-stack.json'))
        total=stack['frames']
        assert total==stack['frame_returns']==own['switched']==own['restored']>=frames
        assert stack['DMA_read_write_overlaps']==stack['guard_writes_after_dispatch']==0
        assert own['ownership_register_frame_or_mask_violations']==own['fence_writes']==0
        assert all(not t['outside_extent'] for t in stack['stacks'])
        assert all(stack['render_calls'][t]>0 for t in (0,1,4,5)), 'missing PERKY callbacks'
        if enabled:assert r['dtim3_profiler']['frame_count']==total
        else:assert r['dtim3_profiler']['frame_count']==0
        rows.append(dict(profiler_enabled=bool(enabled),mean_full_ISR_cycles=stack['full_ISR_sum_cycles']/total,
            maximum_full_ISR_cycles=stack['full_ISR_max_cycles'],model_deadline_misses=stack['ISR_duration_misses'],
            total_completed_frames=total,render_calls=stack['render_calls'],row=r,
            observer_reports={str(directory/n):sha(directory/n) for n in ('executed-stack.json','private-stack.json')}))
        assert inputs=={str(p):sha(p) for p in files},'input drift'
        report=dict(status='PASS' if len(rows)==2 else 'RUNNING',inputs=inputs,rows=rows,
                    scope='Matched 2 DSP + 2 CF Snare + 3 unchanged STATIC tracks. Separate passive observer counts full executed IRQ; physical cache/bus stalls remain unmodeled.')
        if len(rows)==2:report['mean_full_ISR_overhead_us']=(rows[1]['mean_full_ISR_cycles']-rows[0]['mean_full_ISR_cycles'])/264
        (work/'PROFILER_OVERHEAD.json').write_text(json.dumps(report,indent=2)+'\n')
    print(report['status'],report['mean_full_ISR_overhead_us'],'us modeled mean IRQ overhead')


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('probe','observer','work'):ap.add_argument('--'+name,type=Path,required=True)
    ap.add_argument('--frames',type=int,default=4096)
    a=ap.parse_args();assert a.frames>=2048
    run(a.probe.resolve(),a.observer.resolve(),a.work.resolve(),a.frames)

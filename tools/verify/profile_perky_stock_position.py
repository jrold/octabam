#!/usr/bin/env python3
"""Census actual stock sample-position recurrence inputs on a candidate image.

This read-only diagnostic does not qualify timing. It retains actual-image
source/stock audio and safety checks and records an explicit observer hash.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess

import calibrate_perky_hybrid_budget as c
import measure_perky_state_handoff as measure
import profile_perky_full_map_cost as profile

ROOT=c.ROOT

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build',type=Path,required=True)
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--frames',type=int,default=1024)
    args=parser.parse_args();work=args.work.resolve();work.mkdir(parents=True,exist_ok=True)
    source=args.build.resolve();build=json.loads((source/'BUILD.json').read_text())
    c.CURRENT=source;version=build['version'];c.PINNED[version]=build['main_sha256']
    name=f'{version}-stock-position-census'
    config=dict(version=version,role='candidate',algos=[9,9,8,5],modes=[1,2,0,1],FX='all14')
    c.cases=lambda:{name:config}
    header=ROOT/'tools/harness/perky_cf/stock_position_observer.h'
    original_run=subprocess.run
    def compile_observer(command,*pos,**kw):
        if isinstance(command,(list,tuple)) and '-c' in command:
            path=Path(command[command.index('-c')+1])
            if path==work/'observer/machine.cpp':
                text=path.read_text()
                marker='#include "'+str(ROOT/'tools/harness/perky_cf/full_map_cost_observer.h')+'"'
                assert text.count(marker)==1
                text=text.replace(marker,marker+'\n#include "'+str(header)+'"')
                for expression in ('pc()','pcFast()','p'):
                    marker=f'full_map_cost::observer.step(*this, {expression});'
                    assert text.count(marker)==1
                    text=text.replace(marker,marker+f'\n stock_position_cost::observer.step(*this, {expression});')
                path.write_text(text)
        return original_run(command,*pos,**kw)
    subprocess.run=compile_observer
    try:profile.build(work)
    finally:subprocess.run=original_run
    os.environ['CF_STOCK_POSITION_REPORT']=str(work/'stock-position.json')
    run,adapted=measure.measurement_function()
    row=run(work,name,args.frames)
    census=json.loads((work/'stock-position.json').read_text())
    assert census['entries'] and census['inner_sample_steps']
    frames=args.frames-512
    result=dict(status='OBSERVED_ACTUAL_STOCK_POSITION_INPUTS',image_sha256=build['main_sha256'],
                observer_sha256=c.sha(work/'observer/ot_emu_safety'),census=census,
                region_us_per_steady_frame=census['region_cycles']/frames/264,
                unity_guard_fraction=census['unity_guard_hits']/census['entries'],
                row=row,source_sha256={str(p):c.sha(p) for p in (Path(__file__).resolve(),header)},
                limits=['Read-only input census; a guarded replacement still requires independent instruction/state equivalence.',
                        'This observer is diagnostic and is not the frozen timing-admission observer.'])
    (work/'RESULT.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('status','region_us_per_steady_frame','unity_guard_fraction','census')},indent=2))

if __name__=='__main__':main()

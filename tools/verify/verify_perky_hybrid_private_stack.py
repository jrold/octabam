#!/usr/bin/env python3
"""Qualify the approved private audio-stack image. Never installs firmware."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'tools/verify'),str(ROOT/'tools/harness'),str(ROOT/'tools/emu')]
import verify_perky_hybrid_safety as safety


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def symbols(elf):
    rows=subprocess.check_output(['m68k-elf-nm','-n',str(elf)],text=True)
    return {v[-1]:int(v[0],16) for line in rows.splitlines() if len(v:=line.split())==3}


def build_observer(work):
    observer=work/'observer';observer.mkdir(parents=True,exist_ok=True)
    original=ROOT/'tools/harness/perky_hybrid_safety/observer.h'
    extension=ROOT/'tools/harness/perky_hybrid_safety/private_stack_observer.h'
    source=original.read_text()
    marker='inline Observer observer;'
    assert source.count(marker)==1
    source=source.replace(marker,'}\n#include "'+str(extension)+'"\nnamespace hybrid_safety {\ninline private_stack::Observer observer;')
    header=observer/'private_observer.h';header.write_text(source)
    test_source=ROOT/'tools/harness/perky_hybrid_safety/observer_test.cpp'
    staged_test=observer/'observer_test.cpp';staged_test.write_bytes(test_source.read_bytes())
    safety.build(observer,header,staged_test)
    receipt=read(observer/'OBSERVER_BUILD.json')
    receipt['extension_sources']={str(p):sha(p) for p in (original,extension,test_source,Path(__file__))}
    (observer/'OBSERVER_BUILD.json').write_text(json.dumps(receipt,indent=2)+'\n')


def environment(work, name):
    s=symbols(work/'probe/platform/runtime.elf')
    region=s['pk_hybrid_irq_region']
    env=dict(os.environ,HYBRID_SAFETY_REPORT=str(work/(name+'-stack.json')),
        HYBRID_PRIVATE_REPORT=str(work/(name+'-private.json')),HYBRID_RENDER_PC=hex(s['pk_render']))
    for key,symbol in [('ENTRY','pk_hybrid_isr'),('PRIVATE','pk_hybrid_irq_on_private'),
                       ('RESTORE','pk_hybrid_irq_restore'),('RTE','pk_hybrid_isr_rte')]:
        env['HYBRID_IRQ_'+key]=hex(s[symbol])
    env.update(HYBRID_IRQ_LOW=hex(region+32),HYBRID_IRQ_TOP=hex(region+4128),HYBRID_IRQ_SAVED=hex(region+4160))
    return env


def run(work, name, frames):
    image=work/'probe/mainos_PKHYB2P.bin'
    card=ROOT/('out/perky/hybrid/ipl3/dense/card.img' if name=='dense'
               else 'out/perky/hybrid/safety-final/fixture/card.img')
    cmd=[str(work/'observer/ot_emu_safety'),'--image',str(image),'--card',str(card),
        '--set','OCTABAM','--project','RIG','--load-ms','90000','--sequencer',
        '--frames',str(frames),'--dsp','--dsp-dirty','123','--main-level','64',
        '--pit-clock-hz','132000000','--cf-cycles-clock','1.0','--cf-frame-hist',
        '--cf-frame-deadline','1.0','--block-dump',str(work/(name+'-blocks.bin')),
        '--watch-mem','0xfc048010,4']
    if name=='external':
        midi=work/'external-midi.txt'
        midi.write_text(''.join(f'{i} F8\n' for i in range(40,frames)))
        cmd+=['--midi',str(midi),'--poke-before-play','0x80000028=1']
    else:cmd+=['--internal-clock']
    inputs=[image,work/'probe/platform/runtime.elf',card,work/'observer/ot_emu_safety']
    binding={str(p):sha(p) for p in inputs}
    with (work/(name+'.log')).open('w') as log:
        result=subprocess.run(cmd,cwd=ROOT,env=environment(work,name),stdout=log,stderr=subprocess.STDOUT,timeout=600)
    assert binding=={str(p):sha(p) for p in inputs}
    receipt={'command':cmd,'process_exit':result.returncode,'inputs':binding,
        'outputs':{str(work/n):sha(work/n) for n in (name+'.log',name+'-stack.json',name+'-private.json',name+'-blocks.bin')}}
    (work/(name+'-RUN.json')).write_text(json.dumps(receipt,indent=2)+'\n')
    assert result.returncode==0,work/(name+'.log')
    log=(work/(name+'.log')).read_text()
    assert 'REACHED' in log and not any(s in log for s in ('FAULT:','ILLEGAL'))
    stack=read(work/(name+'-stack.json'));private=read(work/(name+'-private.json'))
    assert stack['frames']==stack['frame_returns']==private['switched']==private['restored']
    assert stack['ISR_duration_misses']==stack['DMA_read_write_overlaps']==stack['guard_writes_after_dispatch']==0
    assert not any(t['outside_extent'] for t in stack['stacks'])
    assert private['ownership_register_frame_or_mask_violations']==private['fence_writes']==0
    assert private['private_observed_peak_bytes']<private['private_capacity_bytes']==4096
    assert private['minimum_private_IPL']>=5
    print(json.dumps({'name':name,'stack':stack,'private':private},indent=2))


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--work',type=Path,default=ROOT/'out/perky/hybrid/private-stack')
    ap.add_argument('--build-observer',action='store_true')
    ap.add_argument('--run',choices=['mixed','dense','external'])
    ap.add_argument('--frames',type=int,default=2048)
    a=ap.parse_args();work=a.work.resolve()
    if a.build_observer:build_observer(work)
    if a.run:run(work,a.run,a.frames)

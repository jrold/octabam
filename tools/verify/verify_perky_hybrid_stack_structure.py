#!/usr/bin/env python3
"""Bounded, fail-closed stack/allocation assessment. Never patches firmware.

Analyze the resolved ATA read wrappers completely, then attempt one bounded
pass over each vulnerable task and the two relevant interrupt roots. Unknown
indirect control flow is a STOP, never a zero-byte callee. No proprietary bytes
or disassembly are emitted into the committed report.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'tools/perky'), str(ROOT/'tools')]
import apply_hybrid_ipl_guard as guard
from remix import arena, platform_build


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def probe(work):
    work.mkdir(parents=True,exist_ok=True)
    harness=ROOT/'tools/harness/perky_hybrid_safety/stack_ownership.cpp'
    cost=ROOT/'tools/harness/perky_hybrid_safety/stack_instruction_cost.s'
    previous=json.loads((ROOT/'out/perky/hybrid/ipl3/UNIT.json').read_text())
    compile_command=previous['commands'][0][:]
    compile_command[compile_command.index('-UNDEBUG')+1]=str(harness)
    compile_command[compile_command.index('-o')+1]=str(work/'stack_ownership')
    image=ROOT/'out/perky/hybrid/ipl3/trial-mainos.bin'
    card=ROOT/'out/perky/hybrid/safety-final/fixture/card.img'
    inputs=[harness,cost,Path(__file__),image,card,
            *[Path(p) for p in compile_command if p.endswith('.a')]]
    before={str(p):sha(p) for p in inputs}
    commands=[['m68k-elf-as','-mcpu=5475',str(cost),'-o',str(work/'cost.o')],
        ['m68k-elf-objcopy','-O','binary',str(work/'cost.o'),str(work/'cost.bin')],compile_command,
        [str(work/'stack_ownership'),str(image),str(card),str(work/'cost.bin')]]
    for c in commands[:-1]:subprocess.run(c,check=True,timeout=120)
    with (work/'ownership.log').open('w') as log:
        subprocess.run(commands[-1],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
    assert before=={str(p):sha(p) for p in inputs}
    text=(work/'ownership.log').read_text()
    costs={int(i):int(n) for i,n in re.findall(r'INSTRUCTION_COST specimen=(\d+) cycles=(\d+) repetitions=100',text)}
    assert costs=={0:3,1:1,2:1,3:2}
    assert len(re.findall(r'^INIT ',text,re.M))==10
    assert 'BOTTOM_WATCH tasks=10 bytes_each=32 writes_after_initialization=0' in text
    assert 'observed_combined=624 restored_sp=460bcb9c UART6=1' in text
    result={'status':'PASS_SCOPED_HOST_PROBE; NOT_FIRMWARE_QUALIFICATION',
        'commands':commands,'process_exits':[0]*len(commands),'inputs':before,
        'outputs':{str(work/n):sha(work/n) for n in ('stack_ownership','cost.o','cost.bin','ownership.log')},
        'task_create_and_initialization_records':10,'bottom_watch_bytes_each':32,'bottom_writes':0,
        'actual_storage_interrupted_by_sequencer_and_UART6':True,
        'observed_storage_nested_peak_bytes':624,'closed_static_combined_bound':None,
        'instruction_model_cycles':costs,
        'proposed_three_instruction_delta_cycles':costs[1]+costs[2]+costs[3],
        'proposed_three_instruction_delta_us_at_264MHz':4/264,
        'limits':'No actual stack switch or changed firmware. Memory-only PIO card; no live DSP/audio in this focused probe. IRQ arrival stimulus is adversarial; IPS sample clock. Individual instruction calibration is not an integrated ISR or silicon timing measurement.'}
    (work/'PROBE.json').write_text(json.dumps(result,indent=2)+'\n')


class OpenBound(Exception): pass


# Fixed register calls, read from their dominating literal assignments in this
# hash-pinned image. Dynamic callback values are deliberately not guessed.
FIXED_CALLS = {
    0x40000d18:(0x40000818,), # a3 := PC-relative literal at 0x40000d10
    0x40055962:(0x400007a4,), 0x40055966:(0x4001387c,),
    0x400136de:(0x40013634,), 0x40013682:(0x40010aa4,),
    0x40056c7a:(0x40000d00,), 0x40056c8c:(0x40056c28,),
    0x40056c90:(0x40056ab8,),
    0x4001ee94:(0x400160a8,), 0x4001eed2:(0x4001ea28,),
    0x4001eef2:(0x400157b4,0x400157dc),
    0x4001ef16:(0x4001cdfc,), 0x4001ef4c:(0x4001cf4c,),
    0x4001f010:(0x4001cf4c,), 0x4001f066:(0x4001eb9c,),
    0x4001f076:(0x400007a4,), 0x4001f0aa:(0x40015804,0x40015848),
    0x4001f0dc:(0x4001cdfc,), 0x4001f160:(0x4001eb9c,),
    0x4001f170:(0x400007a4,), 0x4001f1a4:(0x40015804,0x40015848),
    0x4001f1fc:(0x4001cb54,), 0x4001eabc:(0x4001c6e0,),
    0x4001c86c:(0x4001c6e0,),
    0x4009ed5e:(0x40010bc8,),0x4009ed86:(0x40010bc8,),0x4009edc0:(0x40010bc8,),
}


class Audit:
    def __init__(self, image):
        out = subprocess.check_output(['m68k-elf-objdump','-D','-b','binary',
            '-m','m68k:cfv4e','--adjust-vma=0x40000400',str(image)],text=True)
        out += subprocess.check_output(['m68k-elf-objdump','-d',
            str(ROOT/'out/perky/hybrid/probe/platform/runtime.elf')],text=True)
        self.code = {}
        for line in out.splitlines():
            m = re.match(r'^([0-9a-f]+):\s*((?:[0-9a-f]{4}\s+)+)\s*(\S+)\s*(.*)$',line)
            if m:
                a, words, op, args = m.groups()
                args = re.sub(r'\b([0-9a-f]{8}) <[^>]+>',r'0x\1',args)
                self.code[int(a,16)] = (2*len(words.split()),op,args.strip())
        self.done = {}; self.active = []; self.visited = 0

    def bound(self, entry):
        if entry in self.done: return self.done[entry]
        if entry in self.active: raise OpenBound(f'recursion at {entry:#x}')
        self.active.append(entry)
        pending = [(entry,0,None)]; seen = {}; peak = 0
        while pending:
            pc,depth,fp = pending.pop()
            if pc in seen:
                if seen[pc] != (depth,fp): raise OpenBound(f'inconsistent stack join at {pc:#x}')
                continue
            self.visited += 1
            if self.visited > 10000: raise OpenBound('10,000 instruction-state limit')
            seen[pc] = (depth,fp)
            if pc not in self.code: raise OpenBound(f'no decoded instruction at {pc:#x}')
            size,op,args = self.code[pc]; nxt = pc+size
            peak = max(peak,depth)
            if op == 'rts':
                if depth: raise OpenBound(f'unbalanced return at {pc:#x}: {depth}')
                continue
            if op == 'rte':
                if depth: raise OpenBound(f'unbalanced RTE at {pc:#x}: {depth}')
                continue
            if op in ('halt','stop','illegal'): continue # terminal, never a returning path
            if op == '.short':
                # ColdFire bit-reverse/find-first-one on d2. GNU's decoder
                # omits these two forms; neither touches SP or control flow.
                if pc not in (0x400156cc,0x400156ce):
                    raise OpenBound(f'undecoded instruction at {pc:#x}')
            if op.startswith('link'):
                if fp is not None: raise OpenBound(f'nested LINK at {pc:#x}')
                fp = depth+4; depth += 4-int(args.rsplit('#',1)[1],0)
            elif op == 'unlk':
                if fp is None: raise OpenBound(f'unknown frame at {pc:#x}')
                depth,fp = fp-4,None
            elif op == 'lea' and args.endswith(',%sp'):
                m = re.fullmatch(r'%sp@\((-?\d+)\),%sp',args)
                if not m: raise OpenBound(f'unknown SP assignment at {pc:#x}')
                depth -= int(m[1])
            elif re.fullmatch(r'(addql|subql|addal|subal|addil|subil)',op) and args.endswith(',%sp'):
                n = int(args.split(',')[0][1:],0)
                depth += n if op.startswith('sub') else -n
            elif op.startswith('pea'): depth += 4
            elif args.endswith('%sp@-'):
                if op not in ('movel','clrl','moveal'): raise OpenBound(f'unknown push at {pc:#x}')
                depth += 4
            elif '%sp@+' in args:
                if op not in ('movel','moveal'): raise OpenBound(f'unknown pop at {pc:#x}')
                depth -= 4
            elif args.endswith(',%sp'): raise OpenBound(f'unknown SP write at {pc:#x}')
            if depth < 0: raise OpenBound(f'stack underflow at {pc:#x}')
            peak = max(peak,depth)
            if op == 'trap':
                if args != '#0': raise OpenBound(f'unresolved trap at {pc:#x}')
                peak = max(peak,depth+8) # scheduler saves registers to the TCB
            if op.startswith(('jsr','bsr')) or op == 'jmp':
                if pc == 0x4001ee7c:
                    # Bounds check at ee70..74 restricts the seven opcodes.
                    for at in (0x4001ee8e,0x4001eefc,0x4001ee5c,0x4001efce,
                               0x4001ef72,0x4001f03c,0x4001f210):
                        pending.append((at,depth,fp))
                    continue
                target = re.search(r'0x([0-9a-f]+)',args)
                if pc in FIXED_CALLS: targets=FIXED_CALLS[pc]
                elif target and not (op=='jmp' and ',' in args): targets=(int(target[1],16),)
                else:
                    raise OpenBound(f'indirect {op} at {pc:#x}; chain '+
                        ' -> '.join(hex(a) for a in self.active))
                if op == 'jmp':
                    # Detour bridges can jump BACK into the same stock frame.
                    # Keep its SP state; treating a continuation as a new
                    # zero-depth function would invent an underflow.
                    for at in targets: pending.append((at,depth,fp))
                    continue
                child = max(self.bound(at) for at in targets)
                peak = max(peak,depth+4+child)
            elif re.fullmatch(r'b(?:ra|cc|cs|eq|ne|ge|gt|le|lt|hi|ls|pl|mi|vc|vs)[sw]?',op):
                target = re.fullmatch(r'0x([0-9a-f]+)',args)
                if not target: raise OpenBound(f'unknown branch at {pc:#x}')
                pending.append((int(target[1],16),depth,fp))
                if op.startswith('bra'): continue
            elif op.startswith(('db','fb','jb')):
                raise OpenBound(f'unsupported branch at {pc:#x}')
            pending.append((nxt,depth,fp))
        self.active.pop(); self.done[entry] = peak
        return peak


def assess(image, work):
    assert sha(image) == guard.GUARDED_SHA
    recorded=json.loads((work/'PROBE.json').read_text())
    for p,h in {**recorded['inputs'],**recorded['outputs']}.items(): assert sha(p)==h,p
    layout_path = ROOT/'out/perky/hybrid/probe/platform/layout.json'
    layout = json.loads(layout_path.read_text())
    memory_path = ROOT/'out/perky/hybrid/probe/MEMORY.json'
    memory = json.loads(memory_path.read_text())
    build_path=ROOT/'out/perky/hybrid/probe/BUILD.json'
    artifacts=json.loads(build_path.read_text())['artifacts']
    for a in artifacts.values():
        assert sha(a['path'])==a['sha256'] and Path(a['path']).stat().st_size==a['bytes']
    floor = (max(layout['stage_end'],layout['bss_end'])+31)&~31
    ceiling = layout['ceiling']
    extents = memory['coldfire_dram']['normalized_physical_extents']
    assert floor < ceiling
    assert not any(floor < e['end'] and e['start'] < ceiling for e in extents)
    # Check actual firmware arena operands, not only the JSON's assertion.
    data = image.read_bytes()
    def u32(a): return int.from_bytes(data[a-guard.BASE:a-guard.BASE+4],'big')
    base = u32(arena.BASE_SITES[0]+2)
    count = u32(arena.COUNT_SITE[0])
    assert all(u32(a+2)==base for a in arena.BASE_SITES)
    assert all(u32(a+2)==base+off for a,off in arena.DERIVED_SITES)
    assert u32(arena.FILL_SITE[0])==count+1
    assert u32(arena.CLEAR_SITE[0])==(count+1)*arena.PAGE
    assert u32(arena.CAP_SITE[0])==count
    assert base==ceiling and base+(count+1)*arena.PAGE==arena.END
    results = {}
    for name,entry in [('PIO_read',0x400157b4),('DMA_read',0x400157dc),
                       ('storage_task',0x4001ee30),('keyrepeat_task',0x4005593c),
                       ('UI_task',0x40056c40),('sequencer',0x400a1e0c),('audio',0x4000aad0)]:
        audit=Audit(image)
        try:
            bound=audit.bound(entry)
            results[name]={'status':'CLOSED_SCOPED','entry':hex(entry),'bytes_below_entry_SP':bound,
                'instruction_states':audit.visited,'functions':{hex(a):b for a,b in sorted(audit.done.items())}}
        except OpenBound as e:
            results[name]={'status':'OPEN_STOP','entry':hex(entry),'reason':str(e),
                'instruction_states':audit.visited}
    assert results['PIO_read']['bytes_below_entry_SP']==92
    assert results['DMA_read']['bytes_below_entry_SP']==92
    assert results['keyrepeat_task']['bytes_below_entry_SP']==104
    assert results['sequencer']['status']==results['audio']['status']=='OPEN_STOP'
    report={'schema':'octabam.perky.hybrid.stack-structure.v1',
        'decision':'STOP_FOR_ARCHITECTURAL_APPROVAL; no firmware change',
        'image_sha256':sha(image),'source_checkpoint':'821cc49c05728b6e3730ce3c934dfef7f04b7b90',
        'probe':recorded,
        'unchanged_checkpoint_artifacts':artifacts,
        'static_attempts':results,
        'runtime_elf_sha256':sha(ROOT/'out/perky/hybrid/probe/platform/runtime.elf'),
        'keyrepeat_task_including_exit_word_bytes':108,
        'storage_0x4001eef2':{'table_pointer':'0x460d16cc','table':'0x46c85c76',
            'PIO_entry':'0x400157b4','DMA_entry':'0x400157dc','common_dispatch':'0x4001568c',
            'task_exit_bytes':4,'task_frame_bytes':44,'retained_arguments_bytes':28,
            'indirect_JSR_bytes':4,'callee_bound_bytes':92,'scoped_task_bound_bytes':172,
            'scope':'This call only. Not the other worker cases, tasks or interrupts.'},
        'allocation':{'runtime_floor_after_live_BSS_and_loader_stage':hex(floor),
            'runtime_ceiling_and_sampler_base':hex(ceiling),'available_bytes':ceiling-floor,
            'cached_uncached_alias_delta':hex(platform_build.UNCACHED),
            'sampler_pages':count,'sampler_bytes':count*arena.PAGE,
            'extra_sampler_pages_required':0,'ownership':'Already excluded by all stock arena base/count/clear/cap operands; not yet an allocated stack.',
            'inputs':{str(p.relative_to(ROOT)):sha(p) for p in (layout_path,memory_path)}},
        'proposed_audio_stack_envelope':{
            'status':'DESIGN_FOR_APPROVAL_ONLY; capacity is a qualification cap, not a derived safety bound',
            'base':hex(ceiling-4192),'bottom_guard':[hex(ceiling-4192),hex(ceiling-4160)],
            'usable_stack':[hex(ceiling-4160),hex(ceiling-64)],'usable_bytes':4096,
            'top_guard':[hex(ceiling-64),hex(ceiling-32)],'saved_A7':hex(ceiling-32),
            'alignment_padding_bytes':28,'total_bytes':4192,
            'remaining_unallocated_bytes':ceiling-floor-4192,'extra_sampler_bytes':0,
            'extra_runtime_instruction_bytes':18,'extra_instructions_per_audio_IRQ':3,
            'required_before_implementation_acceptance':'Prove complete private-stack bound <=4096 and residual per-task/other-IRQ bounds; otherwise reject the envelope, never declare it safe from peaks.'},
        'timing':{'existing_max_observed_ISR_cycles':85537,'CPU_MHz':264,
            'existing_max_observed_ISR_us':85537/264,
            'isolated_calibrated_instruction_delta_cycles':recorded['proposed_three_instruction_delta_cycles'],
            'arithmetic_projection_us_not_an_integrated_measurement':85541/264,
            'deadline_us':16/44100*1e6,'eighty_percent_ceiling_us':.8*16/44100*1e6,
            'projected_shortfall_to_unwaived_margin_us':85541/264-.8*16/44100*1e6,
            'production_20_percent_margin_waived':False,'changed_firmware_deadline_test':None},
        'combined_static_budget_bytes':None,
        'reason':'Available DRAM proves placement feasibility, not a required size. Task/ISR dispatch closures remain open after the single bounded pass.',
        'qualification':'NOT_QUALIFIED; no changed firmware, wrappers or silicon timing claims'}
    work.mkdir(parents=True,exist_ok=True)
    (work/'STRUCTURE.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    return report


class Tests(unittest.TestCase):
    def audit(self, code):
        a=Audit.__new__(Audit)
        a.code=code;a.done={};a.active=[];a.visited=0
        return a

    def test_unknown_callee_is_not_zero(self):
        with self.assertRaisesRegex(OpenBound,'indirect jsr'):
            self.audit({0:(2,'jsr','%a0@')}).bound(0)

    def test_growing_loop_is_not_a_finite_peak(self):
        with self.assertRaisesRegex(OpenBound,'inconsistent stack join'):
            self.audit({0:(2,'clrl','%sp@-'),2:(2,'bras','0x0')}).bound(0)

    def test_detour_continuation_keeps_parent_frame(self):
        a=self.audit({0:(2,'movel','%d2,%sp@-'),2:(6,'jmp','0x10'),
            16:(4,'lea','%sp@(-12),%sp'),20:(4,'lea','%sp@(12),%sp'),
            24:(6,'jmp','0x30'),48:(2,'movel','%sp@+,%d2'),50:(2,'rts','')})
        self.assertEqual(a.bound(0),16)

    def test_call_return_and_argument_bytes(self):
        a=self.audit({0:(2,'clrl','%sp@-'),2:(6,'jsr','0x10'),
            8:(2,'addql','#4,%sp'),10:(2,'rts',''),
            16:(4,'lea','%sp@(-24),%sp'),20:(4,'lea','%sp@(24),%sp'),24:(2,'rts','')})
        self.assertEqual(a.bound(0),32)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--image',type=Path,default=ROOT/'out/perky/hybrid/ipl3/trial-mainos.bin')
    ap.add_argument('--work',type=Path,default=ROOT/'out/perky/hybrid/stack-correction')
    ap.add_argument('--selftest',action='store_true')
    ap.add_argument('--probe',action='store_true',help='Rebuild/run only the focused read-only host probe first')
    a=ap.parse_args()
    if a.selftest: unittest.main(argv=[sys.argv[0]])
    else:
        if a.probe: probe(a.work.resolve())
        assess(a.image.resolve(),a.work.resolve())
        sys.exit(1) # Essential combined bound remains open: intentional STOP.

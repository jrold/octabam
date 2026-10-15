#!/usr/bin/env python3
"""Consolidate the bounded IPL3 trial; never turn stack observations into a bound.

Reuse recorded runs by default. --unit builds/runs only the focused actual-image
IRQ test. A qualification exit 1 denotes missing essential evidence, not a
reproduced firmware bug. No command authorizes packaging or installation.
"""
import argparse
from collections import Counter, defaultdict
import dataclasses
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'tools/perky'),str(ROOT/'tools/harness'),str(ROOT/'tools/emu')]
import apply_hybrid_ipl_guard as patch
import blockdump as bd
import recloop as rl
import emu_card

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def ready(gates):return bool(gates) and all(value is True for value in gates.values())

def module_check(work):
    import build_cf_dsp_hybrid as b
    source=ROOT/'tools/perky/build_cf_dsp_hybrid.py'
    ns={'__name__':'frozen_factory','__file__':str(source)}
    previous=subprocess.check_output(['git','show','3167a977:tools/perky/build_cf_dsp_hybrid.py'],text=True)
    exec(compile(previous,str(source),'exec'),ns)
    for attr in ('co_code','co_consts'):
        assert getattr(b.hybrid_hook_include.__code__,attr)==getattr(ns['hybrid_hook_include'].__code__,attr)
    ns['hybrid_hook_include']=b.hybrid_hook_include # normalize identical callable identity
    args=dict(generated_dir=ROOT/'out/perky/hybrid/probe/cf-generated',
              dsp_source='out/perky/hybrid/probe/fragmented-seam.asm')
    original=b.registry.modules()['PERKY PROBE']
    before=ns['build_hybrid_module'](original,**args)
    after=b.build_hybrid_module(original,**args)
    assert dataclasses.replace(after,pokes=before.pokes)==before
    assert after.pokes[:-1]==before.pokes
    from remix import ledger
    modules=b.registry.modules()
    selected=[after if key=='PERKY PROBE' else modules[key] for key in b.registry.remix('perky-machine').modules]
    assert not ledger.check(selected)
    poke=after.pokes[-1]
    assert poke.addr==0x400a1e66 and poke.expect==bytes.fromhex('2200') and poke.write==bytes.fromhex('2300')
    base=(ROOT/'out/perky/hybrid/probe/mainos_PKHYB2P.bin').read_bytes()
    trial=bytearray(base);i=poke.addr-patch.BASE
    assert trial[i:i+2]==poke.expect;trial[i:i+2]=poke.write
    assert bytes(trial)==(work/'trial-mainos.bin').read_bytes()
    return {'status':'PASS_ONLY_ADDED_OPERAND_POKE','module_claim_ledger':'PASS_ALL_12_EFFECTS','source_sha256':sha(source),
            'previous_factory_commit':'3167a977c78beda86ade048f3f71545c3005508d'}

def unit(work):
    original=ROOT/'out/perky/hybrid/probe/mainos_PKHYB2P.bin'
    trial=work/'trial-mainos.bin'
    expected=patch.transform(original.read_bytes())
    assert trial.read_bytes()==expected
    assert patch.transform(expected,revert=True)==original.read_bytes()
    old=read(ROOT/'out/perky/hybrid/safety-close/FINAL_SAFETY_STOP.json')['commands'][0]
    command=old[:];command[command.index('-UNDEBUG')+1]=str(ROOT/'tools/harness/perky_hybrid_safety/ipl_guard.cpp')
    command[command.index('-o')+1]=str(work/'ipl_guard')
    inputs=[original,trial,ROOT/'tools/harness/perky_hybrid_safety/ipl_guard.cpp',
            *[Path(p) for p in command if p.endswith('.a')]]
    binding={str(p):sha(p) for p in inputs}
    subprocess.run(command,check=True,timeout=120)
    run=[str(work/'ipl_guard'),str(original),str(trial)]
    with (work/'guard.log').open('w') as log:
        rc=subprocess.run(run,stdout=log,stderr=subprocess.STDOUT,timeout=90).returncode
    assert rc==0,'invalid or failing focused harness; not automatically a firmware regression'
    assert binding=={str(p):sha(p) for p in inputs}
    result={'commands':[command,run],'process_exit':rc,'inputs':binding,
            'outputs':{str(p):sha(p) for p in [work/'ipl_guard',work/'guard.log']}}
    (work/'UNIT.json').write_text(json.dumps(result,indent=2)+'\n')
    print('PASS: full-body non-reentry, single deferral, UART6, original-image negative controls and rollback identity')

def force_counts(log):
    writes=re.findall(r'\[0xfc048010\] <- (0x[0-9a-f]+|0) \(4\) at pc (0x[0-9a-f]+)',log)
    pending=requests=coalesced=cleared=0
    for val,pc in writes:
        n=int(val,0)&1
        if pc in {'0x40005a74','0x4000a9e4','0x4000ae00','0x4000aea0'}:
            requests+=1;coalesced+=pending
        if pending and not n:cleared+=1
        pending=n
    assert requests==cleared and coalesced==pending==0
    return dict(requests=requests,services=cleared,coalesced=coalesced,pending=pending)

def sources(path):
    out=defaultdict(list)
    for line in Path(path).read_text().splitlines():
        a=line.split()
        if a[0]=='SOURCE':
            v=list(map(int,a[1:]));out[v[2]].append(v)
    return out

def publication_check(path,src):
    count=Counter();trigs=Counter();initial=Counter();matched=defaultdict(set)
    events={t:{row[1]:row for row in rows} for t,rows in src.items()}
    for direction,frame,ch,core,ram,half in bd.read(path):
        if direction!='>' or ch!=0 or ram not in {0x80001c90,0x800021d0,0x80002710,0x80002c50}:continue
        assert len(half)==672
        for pos in range(4):
            track=pos+(4 if core==0 else 0);h=half[pos*168:(pos+1)*168]
            words=[(h[i]<<16)|h[i+1] for i in range(0,168,2)]
            # The DMA publishes the previous completed source frame. It also
            # publishes an initial empty slot and inactive pre-PLAY records.
            event=events[track].get(frame-1)
            if event is None:
                assert frame-1<min(events[track]),(track,frame)
                initial[track]+=1;continue
            count[track]+=1;matched[track].add(frame-1)
            if track in (0,4):
                assert words[:1]==[0x504b0000] and words[1]>>16==0x5931
                assert bool(words[1]&1)==bool(event[4]&16)
                trigs[track]+=bool(words[1]&1)
            elif track in (1,5):
                record=rl.words(h);split=event[3]
                assert record[0]==split and record[1]==0 and record[2]==0x40000
                post=4+2*split
                assert record[post]==16-split and record[post+1]==0 and record[post+2]==0x40000
                assert len(rl.record_audio(record))==16
            else:assert len(rl.record_audio(rl.words(h)))==16
    for t in range(8):
        missing=set(events[t])-matched[t]
        assert len(missing)<=1
        assert all(f==max(events[t]) and not (events[t][f][4]&16) for f in missing)
    return {'publications_per_track':dict(count),'native_trigger_records':dict(trigs),
            'leading_inactive_or_empty_publications':dict(initial),
            'terminal_unpublished_nontrigger_frames':{t:len(events[t])-count[t] for t in range(8)},
            'CF_split_geometry':'PASS all frames; source-to-fixed-slot-to-DMA',
            'stock_source_record_geometry':'PASS all frames'}

def analyze(work):
    factory=module_check(work)
    assert sha(work/'trial-mainos.bin')==patch.GUARDED_SHA
    u=read(work/'UNIT.json')
    for p,h in {**u['inputs'],**u['outputs']}.items():assert sha(p)==h,p
    pairs={}
    for prefix,expected in [('paired',143),('midi',986)]:
        rows=[]
        for v in (0,1):
            log=(work/f'{prefix}-{v}.log').read_text()
            assert 'run ended REACHED' in log and not any(s in log for s in ['FAULT:','ILLEGAL'])
            row=force_counts(log);assert row['requests']==expected
            if prefix=='midi':
                clock=re.findall(r'\[0x46c7a19c\] <- (0x[0-9a-f]+|0) \(4\)',log)
                assert clock and int(clock[-1],0)==984
                assert '0 byte(s) still queued at the end' in log
                row['consumed_F8_and_musical_counter']=984
            stack=read(work/f'{prefix}-{v}-stack.json')
            assert stack['ISR_duration_misses']==stack['DMA_read_write_overlaps']==0
            assert not any(t['outside_extent'] for t in stack['stacks'])
            row['full_ISR_cycles']=stack['full_ISR_max_cycles'];rows.append(row)
        assert sha(work/f'{prefix}-0-blocks.bin')==sha(work/f'{prefix}-1-blocks.bin')
        assert rows[0]==rows[1]
        pairs[prefix]={'status':'PASS','original':rows[0],'guarded':rows[1],
            'block_streams_byte_identical':True,'modeled_full_ISR_cycle_delta':0}
    dense=work/'dense';src=sources(dense/'events.txt');ui=sources(dense/'ui-events.txt')
    original_dense=read(dense/'original-stack.json');guard_dense=read(dense/'stack.json')
    assert original_dense['full_ISR_max_cycles']==guard_dense['full_ISR_max_cycles']
    assert sha(dense/'original-blocks.bin')==sha(dense/'blocks.bin')
    pairs['dense']={'status':'PASS','original_max_cycles':original_dense['full_ISR_max_cycles'],
        'guarded_max_cycles':guard_dense['full_ISR_max_cycles'],'observed_peak_cycle_delta':0,
        'block_streams_byte_identical':True}
    for data,n in [(src,30),(ui,31)]:
        for t in range(8):
            events=[x for x in data[t] if x[4]&16]
            assert len(events)==n
            samples=[(x[1]-1)*16+x[3] for x in events]
            assert all(b-a==2205 for a,b in zip(samples,samples[1:])),(t,samples)
    first=publication_check(dense/'blocks.bin',src)
    second=publication_check(dense/'ui-blocks.bin',ui)
    prof=struct.unpack('>67I',(dense/'ui-prof.bin').read_bytes())
    assert prof[38:40]==(31,31)
    expected=read(dense/'EXPECTED.json');part=(dense/'ui-part.bin').read_bytes()
    for t in (1,5):
        assert list(part[48+30*t:53+30*t])==[65,113,2,73,57],('UI control delta/track ownership',t)
        events=[x for x in ui[t] if x[4]&16]
        for i,event in enumerate(events):
            if i%8%2:want=expected['locks'][str(i%8)]
            else:
                want=expected['initial_base_controls'][str(t)]
                if i>=(4 if t==1 else 8):want=list(part[48+30*t:54+30*t])
            assert event[5:]==want,(t,i,event[5:],want)
    queue=[]
    for line in (dense/'ui-events.txt').read_text().splitlines():
        a=line.split()
        if a[:2]==['QUEUE','G']:queue.append(bytes.fromhex(''.join(a[4:])))
    enc=[b for b in queue if b[0]==2];keys=[b for b in queue if b[0]==1]
    assert len(enc)==12 and len(keys)==16
    assert all(sum(int.from_bytes(b[2:3],'big',signed=True) for b in enc if b[1]==k)==2 for k in range(6))
    assert (dense/'ui-events.txt').read_text().splitlines()[-1]=='END 253 253'
    # The first bank-key attempt reopened PATTERN and canceled the temporary
    # bank. Its corrected, bounded panel trace is the accepted playing-bank run.
    banklog=(work/'bank-readiness.log').read_text()
    import ast
    bankrows=[ast.literal_eval(l) for l in banklog.splitlines() if l.startswith('{')]
    switches=[r for r in bankrows if r['label']=='switch_done']
    assert [r['playing'][0] for r in switches]==[1,0]
    assert [r['working'][0] for r in switches]==[1,0]
    files=emu_card.extract_image((work/'bank-panel/card.img').read_bytes())
    exported=files['PKH20000.PRF']
    magic,version,size,sequence=struct.unpack_from('>4I',exported)
    assert magic==0x504b5032 and version==2 and size==len(exported) and sequence%2==0
    choices=read(work/'lifecycle/SNAPSHOTS.json')
    for t in (0,1,4,5):
        assert next(r for r in choices if r['name']==f'T{t+1}-stock')['signatures'][str(t)]=='000000'
        assert next(r for r in choices if r['name']==f'T{t+1}-perky')['signatures'][str(t)]=='504b01'
    assert next(r for r in choices if r['name']=='Part-change')['part']!=choices[0]['part']
    assert (work/'reloaded-controls.bin').read_bytes()==bytes([71,112,2,72,56,0])
    assert 'frames run : 512 since transport start' in (work/'reload.log').read_text()
    reloaded=bd.classes(bd.read(work/'reload-blocks.bin'))
    for track in (1,2,5,6):
        assert sum(abs(v)>64 for v in rl.readback_audio(reloaded,track))>64
    stacks=[read(p) for p in [work/'paired-1-stack.json',work/'midi-1-stack.json',
             dense/'stack.json',dense/'ui-stack.json',work/'lifecycle/stack.json',work/'bank-panel/stack.json']]
    assert all(d['DMA_read_write_overlaps']==d['guard_writes_after_dispatch']==d['ISR_duration_misses']==0 for d in stacks)
    assert all(d['DMA_active_restarts']==0 and d['minimum_frame_IPL']>=5 for d in stacks)
    assert all(shape[2:5]==[336,4,16] for d in stacks for shape in d['source_DMA_shapes'])
    assert all(key.to_bytes(4,'big').count(0x60)<=1 for d in stacks for key,count in d['interrupt_chains'])
    assert all(t['outside_extent']==0 for d in stacks for t in d['stacks'])
    peak=max(d['full_ISR_max_cycles'] for d in stacks)
    # Bounded traces remain observations. The unknown stock-call/task ceiling
    # is an explicit essential gate; neither timing nor an unwaived margin can
    # manufacture a pass or a demonstrated firmware defect from it.
    gates={'guard_local_IRQ_and_producer_checks':True,'bounded_lifecycle':True,
           'dense_delivery_locks_UI_DMA':True,'combined_all_path_stack_bound':None}
    report={'schema':'octabam.perky.hybrid.ipl3-qualification.v1',
        'decision':'READY FOR USER REVIEW' if ready(gates) else 'BLOCKED — COMBINED STACK BOUND NOT ESTABLISHED',
        'software_gates':gates,'demonstrated_guard_regression':False,
        'guard_reverted':False,'qualified_diagnostic_candidate':ready(gates),
        'factory':factory,'original_MAIN_sha256':patch.ORIGINAL_SHA,'guarded_MAIN_sha256':patch.GUARDED_SHA,
        'instruction_address':'0x400a1e64','operand_address':'0x400a1e66','operand_span_bytes':2,'actual_changed_bytes':1,
        'higher_priority_IRQs':'PASS actual UART6 unit + audio5/DMA6 integrated chains',
        'clock_pairs':pairs,'dense':{'expected_first_run_per_track':30,'expected_UI_run_per_track':31,
            'actual_CF_trigs':list(prof[38:40]),'first_publications':first,'UI_publications':second,
            'sample_spacing':2205,'locks_reversion_ALGO_MODE':'PASS CF tuples; unchanged native transport gates reused',
            'UI_enc_reports':12,'UI_key_edges':16,'sys_posts':253,'sys_consumed':253,'final_queue_backlog':0},
        'real_chooser_tracks':[1,2,5,6],'Part_change':True,'real_working_and_playing_banks':[0,1,0],
        'cold_reload_six_controls':[71,112,2,72,56,0],
        'actual_STOP_profile_export':{'file':'PKH20000.PRF','bytes':len(exported),
            'sha256':hashlib.sha256(exported).hexdigest(),'valid_PKP2_header_and_even_sequence':True},
        'fresh_rebuild_or_guarded_wrapper_qualification':False,
        'provenance':'Tested post-link operand change on frozen MAIN; module factory poke reproduces that exact image. No engine/runtime rebuild or new flash wrapper.',
        'proven_software_scopes':['Exact operand and rollback identity; every other image byte unchanged',
            'Actual level3 deferral and actual higher-priority IRQ execution in tested paths',
            'Three paired clock/dense workloads have identical source/DSP blocks and maximum ISR cycles',
            'Real chooser, Part, working/playing bank, saved-card reload and dense lock/UI/DMA paths'],
        'demonstrated_software_defects':[],
        'hardware_only_unknowns':['Physical cache/SDRAM/FlexBus/eDMA contention and coherence',
            'Interrupt release-to-entry and release-to-completion timing on MKII',
            'Per-core DSP completion under physical bus traffic','Physical timer/probe/export cost'],
        'stack':{'maximum_established_all_path_bytes':None,
            'maximum_observed_audio_bytes':max(d['max_frame_stack_bytes'] for d in stacks),
            'smallest_task_capacity_bytes':2048,
            'remaining_specific_path':'storage 0x4001ee30 -> indirect driver call 0x4001eef2 via [0x460d16cc]; interrupted A7 plus sequencer/audio/level6 chain has no closed bound',
            'not_a_demonstrated_overflow':True,'reports':stacks},
        'timing':{'CPU_Hz':264000000,'PIT_Hz':132000000,'max_modeled_full_ISR_cycles':peak,
            'max_modeled_full_ISR_us':peak/264,'deadline_us':16e6/44100,
            'headroom_us':16e6/44100-peak/264,'engineering_margin_waived':False,
            'engineering_margin_passed':False,'physical_WCET_established':False},
        'flash_authorized':False,'Goal2_restarted':False,'Goal3_started':False,'synthesis_optimizations':0,
        'limits':['Arbitrary forced IRQ writes can coalesce; these are not musical clock events. The invalid phase-per-ack assertion was removed, not treated as a firmware regression.',
                  'Stack observations, including complete bounded playback/chooser/export traces, are not all-path ceilings.',
                  'The three sequencer pairs apply the cycle clock. Existing live/interactive paths retain their IPS sample clock even when the parsed cycle-clock option is supplied; their functional traces are not cycle-driven arrival/timing proofs.',
                  'A live quit can leave one in-flight ISR; completed ISR timings exclude that truncated final frame.',
                  'All wrappers remain unchanged historical artifacts; no guarded installable set is qualified.'],
        'source_sha256':{str(ROOT/p):sha(ROOT/p) for p in [
            'tools/perky/build_cf_dsp_hybrid.py','tools/perky/apply_hybrid_ipl_guard.py',
            'tools/verify/verify_perky_hybrid_ipl_guard.py','tools/verify/verify_perky_hybrid_guard_lifecycle.py',
            'tools/harness/perky_hybrid_safety/guard_audit.h','tools/harness/perky_hybrid_safety/ipl_guard.cpp',
            'tools/harness/perky_hybrid_safety/dense_fixture.py','tools/harness/perky_hybrid_safety/bank_panel.py']},
        'evidence_sha256':{str(p):sha(p) for p in work.rglob('*') if p.is_file() and p.suffix in {'.log','.json','.txt','.bin','.script','.cpp','.h','.py'} and p.name not in {'IPL3_QUALIFICATION.json','assessment.log'}},
    }
    (work/'IPL3_QUALIFICATION.json').write_text(json.dumps(report,indent=2)+'\n')
    print(report['decision']);print('PASS scoped guard, lifecycle, dense counts, locks, queues and modeled DMA; UNVERIFIED all-path stack bound')
    return report

class Tests(unittest.TestCase):
    def test_unknown_is_not_ready(self):self.assertFalse(ready({'stack':None,'guard':True}))
    def test_empty_is_not_ready(self):self.assertFalse(ready({}))
    def test_failed_gate_is_not_ready(self):self.assertFalse(ready({'guard':False}))
    def test_physical_timing_not_prerequisite(self):self.assertTrue(ready({'software':True}))
    def test_wrong_image_refused(self):
        with self.assertRaises(AssertionError):patch.transform(bytes(32))

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--work',type=Path,default=ROOT/'out/perky/hybrid/ipl3')
    ap.add_argument('--unit',action='store_true');ap.add_argument('--selftest',action='store_true')
    args=ap.parse_args()
    if args.selftest:unittest.main(argv=[sys.argv[0]])
    elif args.unit:unit(args.work.resolve())
    else:sys.exit(0 if analyze(args.work.resolve())['qualified_diagnostic_candidate'] else 1)

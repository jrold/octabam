#!/usr/bin/env python3
"""Consolidate bounded hybrid safety evidence; never infer a ceiling from a peak.

Exit 1 means the software qualification remains unverified. Hardware timing and the
unwaived 20% margin are reported separately and do not enter the software verdict.
Run --selftest to exercise the fail-closed decision and noncircular timing policy.
"""
import argparse
import json
from pathlib import Path
import re
import sys
import unittest
import verify_perky_hybrid_safety as support
ROOT=support.ROOT


REQUIRED_GATES=(
    'observed_stack_extents_and_bottom_guards',
    'combined_stock_task_and_nested_ISR_upper_bound',
    'linked_selection_and_generation_regressions',
    'real_panel_stop_start_Part_and_knob_paths',
    'saved_six_controls_and_cold_reload_active_audio',
    'complete_real_machine_and_playing_bank_transition_paths',
    'modeled_source_DMA_ownership_for_observed_shapes',
    'end_to_end_dense_locks_reversion_and_trigger_delivery_accounting',
)

def decision(gates):
    missing=[name for name in REQUIRED_GATES if gates.get(name) is not True]
    failed=[name for name in REQUIRED_GATES if gates.get(name) is False]
    return ('FAILED — SOFTWARE SAFETY GATE' if failed else
            'UNVERIFIED — SOFTWARE SAFETY EVIDENCE INCOMPLETE' if missing else
            'READY FOR USER REVIEW OF RESTRICTED MKII PROBE'), missing


def analyze_banks(work):
    log=(work/'banks/port.log').read_text()
    assert 'DID NOT RETURN' not in log and 'FAULT:' not in log and 'ILLEGAL' not in log
    assert re.search(r'frames run\s*:\s*2048 .*REACHED',log)
    assert log.count('call       : 0x40000c3c(2 args) returned')==2
    writes=re.findall(r'\[0x46c82456\] <- (0x[0-9a-f]+).*?at pc (0x[0-9a-f]+) in (\w+)',log)
    sys_writes=[p for p,pc,t in writes if pc=='0x400622aa' and t=='sys']
    assert sys_writes==['0x4017d520','0x400e21e0'], sys_writes
    command=['out/emu/ot_emu','--image','out/perky/hybrid/probe/mainos_PKHYB2P.bin',
        '--card','out/perky/hybrid/safety-final/fixture/card.img','--set','OCTABAM','--project','RIG',
        '--load-ms','90000','--sequencer','--internal-clock','--bank','0','--frames','2048',
        '--dsp','--dsp-dirty','123','--pit-clock-hz','132000000','--cf-cycles-clock','1.0',
        '--step','512:poke:0x46c00000=0x15;0x46c00001=0x01;0x46c00002=0x00;0x46c00003=0x00',
        '--step','512:call:0x40000c3c,0x460d17ae,0x46c00000',
        '--step','1536:poke:0x46c00000=0x15;0x46c00001=0x00',
        '--step','1536:call:0x40000c3c,0x460d17ae,0x46c00000',
        '--watch-mem','0x46c82456,4','--block-dump','out/perky/hybrid/safety-final/banks/records.bin']
    return {'status':'PASS_WORKING_BANK_A_B_A','frames':2048,'command':command,
            'exit_status':0,'command_recording':'Completed local invocation; transcribed into receipt during consolidation',
            'stock_sys_pointer_writes':sys_writes,
            'log_sha256':support.sha(work/'banks/port.log'),
            'limits':['Stock sys selection message executed; this is not a real-panel bank/pattern switch.',
                      'Sequencer playing-bank selection stays A; no assertion of complete pattern-bank transition.']}


def assess(work,output):
    panel=json.loads((work/'panel-stack.json').read_text())
    run=json.loads((work/'PANEL_RUN.json').read_text())
    lifecycle=json.loads((work/'LIFECYCLE_COMPONENT.json').read_text())
    saved=json.loads((work/'saved-project/SAVED_PROJECT.json').read_text())
    build=json.loads((work/'final-observer/OBSERVER_BUILD.json').read_text())
    for p,h in run['inputs'].items(): assert support.sha(p)==h, ('panel input drift',p)
    for p,h in run['outputs'].items(): assert support.sha(p)==h, ('panel output drift',p)
    assert support.sha(work/'final-observer/ot_emu_safety')==build['binary_sha256']
    for p,h in build['source_hashes'].items(): assert support.sha(p)==h, ('observer source drift',p)
    assert lifecycle['status']=='PASS_COMPONENT_SCOPES'
    assert saved['status']=='PASS_SCOPED_SAVE_RELOAD' and saved['input_hashes_unchanged']
    assert panel['frames']==panel['frame_returns']>0
    assert not any(s['outside_extent'] for s in panel['stacks'])
    assert panel['guard_writes_after_dispatch']==0
    assert panel['DMA_read_write_overlaps']==0 and panel['source_DMA_starts']>0
    assert panel['ISR_duration_misses']==0
    transitions={i:set() for i in range(5)}
    for line in (work/'panel-events.txt').read_text().splitlines():
        fields=line.split()
        if len(fields)==4 and fields[0].isdigit():
            transitions[int(fields[2])].add(int(fields[3]))
    assert {0,1}<=transitions[2], 'real panel STOP/START not established'
    assert {1,5}<=transitions[3], 'track selection did not reach both CF voices'
    assert 2 in transitions[1], 'Part chooser transition did not complete'

    banks=analyze_banks(work)
    # No static/inductive stock-task bound has been established by these runs.
    # A nonzero dynamic high-water mark is deliberately insufficient here.
    gates={
        'observed_stack_extents_and_bottom_guards':True,
        'combined_stock_task_and_nested_ISR_upper_bound':None,
        'linked_selection_and_generation_regressions':True,
        'real_panel_stop_start_Part_and_knob_paths':True,
        'saved_six_controls_and_cold_reload_active_audio':True,
        'complete_real_machine_and_playing_bank_transition_paths':None,
        'modeled_source_DMA_ownership_for_observed_shapes':True,
        'end_to_end_dense_locks_reversion_and_trigger_delivery_accounting':None,
    }
    verdict,missing=decision(gates)
    report={
        'schema':'octabam.perky.hybrid.bounded-safety-followup.v1',
        'decision':verdict,'software_gates':gates,'unresolved_software_safety':missing,
        'positive_evidence':{'stack_and_concurrency':panel,'lifecycle_component':lifecycle,
                             'saved_project':saved,'working_bank':banks},
        'stack_upper_bound_bytes':None,
        'stack_upper_bound_status':'NOT_ESTABLISHED; all reported peaks are observations',
        'timing':{'CPU_Hz':264000000,'PIT_Hz':132000000,
                  'retained_worst_full_ISR_cycles':85474,'retained_worst_full_ISR_us':85474/264,
                  'frame_deadline_us':16e6/44100,
                  'modeled_headroom_us':16e6/44100-85474/264,
                  'engineering_margin_passed':False,'margin_waived':False,
                  'engineering_ceiling_us':0.8*16e6/44100,
                  'margin_shortfall_us':85474/264-0.8*16e6/44100,
                  'this_panel_peak_us':panel['full_ISR_max_cycles']/264,
                  'hardware_WCET_established':False,
                  'timing_is_not_the_software_blocking_criterion':True},
        'hardware_only_unknowns':['Cache/SDRAM/FlexBus/eDMA contention and coherence on MKII',
            'Physical interrupt release-to-entry latency and release-to-completion deadlines',
            'Per-core DSP completion times under shared physical bus traffic',
            'Physical DTIM3 read/instrumentation cost and card export behavior'],
        'runtime_or_synthesis_changes':False,'flash_authorized':False,
        'next_goal_started':False,'optimization_iterations':0,
        'evidence_sha256':{str(p):support.sha(p) for p in [
            work/'PANEL_RUN.json',work/'panel-stack.json',work/'panel-events.txt',
            work/'LIFECYCLE_COMPONENT.json',work/'saved-project/SAVED_PROJECT.json',
            work/'final-observer/OBSERVER_BUILD.json',work/'final-observer-build.log']},
    }
    output.write_text(json.dumps(report,indent=2)+'\n')
    print(verdict)
    for item in missing:print('UNESTABLISHED:',item)
    return report


class DecisionTests(unittest.TestCase):
    def complete(self):return dict.fromkeys(REQUIRED_GATES,True)
    def test_missing_stack_is_blocked(self):
        g=self.complete();g['combined_stock_task_and_nested_ISR_upper_bound']=None
        self.assertTrue(decision(g)[0].startswith('UNVERIFIED'))
    def test_failed_ownership_is_blocked(self):
        g=self.complete();g['modeled_source_DMA_ownership_for_observed_shapes']=False
        self.assertTrue(decision(g)[0].startswith('FAILED'))
    def test_physical_timing_not_prerequisite(self):
        # Software review can be offered while physical timing is unknown and
        # the engineering margin remains unwaived; this never authorizes a flash.
        self.assertTrue(decision(self.complete())[0].startswith('READY FOR USER REVIEW'))
    def test_empty_evidence_is_blocked(self):
        self.assertEqual(decision({})[1],list(REQUIRED_GATES))



if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--work',type=Path,default=ROOT/'out/perky/hybrid/safety-final')
    ap.add_argument('--out',type=Path)
    ap.add_argument('--selftest',action='store_true')
    args=ap.parse_args()
    if args.selftest:
        unittest.main(argv=[sys.argv[0]])
    else:
        report=assess(args.work.resolve(),args.out or args.work/'ASSESSMENT.json')
        raise SystemExit(1 if report['unresolved_software_safety'] else 0)

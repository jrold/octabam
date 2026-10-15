#!/usr/bin/env python3
"""Bounded final stack decision. Exit 1 is a safety STOP, not a crashed test.

Reuse the accepted previous receipts; execute only the new actual-image nesting
test and its disposable-memory counterfactual. Never write or rebuild firmware.
"""
import argparse
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
import unittest

import verify_perky_hybrid_safety as support

ROOT = support.ROOT
IMAGE_SHA = 'a2d6915bc71a97d63f44e223e558cc4941d52113708f7ba92a57bdd669339b40'
A = 'A. SOFTWARE SAFETY GATES PASS'
B = 'B. STRUCTURAL SAFETY CHANGE REQUIRED'
C = 'C. DEMONSTRATED CORRECTNESS FAILURE'


def decision(*, structural_path, demonstrated_failure, gates):
    if demonstrated_failure:
        return C
    if structural_path:
        return B
    if len(gates) == 3 and all(v is True for v in gates):
        return A
    return 'UNVERIFIED — SOFTWARE SAFETY EVIDENCE INCOMPLETE'


def run(work):
    work.mkdir(parents=True, exist_ok=True)
    image = ROOT/'out/perky/hybrid/probe/mainos_PKHYB2P.bin'
    prior_path = ROOT/'out/perky/hybrid/safety-final/ASSESSMENT.json'
    prior = json.loads(prior_path.read_text())
    assert support.sha(image) == IMAGE_SHA
    # Receipts are immutable accepted evidence, not rerun scenarios. The old
    # verdict's word "defects" is explicitly superseded by this classification.
    for p, h in prior['evidence_sha256'].items():
        assert support.sha(p) == h, ('previous evidence drift', p)
    panel_run = json.loads((prior_path.parent/'PANEL_RUN.json').read_text())
    for p, h in {**panel_run['inputs'], **panel_run['outputs']}.items():
        assert support.sha(p) == h, ('previous panel binding drift', p)
    assert prior['positive_evidence']['lifecycle_component']['status'] == 'PASS_COMPONENT_SCOPES'
    assert prior['positive_evidence']['saved_project']['status'] == 'PASS_SCOPED_SAVE_RELOAD'
    assert prior['positive_evidence']['working_bank']['status'] == 'PASS_WORKING_BANK_A_B_A'
    source = ROOT/'tools/harness/perky_hybrid_safety/stack_reentry.cpp'
    flags_path = ROOT/'out/emu/CMakeFiles/ot_machine.dir/flags.make'
    flags = flags_path.read_text()
    options = []
    for key in ('CXX_DEFINES', 'CXX_INCLUDES', 'CXX_FLAGS'):
        options += shlex.split(next(line.split(' = ', 1)[1] for line in flags.splitlines()
                                    if line.startswith(key+' = ')))
    libs = [ROOT/'out/emu'/p for p in (
        'libot_machine.a', 'mc68k/lib68kEmu.a', 'dsp56300/dsp56kEmu/libdsp56kEmu.a',
        'dsp56300/dsp56kBase/libdsp56kBase.a', 'dsp56300/asmjit/libasmjit.a')]
    executable = work/'stack_reentry'
    command = ['/usr/bin/c++', *options, '-UNDEBUG', str(source), '-o', str(executable),
               *map(str, libs), '-lpthread']
    inputs = [image, source, Path(__file__), flags_path, prior_path, *libs]
    binding = {str(p): support.sha(p) for p in inputs}
    subprocess.run(command, check=True, timeout=120)
    test_command = [str(executable), str(image)]
    log = work/'stack-reentry.log'
    with log.open('w') as stream:
        result = subprocess.run(test_command, stdout=stream, stderr=subprocess.STDOUT, timeout=90)
    assert result.returncode == 0, f'nesting harness FAILED: {log}'
    rows = re.findall(r'ENTRY variant=UNCHANGED depth=(\d+) task=0x460d4f80 task_bytes=16 nested_bytes=(\d+) sp=0x([0-9a-f]+) free=(\d+)', log.read_text())
    assert len(rows) == 9
    for d, n, sp, free in rows:
        assert int(n) == 216*int(d)
        assert int(sp, 16) == 0x460d4f80 - 16 - int(n)
        assert int(free) == 2048 - 16 - int(n)
    assert 'PASS_UNCHANGED:' in log.read_text() and 'PASS_COUNTERFACTUAL:' in log.read_text()
    assert binding == {str(p): support.sha(p) for p in inputs}, 'input changed during test'
    report = {
        'schema': 'octabam.perky.hybrid.final-safety-stop.v1',
        'decision': decision(structural_path=True, demonstrated_failure=False, gates=[False, None, None]),
        'start_commit': '689860d71b1b7447223885481c209cc4df5adaf6',
        'areas': {
            'stack': 'FAIL_STRUCTURAL_BOUND: actual sequencer self-nesting; no proved arrival/service bound',
            'lifecycle': 'UNVERIFIED_COMPLETE_CHOOSER_AND_PLAYING_BANK; prior scoped passes retained',
            'parameter_lock_trigger_accounting': 'UNVERIFIED_END_TO_END; prior ownership passes retained',
        },
        'stop_reason': 'Precise unbounded nesting path identified; stop for structural-change approval under execution limit',
        'demonstrated_playback_corruption_race_overflow_or_deadline_failure': False,
        'test_arrivals': 'Adversarial host writes to actual modeled INTC0 force register, not natural playback or a silicon timing claim',
        'stack': {
            'task': 'keyrepeat', 'capacity_bytes': 2048, 'interrupted_task_bytes': 16,
            'tested_nested_depth': 9, 'bytes_per_sequencer_entry': 216,
            'established_observed_combined_bytes': 1960, 'remaining_bytes': 88,
            'tenth_entry_required_bytes': 2176, 'tenth_entry_excess_bytes': 128,
            'tenth_request_issued': False, 'maximum_all_path_requirement_bytes': None,
            'self_cycle': ['vector 0x60 level 3', '0x400a1e0c mask 7', '0x400a1e10 reserve 208',
                           '0x400a1e1a clear source 32 force bit', '0x400a1e64 mask 2', 'another source 32 request'],
            'prior_audio_peak_including_observed_level6_bytes': 1316,
            'prior_audio_peak_is_a_bound': False,
        },
        'proposed_minimum_remedy': {
            'change': 'SR immediate at 0x400a1e64 from 0x2200 to 0x2300 (operand address 0x400a1e66)',
            'implemented_in_firmware': False, 'disposable_test_memory_only': True,
            'image_bytes_changed_if_approved': 2, 'extra_DRAM_bytes': 0, 'extra_stack_bytes': 0,
            'added_instructions': 0, 'direct_modeled_instruction_cost_delta': 0,
            'effect': 'Prevent same-level sequencer/ATA-DMA14 preemption while IPL remains >=3; retain audio5 and DMA6 eligibility',
            'behavioral_risk': 'Defers level3 work; force bit can coalesce arrivals. Pending-tick delivery/counts and ATA latency must be qualified before acceptance.',
            'tested': 'One forced request remains pending through the first actual body call; no second sequencer entry',
            'not_proven': 'Whole-body mask/callee behavior, all-task combined bound and arrival-loss semantics; this counterfactual is not an approved fix',
            'acceptance_tests_if_authorized': [
                'Audit all sequencer callees and SR restores; repeated force requests must not grow the chain; pending delivery/counts must match defined tick semantics',
                'Close finite task + sequencer + actual CF-engine + level6 frame bounds against each task capacity, including indirect paths and level7 policy',
                'Check ATA-DMA14 service latency with audio5/DMA6 preemption; complete the remaining chooser/playing-bank and dense lock/trigger counts',
                'Recheck unchanged DSP/guard/FX/PCM/state/RNG identities and full corrected-clock ISR timing after any approved firmware edit',
            ],
        },
        'firmware_sha256_unchanged': IMAGE_SHA,
        'firmware_changes': False, 'firmware_correction_iterations': 0,
        'timing': prior['timing'], 'hardware_only_unknowns': prior['hardware_only_unknowns'],
        'flash_authorized': False, 'probe_recommended': False,
        'Goal2_restarted': False, 'Goal3_started': False,
        'commands': [command, test_command], 'test_process_exit_status': result.returncode,
        'inputs_sha256': binding,
        'outputs_sha256': {str(p): support.sha(p) for p in [log, executable]},
        'reused_evidence_sha256': prior['evidence_sha256'],
    }
    (work/'FINAL_SAFETY_STOP.json').write_text(json.dumps(report, indent=2)+'\n')
    print(report['decision'])
    print('PASS: nine actual entries and IPL3 counterfactual; STOP: structural bound fails, other two completion gates UNVERIFIED')
    return report


class DecisionTests(unittest.TestCase):
    def test_structural_path_stops(self):
        self.assertEqual(decision(structural_path=True, demonstrated_failure=False, gates=[True]*3), B)
    def test_missing_evidence_is_not_a_demonstrated_bug(self):
        self.assertTrue(decision(structural_path=False, demonstrated_failure=False, gates=[True, None, None]).startswith('UNVERIFIED'))
    def test_actual_failure_has_separate_classification(self):
        self.assertEqual(decision(structural_path=False, demonstrated_failure=True, gates=[True]*3), C)
    def test_software_pass_does_not_require_physical_timing(self):
        self.assertEqual(decision(structural_path=False, demonstrated_failure=False, gates=[True]*3), A)
    def test_empty_gates_cannot_pass(self):
        self.assertTrue(decision(structural_path=False, demonstrated_failure=False, gates=[]).startswith('UNVERIFIED'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, default=ROOT/'out/perky/hybrid/safety-close')
    parser.add_argument('--selftest', action='store_true')
    args = parser.parse_args()
    if args.selftest:
        unittest.main(argv=[sys.argv[0]])
    else:
        report = run(args.work.resolve())
        sys.exit(0 if report['decision'] == A else 1)

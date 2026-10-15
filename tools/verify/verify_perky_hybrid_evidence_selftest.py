#!/usr/bin/env python3
"""Negative tests for the hybrid qualification receipt gate; no firmware needed."""
import json
import tempfile
import unittest
from pathlib import Path

import verify_perky_hybrid as gate


class EvidenceRefusal(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='perky-hybrid-evidence-')
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name)
        self.reports = {
            'BUILD': {
                'git_commit': gate.git('rev-parse', 'HEAD'),
                'sources': {'README.md': gate.sha(gate.ROOT / 'README.md')},
                'artifacts': {},
            },
            'TIMING': {
                'status': 'LOCAL_MODEL_WITHIN_BUDGET_HARDWARE_PENDING',
                'summary': {'global_deadline_misses': 0, 'global_within_80pct_margin': True},
                'clocks': {'dtim3_bus_hz': 132000000},
                'hardware_profiler_qualification': {'status': 'PASS'},
                'mandatory_rows_60s': self.rows([
                    ('V1', 'V1'), ('V1', 'V2'), ('V2', 'snare'), ('V1', 'bass'),
                    ('snare', 'snare'), ('bass', 'snare'), ('third', 'third')]),
                'extra_rows_60s': self.rows([
                    ('V2', 'V2'), ('V2', 'V1'), ('snare', 'V2'), ('bass', 'V1'), ('snare', 'bass')]),
                'worst_row_10min': {'frames': 1653750},
                'profiler_and_arm_comparisons': {'fixture': True},
            },
            'PROBE_GATES': {'dsp_readback_and_12_fx': {'status': 'PASS'},
                            'lifecycle_and_reference': {'status': 'PASS'}},
        }
        for label in ('mainos', 'runtime_elf'):
            path = self.work / (label + '.synthetic.txt')
            path.write_text('synthetic receipt test, contains no firmware')
            self.reports['BUILD']['artifacts'][label] = gate.item(path)
        for name in ('TIMING', 'PROBE_GATES'):
            self.reports[name]['evidence'] = {
                label + '_sha256': self.reports['BUILD']['artifacts'][label]['sha256']
                for label in ('mainos', 'runtime_elf')}
            self.reports[name]['evidence']['emulator_sha256'] = gate.sha(gate.ROOT / 'out/emu/ot_emu')

    @staticmethod
    def rows(pairs):
        return [{'row': '/'.join(pair), 't2': pair[0], 't6': pair[1], 'frames': 165375,
                 'audio_verification': {f'T{t}': {'chain_significant': 100} for t in range(1, 9)}}
                for pair in pairs]

    def errors(self):
        for name, report in self.reports.items():
            (self.work / f'{name}.json').write_text(json.dumps(report))
        return gate.probe_evidence_errors(self.work)

    def test_structural_fixture(self):
        # Exercises only the supplementary receipt validator, not qualification.
        self.assertEqual(self.errors(), [])

    def test_smoke_cannot_qualify(self):
        self.reports['TIMING']['mandatory_rows_60s'][0]['frames'] = 1000
        self.assertTrue(any('shorter than 60' in e for e in self.errors()))

    def test_missing_timer_and_wrap_qualification(self):
        del self.reports['TIMING']['hardware_profiler_qualification']
        self.reports['TIMING']['clocks']['dtim3_bus_hz'] = 88000000
        errors = self.errors()
        self.assertTrue(any('frequency/wrap/overhead/export' in e for e in errors))
        self.assertTrue(any('132 MHz' in e for e in errors))

    def test_deadline_or_margin_failure(self):
        self.reports['TIMING']['summary'].update(global_deadline_misses=1, global_within_80pct_margin=False)
        self.assertTrue(any('deadline and 80%' in e for e in self.errors()))

    def test_skip_and_missing_lifecycle(self):
        self.reports['PROBE_GATES'] = {'dsp_readback_and_12_fx': {'status': 'SKIPPED'}}
        errors = self.errors()
        self.assertTrue(any('retained FX' in e for e in errors))
        self.assertTrue(any('generation' in e for e in errors))

    def test_silent_or_missing_capture(self):
        del self.reports['TIMING']['mandatory_rows_60s'][0]['audio_verification']['T3']
        self.assertTrue(any('all-eight-track' in e for e in self.errors()))

    def test_uncommitted_source_and_corrupt_artifact(self):
        self.reports['BUILD']['sources']['modules/perky/not-in-recorded-commit.c'] = '0' * 64
        p = self.work / 'synthetic.txt'
        p.write_text('synthetic test data, no firmware')
        self.reports['BUILD']['artifacts']['synthetic'] = {
            'path': str(p), 'bytes': p.stat().st_size, 'sha256': '0' * 64}
        errors = self.errors()
        self.assertTrue(any('absent from recorded commit' in e for e in errors))
        self.assertTrue(any('artifact drift' in e for e in errors))

    def test_missing_reports(self):
        self.assertTrue(gate.probe_evidence_errors(self.work))

    def test_stale_timing_image(self):
        self.reports['TIMING']['evidence']['mainos_sha256'] = '0' * 64
        self.assertTrue(any('not bound to the actual hybrid mainos' in e for e in self.errors()))


if __name__ == '__main__':
    unittest.main()

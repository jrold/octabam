#!/usr/bin/env python3
"""Bind the completed footprint campaign to its two actual firmware builds.

This is an aggregation gate, not an additional hardware qualification. It
refuses incomplete sustained/activation runs and changed evidence inputs.
"""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def qualify(work, output):
    receipts = {}

    def read(name, prefix=None):
        path = work / name
        data = json.loads(path.read_text())
        if prefix:
            assert data['status'].startswith(prefix), (name, data['status'])
        receipts[str(path)] = sha(path)
        return data

    def pins(mapping):
        for path, digest in mapping.items():
            assert sha(path) == digest, 'evidence input changed: ' + path

    builds = {}
    for kind in ('diagnostic', 'performance'):
        build = read(f'final-{kind}/probe/BUILD.json')
        assert build['source_tree_clean'] and build['git_tree_clean']
        assert build['dsp_identity_status'] == build['memory_status'] == 'PASS'
        for path, digest in build['sources'].items():
            assert sha(ROOT / path) == digest, 'firmware source changed: ' + path
        for artifact in build['artifacts'].values():
            path = Path(artifact['path'])
            assert path.stat().st_size == artifact['bytes']
            assert sha(path) == artifact['sha256'], 'artifact changed: ' + str(path)
        for name in ('COLD.json', 'static/BOUNDS.json', 'package-check/PACKAGES.json'):
            check = read(f'final-{kind}/' + name, 'PASS')
            if name == 'package-check/PACKAGES.json':
                assert check['build_sha256'] == sha(work/f'final-{kind}/probe/BUILD.json')
            else:
                assert check['image_sha256'] == build['artifacts']['mainos']['sha256']
            if name == 'COLD.json':
                assert check['elf_sha256'] == build['artifacts']['runtime_elf']['sha256']
        builds[kind] = build
    assert builds['diagnostic']['git_commit'] == builds['performance']['git_commit']
    assert builds['diagnostic']['hybrid_source_id'] == builds['performance']['hybrid_source_id']
    # BUILD.sources lists selected direct units. The embedded fingerprint also
    # covers every module C/header/assembly file, including transitive helpers.
    source_files = sorted(p for p in (ROOT/'modules/perky').iterdir()
                          if p.suffix in ('.c','.h','.s')) + [ROOT/'tools/perky/build_cf_dsp_hybrid.py']
    fingerprint = hashlib.sha256(b''.join(
        str(p.relative_to(ROOT)).encode()+b'\0'+p.read_bytes() for p in source_files)).hexdigest()
    assert fingerprint == builds['diagnostic']['hybrid_source_id'], 'complete source fingerprint changed'
    all_source_hashes = {str(p):sha(p) for p in source_files}
    pair = read('FINAL_CONFIGURATION_PAIR.json', 'PASS_SINGLE_LOADED_PROFILE_WORD_ONLY')
    pins(pair['inputs'])
    suite = read('FINAL_QUALIFICATION_JOBS.json', 'PASS')
    assert len(suite['jobs']) == 20
    assert all(j['status'] == 'PASS' and j['exit_code'] == 0 for j in suite['jobs'])
    safety = read('final-diagnostic/QUALIFICATION.json', 'LOCALLY_QUALIFIED_DIAGNOSTIC_SCOPED')
    assert safety['artifacts']['mainos']['sha256'] == builds['diagnostic']['artifacts']['mainos']['sha256']
    pins(safety['receipt_hashes'])
    for path, digest in safety['source_hashes'].items():
        assert sha(ROOT / path) == digest, 'qualification source changed: ' + path
    read('final-performance/seven-track-audio/PERFORMANCE_AUDIO.json', 'PASS')
    summary = read('FINAL_STOCK_SUMMARY.json', 'COMPLETED_INPUT_MATRICES')
    pins(summary['receipts'])
    assert len(summary['rows']) == 64 and len(summary['marginal_voice_costs']) == 50
    main_sha = builds['diagnostic']['artifacts']['mainos']['sha256']
    assert all(r['image_sha256'] == main_sha for r in summary['rows'])
    pairs = {tuple(r['pair']) for r in summary['rows']
             if r['scenario'] == 'F' and r['kind'] == 'static'}
    assert len(pairs) == 25
    assert all(r['full_ISR_CPU_us']['modeled_deadline_misses'] == 0 for r in summary['rows'])
    for path in summary['receipts']:
        matrix = json.loads(Path(path).read_text())
        assert matrix['status'] == 'PASS_EXERCISED_MATRIX'
        pins(matrix['inputs'])
    for name in ('FINAL_CALLBACK_RESOURCES.json', 'FINAL_PRODUCTION_WORKING_SETS.json'):
        resource = read(name, 'PASS')
        pins(resource['inputs'])
    for name in ('final-callback-proof/CALLBACK_REPORT.json',
                 'final-profile-callback-proof/CALLBACK_REPORT.json',
                 'PKH4O2-callback-resource-control/CALLBACK_REPORT.json',
                 'production-working-sets/OBSERVATION.json'):
        proof = read(name, 'PASS')
        pins(proof['inputs'])
    read('SOURCE_PRESERVATION.json', 'PASS_PRODUCTION_DIFF_CONFINED_TO_PERKY')
    activation = read('activation-tool-all-splits/RECEIPT.json', 'PASS')
    pins(activation['inputs'])
    assert activation['result']['calls'] == 149600
    assert activation['result']['T2_exact_checks'] == 81600
    assert activation['calibration'] == 'PASS_ALL_REFERENCE_COLUMNS_IDENTICAL'
    admission = read('FINAL_ACTIVATION_RESOURCES.json', 'PASS_ALL_25_PAIRS')
    pins(admission['inputs'])
    for name, count in [('panel-second-CF/PANEL_VALIDATION.json', 3),
                        ('panel-tool-fresh-control/PANEL_ACTIVATION.json', 1)]:
        panel = read(name, 'PASS')
        pins(panel['inputs'])
        assert len(panel['rows']) == count
        for row in panel['rows']:
            pins(row['capture_inputs']['inputs'])
            pins(row['observer_reports'])
            assert sha(row['snapshots']) == row['snapshots_sha256']
    sustained = read('final-sustained/STOCK_MATRIX.json', 'PASS_EXERCISED_MATRIX')
    pins(sustained['inputs'])
    assert sustained['frames'] == 1653750 and len(sustained['rows']) == 1
    sustained_row = sustained['rows'][0]
    assert sustained_row['status'] == 'LOCALLY_EXERCISED_SHORT_ROW'
    result = sustained_row['result']
    assert result['frames'] == 1653750 and result['cycle_clock_before_transport']
    assert result['ot_emu']['playback_card']['read_sectors'] > 0
    assert result['dtim3_profiler']['deadline_misses_100pct'] == 0
    report = dict(
        schema='octabam.perky.hybrid.footprint-qualification.v1',
        status='LOCALLY_QUALIFIED_DIAGNOSTIC_AND_PERFORMANCE; PHYSICAL_MKII_ACCEPTANCE_PENDING',
        firmware_source_commit=builds['diagnostic']['git_commit'],
        hybrid_source_id=builds['diagnostic']['hybrid_source_id'],
        configurations={k: dict(version=b['version'], artifacts=b['artifacts']) for k,b in builds.items()},
        qualification_jobs=20, stock_workload_rows=64,
        ordered_two_CF_pairs=25, matched_marginal_voice_comparisons=50,
        activation=activation['result'], sustained=result,
        scoped_safety_status=safety['status'],
        static_stack_limits=safety['static_scope_limits'],
        unchanged_larger_stock_task_graphs=safety['unchanged_larger_stock_task_graphs'],
        source_preservation=dict(stock_machine_playback_implementations_changed=False,
                                 DSP_implementations_frozen=True,
                                 CF_voices=2, algorithms_restricted=False),
        physical_acceptance=False, hardware_flashed=False,
        limits=summary['limits'] + [
            'User hardware finding establishes one-CF success and dual-CF failure for the reported workloads; algorithms were unspecified.',
            'The model also passes the known-failing PKH4O2 workload. It cannot establish cache, SDRAM, card, DMA, UI or hardware voice feasibility.',
            'The approved private-stack correction closes its scoped budgets; larger unchanged stock task graphs remain explicitly open.',
            'Performance differs only in the initial profiler enable word; full diagnostic code remains present.'],
        receipts=receipts, complete_module_source_hashes=all_source_hashes,
        aggregator_sha256=sha(__file__))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(report['status'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    qualify(args.work.resolve(), args.out.resolve())

#!/usr/bin/env python3
"""Collect the PKFM22-PKFM27 campaign receipt (modules/perky/hybrid/KERNEL_CF_QUALIFICATION.json).

Reads only completed local evidence: each candidate's BUILD.json and image
hashes, every PKFM26 sustained row's frozen-budget assessment and exact-source
witness, and the gate receipts in the PKFM26 build directory. It exits 1 with
the explicit performance hold when any ceiling fails, as the frozen admission
checkers do; any missing or inexact evidence is an error instead.
"""
import glob
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HYBRID = ROOT / 'out/perky/hybrid'
CANDIDATES = {
    'PKFM22': ('full-map-merge-v1', 'merge-campaign', 'kept'),
    'PKFM23': ('full-map-dispatch-v1', 'dispatch-campaign', 'rejected: seam-keeping fast path raised p99.9 and peak'),
    'PKFM24': ('full-map-kernels-v1', 'kernels-campaign', 'kept'),
    'PKFM25': ('full-map-kernels-v2', 'kernels2-campaign', 'kept'),
    'PKFM26': ('full-map-kernels-v3', 'kernels3-campaign', 'best candidate'),
    'PKFM27': ('full-map-kernels-v4', 'kernels4-campaign', 'rejected: slower than PKFM26'),
}
GATES = ('SOURCE_GATE.json', 'KERNEL_GATE.json', 'HANDOFF_GATE.json', 'DMA_GATE.json', 'MERGED_GATE.json',
         'DISPATCH_DIFFERENTIAL.json', 'MATRIX.json', 'SCENES.json', 'lifecycle/RESULT.json')
SOURCES = ('modules/perky/cf_env_block.s', 'modules/perky/cf_wt_frequency_block.s', 'modules/perky/cf_wt_render.s',
           'modules/perky/cf_nt_render.s', 'tools/perky/generate_cf_merged_segments.py', 'tools/perky/build_perky_merge_cf.py',
           'tools/perky/generate_cf_wt_render_asm.py', 'tools/perky/generate_cf_slap_env_asm.py',
           'tools/perky/generate_cf_nt_render_asm.py', 'tools/perky/generate_cf_v4_merge.py',
           'tools/perky/build_perky_kernels_cf.py', 'tools/perky/generate_cf_dispatch_fast.py',
           'tools/perky/build_perky_dispatch_cf.py', 'tools/perky/generate_cf_dispatch_lean.py',
           'tools/verify/verify_perky_merged_segments.py', 'tools/verify/verify_perky_dispatch_differential.py',
           'tools/verify/capture_perky_kernel_vectors.py', 'tools/verify/bench_perky_kernel.py',
           'tools/verify/kernels/test_env_block.py', 'tools/verify/kernels/env_block_driver.s',
           'tools/harness/perky_cf/cf_cycle_bench.cpp', 'tools/harness/perky_cf/build_cf_cycle_bench.sh',
           'tools/harness/perky_cf/cf_cycle_bench_shim/machine.h', 'tools/verify/qualify_perky_kernels_cf.py')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    receipt = dict(schema='octabam.perky.kernel-cf-qualification.v1',
                   budget_sha256=sha(ROOT / 'modules/perky/hybrid/EMULATOR_BUDGET.json'),
                   observer_sha256=sha(HYBRID / 'budget-calibration/observer/ot_emu_safety'),
                   budget_us=json.loads((ROOT / 'modules/perky/hybrid/EMULATOR_BUDGET.json').read_text())['budgets_us'],
                   candidates={}, rows={}, gates={},
                   source_sha256={s: sha(ROOT / s) for s in SOURCES})
    for version, (build, campaign, verdict) in CANDIDATES.items():
        b = json.loads((HYBRID / build / 'BUILD.json').read_text())
        image = HYBRID / build / 'probe' / f'mainos_{version}.bin'
        assert sha(image) == b['main_sha256'], version
        worst = sorted(glob.glob(str(HYBRID / campaign / 'workload' / f'{version}-WTWT-SlapControl-NoiseTone-all14/ROW.json')))
        entry = dict(build=str((HYBRID / build).relative_to(ROOT)), main_sha256=b['main_sha256'],
                     elf_sha256=b['runtime_sha256'], verdict=verdict)
        if worst:
            row = json.loads(Path(worst[0]).read_text())
            entry['worst_row_steady_ISR'] = row['steady_ISR']
            entry['worst_row_exact_source'] = {k: row['exact_source'][k] for k in ('source_frames', 'PCM_mismatches', 'oracle_errors')}
        receipt['candidates'][version] = entry
    hold = False
    for path in sorted(glob.glob(str(HYBRID / 'kernels3-campaign/workload/PKFM26-*/ROW.json'))):
        row = json.loads(Path(path).read_text())
        assessment = json.loads((Path(path).parent / 'BUDGET_ASSESSMENT.json').read_text())
        exact = row['exact_source']
        assert not any(exact['PCM_mismatches']) and exact['oracle_errors'] == 0, path
        assert exact['DSP_state_mismatches'] == exact['DSP_side_mismatches'] == exact['DSP_clock_mismatches'] == exact['feedback_mismatches'] == 0, path
        assert exact['source_frames'][:3] == [32768] * 3 and exact['source_frames'][3] >= 32766, path
        assert row['transport']['pk_nhr_failures'] == 0, path
        hold |= not assessment['pass_budget']
        receipt['rows'][row['case']] = dict(
            row_sha256=sha(path), image_sha256=row['image_sha256'],
            checks={k: dict(measured_us=v['measured_us'], pass_budget=v['pass_budget']) for k, v in assessment['checks'].items()},
            exact_source={k: exact[k] for k in ('source_frames', 'PCM_mismatches', 'DSP_state_mismatches', 'DSP_side_mismatches',
                                                'DSP_clock_mismatches', 'feedback_mismatches', 'oracle_errors')})
    assert len(receipt['rows']) == 8, 'all eight sustained rows are required'
    for gate in GATES:
        path = HYBRID / 'full-map-kernels-v3' / gate
        data = json.loads(path.read_text())
        status = data.get('status') or data.get('state_handoff', {}).get('status')
        assert status and status.startswith('PASS'), (gate, status)
        receipt['gates'][gate] = dict(status=status, sha256=sha(path))
    floors = HYBRID / 'kernels3-campaign/floors'
    receipt['default_floors'] = {}
    for name in ('default-check', 'refhash', 'default-restore'):
        log = floors / f'{name}.log'
        text = log.read_text()
        assert '\nexit 0\n' in text, (name, 'did not pass')
        receipt['default_floors'][name] = dict(exit=0, log_sha256=sha(log),
                                               skips=[l.strip() for l in text.splitlines() if l.strip().startswith('[SKIP]')])
    assert 'ALL 24 CASES BIT-IDENTICAL' in (floors / 'refhash.log').read_text()
    receipt['verdict'] = 'FAIL_HOLD' if hold else 'PASS_EMULATOR_BUDGET'
    receipt['admission'] = 'HOLD_FOR_PERFORMANCE_WORK' if hold else 'READY_FOR_PACKAGING_REVIEW'
    receipt['hardware_validated'] = False
    out = ROOT / 'modules/perky/hybrid/KERNEL_CF_QUALIFICATION.json'
    out.write_text(json.dumps(receipt, indent=2) + '\n')
    print(receipt['verdict'], receipt['admission'])
    sys.exit(1 if hold else 0)


if __name__ == '__main__':
    main()

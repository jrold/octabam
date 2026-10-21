#!/usr/bin/env python3
"""Freeze a hardware-informed model screening budget and assess an image.

Uses configuration labels from physical observations, not paired hardware
waveforms. Never estimates a hardware MHz rate by dividing unmatched maxima.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/verify'))
import calibrate_perky_hybrid_budget as replay

METRICS = {
    'steady_ISR_mean': ('steady_ISR', 'mean_us'),
    'steady_ISR_p99': ('steady_ISR', 'p99_us'),
    'steady_ISR_p99_9': ('steady_ISR', 'p99_9_us'),
    'full_ISR_peak': ('full_ISR', 'max_us'),
    'whole_CPU_mean': None,
    'whole_CPU_p99': ('whole_CPU', 'cf_ack_interval', 'p99_us'),
    'whole_CPU_peak': ('whole_CPU', 'cf_ack_interval', 'max_us_exact'),
}


def metric(row, name):
    if name == 'whole_CPU_mean':
        ack = row['whole_CPU']['cf_ack_interval']
        # main.cpp prints the cycles since transport start divided by `ran`.
        # Its separate ACK histogram also contains startup windows; those are
        # not the denominator of this playback-only cycle sum.
        return ack['total_cf_cycles'] / row['requested_transport_frames'] / 264
    value = row
    for key in METRICS[name]:
        value = value[key]
    return value


def read_rows(work):
    rows = []
    for name, case in replay.cases().items():
        if case['version'] == 'PKFM6' and case['FX'] != 'all14' and name != 'F6-WTWT-Slap-5-M1-shared12':
            continue
        path = work / name / 'ROW.json'
        row = json.loads(path.read_text())
        assert row['configuration'] == json.loads(json.dumps(case))
        assert row['image_sha256'] == replay.PINNED[case['version']]
        assert row['frames'] >= 16384
        assert row['clocks'] == dict(CF=264000000, PIT=132000000)
        assert row['full_ISR']['modeled_misses'] == 0
        assert row['playback_card_read_commands'] > 0
        inputs = json.loads((path.parent / 'INPUTS.json').read_text())
        command = inputs['command']
        row['requested_transport_frames'] = int(command[command.index('--frames') + 1])
        assert row['requested_transport_frames'] == 16384
        stack = json.loads((path.parent / 'stack.json').read_text())
        assert stack['frames'] == stack['frame_returns'] == row['frames']
        assert replay.histogram_stats(stack['budget_cycles']['steady_histogram']) == row['steady_ISR']
        assert replay.histogram_stats(stack['budget_cycles']['all_histogram']) == row['all_ISR']
        log = (path.parent / 'port.log').read_text()
        assert 'cycle clock: startup/pre-roll/transport use x1.00' in log
        assert 'one sample is 5986 ColdFire cycles at 264 MHz' in log
        assert 'PIT clock  : 132000000 Hz' in log
        assert replay.integrated.workload.parse_ot_emu_log(log) == row['whole_CPU']
        assert abs(metric(row, 'whole_CPU_mean') - row['whole_CPU']['cf_ack_interval']['mean_us']) <= .051
        assert row['whole_CPU']['cf_ack_interval']['frames_sampled'] == row['frames']
        assert row['whole_CPU']['dsp_exchange_and_cores']['words_not_in_time'] == 0
        row['receipt'] = str(path)
        row['receipt_sha256'] = replay.sha(path)
        rows.append(row)
    assert len({r['observer_sha256'] for r in rows}) == 1
    for version in replay.PINNED:
        sources = [r for r in rows if r['configuration']['version'] == version]
        image_paths = {p for r in sources for p in r['inputs'] if p.endswith(f'mainos_{version}.bin')}
        assert len(image_paths) == 1 and replay.sha(Path(next(iter(image_paths)))) == replay.PINNED[version]
    return rows


def evaluate(row, gates):
    checks = {name: dict(measured_us=metric(row, name), budget_us=budget,
                         pass_budget=metric(row, name) <= budget,
                         excess_percent=100 * (metric(row, name) / budget - 1))
              for name, budget in gates.items()}
    return dict(case=row['case'], pass_budget=all(c['pass_budget'] for c in checks.values()),
                checks=checks)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, default=replay.DEFAULT_WORK / 'replay')
    parser.add_argument('--output', type=Path, default=ROOT / 'modules/perky/hybrid/EMULATOR_BUDGET.json')
    parser.add_argument('--check', action='store_true', help='Exit 1 when the current candidate exceeds the frozen screening budget')
    parser.add_argument('--assess', type=Path, help='Assess a new ROW.json against the saved budget without recalibrating it')
    args = parser.parse_args()
    if args.assess:
        frozen = json.loads(args.output.read_text())
        row = json.loads(args.assess.read_text())
        inputs = json.loads((args.assess.parent / 'INPUTS.json').read_text())
        command = inputs['command']
        row['requested_transport_frames'] = int(command[command.index('--frames') + 1])
        assert row['observer_sha256'] == frozen['observer_sha256'], 'different measuring instrument'
        assert row['clocks'] == frozen['clocks'] and row['frames'] >= 16384
        assert row['full_ISR']['modeled_misses'] == 0 and row['playback_card_read_commands'] > 0
        assert replay.full.exact(row['exact_source']), 'source correctness failure'
        for name in ('pk_nhr_failures', 'pk_nhb_overflows', 'pk_nhb_clock_errors'):
            assert row['transport'][name] == 0
        assert row['transport']['pk_nhb_completed'] > 0
        assessment = evaluate(row, frozen['budgets_us'])
        assessment.update(budget_sha256=replay.sha(args.output), row_sha256=replay.sha(args.assess),
                          image_sha256=row['image_sha256'])
        print(json.dumps(assessment, indent=2))
        raise SystemExit(0 if assessment['pass_budget'] else 1)
    work = args.work.resolve()
    rows = read_rows(work)
    good = [r for r in rows if r['configuration']['role'] == 'working-shape']
    bad = [r for r in rows if r['configuration']['role'] == 'failing-shape']
    boundaries = {}
    gates = {}
    for name in METRICS:
        good_max = max(metric(r, name) for r in good)
        bad_min = min(metric(r, name) for r in bad)
        separating = good_max < bad_min
        # Freeze the observed working envelope as the engineering target. A
        # midpoint is reported only when it actually separates all four pairs.
        boundaries[name] = dict(working_envelope_max_us=good_max,
            failing_envelope_min_us=bad_min, separates_replayed_shapes=separating,
            separating_midpoint_us=(good_max + bad_min)/2 if separating else None)
        gates[name] = good_max
    candidates = [r for r in rows if r['configuration']['role'] == 'candidate']
    assessments = [evaluate(r, gates) for r in candidates]
    baseline_path = work / 'PERKY4S/ROW.json'
    baseline = json.loads(baseline_path.read_text())
    assert baseline['image_sha256'] == 'be74504aadc747817c54dc1226944abfb062244d404408c46d6040744a9ae1d0'
    assert baseline['observer_sha256'] == rows[0]['observer_sha256']
    assert baseline['clocks'] == dict(CF=264000000, PIT=132000000)
    assert baseline['requested_transport_frames'] == 16384
    assert len(baseline['stock_audio']) == 8 and baseline['playback_card_read_commands'] > 0
    assert baseline['full_ISR']['modeled_misses'] == 0
    hardware = ROOT / 'modules/perky/hybrid/CF_FOOTPRINT_20261016_HARDWARE.json'
    controls = [replay.DEFAULT_WORK / (n + '-OBSERVER_CONTROL.json') for n in
                ('H4-failing-shape-snare-bass', 'F6-WTWT-Slap-5-M1-shared12')]
    for path in controls:
        assert json.loads(path.read_text())['status'] == 'PASS_IDENTICAL_TARGET_DUMPS_AUDIO_AND_CYCLES'
    summary = dict(schema='octabam.perky.empirical-model-budget.v1',
        status='PASS_EMPIRICAL_WORKING_ENVELOPE' if all(a['pass_budget'] for a in assessments) else 'FAIL_EMPIRICAL_WORKING_ENVELOPE',
        calibration_status=('PROVISIONAL_CONFIGURATION_LABEL_SEPARATION' if any(
            b['separates_replayed_shapes'] for b in boundaries.values()) else
            'NO_UNIVERSAL_SCALAR_SEPARATOR_USE_WORKING_ENVELOPE_TARGET'),
        historical_image_sha256=replay.PINNED['PKH4O2'], current_image_sha256=replay.PINNED['PKFM6'],
        observer_sha256=rows[0]['observer_sha256'], clocks=dict(CF=264000000, PIT=132000000),
        PERKY4S_reference=dict(receipt=str(baseline_path), receipt_sha256=replay.sha(baseline_path),
            image_sha256=baseline['image_sha256'],
            metrics_us={m:metric(baseline,m) for m in METRICS},
            configuration=baseline['configuration'],
            scope='Exact hardware-confirmed PERKY4S MAIN; same port, stock samples and twelve FX, two DSP voices plus six STATIC tracks. Reference, not a matched voice-count performance A/B.'),
        physical_acceptance=False,
        admission='HOLD_FOR_PERFORMANCE_WORK' if not all(a['pass_budget'] for a in assessments) else 'PHYSICAL_ACCEPTANCE_STILL_REQUIRED',
        steady_window='Exclude first 512 completed audio interrupts; all remaining frames included.',
        hardware_evidence=dict(path=str(hardware), sha256=replay.sha(hardware)),
        hardware_labels=dict(working='2 DSP + 1 CF + 5 FLEX/STATIC tracks reported working',
                             failing='2 DSP + 2 CF + 3 stock tracks reported sluggish and eventual lockup'),
        controls={str(p):replay.sha(p) for p in controls},
        historical_source_binding=dict(
            record=str(ROOT/'modules/perky/hybrid/CF_OPTIMIZATION_20261016.json'),
            sha256=replay.sha(ROOT/'modules/perky/hybrid/CF_OPTIMIZATION_20261016.json'),
            meaning='Selected PKH4O2 source/image binding; same preserved binary used for one- and two-CF configurations.'),
        policy='Meet every observed working-envelope ceiling; do not allow an interrupt-only pass to hide background work. No clock throttling.',
        budgets_us=gates, separation=boundaries,
        historical_classification={role:[evaluate(r,gates) for r in rows if r['configuration']['role']==role]
                                   for role in ('working-shape','matched-one','failing-shape')},
        current_assessments=assessments,
        measurements=[dict(case=r['case'], configuration=r['configuration'], frames=r['frames'],
                           metrics_us={m:metric(r,m) for m in METRICS},
                           receipt=r['receipt'],receipt_sha256=r['receipt_sha256']) for r in rows],
        sources={str(p.relative_to(ROOT)):replay.sha(p) for p in (Path(__file__), Path(replay.__file__))},
        limits=[
            'Hardware algorithm pairs, complete control history, card contents and exact capture project are unavailable. These are matched local configuration replays, not exact hardware trace replays.',
            'All four algorithm choices in a configuration shape are model envelope samples, not four independently hardware-confirmed working or failing cases.',
            'Budgets are conservative engineering ceilings copied from the working-shape envelope, not physical safety thresholds. Overlapping distributions cannot establish a universal scalar conversion.',
            'Independent per-metric envelope maxima may come from different rows. No row or number is an analytical worst-case bound.',
            'Whole-CPU mean is the exact playback CPU-cycle sum divided by requested transport frames; ACK quantiles/peaks additionally contain startup windows. Both include intervening stock tasks and the actual Hat shadow worker; neither measures interrupt latency.',
            'No cache, SDRAM/card contention or physical UI latency has been added to the model.',
            'The nominal-clock exact-audio qualification remains evidence of correctness; it is not evidence of passing this performance gate.'])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    replay.save(args.output, summary)
    with args.output.with_suffix('.csv').open('w') as stream:
        writer = csv.writer(stream)
        writer.writerow(['case', *METRICS])
        for row in rows:
            writer.writerow([row['case'], *(f'{metric(row,m):.6f}' for m in METRICS)])
    print(summary['status'])
    print(json.dumps(dict(budgets_us=gates,separation=boundaries),indent=2))
    if args.check and summary['status'] != 'PASS_EMPIRICAL_WORKING_ENVELOPE':
        raise SystemExit(1)


if __name__ == '__main__':
    main()

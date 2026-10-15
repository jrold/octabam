#!/usr/bin/env python3
"""Audit cumulative PKHYB2P hardware exports against the C field layout.

Inputs stay read-only. Differences are snapshot intervals, never isolated runs.
All unsigned counters use modular subtraction; spans use the 132 MHz timer.
"""
import argparse
import hashlib
import json
import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/perky'))
from read_hybrid_profile import read_export


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def layout():
    source = (ROOT / 'modules/perky/control_cf_dsp_hybrid.c').read_text()
    body = source.split('} pk_hybrid_profiler;')[0].rsplit('typedef struct {', 1)[1]
    body = re.sub(r'/\*.*?\*/', '', body, flags=re.S)
    constants = {'PK_HYB_CF_INSTANCE_COUNT': 2, 'PK_HYB_PROF_RING_LEN': 64}
    fields = {}
    offset = 0
    for declaration in body.split(';'):
        if not declaration.strip():
            continue
        match = re.fullmatch(r'\s*uint32_t\s+(\w+)(?:\[(\w+)\])?\s*', declaration)
        assert match, declaration
        name, extent = match.groups()
        count = constants.get(extent, int(extent) if extent and extent.isdigit() else 1)
        fields[name] = (offset, count)
        offset += count
    assert offset == 445
    return fields


def analyze(directory, build):
    fields = layout()
    snapshots = []
    previous = None
    phases = ('full_frame', 'cf_callback', 'cf_control', 'cf_render', 'cf_pack', 'dsp_callback')
    counts = ('frame_count', 'cf_active_frames', 'dsp_active_frames', 'cf_sample_count',
              'ui_tick_count', 'deadline_misses_100pct', 'margin_exceeded_80pct',
              'reset_count', 'readiness_faults', 'snapshot_retries', 'handoff_pending_frames')
    for path in sorted(directory.glob('PKH2000[0-7].PRF')):
        decoded = read_export(path, build)
        words = struct.unpack('>445I', path.read_bytes()[84:])
        values = {name: words[o] if n == 1 else list(words[o:o+n])
                  for name, (o, n) in fields.items()}
        # Independently located fields must agree with the existing decoder.
        profile = decoded['profile']
        for name in counts[:7]:
            assert values[name] == profile[name], name
        assert values['reset_count'] == profile['extension']['reset_count']
        assert values['histogram'] == profile['extension']['histogram_ticks_1024']
        assert sum(values['histogram']) == values['frame_count']
        sums = {phase: (values['sum_' + phase + '_hi'] << 32) | values['sum_' + phase + '_lo']
                for phase in phases}
        assert abs(sums['full_frame']/values['frame_count'] -
                   profile['dtim3_ticks']['mean_perky_service_ticks']) < .006
        row = {'file': path.name, 'sha256': sha(path), 'source_id': decoded['source_id'],
               'export_sequence': decoded['sequence'], 'counters': {k: values[k] for k in counts},
               'active_mask': hex(values['active_voice_mask']),
               'active_CF_DSP_voices': [values['active_cf_voices'], values['active_dsp_voices']],
               'calls': values['inst_calls'], 'triggers': values['inst_trigs'],
               'cumulative_sums_ticks': sums,
               'cumulative_max_us': {phase: values['max_' + phase + '_ticks']/132 for phase in phases},
               'period_min_max_ticks': [values['period_min_ticks'], values['period_max_ticks']],
               'wait_loop_max_us': [v/132 for v in values['wait_loop_max_ticks']],
               'wait_loop_sum_ticks': profile['extension']['wait_loop_sum_ticks']}
        base = previous if previous is not None else {k: 0 for k in counts}
        delta = {k: (values[k] - base[k]) & 0xffffffff for k in counts}
        assert delta['frame_count'] > 0
        hist = [(v - (previous['histogram'][i] if previous else 0)) & 0xffffffff
                for i, v in enumerate(values['histogram'])]
        assert sum(hist) == delta['frame_count']
        means = {phase: ((sums[phase] - (previous['sums'][phase] if previous else 0)) &
                          0xffffffffffffffff)/delta['frame_count']/132 for phase in phases}
        means['CF_unattributed'] = means['cf_callback'] - sum(means[k] for k in ('cf_control','cf_render','cf_pack'))
        means['outside_CF_and_DSP_callbacks'] = means['full_frame'] - means['cf_callback'] - means['dsp_callback']
        row['interval'] = {'from': snapshots[-1]['file'] if snapshots else 'boot', 'counts': delta,
                           'mean_us_per_ISR': means, 'histogram_delta': hist,
                           'inst_calls_delta': [(v - (previous['inst_calls'][i] if previous else 0)) & 0xffffffff
                                                for i, v in enumerate(values['inst_calls'])],
                           'UI_ticks_per_1000_frames': 1000*delta['ui_tick_count']/delta['frame_count']}
        row['recent_64_mean_us'] = {phase: sum(values['ring_' + short + '_ticks'])/64/132
                                  for phase, short in [('full_frame','full'),('cf_callback','cf'),
                                                       ('cf_control','ctrl'),('cf_render','rend'),('cf_pack','pack')]}
        snapshots.append(row)
        previous = dict(values, sums=sums)
    assert len(snapshots) == 8
    assert len({s['source_id'] for s in snapshots}) == 1
    return {'schema': 'octabam.perky.hardware-profile-intervals.v1', 'status': 'PASS',
            'layout_words': 445, 'timer_hz': 132000000, 'snapshots': snapshots,
            'limits': ['Cumulative maxima cannot be subtracted or summed across phases.',
                       'No per-algorithm timing, UI queue depth, missing-input counter, or cache-stall counter exists in PRF v2.',
                       'UI ticks count hybrid UI hook calls, not UI input events or completed screen redraws.',
                       'period_max spans stop/start and modulo timer gaps; it is not a continuous-play jitter bound.',
                       'Full-frame stamp precedes final profiler tail and return; not an exhaustive silicon WCET.']}


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('directory', type=Path)
    ap.add_argument('--build', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    report = analyze(args.directory, json.loads(args.build.read_text()))
    args.out.write_text(json.dumps(report, indent=2) + '\n')
    for row in report['snapshots']:
        interval = row['interval']; means = interval['mean_us_per_ISR']
        print(row['file'], 'frames', interval['counts']['frame_count'],
              'misses', interval['counts']['deadline_misses_100pct'],
              'us', {k: round(v, 3) for k, v in means.items()},
              'CF calls', interval['inst_calls_delta'],
              'UI/1000', round(interval['UI_ticks_per_1000_frames'], 3))

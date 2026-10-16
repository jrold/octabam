#!/usr/bin/env python3
"""Audit the frozen paired campaign and full-duration timing receipts.

Reads actual target/emulator outputs; never builds, runs, installs or alters an
image. The split sustained schedule includes its completed first serial row.
--snapshot reports incomplete coverage without qualifying it.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

import measure_perky_hybrid_campaign as campaign
from hybrid_profile import decode_profiler_dump


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def audit(work, output, snapshot=False):
    receipts = {}
    selected = read(work/'final/probe/BUILD.json')['artifacts']
    selected_main = selected['mainos']['sha256']
    selected_elf = selected['runtime_elf']['sha256']

    def load(path):
        data = read(path)
        receipts[str(path)] = sha(path)
        return data

    def hashes(items):
        for path, digest in items.items():
            assert sha(path) == digest, ('input/report drift', path)

    def row(data, directory, frames, full_duty):
        assert data['frames'] == frames
        assert data['cycle_clock_factor'] == 1.0
        assert data['coldfire_clock_hz'] == 264000000
        assert data['pit_clock_hz'] == 132000000
        hashes(data['inputs'])
        raw = load(directory/'ROW.json')
        assert all(data[key] == value for key, value in raw.items()), directory
        log = (directory/'port.log').read_text()
        assert re.search(rf'frames run\s*:\s*{frames}\s+since transport start.*REACHED', log), directory
        assert 'FAULT:' not in log and 'ILLEGAL' not in log
        assert 'PIT clock  : 132000000 Hz' in log
        receipts[str(directory/'port.log')] = sha(directory/'port.log')
        receipts[str(directory/'prof.bin')] = sha(directory/'prof.bin')
        prof = data['dtim3_profiler']
        assert decode_profiler_dump((directory/'prof.bin').read_bytes()) == prof
        assert prof['profiler_enabled'] and prof['cf_armed']
        assert prof['frame_count'] == frames
        assert sum(prof['extension']['histogram_ticks_1024']) == frames
        assert prof['active_voice_mask'] == '0x33'
        assert prof['extension']['full_frame_window']
        assert prof['extension']['readiness_faults'] == 0
        if full_duty:
            assert prof['cf_active_frames'] == prof['dsp_active_frames'] == frames
            assert prof['cf_sample_count'] == 32*frames
            assert prof['dtim3_ticks']['inst_calls'] == [2*frames-1]*2
            # The 120 BPM fixture has 45 trigs per 64-step / eight-second
            # pattern. Require at least five per second on BOTH voices,
            # allowing startup/edge phase without accepting a stuck pattern
            # that merely continues calling the renderer through its tail.
            minimum_triggers = int(frames*16/44100*5)
            assert all(n >= minimum_triggers for n in prof['dtim3_ticks']['inst_trigs'])
        dsp = data['ot_emu']['dsp_exchange_and_cores']
        assert dsp['words_not_in_time'] == 0
        assert dsp['nonzero_words_to_dsps'] > 0 and dsp['nonzero_words_from_dsps'] > 0
        assert data['ot_emu']['cf_ack_interval']['frames_sampled'] == frames
        return {
            'pair': data['row'], 'frames': frames,
            'timer_window_mean_us': prof['dtim3_us']['mean_perky_service_us'],
            'timer_window_max_us': prof['dtim3_us']['max_full_frame_us'],
            'timer_window_deadline_misses': prof['deadline_misses_100pct'],
            'timer_window_above_80_percent': prof['margin_exceeded_80pct'],
            'trigger_count_per_instance': prof['dtim3_ticks']['inst_trigs'],
            'ACK_work': data['ot_emu']['cf_ack_interval'],
        }

    def matrix(name, expected_frames, full_duty=False):
        path = work/name/'MATRIX.json'
        data = load(path)
        hashes(data['inputs'])
        if not snapshot:
            assert data['status'] == 'PASS_MEASURED_MATRIX', path
        rows = {r['row']: (r, row(r, path.parent/r['row'], expected_frames, full_duty))
                for r in data['rows']}
        assert len(rows) == len(data['rows']), ('duplicate matrix row', path)
        return rows

    expected = {'_'.join(pair) for pair in campaign.PAIRS}
    baseline = {**matrix('baseline-matrix-a', 4096), **matrix('baseline-matrix-b', 4096)}
    candidate = {**matrix('final-matrix-a', 4096), **matrix('final-matrix-b', 4096)}
    assert baseline.keys() == candidate.keys() == expected
    paired = []
    for name in sorted(expected):
        before, _ = baseline[name]
        after, summary = candidate[name]
        assert selected_main in after['inputs'].values()
        assert selected_elf in after['inputs'].values()
        for value in (before, after):
            full = value['executed_full_ISR']
            hashes(full['reports'])
            receipts.update(full['reports'])
            reports = [read(Path(path)) for path in full['reports']]
            stack = next(r for r in reports if 'full_ISR_max_cycles' in r)
            private = next(r for r in reports if 'switched' in r)
            assert stack['frames'] == stack['frame_returns'] == private['switched'] == private['restored'] == 4096
            assert stack['DMA_read_write_overlaps'] == stack['guard_writes_after_dispatch'] == 0
            assert private['ownership_register_frame_or_mask_violations'] == private['fence_writes'] == 0
            assert not any(t['outside_extent'] for t in stack['stacks'])
            assert full['maximum_cycles'] == stack['full_ISR_max_cycles']
            assert full['duration_misses'] == stack['ISR_duration_misses']
        assert after['executed_full_ISR']['duration_misses'] == 0
        assert summary['timer_window_deadline_misses'] == 0
        assert set(after['audio_verification']) == {f'T{i}' for i in range(1, 9)}
        assert all(track['chain_significant'] > 64 for track in after['audio_verification'].values())
        paired.append(dict(pair=name, baseline=before['executed_full_ISR'],
                           candidate=after['executed_full_ISR']))

    first = work/'final-sustained/snare_snare/ROW.json'
    data = load(first)
    sustained = {'snare_snare': (data, row(data, first.parent, 165376, True))}
    for name in ('final-sustained-a', 'final-sustained-b'):
        shard = matrix(name, 165376, True)
        assert not sustained.keys() & shard.keys(), 'duplicated sustained pair'
        sustained.update(shard)
    assert sustained.keys() <= expected
    stress = matrix('final-stress', 1653750, True)
    assert stress.keys() <= {'snare_snare'}
    complete = sustained.keys() == expected and len(stress) == 1
    if not snapshot:
        assert complete, ('incomplete coverage', sorted(expected-sustained.keys()), len(stress))
    summaries = [r[1] for r in sustained.values()] + [r[1] for r in stress.values()]
    for data, _ in [*sustained.values(), *stress.values()]:
        assert selected_main in data['inputs'].values()
        assert selected_elf in data['inputs'].values()
    for summary in summaries:
        assert summary['timer_window_deadline_misses'] == 0
        assert summary['timer_window_above_80_percent'] == 0
        assert summary['ACK_work']['frames_over_362_8us_period'] == 0
    if complete:
        worst = max(sustained.values(), key=lambda r: r[1]['timer_window_max_us'])[0]['row']
        assert worst == 'snare_snare', ('stress must cover discovered worst timer row', worst)
    result = {
        'schema': 'octabam.perky.campaign-receipt-audit.v1',
        'status': 'PASS_COMPLETE_LOCAL_TIMING_COVERAGE' if complete else 'INCOMPLETE_SNAPSHOT',
        'MAIN_sha256': selected_main,
        'runtime_ELF_sha256': selected_elf,
        'paired_full_ISR': paired,
        'sustained_60_second_rows': [sustained[k][1] for k in sorted(sustained)],
        'continuous_600_second_rows': [stress[k][1] for k in sorted(stress)],
        'missing_sustained_pairs': sorted(expected-sustained.keys()),
        'receipt_hashes': receipts,
        'limits': [
            'All timing is emulated ColdFire at 264 MHz, not physical MKII timing.',
            'Full executed ISR observer is present in the paired 4096-frame rows.',
            'Sustained/continuous runs use the firmware timer window; entry-save and post-stamp footer are excluded.',
            'ACK-to-ACK CPU work includes intervening stock tasks; it is not ISR duration or interrupt latency.',
            'All-eight-track audio is verified in separate short captures for every paired row.',
            'Does not replace cold-boot, memory, package, lifecycle or private-stack qualification.',
        ],
        'hardware_qualified': False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2)+'\n')
    print(result['status'], len(sustained), 'sustained rows;', len(stress), 'continuous rows')
    return result


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--work', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--snapshot', action='store_true')
    args = ap.parse_args()
    audit(args.work.resolve(), args.out.resolve(), args.snapshot)

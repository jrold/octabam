#!/usr/bin/env python3
"""Actual production lifecycle with positive on-demand handoff witnesses."""
import json
from pathlib import Path
import qualify_perky_full_map_lifecycle as lifecycle

COUNTERS = ('pk_nhb_inner_calls', 'pk_nhb_snapshot_requests', 'pk_nhb_snapshot_completed',
            'pk_nhb_snapshot_rejected', 'pk_nhb_snapshot_words', 'pk_nhb_snapshot_cancelled',
            'pk_nhb_cancelled_jobs', 'pk_nhb_replay_frames', 'pk_nhb_handoff_jobs')


def main():
    lifecycle.COUNTS += COUNTERS
    lifecycle.main()
    path = lifecycle.W / 'lifecycle/RESULT.json'
    result = json.loads(path.read_text())
    counts = result['events'][-1]['counts']
    assert counts['pk_nhb_inner_calls'] > 0, 'CF catch-up renderer was never exercised'
    assert counts['pk_nhb_snapshot_requests'] >= counts['pk_nhb_snapshot_completed'] > 0
    assert counts['pk_nhb_snapshot_words'] >= 190 * counts['pk_nhb_snapshot_completed']
    assert counts['pk_nhb_replay_frames'] > 0 and counts['pk_nhb_handoff_jobs'] > 0
    assert counts['pk_nhb_completed'] <= counts['pk_nhb_produced']
    assert counts['pk_nhb_switches'] >= 22
    result['state_handoff'] = dict(
        status='PASS_ACTUAL_IMAGE_ON_DEMAND_HANDOFF_AND_GENERATIONS', counters=counts,
        source_sha256={str(Path(__file__).resolve()): lifecycle.f.c.sha(Path(__file__).resolve())},
        limits=['Real panel/backend transitions and independent source oracle; no target-state repair.',
                'Actual native-call counter is positive in this directed run and must be zero in steady DSP-owned measurement rows.'])
    path.write_text(json.dumps(result, indent=2) + '\n')
    print(result['state_handoff']['status'])


if __name__ == '__main__':
    main()

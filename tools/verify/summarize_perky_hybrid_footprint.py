#!/usr/bin/env python3
"""Summarize hash-bound target traffic and instruction working-set receipts."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import subprocess


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--bench', type=Path, required=True)
    ap.add_argument('--profile', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    bench, profile = args.bench.resolve(), args.profile.resolve()
    b = json.loads((bench/'BENCH.json').read_text())
    p = json.loads((profile/'PROFILE.json').read_text())
    assert b['status'] == 'PASS_EXACT_FROZEN_REFERENCE'
    assert p['status'] == 'PASS_EXACT_UNPERTURBED_SYMBOL_PROFILE'
    for name in ('target.elf', 'target.bin', 'target.nm', 'costs.csv'):
        assert sha(bench/name) == b['artifacts'][name]
        assert (profile/name).read_bytes() == (bench/name).read_bytes()
    assert sha(profile/'resources.csv') == p['outputs']['resources.csv']
    costs = list(csv.DictReader((bench/'costs.csv').open()))
    traffic = list(csv.DictReader((profile/'resources.csv').open()))
    # The canonical runner also performs two startup init controls and two
    # un-emitted tail setup calls per algorithm. Join explicitly by entry/pair;
    # assert that the only skipped calls are those twenty setup controls.
    matched, skipped, index = [], [], 0
    for cost in costs:
        entry = 'bench_init' if cost['phase']=='init' else 'bench_prepare' if cost['phase'].startswith('prepare') else 'bench_render'
        pair = cost['left']+'/'+cost['right']
        while index < len(traffic) and (traffic[index]['pair'], traffic[index]['entry']) != (pair, entry):
            skipped.append(traffic[index]); index += 1
        assert index < len(traffic), 'canonical/resource call sequence diverged'
        matched.append((cost, traffic[index])); index += 1
    assert index == len(traffic) and len(skipped)==20
    assert all(r['entry'] in ('bench_init','bench_prepare') for r in skipped)
    metrics = [k for k in traffic[0] if k not in ('call','pair','entry','cycles','instructions')]
    for c, r in matched:
        for key in ('cycles','instructions'):
            if key in r:
                assert c[key] == r[key], 'resource/cost call attribution changed'

    def summarize(rows):
        assert rows
        out = {'calls': len(rows)}
        for key in ('cycles','instructions','stack_bytes'):
            values = sorted(int(c[key]) for c, _ in rows)
            out[key] = dict(mean=sum(values)/len(values), p50=values[(len(values)-1)//2],
                            p95=values[(len(values)-1)*95//100], p99=values[(len(values)-1)*99//100], maximum=values[-1])
        out['resources'] = {}
        for key in metrics:
            values = [int(r[key]) for _, r in rows]
            out['resources'][key] = dict(mean=sum(values)/len(values), maximum=max(values))
        return out

    algorithms = {}
    for algo in ('V1M1','V1M2','V1M3','V2M1','V2M2','V2M3','snare','bass','third'):
        rows = [(c,r) for c,r in matched if c['left']==c['right']==algo]
        algorithms[algo] = {
            'two_voice_render_before_switch': summarize([(c,r) for c,r in rows if c['phase']=='render' and int(c['frame'])<40]),
            'two_voice_tail': summarize([(c,r) for c,r in rows if c['phase']=='tail-render'])}
    sections = subprocess.check_output(['m68k-elf-size','-A',str(bench/'target.elf')], text=True)
    voices_path = profile/'resources.csv-voices.csv'
    pair_resources = {}
    if voices_path.is_file():
        assert sha(voices_path) == p['outputs'][voices_path.name]
        voices = list(csv.DictReader(voices_path.open()))
        assert len(voices) == 2*sum(r['entry']=='bench_render' for r in traffic)
        grouped, voice_index, by_call = {}, 0, {}
        for row in traffic:
            if row['entry'] != 'bench_render':
                continue
            left, right = voices[voice_index:voice_index+2]
            voice_index += 2
            assert left['pair'] == right['pair'] == row['pair']
            assert left['entry'].startswith('0:') and right['entry'].startswith('1:')
            by_call[row['call']] = (left, right)
        for cost, row in matched:
            if cost['phase']=='render' and int(cost['frame'])<40:
                grouped.setdefault(row['pair'], []).append((cost,row,*by_call[row['call']]))
        for pair, rows in sorted(grouped.items()):
            fields = [k for k in voices[0] if k not in ('call','pair','entry')]
            out = {'samples':len(rows), 'voices':{}}
            for index, label in ((2,'first'),(3,'second')):
                out['voices'][label] = {k:{'mean':sum(int(r[index][k]) for r in rows)/len(rows),
                                          'maximum':max(int(r[index][k]) for r in rows)} for k in fields}
            out['two_voice_including_benchmark_adapter'] = summarize([(r[0],r[1]) for r in rows])
            overhead = [int(c['cycles'])-int(l['cycles'])-int(r['cycles']) for c,_,l,r in rows]
            assert min(overhead)>=0
            out['benchmark_adapter_cycles'] = dict(mean=sum(overhead)/len(overhead), maximum=max(overhead))
            pair_resources[pair] = out
    report = dict(schema='octabam.perky.architectural-footprint.v1', status='PASS_BOUND_UNPERTURBED_FOOTPRINT',
                  inputs={str(q): sha(q) for q in (bench/'BENCH.json', profile/'PROFILE.json', profile/'resources.csv', Path(__file__).resolve())},
                  sections={m[1]:int(m[2]) for m in re.finditer(r'^(\.\w+)\s+(\d+)\s+\d+', sections, re.M)},
                  matched_calls=len(matched), omitted_setup_calls=len(skipped), algorithms=algorithms,
                  per_voice_pair_resources=pair_resources,
                  limits=['Requested architectural bytes and 16-byte address-line working sets, not cache misses or bus transactions.',
                          'Instruction byte working sets include decoded extension words; instruction_stream reads are separated from data.',
                          'Stack bytes include ABI saves, local arrays and spills; these are not exclusively compiler spills.',
                          'Asset memory is explicitly mapped because auto-grown pages bypass read watches.',
                          'Canonical rows are two CF voices, excluding firmware callbacks, stock work, interrupts and physical stalls.',
                          'First/second nested renderer scopes share a two-voice execution; they are not standalone single-voice full-machine runs or a cache model.',
                          'Initial algorithm labels cease to describe execution after frame 40; only pre-switch rows and separate tails are summarized.'])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2)+'\n')
    print(report['status'])


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Summarize measured first-frame T6 admission work and address unions."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
from statistics import mean


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def summary(work, output):
    receipt = json.loads((work / 'RECEIPT.json').read_text())
    assert receipt['status'] == 'PASS'
    assert receipt['result']['activation_splits'] == 17
    path = work / 'activation.csv'
    assert sha(path) == receipt['outputs']['activation.csv']
    rows = list(csv.DictReader(path.open()))
    warm = receipt['result']['activation_frame']
    first = [r for r in rows if int(r['frame']) == warm]
    assert len(first) == 850

    def span(values):
        return dict(minimum=min(values), mean=mean(values), maximum=max(values))

    groups = {}
    for prof in ('0', '1'):
        for left in ('V1', 'V2', 'snare', 'bass', 'third'):
            for right in ('V1', 'V2', 'snare', 'bass', 'third'):
                selected = [r for r in first if (r['profiler'], r['T2'], r['T6']) == (prof, left, right)]
                assert len(selected) == 17
                steady = [r for r in rows if int(r['frame']) > warm
                          and (r['profiler'], r['T2'], r['T6']) == (prof, left, right)]
                assert len(steady) == 119
                value = lambda r, k: int(r[k])
                groups[f'{prof}:{left}/{right}'] = dict(
                    first_T6_frame_cycles=span([value(r,'T6_cycles') for r in selected]),
                    incremental_total_callback_cycles=span([
                        value(r,'T6_cycles') + value(r,'dual_T2_cycles') - value(r,'baseline_T2_cycles') for r in selected]),
                    T2_cycle_change=span([value(r,'dual_T2_cycles') - value(r,'baseline_T2_cycles') for r in selected]),
                    additional_instruction_byte_union=span([
                        value(r,'dual_code_bytes') - value(r,'baseline_code_bytes') for r in selected]),
                    additional_instruction_lines16_union=span([
                        value(r,'dual_code_lines16') - value(r,'baseline_code_lines16') for r in selected]),
                    T6_architectural_requests={g: dict(
                        reads=span([value(r,f'T6_{g}_read_bytes') for r in selected]),
                        writes=span([value(r,f'T6_{g}_write_bytes') for r in selected]),
                        additional_lines16_union=span([
                            value(r,f'dual_{g}_lines16') - value(r,f'baseline_{g}_lines16') for r in selected]))
                        for g in ('stack','state','PCM','source_RAM','instruction_stream',
                                  'module_other','external_control_and_reservation')},
                    next_seven_frames=dict(
                        samples=len(steady),
                        T2_cycle_change=span([value(r,'dual_T2_cycles')-value(r,'baseline_T2_cycles') for r in steady]),
                        additional_total_callback_cycles=span([
                            value(r,'T6_cycles')+value(r,'dual_T2_cycles')-value(r,'baseline_T2_cycles') for r in steady]),
                        additional_instruction_byte_union=span([
                            value(r,'dual_code_bytes')-value(r,'baseline_code_bytes') for r in steady]),
                        additional_data_lines16_union={g:span([
                            value(r,f'dual_{g}_lines16')-value(r,f'baseline_{g}_lines16') for r in steady])
                            for g in ('stack','state','PCM','source_RAM','module_other','external_control_and_reservation')},
                        scope='Seven following dense frames for each of the 17 admission histories. CPU/branch effects only; no silicon cache latency.'))
    report = dict(status='PASS_ALL_25_PAIRS_BOTH_PROFILE_MODES_17_ADMISSION_SPLITS',
                  inputs={str(work/'RECEIPT.json'):sha(work/'RECEIPT.json'), str(path):sha(path)},
                  exactness=receipt['result'], first_frame=groups,
                  scope='Two stock-format callbacks making the first T6 frame after 32 T2-only warmup frames. Ranges cover all first splits 0..16. Different subsequent histories are not combined with this admission window.',
                  limits=['Executed code/data address unions and architectural byte requests are not cache misses or SDRAM transactions.',
                          'Native CPU and branch-predictor execution only; stock ISR, DSP, actual IRQ stack coloring and physical latency are excluded.',
                          'Use the full-OS matched matrix for incremental total IRQ cost and panel test for actual stock-chooser admission.'])
    output.write_text(json.dumps(report, indent=2)+'\n')
    print(report['status'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    summary(args.work.resolve(), args.out.resolve())

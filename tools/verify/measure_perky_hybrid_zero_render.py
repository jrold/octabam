#!/usr/bin/env python3
"""Measure empty engine renders and complete ISR spans on one hybrid image.

Uses existing PC watches, not additional firmware instrumentation. The first
ISR LEA is missed by an interrupt-step PC watch, so watch the next instruction
and account for the model's LEA (1 cycle) and RTE (10 cycles) separately.
"""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import statistics
import subprocess

import verify_perky_hybrid_workload as workload

ROOT = Path(__file__).resolve().parents[2]
ENGINES = ('pk_cf_wt_render', 'pk_cf_res_snare_render',
           'pk_cf_res_bass_render', 'pk_cf_nt_shared_render')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def measure(probe, output, frames, *, profiler_enable=1, cf_arm=1):
    image, elf = probe/'mainos_PKHYB2P.bin', probe/'platform/runtime.elf'
    symbols = workload.load_elf_symbols(elf)
    nm = subprocess.check_output(['m68k-elf-nm', '-S', str(elf)], text=True)
    sizes = {f[3]: int(f[1], 16) for line in nm.splitlines()
             if len(f := line.split()) == 4}
    returns = {}
    for name in ENGINES:
        dis = subprocess.check_output([
            'm68k-elf-objdump', '-d', str(elf),
            f'--start-address={symbols[name]}',
            f'--stop-address={symbols[name]+sizes[name]}'], text=True)
        for pc in re.findall(r'^([0-9a-f]+):\s+4e75\s+rts\b', dis, re.M):
            returns[int(pc, 16)] = name
    assert set(returns.values()) == set(ENGINES)
    starts = {symbols[name]: name for name in ENGINES}
    frame_start, frame_end = symbols['pk_hybrid_isr']+4, symbols['pk_hybrid_isr_rte']
    sources = (image, elf, workload.EMU, Path(__file__), Path(workload.__file__))
    hashes = {str(p): digest(p) for p in sources}
    baseline = json.loads((ROOT/'modules/perky/hybrid/BASELINE.json').read_text())
    row = workload.run_integrated_row(
        'zero_render_snare_snare', 'snare', 'snare', image_path=image,
        syms=symbols, project_src=Path(baseline['project']['root']),
        work_dir=output/'workload', tone_path=ROOT/'out/perky/hybrid/probe/workload/HYB_SAMPLER_440.wav',
        frames=frames, cycle_clock=1.0,
        profiler_enable=profiler_enable, cf_arm=cf_arm,
        watch_pcs=[frame_start, frame_end, *starts, *returns])
    assert hashes == {str(p): digest(p) for p in sources}, 'execution source drift'
    log = (output/'workload/port.log').read_text()
    assert re.search(r'cycle clock: on, x1\.00.*at 264 MHz', log), 'clock/model mismatch'
    hits = re.findall(r'\[\s*\d+ cyc\s+(\d+)\] at (0x[0-9a-f]+).*?'
                      r'\[sp (0x[0-9a-f]+): ([^\]]+)\]', log)
    active = None
    frame = None
    spans = []
    per_frame_empty = []
    empty_cycles = 0
    counts = defaultdict(list)
    frame_sp = None
    lowest_sp = None
    deepest_observed = 0
    for cyc, pc, sp, stack in hits:
        cyc, pc = int(cyc), int(pc, 16)
        stack = [int(x, 0) for x in stack.split()]
        if pc == frame_start:
            assert frame is None
            frame, empty_cycles = cyc, 0
            frame_sp = lowest_sp = int(sp, 16)
        elif pc == frame_end:
            assert frame is not None and active is None
            assert int(sp, 16) == frame_sp+16, 'unbalanced ISR stack'
            deepest_observed = max(deepest_observed, frame_sp+16-lowest_sp)
            spans.append(cyc-frame+11)
            per_frame_empty.append(empty_cycles)
            frame = None
        elif pc in starts:
            assert active is None and frame is not None
            lowest_sp = min(lowest_sp, int(sp, 16))
            # C ABI stack: return PC, state*, destination*, sample count, ...
            active = (starts[pc], cyc, stack[3], int(sp, 16))
        elif pc in returns:
            assert active is not None and active[0] == returns[pc]
            name, begin, count, entry_sp = active
            assert int(sp, 16) == entry_sp
            elapsed = cyc-begin+8  # direct JSR=3, RTS=5 in corrected model
            counts[(name, count)].append(elapsed)
            if count == 0:
                empty_cycles += elapsed
            active = None
    assert len(spans) == frames and frame is None and active is None
    order = sorted(spans)
    peak = max(range(len(spans)), key=spans.__getitem__)
    result = {
        'status': 'MEASURED_LOCAL_MODEL_ONLY', 'frames': frames,
        'coldfire_clock_hz': workload.CF_CLOCK_HZ,
        'stack_observation': {
            'balanced_ISR_returns': len(spans),
            'observed_depth_below_exception_frame_bytes': deepest_observed,
            'scope': 'Sampled at engine entries only; lower bound, not stack/nesting qualification'},
        'execution_hashes': hashes, 'workload': row,
        'whole_ISR': {
            'mean_us': statistics.mean(spans)/(workload.CF_CLOCK_HZ/1e6),
            'p99_us': order[int(.99*len(order))]/(workload.CF_CLOCK_HZ/1e6),
            'max_cycles': max(spans), 'max_us': max(spans)/(workload.CF_CLOCK_HZ/1e6),
            'deadline_misses': sum(x/(workload.CF_CLOCK_HZ/1e6) > 16/44100*1e6 for x in spans),
            'peak_frame_index': peak,
            'empty_render_us_in_peak_frame': per_frame_empty[peak]/(workload.CF_CLOCK_HZ/1e6),
            'mean_empty_render_us_per_frame': statistics.mean(per_frame_empty)/(workload.CF_CLOCK_HZ/1e6),
            'max_empty_render_us_per_frame': max(per_frame_empty)/(workload.CF_CLOCK_HZ/1e6),
            'scope': 'Matched PC spans on every frame, plus LEA=1/RTE=10 model cycles'},
        'engine_calls': [
            {'engine': name, 'samples': count, 'calls': len(values),
             'mean_cycles': statistics.mean(values), 'max_cycles': max(values),
             'mean_us': statistics.mean(values)/(workload.CF_CLOCK_HZ/1e6), 'max_us': max(values)/(workload.CF_CLOCK_HZ/1e6)}
            for (name, count), values in sorted(counts.items())],
        'limits': ['Corrected CPU-cycle model, not silicon/cache/stall qualification.',
                   'Engine spans include model JSR/RTS but not caller setup.']}
    (output/'MEASUREMENT.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k: result[k] for k in ('whole_ISR', 'engine_calls')}, indent=2))
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--probe', type=Path, default=ROOT/'out/perky/hybrid/probe')
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--frames', type=int, default=4000)
    ap.add_argument('--profiler-enable', type=int, choices=(0, 1), default=1)
    ap.add_argument('--cf-arm', type=int, choices=(0, 1), default=1)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    measure(args.probe.resolve(), args.out.resolve(), args.frames,
            profiler_enable=args.profiler_enable, cf_arm=args.cf_arm)


if __name__ == '__main__':
    main()

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


def measure(probe, output, frames):
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
        watch_pcs=[frame_start, frame_end, *starts, *returns])
    assert hashes == {str(p): digest(p) for p in sources}, 'execution source drift'
    log = (output/'workload/port.log').read_text()
    hits = re.findall(r'\[\s*\d+ cyc\s+(\d+)\] at (0x[0-9a-f]+).*?'
                      r'\[sp (0x[0-9a-f]+): ([^\]]+)\]', log)
    active = None
    frame = None
    spans = []
    per_frame_empty = []
    empty_cycles = 0
    counts = defaultdict(list)
    for cyc, pc, sp, stack in hits:
        cyc, pc = int(cyc), int(pc, 16)
        stack = [int(x, 0) for x in stack.split()]
        if pc == frame_start:
            assert frame is None
            frame, empty_cycles = cyc, 0
        elif pc == frame_end:
            assert frame is not None and active is None
            spans.append(cyc-frame+11)
            per_frame_empty.append(empty_cycles)
            frame = None
        elif pc in starts:
            assert active is None and frame is not None
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
        'execution_hashes': hashes, 'workload': row,
        'whole_ISR': {
            'mean_us': statistics.mean(spans)/266,
            'p99_us': order[int(.99*len(order))]/266,
            'max_cycles': max(spans), 'max_us': max(spans)/266,
            'deadline_misses': sum(x/266 > 16/44100*1e6 for x in spans),
            'peak_frame_index': peak,
            'empty_render_us_in_peak_frame': per_frame_empty[peak]/266,
            'mean_empty_render_us_per_frame': statistics.mean(per_frame_empty)/266,
            'max_empty_render_us_per_frame': max(per_frame_empty)/266,
            'scope': 'Matched PC spans on every frame, plus LEA=1/RTE=10 model cycles'},
        'engine_calls': [
            {'engine': name, 'samples': count, 'calls': len(values),
             'mean_cycles': statistics.mean(values), 'max_cycles': max(values),
             'mean_us': statistics.mean(values)/266, 'max_us': max(values)/266}
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
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    measure(args.probe.resolve(), args.out.resolve(), args.frames)


if __name__ == '__main__':
    main()

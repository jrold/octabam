#!/usr/bin/env python3
"""Build a diagnostic variant of the frozen cost observer. Not an admission tool.

  build_diagnostic_observer.py count OUT_DIR   # full_map_count_observer.h: function entry counts
  build_diagnostic_observer.py spike OUT_DIR   # full_map_spike_observer.h: ISRs above CF_SPIKE_THRESHOLD only

The variant adds one read-only observer beside the reused cost observer
(out/perky/hybrid/resonant-cf-optimization/profiles/observer) and links the
same objects. A profile made with it is valid only when the profile tool's
own exact-equality checks against the unprofiled control row pass, as they do
for the cost observer. Environment: CF_COUNT_SYMBOLS/CF_COUNT_REPORT or
CF_SPIKE_SYMBOLS/CF_SPIKE_REPORT/CF_SPIKE_THRESHOLD (cycles).
"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
BASE = ROOT / 'out/perky/hybrid/resonant-cf-optimization/profiles/observer'
VARIANTS = {'count': ('full_map_count_observer.h', 'full_map_count'),
            'spike': ('full_map_spike_observer.h', 'full_map_spike')}


def main():
    kind, out = sys.argv[1], Path(sys.argv[2]).resolve()
    header_name, namespace = VARIANTS[kind]
    out.mkdir(parents=True, exist_ok=True)
    header = Path(__file__).resolve().parent / header_name
    text = (BASE / 'machine.cpp').read_text()
    needle = '#include "' + str(ROOT / 'tools/harness/perky_cf/full_map_cost_observer.h') + '"'
    assert text.count(needle) == 1
    text = text.replace(needle, needle + f'\n#include "{header}"')
    for expression in ('pc()', 'pcFast()', 'p'):
        marker = f'full_map_cost::observer.step(*this, {expression});'
        assert text.count(marker) == 1
        text = text.replace(marker, marker + f'\n {namespace}::observer.step(*this, {expression});')
    (out / 'machine.cpp').write_text(text)
    build = json.loads((BASE / 'BUILD.json').read_text())
    compile_command = list(build['commands'][0])
    compile_command[compile_command.index('-c') + 1] = str(out / 'machine.cpp')
    compile_command[compile_command.index('-o') + 1] = str(out / 'machine.o')
    link = list(build['commands'][-1])
    link[link.index(str(BASE / 'machine.o'))] = str(out / 'machine.o')
    link[link.index('-o') + 1] = str(out / 'ot_emu_safety')
    subprocess.run(compile_command, check=True)
    subprocess.run(link, check=True)
    digest = hashlib.sha256((out / 'ot_emu_safety').read_bytes()).hexdigest()
    (out / 'BUILD.json').write_text(json.dumps(dict(binary_sha256=digest, parent_sha256=build['parent_sha256'],
                                                    diagnostic=kind, header=str(header)), indent=2) + '\n')
    print(out / 'ot_emu_safety', digest)


if __name__ == '__main__':
    main()

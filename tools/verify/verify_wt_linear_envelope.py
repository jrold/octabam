#!/usr/bin/env python3
"""Run the PKFM17 native/state/partial-failure gate for linear WT assembly."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'tools/perky')]
import generate_wt_linear_envelope as candidate
import verify_wt_envelope_blocks as envelope


if __name__ == '__main__':
    envelope.candidate = candidate
    envelope.__file__ = __file__
    envelope.main()
    work = Path(sys.argv[sys.argv.index('--work') + 1])
    path = work / 'RESULT.json'
    report = json.loads(path.read_text())
    report['source_sha256'].update({str(p): envelope.sha(p) for p in (
        ROOT / 'tools/verify/verify_wt_envelope_blocks.py',
        ROOT / 'tools/harness/perky_cf/wt_oscillator_block.s')})
    path.write_text(json.dumps(report, indent=2) + '\n')

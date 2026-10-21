#!/usr/bin/env python3
"""Run unchanged original-author renderer and clock oracles at B-tail PCs."""
import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/p) for p in ('tools', 'tools/build', 'tools/perky', 'modules/perky', 'tools/verify')]
os.environ.setdefault('REMIX', 'perky-machine')
import perky_dsp_b_specialization as S
import perky_emit_shards as E
import verify_perky_four_renderer as raw
import verify_perky_four_clock_audio as clock


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--work',type=Path,default=ROOT/'out/perky/hybrid/dsp-b-feasibility')
    work = p.parse_args().work.resolve()
    raw.address.TAG = 'B'
    assert clock.a is raw.address
    os.environ['PERKY_FOUR_RENDERER_WORK'] = str(work/'original-renderer')
    os.environ['PERKY_FOUR_CLOCK_WORK'] = str(work/'original-clock')
    # Scoped to this verifier process. Original oracle/control assertions and
    # sources stay intact; only the code's destination addresses change.
    E.emit = S.emit
    raw.main()
    clock.main()
    print('[PASS] original ARM/native Complex and independent four-engine clock/transition oracles at specialized DSP-B addresses')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Run existing Simple/Noise shipping regression on the Fold composition."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/perky'))
import build_fold_candidate as candidate
import verify_perky_multi_seam_exec as gate

def build(assets,out):
    source,_=candidate.build(out)
    (out/'multi.asm').write_text(source)

if __name__=='__main__':
    gate.payload.build=build
    gate.OUT=ROOT/'out/perky/fold-regression'
    gate.main()
    print('Fold composition Simple Drum/Noise-Tone regression: PASS')

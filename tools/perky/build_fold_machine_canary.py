#!/usr/bin/env python3
"""Local three-engine image; updater emitted only after complete port gates.

Candidate flag is scoped to this build; the two-engine builder keeps its UI.
"""
from pathlib import Path
import os,subprocess,sys
import build_fold_candidate as candidate
import build_multi_machine_canary as multi
ROOT=multi.ROOT

def main():
    if not os.environ.get('OT_PROJECT'):raise SystemExit('OT_PROJECT is required')
    for script in ('verify_perky_fold_drum_exec.py','verify_perky_fold_transport.py','verify_perky_fold_seam_exec.py','verify_perky_fold_regression.py'):
        multi.run(script)
    subprocess.run(['make','check','REMIX=perky-machine','OT_PROJECT='],cwd=ROOT,check=True)
    work=ROOT/'out/perky/fold-multi';source,_=candidate.build(work)
    (work/'multi.asm').write_text(source)
    control_input=work/'control-candidate.c';control_input.write_text('#define PK_FOLD_CANDIDATE 1\n#include "../../../modules/perky/control.c"\n')
    multi.build_image(work,4,'PERKY4',control_input=control_input,engine_ids=(10,2,0),engine_description='001 FOLD DRUM (authentic v1.2.1); 003 SIMPLE DRUM (authentic v1.2.1); 011 NOISE/TONE (preserved PERKY2 synthetic)')
if __name__=='__main__':main()

#!/usr/bin/env python3
"""Build the two-voice light-engine PERKY hardware candidate.

Target architecture
-------------------
  * exactly TWO PERKY synthesis voices: track 1 and track 5, one per DSP core
    (payload B serves tracks 1-4, payload A serves 5-8, so T1 and T5 are on
    different cores by construction);
  * T2/T3/T4 and T6/T7/T8 remain ordinary stock tracks -- the ColdFire
    admission module admits only those two, lowest-selected-wins per core;
  * one algorithm at a time per PERKY voice;
  * SRC page 1 exposes six controls in this exact order, all staged for
    p-lock/LFO by the descriptor's 0x1c6 mask:
        DECAY / TUNE / PARAM1 / PARAM2 / MODE / ALGO
  * ALGO selects the engine, so an ALGO trig p-lock changes the engine for that
    trig alone and the track's base ALGO resumes on the next unlocked trig.

Engine pool (Wavetable deliberately deferred -- it needs a separate
shared-memory project and is NOT part of this milestone):
    0  Fold Drum 1
    3  Fold Drum 2
    2  Simple Drum
   10  Noise/Tone (preserved PERKY2 production path)

Resonant Bass and Resonant Snare are retired: this path is the light
PK_FOLD_CANDIDATE build, which has no resonant renderer, no 108-word
generalized voice slot, no 88/101-word fresh-state transport and no resonant
Y-table banks.

Everything is local: no GitHub Actions, no network.
"""
from pathlib import Path
import os, subprocess, sys

import build_fold_candidate as candidate
import build_multi_machine_canary as multi

ROOT = multi.ROOT

CONTROL_SOURCE = ROOT / 'modules/perky/control_light2_candidate.c'

# The shipping light engines for this first candidate, by their real engine ids.
# Fold Drum 2 (id 3) joins as its own attributable step once the perky4-light
# Fold2 dispatch is brought across and the port gate's engine list admits it.
ENGINE_IDS = (0, 2, 10)
ENGINE_DESCRIPTION = (
    '000 FOLD DRUM 1 (authentic v1.2.1); '
    '002 SIMPLE DRUM (authentic v1.2.1); '
    '010 NOISE/TONE (preserved PERKY2 synthetic)'
)


def main() -> None:
    if not os.environ.get('OT_PROJECT'):
        raise SystemExit('OT_PROJECT is required for the sequencer gate')

    for script in ('verify_perky_fold_drum_exec.py',
                   'verify_perky_fold_transport.py',
                   'verify_perky_fold_seam_exec.py',
                   'verify_perky_fold_regression.py'):
        multi.run(script)

    subprocess.run(['make', 'check', 'REMIX=perky-machine', 'OT_PROJECT='],
                   cwd=ROOT, check=True)

    work = ROOT / 'out/perky/light2'
    source, _ = candidate.build(work)
    (work / 'multi.asm').write_text(source)

    if not CONTROL_SOURCE.exists():
        raise SystemExit(f'missing control source: {CONTROL_SOURCE}')

    multi.build_image(
        work, 5, 'PERKY2V',
        control_input=CONTROL_SOURCE,
        engine_ids=ENGINE_IDS,
        engine_description=ENGINE_DESCRIPTION,
    )


if __name__ == '__main__':
    main()

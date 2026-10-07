#!/usr/bin/env python3
"""Build the first four-voice hardware-style PERKY audition firmware.

Fixed first-audition map:
  T1 -> V1 Fold Drum 1       (authentic v1.2.1 path)
  T2 -> V3 Karplus           (authentic renderer/trigger; fixed ARM control state)
  T5 -> V2 Fold Drum 2       (authentic v1.2.1 path)
  T6 -> V4 Noise/Tone        (preserved physically tested PERKY2 production path)

The audition remix retains stock FILTER and ColdFire DELAY only; other stock DSP
FX are intentionally harvested.  Flashable card/MIDI artifacts are emitted only
after local ARM/DSP qualification, full-image boot checks and the simultaneous
four-track emulator gate pass.  No GitHub Actions/network work is used.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'tools'), str(ROOT / 'tools/perky'), str(ROOT / 'tools/build')]

import build_machine_canary as base
import build_hw4_karplus_candidate as candidate
import perky_machine_module
import repack_hw4_loader
from remix import registry
from remix.schema import DspRange

DEFAULT_FIRMWARE = Path.home() / 'Downloads/perkons_both_v1.2.1-0-gbcccfd0.img'
DEFAULT_SOURCE = Path.home() / 'Downloads/perkybits'
WORK = ROOT / 'out/perky/hw4-machine'
MAINOS = ROOT / 'out/mainos_perky_hw4.bin'


def run(script, *args, env=None):
    cmd = [sys.executable, str(ROOT / script), *map(str, args)]
    print('+ ' + ' '.join(cmd), flush=True)
    subprocess.run(cmd, cwd=ROOT, env=env, check=True)


def require(path: Path, label: str):
    path = path.expanduser().resolve()
    if not path.exists():
        raise SystemExit(f'PERKY HW4: missing {label}: {path}')
    return path


def qualify(firmware: Path, source: Path):
    run('tools/verify/verify_perky_hw4_profile.py')
    run('tools/verify/verify_perky_hw4_harvest.py')

    fold = [
        sys.executable, str(ROOT / 'tools/perky/qualify_fold2_trigger.py'),
        '--firmware', str(firmware), '--source', str(source),
    ]
    if (ROOT / 'out/perky/engine-fixtures/manifest.json').exists():
        fold.append('--reuse-fixtures')
    print('+ ' + ' '.join(fold), flush=True)
    subprocess.run(fold, cwd=ROOT, check=True)

    run('tools/perky/qualify_karplus_trigger.py', '--firmware', firmware, '--source', source)
    run('tools/verify/verify_perky_fold_regression.py')
    run('tools/verify/verify_perky_hw4_candidate_source.py')


def build_module(work: Path, build_number: int):
    source = candidate.build(work)
    dsp_source = work / 'hw4-karplus.asm'
    assert dsp_source.read_text() == source

    control_source = work / 'control.s'
    control_gen = base.load_module('perky_hw4_control_generate', ROOT / 'modules/perky/generate.py')
    control_gen.write(control_source, source=ROOT / 'modules/perky/control_hw4_candidate.c')
    if not control_source.exists() or not control_source.stat().st_size:
        raise SystemExit('PERKY HW4: ColdFire control generator produced no assembly')

    mods = registry.modules()
    original = mods['PERKY PROBE']
    full = perky_machine_module.build(
        original,
        control_source=base.repo_relative(control_source),
        dsp_source=base.repo_relative(dsp_source),
    )
    # Profile-specific physical data claims.  Keep stable PERKY module geometry
    # untouched; only this in-memory audition module owns the extended ranges.
    ranges = (
        DspRange('x', 0x3800, 0x39C4 - 0x3800,
                 'PERKY HW4 two overlays, RNG, 128-word scratch, cache, Fold2 shadow'),
        DspRange('y', 0x07A5, 0x1000 - 0x07A5,
                 'PERKY packed authentic/common tables'),
        DspRange('y', 0x1000, 0x0800,
                 'PERKY HW4 Karplus 2K feedback ring'),
    )
    full = dataclasses.replace(
        full,
        claims=dataclasses.replace(full.claims, dsp_ranges=ranges),
        proof_note='HW4 four-voice audition candidate; physical hardware pending',
        doc='Fixed T1 Fold1 / T2 Karplus / T5 Fold2 / T6 Noise-Tone audition machine.',
    )

    prior = {key: os.environ.get(key) for key in ('REMIX', 'BUILD')}
    try:
        mods['PERKY PROBE'] = full
        os.environ['REMIX'] = 'perky-hw4'
        os.environ['BUILD'] = str(build_number)
        runpy.run_path(str(ROOT / 'tools/build/build_bus.py'), run_name='__main__')
    finally:
        mods['PERKY PROBE'] = original
        for key, value in prior.items():
            if value is None: os.environ.pop(key, None)
            else: os.environ[key] = value
    return control_source, dsp_source


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--firmware', type=Path, default=Path(os.environ.get('PERKONS_FIRMWARE', DEFAULT_FIRMWARE)))
    ap.add_argument('--source', type=Path, default=Path(os.environ.get('PERKYBITS_ROOT', DEFAULT_SOURCE)))
    ap.add_argument('--build', type=int, default=5)
    ap.add_argument('--version', default='PERKYH4')
    ap.add_argument('--skip-qualification', action='store_true',
                    help='reuse already-passing local ARM/DSP evidence; full image/port gates still run')
    a = ap.parse_args()
    if not os.environ.get('OT_PROJECT'):
        raise SystemExit('PERKY HW4: OT_PROJECT=<saved stock project> is required')
    firmware = require(a.firmware, 'PĒRKONS v1.2.1 firmware')
    source = require(a.source, 'PerkyBits checkout')
    if not (source / 'Source/PerkonsVoices.cpp').exists():
        raise SystemExit(f'PERKY HW4: not a PerkyBits checkout: {source}')
    if not 0 <= a.build <= 99:
        raise SystemExit('PERKY HW4: --build must be 0..99')
    if not (1 <= len(a.version) <= 10 and a.version.isascii() and not any(c.isspace() for c in a.version)):
        raise SystemExit('PERKY HW4: --version must be 1..10 ASCII non-whitespace chars')

    if not a.skip_qualification:
        qualify(firmware, source)
    else:
        for needed in (
            ROOT / 'out/perky/fold2-trigger-plan.json',
            ROOT / 'out/perky/karplus-trigger-plan.json',
            ROOT / 'out/perky/engine-fixtures/manifest.json',
        ):
            require(needed, 'reused qualification evidence')
        run('tools/verify/verify_perky_hw4_profile.py')
        run('tools/verify/verify_perky_hw4_harvest.py')
        run('tools/verify/verify_perky_hw4_candidate_source.py')

    WORK.mkdir(parents=True, exist_ok=True)
    control_source, dsp_source = build_module(WORK, a.build)
    normal = ROOT / 'out/mainos_bus.bin'
    require(normal, 'normal HW4 build image')
    require(ROOT / 'out/platform/runtime.raw', 'platform runtime')

    print('=== PERKY HW4: repack platform loader + DSP X/Y uploads ===')
    repack_hw4_loader.build(
        normal, WORK, MAINOS,
        platform_dir=ROOT / 'out/platform',
        work=ROOT / 'out/platform-perky-hw4',
    )
    run('tools/verify/verify_perky_machine_boot.py', '--image', MAINOS, '--packed', WORK)

    env = os.environ.copy()
    env['PERKY_HW4_IMAGE'] = str(MAINOS.resolve())
    run('tools/verify/verify_perky_hw4_port.py', env=env)

    # Only now create flashable containers.
    card, midi, manifest = base.wrap_flashable(MAINOS, a.version)
    candidate_bin = ROOT / 'out/perky/hw4-production-candidate/candidate-full.bin'
    pwords = candidate_bin.stat().st_size // 3 if candidate_bin.exists() else -1
    layout = json.loads((WORK / 'layout.json').read_text())
    manifest.write_text(
        'PERKY HW4 FOUR-VOICE HARDWARE AUDITION\n'
        f'version={a.version}\n'
        f'build={a.build}\n'
        f'git={base.revision()}\n'
        'tracks=T1:V1/Fold1,T2:V3/Karplus,T5:V2/Fold2,T6:V4/NoiseTone\n'
        'voice_limit=two fixed PERKY tracks per DSP core\n'
        'fx=stock FILTER + DELAY retained; other stock DSP FX temporarily harvested\n'
        'karplus=exact renderer/first-trigger/retrigger; fixed authentic v1.2.1 mid-control state\n'
        'noise_tone=preserved physically-tested PERKY2 production path; not yet final original-v1.2.1 replacement\n'
        f'p_words={pwords}\n'
        f'karplus_ring=Y:$1000..$17ff ({layout.get("extra_y_init")})\n'
        f'mainos_sha256={base.sha256(MAINOS)}\n'
        f'card_sha256={base.sha256(card)}\n'
        f'midi_sha256={base.sha256(midi)}\n'
        f'dsp_source_sha256={base.sha256(dsp_source)}\n'
        f'control_assembly_sha256={base.sha256(control_source)}\n'
        'status=local ARM/DSP/full-image/emulator gates passed; PHYSICAL OCTATRACK TEST PENDING\n'
    )
    print('\n=== PERKY HW4 READY FOR PHYSICAL AUDITION ===')
    print('card :', card)
    print('MIDI :', midi)
    print('OS   :', MAINOS)
    print('notes:', manifest)


if __name__ == '__main__':
    main()

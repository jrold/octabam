#!/usr/bin/env python3
"""Build the first static four-voice PĒRKONS hardware-audition firmware.

This is intentionally a conservative audition milestone, not the final PERKY
architecture.  Four physical OT tracks are pinned to one authentic engine from
each PĒRKONS hardware voice family:

  T1 -> Fold Drum 1    (engine 0)
  T2 -> Karplus        (engine 8; fixed authentic control state for audition 1)
  T5 -> Fold Drum 2    (engine 3)
  T6 -> Noise / Tone   (engine 10)

The dedicated ``perky-hw4`` remix temporarily harvests most stock DSP effects
and reserves part of FX1 Y memory for Karplus.  No updater is emitted until the
local ARM/DSP evidence gates, full-source assembler, normal Octabam full-image
placer, boot/readback verifier and four-voice OT emulator port gate all pass.
Nothing in this script flashes hardware and it never uses GitHub Actions/CI.
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

import build_machine_canary as base
import build_hw4_audition_candidate as candidate
import hw4_memory as memory
from remix.schema import DspRange

ROOT = base.ROOT
WORK = ROOT / 'out/perky/hw4-production-candidate'
MAINOS = ROOT / 'out/mainos_perky_hw4.bin'
PLATFORM_WORK = ROOT / 'out/platform-perky-hw4'
DEFAULT_FIRMWARE = Path.home() / 'Downloads/perkons_both_v1.2.1-0-gbcccfd0.img'
DEFAULT_SOURCE = Path.home() / 'Downloads/perkybits'


def run(script: str, *args: object, env: dict[str, str] | None = None) -> None:
    path = ROOT / script
    if not path.exists():
        base.die(f'missing gate/tool {path}')
    command = [sys.executable, str(path), *map(str, args)]
    print('+ ' + ' '.join(command), flush=True)
    subprocess.run(command, cwd=ROOT, env=env, check=True)


def qualify(firmware: Path, source: Path, reuse_fixtures: bool) -> None:
    """Regenerate/verify the evidence needed by the four-engine composition."""
    print('=== PERKY HW4 1/6: original-ARM / DSP evidence ===')
    fold2 = [
        '--firmware', firmware,
        '--source', source,
    ]
    if reuse_fixtures:
        fold2.append('--reuse-fixtures')
    run('tools/perky/qualify_fold2_trigger.py', *fold2)

    # Fold2's driver regenerates the all-engine corpus unless --reuse-fixtures
    # was requested.  Karplus uses that same pinned corpus.
    run('tools/perky/analyze_karplus_trigger.py')
    run('tools/verify/verify_perky_karplus_trigger_contract.py')
    run('tools/verify/verify_perky_karplus_trigger_exec.py')
    reference_env = os.environ.copy()
    reference_env['PERKYBITS_SOURCE'] = str(source / 'Source')
    run('tools/verify/verify_perky_karplus_dsp_exec.py', '--firmware', firmware,
        env=reference_env)
    run('tools/verify/verify_perky_fold_regression.py')

    # Complete four-engine source: exact labels, private X/Y geometry and P size.
    run('tools/verify/verify_perky_hw4_candidate_source.py')


def build_module(work: Path, build_number: int):
    print('=== PERKY HW4 2/6: compose DSP + ColdFire sources ===')
    source, _fold2_words = candidate.build(work)
    control_source = work / 'control.s'
    control_input = ROOT / 'modules/perky/control_hw4_candidate.c'
    control_gen = base.load_module('perky_hw4_control_gen', ROOT / 'modules/perky/generate.py')
    control_gen.write(control_source, source=control_input)
    if not control_source.exists() or not control_source.stat().st_size:
        base.die('HW4 ColdFire generator produced no assembly')

    # The source gate assembled this exact builder output after resolving the
    # stock continuation marker.  Reuse its measured word count in the manifest.
    measured = work / 'candidate-full.bin'
    if not measured.exists() or measured.stat().st_size % 3:
        base.die('HW4 source gate produced no whole-word candidate-full.bin')
    pwords = measured.stat().st_size // 3
    qualified = (work / 'candidate-full.asm').read_text()
    if qualified != source.replace('@CONT@', '$000426'):
        base.die('HW4 packaging source differs from the qualified composition')

    mods = base.registry.modules()
    key = 'PERKY PROBE'
    original = mods[key]
    full = base.perky_machine_module.build(
        original,
        control_source=base.repo_relative(control_source),
        dsp_source=base.repo_relative(work / 'hw4-audition.asm'),
    )

    # Start with the tracked probe claims, then enlarge/append only the ranges
    # the HW4 source actually uses.  The normal build ledger still checks these
    # against the finalized stock uploads and the reduced-FX remix.
    ranges = []
    for r in full.claims.dsp_ranges:
        if r.space == 'x' and r.start == 0x38EC:
            ranges.append(dataclasses.replace(r, length=6))
        elif r.space == 'x' and r.start == memory.SCRATCH_BASE:
            ranges.append(dataclasses.replace(r, length=memory.SCRATCH_WORDS))
        else:
            ranges.append(r)
    ranges.extend((
        DspRange('x', memory.PITCH_CACHE_BASE, memory.PITCH_CACHE_WORDS,
                 'HW4 shared control-rate pitch cache'),
        DspRange('x', memory.FOLD2_SHADOW_BASE, memory.FOLD2_SHADOW_WORDS,
                 'HW4 Fold2 frozen pre-trigger snapshot'),
        DspRange('x', memory.KARPLUS_SHADOW_BASE, memory.KARPLUS_SHADOW_WORDS,
                 'HW4 Karplus frozen pre-trigger snapshot'),
        DspRange('y', memory.HW4_Y_BASE, memory.KARPLUS_RING_END - memory.HW4_Y_BASE,
                 'HW4 audition Karplus envelopes + 2K ring (temporary FX1 arena)'),
    ))
    full = dataclasses.replace(
        full,
        claims=dataclasses.replace(full.claims, dsp_ranges=tuple(ranges)),
    )

    print('=== PERKY HW4 3/6: normal Octabam full-image placer ===')
    prior = {name: os.environ.get(name) for name in ('REMIX', 'BUILD')}
    try:
        mods[key] = full
        os.environ['REMIX'] = 'perky-hw4'
        os.environ['BUILD'] = str(build_number)
        runpy.run_path(str(ROOT / 'tools/build/build_bus.py'), run_name='__main__')
    finally:
        mods[key] = original
        for name, value in prior.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    normal = ROOT / 'out/mainos_bus.bin'
    if not normal.exists():
        base.die('HW4 build_bus returned without out/mainos_bus.bin')

    (work / 'memory.json').write_text(json.dumps({
        'p_words': pwords,
        'gross_reclaimed_p_words': 5431,
        'private_x_end_exclusive': memory.PRIVATE_X_END,
        'karplus_y_base': memory.HW4_Y_BASE,
        'karplus_y_end_exclusive': memory.KARPLUS_RING_END,
        'dsp_ranges': [dataclasses.asdict(r) for r in ranges],
        'note': 'build_bus placer is authoritative after stock pinned-routine subtraction',
    }, indent=2) + '\n')
    return normal, control_source, pwords


def package(work: Path, normal: Path, control_source: Path, pwords: int,
            build_number: int, version: str) -> None:
    print('=== PERKY HW4 4/6: loader + exact DSP boot payload verification ===')
    base.repack_machine_loader.build(
        normal,
        work,
        MAINOS,
        platform_dir=ROOT / 'out/platform',
        work=PLATFORM_WORK,
    )
    run(
        'tools/verify/verify_perky_machine_boot.py',
        '--image', MAINOS,
        '--packed', work,
        '--platform-work', PLATFORM_WORK,
        '--normal-image', normal,
    )

    print('=== PERKY HW4 5/6: four simultaneous voices in OT emulator ===')
    port_env = os.environ.copy()
    port_env['PERKY_HW4_IMAGE'] = str(MAINOS.resolve())
    run('tools/verify/verify_perky_hw4_port.py', env=port_env)

    print('=== PERKY HW4 6/6: card/MIDI firmware wrapper ===')
    card, midi, manifest = base.wrap_flashable(MAINOS, version)
    layout = json.loads((work / 'layout.json').read_text())
    manifest.write_text(
        'PERKY HW4 FOUR-VOICE HARDWARE AUDITION\n'
        f'version={version}\n'
        f'build={build_number}\n'
        f'git={base.revision()}\n'
        'tracks=T1 Fold Drum 1 (engine 0); T2 Karplus (engine 8); '
        'T5 Fold Drum 2 (engine 3); T6 Noise/Tone (engine 10)\n'
        'voice_topology=two PERKY voices per DSP core; T3/T4/T7/T8 ordinary/non-PERKY\n'
        'karplus_controls=fixed authentic v1.2.1 captured middle-corner state for audition 1\n'
        'fx_policy=temporary reduced-FX audition remix; FILTER + DELAY retained; '
        'most stock DSP FX harvested\n'
        f'karplus_y=0x{memory.HW4_Y_BASE:04x}..0x{memory.KARPLUS_RING_END - 1:04x} '
        '(temporary FX1 arena reservation)\n'
        f'p_words={pwords}; gross_reclaimed_p_words=5431; full-image placer passed\n'
        f'dsp_source_sha256={base.sha256(work / "hw4-audition.asm")}\n'
        f'control_assembly_sha256={base.sha256(control_source)}\n'
        f'layout_sha256={base.sha256(work / "layout.json")}\n'
        f'mainos={MAINOS.name} sha256={base.sha256(MAINOS)}\n'
        f'card={card.name} sha256={base.sha256(card)}\n'
        f'midi={midi.name} sha256={base.sha256(midi)}\n'
        'gates=Fold2 ARM trigger/renderer; Karplus ARM trigger/renderer; HW4 full-source '
        'assembler; FX harvest; two-voices/core realtime budget; '
        'stock-aware full-image placer; byte-exact boot uploads; 32000-frame '
        'four-voice dirty-memory OT emulator\n'
        'status=LOCAL GATES PASSED; PHYSICAL OCTATRACK AUDITION PENDING\n'
        f'layout_engines={layout["hw4_audition"]["engines"]}\n'
    )

    print('\nREADY FOR PHYSICAL HW4 AUDITION')
    print(f'  card image : {card}')
    print(f'  MIDI image : {midi}')
    print(f'  patched OS : {MAINOS}')
    print(f'  test record: {manifest}')
    print(f'  DSP source : {pwords} P words')
    print('  map        : T1 Fold1 / T2 Karplus / T5 Fold2 / T6 Noise-Tone')


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--firmware', type=Path,
                    default=Path(os.environ.get('PERKONS_FIRMWARE', DEFAULT_FIRMWARE)))
    ap.add_argument('--source', type=Path,
                    default=Path(os.environ.get('PERKYBITS_ROOT', DEFAULT_SOURCE)))
    ap.add_argument('--reuse-fixtures', action='store_true')
    ap.add_argument('--build', type=int, default=5)
    ap.add_argument('--version', default='PERKYH4')
    args = ap.parse_args()

    firmware = args.firmware.expanduser().resolve()
    source = args.source.expanduser().resolve()
    if not firmware.exists():
        base.die(f'missing PĒRKONS firmware: {firmware}')
    if not (source / 'Source/PerkonsVoices.cpp').exists():
        base.die(f'not a PerkyBits checkout: {source}')
    if not os.environ.get('OT_PROJECT'):
        base.die('OT_PROJECT is required for the final four-voice sequencer/emulator gate')
    if not 0 <= args.build <= 99:
        base.die('--build must be 0..99')

    version = args.version or f'PKHW4{args.build}'
    if not (1 <= len(version) <= 10 and version.isascii()
            and not any(ch.isspace() for ch in version)):
        base.die('--version must be 1..10 ASCII non-whitespace characters')

    WORK.mkdir(parents=True, exist_ok=True)
    qualify(firmware, source, args.reuse_fixtures)
    normal, control_source, pwords = build_module(WORK, args.build)
    package(WORK, normal, control_source, pwords, args.build, version)


if __name__ == '__main__':
    main()

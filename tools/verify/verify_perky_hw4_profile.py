#!/usr/bin/env python3
"""Static invariants for the hardware-style four-voice PERKY audition profile."""
from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[2]
PROFILE = ROOT / 'modules/perky/hw4_profile.py'
CONTROL = ROOT / 'modules/perky/control_hw4_candidate.c'
BUILDER = ROOT / 'tools/perky/build_hw4_candidate.py'


def load(path):
    spec = importlib.util.spec_from_file_location('perky_hw4_profile', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    p = load(PROFILE)
    p.validate()

    assert p.TRACK_VOICE == {0: 1, 1: 3, 4: 2, 5: 4}
    assert p.VOICE_ENGINES == {
        1: (0, 1, 2),
        2: (3, 4, 5),
        3: (6, 7, 8),
        4: (9, 10, 11),
    }
    assert p.DSP_GROUPS == {1: (0, 1), 0: (4, 5)}
    assert len(p.ENGINE_NAMES) == 12

    # Four voices, exactly once, and exactly two admitted tracks on each core.
    assert set(p.TRACK_VOICE.values()) == {1, 2, 3, 4}
    assert all(len(tracks) == 2 for tracks in p.DSP_GROUPS.values())
    assert all(track % 4 in (0, 1) for track in p.TRACK_VOICE)
    assert all(not p.track_allowed(track) for track in (2, 3, 6, 7))

    # Hardware confinement: every engine belongs to one and only one voice.
    memberships = {engine: [] for engine in range(12)}
    for voice, engines in p.VOICE_ENGINES.items():
        for engine in engines:
            memberships[engine].append(voice)
    assert all(len(v) == 1 for v in memberships.values()), memberships

    control = CONTROL.read_text()
    for needle in (
        'track == 0u', 'track == 1u', 'track == 4u', 'track == 5u',
        '#include "control_fold2_candidate.c"',
    ):
        assert needle in control, needle
    assert 'FOLD DRUM 2' not in control, 'HW4 wrapper must not expose an unqualified browser row'

    builder = BUILDER.read_text()
    for needle in (
        'cmp     #>$40,a',
        'HW4 has no per-core first-wins latch',
        "(out / 'hw4.asm').write_text(source)",
    ):
        assert needle in builder, needle
    assert 'move    a1,x:>$38ed' not in builder, 'HW4 builder must not reintroduce first-wins admission'

    print('PERKY HW4 profile: PASS')
    print('  DSP core tracks 1-4: T1=V1, T2=V3')
    print('  DSP core tracks 5-8: T5=V2, T6=V4')
    print('  each voice retains exactly three hardware-family engine ids')


if __name__ == '__main__':
    main()

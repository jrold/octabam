#!/usr/bin/env python3
"""Compose the static two-voices-per-core HW4 audition DSP candidate.

This intentionally does *not* expose new browser engines or emit firmware.
It builds on the hidden Fold2 production composition and changes only realtime
admission: DSP local slots 0 and 1 may render, while slots 2 and 3 are silent.
That corresponds to global T1/T2 and T5/T6, the four tracks pinned by
modules/perky/hw4_profile.py.

Engine-family restrictions remain a ColdFire/browser responsibility.  The DSP
still rejects unsupported engine ids through the existing dispatcher.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'modules/perky'))
sys.path.insert(0, str(ROOT / 'tools/perky'))

import build_fold2_candidate as fold2
import build_noise_tone_synth_source as noise
import hw4_profile as profile

OUT = ROOT / 'out/perky/hw4-candidate'


def once(source: str, old: str, new: str, what: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f'{what}: expected one anchor, found {count}')
    return source.replace(old, new, 1)


def build(out: Path = OUT):
    profile.validate()
    source, fold2_words = fold2.build(out)

    old = '''        ; Additional PERKY tracks on this core produce silence, preserving
        ; transport timing. The first signed track is admitted each frame.
        move    x:>$38ed,a
        tst     a
        bne     pks_silence
        move    #>$1,a
        move    a1,x:>$38ed

        ; Resolve this core's track slot to one 58-word voice base.
'''
    new = '''        ; HW4 audition profile: two voices per core.  Only local stock slots
        ; 0 and 1 may synthesize (global T1/T2 or T5/T6); slots 2/3 are silent.
        ; No first-wins latch is used, so either admitted voice can render on
        ; every block regardless of track order or trigger state.
        move    x:>$418,a
        cmp     #>$40,a
        bge     pks_silence

        ; Resolve this core's track slot to one 58-word voice base.
'''
    source = once(source, old, new, 'HW4 two-slot admission')

    # The old per-frame latch reset is now intentionally dead state.  Remove it
    # rather than leave a misleading write that could be mistaken for admission.
    old_reset = '''        ; One development voice per core. Reset on stock slot0 even when
        ; that track is ordinary FLEX. No uninitialized word controls an address.
        move    x:>$418,b
        tst     b
        bne     pks_frame_ready
        clr     b
        move    b1,x:>$38ed
pks_frame_ready:
        move    x:>$209,r4              ; current track's source record
'''
    new_reset = '''        ; HW4 has no per-core first-wins latch.  The local slot test below
        ; is the entire admission policy.
        move    x:>$209,r4              ; current track's source record
'''
    source = once(source, old_reset, new_reset, 'HW4 latch removal')

    # Slots 2/3 are unreachable after the >= $40 guard.  Keep their state-base
    # labels out of the candidate entirely so later audits cannot mistake four
    # allocated overlays for four admitted voices per core.
    old_slots = '''pks_voice1:
        move    #>$00383a,r6
        bra     pks_voice_ready
pks_voice2:
        move    #>$003874,r6
        bra     pks_voice_ready
pks_voice3:
        move    #>$0038ae,r6
pks_voice_ready:
'''
    new_slots = '''pks_voice1:
        move    #>$00383a,r6
        bra     pks_voice_ready
pks_voice2:
        bra     pks_silence
pks_voice3:
        bra     pks_silence
pks_voice_ready:
'''
    source = once(source, old_slots, new_slots, 'HW4 unreachable overlay slots')

    # Re-run the assembler-specific branch/JSR normalization after editing the
    # composed source.  Import this helper directly rather than relying on the
    # incidental nested import chain of the Fold2 builder.
    source = noise.force_long_local_jsr(noise.relativize_local_conditionals(source))
    out.mkdir(parents=True, exist_ok=True)
    (out / 'hw4.asm').write_text(source)
    print('HW4 DSP candidate: local slots 0+1 admitted on each core; slots 2+3 silent')
    print('HW4 logical tracks: T1=V1, T2=V3, T5=V2, T6=V4')
    print('Browser remains unchanged; this builder emits no updater')
    return source, fold2_words


if __name__ == '__main__':
    build()

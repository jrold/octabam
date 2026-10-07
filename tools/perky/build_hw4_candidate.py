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
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'modules/perky'))
sys.path.insert(0, str(ROOT / 'tools/perky'))

import build_fold2_candidate as fold2
import build_noise_tone_synth_source as noise
import hw4_memory as memory
import hw4_profile as profile

OUT = ROOT / 'out/perky/hw4-candidate'


def once(source: str, old: str, new: str, what: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f'{what}: expected one anchor, found {count}')
    return source.replace(old, new, 1)


def build(out: Path = OUT):
    profile.validate()
    memory.validate()

    # Fold2's reusable hidden builder keeps the earlier PERKY4 shadow address.
    # Override it only while composing HW4 so the older audition paths remain
    # byte-for-byte untouched.
    old_shadow = fold2.SHADOW_X
    try:
        fold2.SHADOW_X = memory.FOLD2_SHADOW_BASE
        source, fold2_words = fold2.build(out)
    finally:
        fold2.SHADOW_X = old_shadow

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

    # Karplus requires 128 words of shared scratch.  Move the Simple/Fold pitch
    # decoder's persistent cache above that scratch; the HW4 image injector uses
    # the same layout metadata when it seeds the cache tag.
    source = once(
        source,
        '        move    #>$003964,r4',
        f'        move    #>${memory.PITCH_CACHE_BASE:06x},r4',
        'HW4 pitch-cache relocation',
    )

    # Keep the generated asset layout synchronized with the source relocation.
    # perky_image.py consumes this metadata when adding the cache initializer to
    # each finalized DSP upload.
    layout_path = out / 'layout.json'
    layout = json.loads(layout_path.read_text())
    cache = dict(layout.get('pitch_cache') or {})
    if int(cache.get('words', memory.PITCH_CACHE_WORDS)) != memory.PITCH_CACHE_WORDS:
        raise RuntimeError('HW4 pitch-cache metadata has unexpected geometry')
    cache.update(
        base_word=memory.PITCH_CACHE_BASE,
        words=memory.PITCH_CACHE_WORDS,
        initial_tag=int(cache.get('initial_tag', 0xffff)),
    )
    layout['pitch_cache'] = cache
    layout['hw4_private_x'] = {
        'scratch_base': memory.SCRATCH_BASE,
        'scratch_words': memory.SCRATCH_WORDS,
        'fold2_shadow_base': memory.FOLD2_SHADOW_BASE,
        'fold2_shadow_words': memory.FOLD2_SHADOW_WORDS,
    }
    layout_path.write_text(json.dumps(layout, indent=2) + '\n')

    # Re-run the assembler-specific branch/JSR normalization after editing the
    # composed source.  Import this helper directly rather than relying on the
    # incidental nested import chain of the Fold2 builder.
    source = noise.force_long_local_jsr(noise.relativize_local_conditionals(source))
    out.mkdir(parents=True, exist_ok=True)
    (out / 'hw4.asm').write_text(source)
    print('HW4 DSP candidate: local slots 0+1 admitted on each core; slots 2+3 silent')
    print('HW4 logical tracks: T1=V1, T2=V4, T5=V2, T6=V3')
    print(f'HW4 X scratch/cache/Fold2 shadow: ${memory.SCRATCH_BASE:04x}..${memory.FOLD2_SHADOW_END-1:04x}')
    print('Browser remains unchanged; this builder emits no updater')
    return source, fold2_words


if __name__ == '__main__':
    build()

#!/usr/bin/env python3
"""Canonical gated builder for the first four-voice PERKY hardware audition.

This wrapper deliberately keeps the development canary builder reusable while
making the two-voices-per-core realtime deadline a mandatory release gate.
No card/MIDI firmware can be emitted through this entry point unless the exact
HW4 Fold1+Karplus and Fold2+Noise/Tone pairings pass the conservative cycle
budget (2x DSP timing-model margin plus measured stock reserve).

It never uses GitHub Actions/CI and does not flash hardware.
"""
from __future__ import annotations

import build_hw4_machine_canary as hw4


_base_qualify = hw4.qualify


def qualify(firmware, source, reuse_fixtures):
    _base_qualify(firmware, source, reuse_fixtures)
    print('=== PERKY HW4 1b/6: two-voices/core realtime deadline ===')
    hw4.run('tools/verify/verify_perky_hw4_realtime_budget.py')


hw4.qualify = qualify


if __name__ == '__main__':
    hw4.main()

#!/usr/bin/env python3
"""Canonical gated builder for the four-voice PERKY hardware audition.

The shared builder's source gate enforces both the FX-harvest audit and the
exact two-voices-per-core realtime budget before any firmware packaging.
"""
from build_hw4_machine_canary import main

if __name__ == '__main__':
    main()

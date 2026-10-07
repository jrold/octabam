#!/usr/bin/env python3
"""Build the qualified four-voice PERKY HW4 hardware audition.

Compatibility entry point for the documented command. Every entry point uses
one composition and the same mandatory source, harvest, timing, boot and port
gates. Use --reuse-fixtures to reuse captures while rerunning qualification.
"""
from build_hw4_machine_canary import main

if __name__ == '__main__':
    main()

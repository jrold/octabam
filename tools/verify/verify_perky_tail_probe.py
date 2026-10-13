#!/usr/bin/env python3
"""Keep the tail-record probe honest.

`tools/perky/probe_tail_record.py` exists to answer step 2's one open question:
does the stock DSP boot routine accept a record at an address no stock record
covers? It produces the image that settles it.

A tool that answers the critical question must not rot. This runs its
`--selftest`, which re-parses an edited payload copy and checks eight
properties of the edit -- the format, the record count, the address, the word
count, the payload length and the build's own mapper.

It writes nothing: the selftest operates on an in-memory copy.
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
PROBE = ROOT / 'tools/perky/probe_tail_record.py'


def main() -> int:
    if not PROBE.is_file():
        raise SystemExit(f'tail-record probe is missing: {PROBE}')
    image = ROOT / 'out/mainos_bus.bin'
    if not image.is_file():
        print(f'  [SKIP] no {image.name} (run `make bus REMIX=perky-machine`); '
              'the probe reads payload A from the built image')
        return 0

    p = subprocess.run([sys.executable, str(PROBE), '--selftest'],
                       cwd=ROOT, capture_output=True, text=True)
    for line in p.stdout.splitlines():
        print(f'  {line}')
    if p.returncode != 0:
        if p.stderr:
            print(f'  {p.stderr.strip()}', file=sys.stderr)
        raise SystemExit('the tail-record probe no longer round-trips its own edit')
    print('  [PASS] the tail-record probe reproduces the re-point edit exactly')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

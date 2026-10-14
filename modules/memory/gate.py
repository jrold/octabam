#!/usr/bin/env python3
"""MEMORY's module gate: verify_reserve_writes on its two fixtures.

    python3 modules/memory/gate.py [carrier remix, ignored]

A once-per-run gate (schema.Gate once=True): the shared half hands it one
carrying remix; it checks octabam-bus (the shipping rig; bottleservice reserved 535 pages) and bus (2 pages, the most given back) whatever that remix is.
"""
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
FIXTURES = ("octabam-bus", "bus")

rc = 0
for remix in FIXTURES:
    r = subprocess.run([sys.executable, str(ROOT / "tools/verify/verify_reserve_writes.py"), remix], cwd=ROOT)
    rc |= r.returncode
sys.exit(rc)

#!/usr/bin/env python3
"""Qualify modules/perky/cf_softfloat.h against the host's own IEEE-754 float.

Acoustic Hats is the only engine whose arithmetic is single-precision, and the
ColdFire build is freestanding -msoft-float: the port has to do the float work
itself.  This gate compiles perky_cf_softfloat_check.c -- which compares every
soft operation's bits against the platform's own float over millions of
operands, the whole int32->float domain and the filter's exact operands -- and
requires zero mismatches.
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]


def main() -> None:
    work = ROOT / "out/perky/cf-softfloat"
    work.mkdir(parents=True, exist_ok=True)
    exe = work / "softfloat_check"
    cmd = ["cc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
           "-I", ROOT / "modules/perky",
           ROOT / "tools/verify/perky_cf_softfloat_check.c", "-o", exe]
    print("+ " + " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], cwd=ROOT, check=True)
    env = dict(os.environ)
    r = subprocess.run([str(exe)], cwd=ROOT, env=env, capture_output=True, text=True)
    print(r.stdout, end="")
    if r.returncode:
        raise SystemExit("PERKY CF soft-float: FAIL (a soft operation differs "
                         "from the platform's own single precision)")
    print("PERKY CF soft-float: PASS (exact binary32 mul/add/i32->f32/f32->i32)")


if __name__ == "__main__":
    main()

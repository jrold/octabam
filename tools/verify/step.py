#!/usr/bin/env python3
"""Run a command and print one stamped line with its wall time.

    python3 tools/verify/step.py <command> [args ...]

    step: 14:03:22 +  7.4 s  rc=0  python3 tools/remix/selftest.py

The line goes to stdout after the command's own output, so a gate's log
keeps a per-step time (`make verify-shared` runs each of its steps through
this). The exit code is the command's.
"""
import subprocess
import sys
import time


def main(argv):
    if not argv:
        sys.exit("usage: step.py <command> [args ...]")
    t0 = time.monotonic()
    rc = subprocess.run(argv).returncode
    print(f"step: {time.strftime('%H:%M:%S')} + {time.monotonic() - t0:5.1f} s  rc={rc}  {' '.join(argv)}", flush=True)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

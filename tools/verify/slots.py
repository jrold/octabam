#!/usr/bin/env python3
"""Gate slots shared by every session on the machine.

    python3 tools/verify/slots.py            # who holds a slot now
    OCTABAM_SLOTS=4 make reach RUN=1         # the slot count (default 3)

Several sessions run gates on one Mac at once; each run sized its shards
for an idle machine, and the same gate's wall time moved up to 11x with
the load (verify_set on bottleservice: 35.7 s to 395 s across reach runs,
5-10 Oct 2026). `check_shards.py` takes a slot for each job and `reach.py`
for each command it runs in its own tree, so at most N heavy jobs run at
once, machine-wide; the rest wait in line and say who they are waiting
for. Default 3: four port boots at once ran slower than three on the four
performance cores (TESTING.md section 7).

A slot is an flock on <git common dir>/octabam-slots/<i>.lock: the kernel
releases it when the holder exits, killed or not. A process that already
holds a slot does not take a second one for a child (OCTABAM_SLOT is set
in the child's environment), so `reach` -> `make check-shared` -> a gate
holds one slot, and `check_shards` under `reach` takes its own per job.
"""
import contextlib
import fcntl
import os
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]


def count():
    try:
        return max(1, int(os.environ.get("OCTABAM_SLOTS", "3")))
    except ValueError:
        return 3


def slot_dir(root=ROOT):
    r = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                       cwd=root, capture_output=True, text=True, check=True)
    d = pathlib.Path(r.stdout.strip()) / "octabam-slots"
    d.mkdir(parents=True, exist_ok=True)
    return d


def holders(root=ROOT):
    """[(slot, holder line)] for the slots held now."""
    out = []
    d = slot_dir(root)
    for i in range(count()):
        p = d / f"{i}.lock"
        if not p.exists():
            continue
        with open(p, "a+") as f:
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(f, fcntl.LOCK_UN)
            except OSError:
                f.seek(0)
                out.append((i, f.read().strip()))
    return out


@contextlib.contextmanager
def slot(label, root=ROOT, poll=2.0, say=print):
    """Hold one of the machine's slots for the block. Yields the
    environment a child should run with (OCTABAM_SLOT set)."""
    env = dict(os.environ)
    if os.environ.get("OCTABAM_SLOT") or os.environ.get("OCTABAM_SLOTS") == "off":
        yield env
        return
    d = slot_dir(root)
    n = count()
    t0 = time.monotonic()
    told = False
    while True:
        for i in range(n):
            f = open(d / f"{i}.lock", "a+")
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                f.close()
                continue
            f.seek(0); f.truncate()
            f.write(f"pid {os.getpid()} {pathlib.Path.cwd()} {label}\n"); f.flush()
            waited = time.monotonic() - t0
            if told:
                say(f"slots: {label}: slot {i} after {waited:.0f} s", flush=True)
            env["OCTABAM_SLOT"] = str(i)
            try:
                yield env
            finally:
                f.seek(0); f.truncate()
                fcntl.flock(f, fcntl.LOCK_UN)
                f.close()
            return
        if not told:
            who = "; ".join(f"{i}: {h}" for i, h in holders(root)) or "?"
            say(f"slots: {label}: all {n} slots busy, waiting ({who})", flush=True)
            told = True
        time.sleep(poll)


def main():
    held = holders()
    print(f"slots: {len(held)} of {count()} held ({slot_dir()})")
    for i, h in held:
        print(f"  {i}: {h}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

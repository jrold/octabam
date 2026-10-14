#!/usr/bin/env python3
"""Every gate failure, kept for every worktree of the repository.

    python3 tools/verify/gate_ledger.py            # failures per gate, most first
    python3 tools/verify/gate_ledger.py --all      # every record, newest last

module_gates.py, check_shards.py and reach.py append one JSON line per
failure to <git common dir>/octabam-gate-failures.jsonl: when, the commit
(and whether the tree had uncommitted changes), the worktree, the gate,
the remix and the failure's first [FAIL] line. The gate cache keeps only
passes, so until 11 Oct 2026 nothing said which gates ever caught
anything; this is the record that will.
"""
import argparse
import collections
import fcntl
import json
import os
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]


def path(root=ROOT):
    r = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                       cwd=root, capture_output=True, text=True, check=True)
    return pathlib.Path(r.stdout.strip()) / "octabam-gate-failures.jsonl"


def first_fail(text):
    """The first [FAIL] line of a gate's output, else its last non-empty line."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    return next((l for l in lines if "[FAIL]" in l or "FAILED" in l), lines[-1] if lines else "")


def record(gate, remix, line, root=ROOT):
    """Append one failure; never fails the caller."""
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=root,
                                    capture_output=True, text=True).stdout.strip())
        rec = dict(when=time.strftime("%Y-%m-%dT%H:%M:%S"), head=head, dirty=dirty, tree=str(root),
                   gate=gate, remix=remix or "", line=line[:300])
        with open(path(root), "a") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            f.write(json.dumps(rec) + "\n")
    except (OSError, subprocess.SubprocessError):
        pass


def read(root=ROOT):
    try:
        return [json.loads(l) for l in path(root).read_text().splitlines() if l.strip()]
    except OSError:
        return []


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()
    recs = read()
    if a.all:
        for r in recs:
            print(f"{r['when']}  {r['head'][:10]}{'+' if r['dirty'] else ' '}  {r['gate']:40s} {r['remix']:16s} {r['line']}")
        return 0
    by = collections.Counter(r["gate"] for r in recs)
    commits = collections.defaultdict(set)
    for r in recs:
        commits[r["gate"]].add(r["head"])
    print(f"{len(recs)} failure(s) recorded at {path()}")
    for gate, n in by.most_common():
        print(f"  {n:5d}  {len(commits[gate]):4d} commit(s)  {gate}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

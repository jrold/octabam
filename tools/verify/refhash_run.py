#!/usr/bin/env python3
"""scripts/refhash.sh's build matrix, across scratch trees.

    printf '%s\n' 'name|ENV=1 ...' ... | python3 tools/verify/refhash_run.py OUTDIR [--jobs N]

Each line is a case (a name, then the environment its build gets after
REMIX=bus). The builds are single-threaded python that write fixed names
under out/, so they cannot share a tree; the 24 of them ran one after
another in one (70 s). This runs them over N trees, the current one and N-1
scratch worktrees of it (check_shards.make_shard, kept in out/refhash-trees/
between runs), each worker taking the next case when it is free, and writes
what refhash.sh wrote: OUTDIR/<name>.log (normalised) and OUTDIR/manifest.txt
in case order -- `case NAME rc=N`, the sha256 of each artifact the build
left, the sha256 of the log.
"""
import argparse
import concurrent.futures as cf
import glob
import hashlib
import os
import pathlib
import queue
import re
import subprocess
import sys
import threading

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/verify"))
ARTIFACTS = ("out/mainos_bus.bin", "out/mainos_bus_dev.bin", "out/mainos_bus_mode*.bin",
             "out/mainos_bus_delayprobe_*.bin", "out/dsp/mem_dev_A.mem")
# a traceback carries source line numbers, which every refactor moves
TRACE = re.compile(r'File "[^"]*", line [0-9]+')


def artifacts(tree):
    found = [p for pat in ARTIFACTS for p in glob.glob(str(tree / pat))]
    rel = [os.path.relpath(p, tree) for p in found]
    # byte order, whatever the machine's locale: `ls | sort` ordered by the
    # locale, and no case writes two names the two orders put differently
    return sorted(rel)


def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def run_case(tree, name, envs, outdir):
    for p in artifacts(tree):
        os.unlink(tree / p)
    env = dict(os.environ)
    env["REMIX"] = "bus"
    for tok in envs.split():
        k, _, v = tok.partition("=")
        env[k] = v
    log = outdir / f"{name}.log"
    with log.open("wb") as f:
        rc = subprocess.run(["python3", "tools/build/build_bus.py"], cwd=tree, env=env,
                            stdout=f, stderr=subprocess.STDOUT).returncode
    log.write_text(TRACE.sub('File "<src>", line <n>', log.read_text(errors="surrogateescape")),
                   errors="surrogateescape")
    lines = [f"case {name} rc={rc}"]
    lines += [f"  {sha(tree / p)}  {p}" for p in artifacts(tree)]
    lines.append(f"  {sha(log)}  <report>")
    return rc, lines


def trees(jobs, say):
    """The current tree, then scratch worktrees of it, each set up when its
    worker asks (a kept one is refreshed in a few seconds)."""
    import check_shards
    out = [ROOT]
    for i in range(1, jobs):
        path = ROOT / "out/refhash-trees" / str(i)
        out.append(path)
    return out, check_shards


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("outdir", type=pathlib.Path)
    ap.add_argument("--jobs", type=int, default=1)
    a = ap.parse_args(argv)
    cases = [l.rstrip("\n").split("|", 1) for l in sys.stdin if l.strip()]
    a.outdir.mkdir(parents=True, exist_ok=True)
    jobs = max(1, min(a.jobs, len(cases)))
    todo = queue.Queue()
    for i, c in enumerate(cases):
        todo.put((i, c[0], c[1] if len(c) > 1 else ""))
    results = {}
    lock = threading.Lock()
    paths, check_shards = trees(jobs, print)

    def worker(n):
        tree = paths[n]
        if n:
            (ROOT / "out/refhash-trees").mkdir(parents=True, exist_ok=True)
            check_shards.make_shard(tree, ROOT / f"out/refhash-trees/{n}.setup.log", port=False)
        while True:
            try:
                i, name, envs = todo.get_nowait()
            except queue.Empty:
                return
            res = run_case(tree, name, envs, a.outdir)
            with lock:
                results[i] = (name, *res)

    with cf.ThreadPoolExecutor(max_workers=jobs) as ex:
        for f in [ex.submit(worker, n) for n in range(jobs)]:
            f.result()
    with (a.outdir / "manifest.txt").open("w") as m:
        for i in range(len(cases)):
            name, rc, lines = results[i]
            m.write("\n".join(lines) + "\n")
            print(f"  {name:<16} rc={rc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

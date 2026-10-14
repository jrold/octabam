#!/usr/bin/env python3
"""The refhash baseline, saved once per merge-base for every worktree.

    python3 tools/verify/refhash_store.py fetch [--base origin/main]   # out/refhash/baseline for this tree
    python3 tools/verify/refhash_store.py key   [--base origin/main]
    python3 tools/verify/refhash_store.py list

`scripts/refhash.sh check` compared a branch's 24 builds against whatever
baseline the last `scripts/refhash.sh save` left in the tree: a baseline
from some other commit passed or failed it for no reason, and every session
saved its own (55 s) before the 65 s check. The baseline is now the 24
builds of the branch's merge-base with BASE (origin/main), saved once into
<git common dir>/octabam-refhash/<key>/ and copied into out/refhash/baseline
by `check`. The first run after a main merge saves it, in a temporary
detached worktree at the merge-base (under an flock, so concurrent runs
wait for one save); every later run on that merge-base copies it.

The key is a sha256 over the merge-base commit, the stock OS slice, dsp_asm
and dsp_host (by content), the m68k assembler's version and the python
major.minor: the inputs a build reads that git does not hold. The newest
KEEP baselines are kept.
"""
import argparse
import fcntl
import hashlib
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
KEEP = 8
TOOLCHAIN = ("vendor/dsp56300/build/source/dsp_host/dsp_asm", "vendor/dsp56300/build/source/dsp_host/dsp_host")


def run(*args, cwd=ROOT, check=True):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=check)


def store_dir(root=ROOT):
    common = run("git", "rev-parse", "--path-format=absolute", "--git-common-dir", cwd=root).stdout.strip()
    return pathlib.Path(common) / "octabam-refhash"


def merge_base(base, root=ROOT):
    return run("git", "merge-base", "HEAD", base, cwd=root).stdout.strip()


def sha_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "none"


def tool_version(tool):
    """First line of `tool --version`; "none" when the tool is not installed."""
    try:
        out = run(tool, "--version", check=False).stdout.splitlines()
    except FileNotFoundError:
        return "none"
    return out[0] if out else "none"


def key(base, root=ROOT):
    h = hashlib.sha256()
    h.update(merge_base(base, root).encode())
    h.update(sha_file(root / "out/raw/section_3_MAIN_OS.bin").encode())
    for rel in TOOLCHAIN:
        h.update(sha_file(root / rel).encode())
    h.update(tool_version("m68k-elf-as").encode())
    h.update(f"{sys.version_info.major}.{sys.version_info.minor}".encode())
    return h.hexdigest()


def save_baseline(k, mb, root=ROOT):
    """Save the 24 builds of commit `mb` into the store as key `k`."""
    sd = store_dir(root)
    sd.mkdir(parents=True, exist_ok=True)
    work = sd / f"work-{k[:12]}"
    if work.exists():
        run("git", "worktree", "remove", "--force", str(work), cwd=root, check=False)
        shutil.rmtree(work, ignore_errors=True)
    run("git", "worktree", "add", "--detach", str(work), mb, cwd=root)
    try:
        for name in ("vendor", ".venv"):
            if (root / name).exists():
                os.symlink(os.path.realpath(root / name), work / name)
        (work / "out/raw").mkdir(parents=True)
        shutil.copy2(root / "out/raw/section_3_MAIN_OS.bin", work / "out/raw/section_3_MAIN_OS.bin")
        run("git", "submodule", "update", "--init", "--recursive", "-q", cwd=work)
        env = dict(os.environ)
        env["PATH"] = f"{work / '.venv/bin'}{os.pathsep}{env['PATH']}"
        r = subprocess.run(["scripts/refhash.sh", "save"], cwd=work, env=env, capture_output=True, text=True)
        if r.returncode or not (work / "out/refhash/baseline/manifest.txt").is_file():
            raise SystemExit(f"refhash_store: saving the baseline at {mb[:10]} failed ({r.returncode})\n"
                             f"{r.stdout[-1500:]}{r.stderr[-1500:]}")
        tmp = pathlib.Path(tempfile.mkdtemp(prefix=f"{k[:12]}.", dir=sd))
        shutil.copytree(work / "out/refhash/baseline", tmp / "baseline")
        (tmp / "baseline/KEY").write_text(k + "\n")
        (tmp / "baseline/COMMIT").write_text(mb + "\n")
        os.replace(tmp / "baseline", sd / k)
        shutil.rmtree(tmp, ignore_errors=True)
    finally:
        run("git", "worktree", "remove", "--force", str(work), cwd=root, check=False)
        shutil.rmtree(work, ignore_errors=True)
        run("git", "worktree", "prune", cwd=root, check=False)


def prune(root=ROOT):
    sd = store_dir(root)
    done = sorted((p for p in sd.iterdir() if p.is_dir() and (p / "manifest.txt").is_file()),
                  key=lambda p: p.stat().st_mtime, reverse=True)
    for p in done[KEEP:]:
        shutil.rmtree(p, ignore_errors=True)


def fetch(base, root=ROOT, say=print):
    """out/refhash/baseline for this tree's merge-base with `base`, from the
    store, saved first if it is not there. Returns the store directory."""
    k = key(base, root)
    dest = root / "out/refhash/baseline"
    sd = store_dir(root)
    src = sd / k
    if (dest / "KEY").is_file() and (dest / "KEY").read_text().strip() == k and (dest / "manifest.txt").is_file():
        say(f"refhash: baseline for merge-base {merge_base(base, root)[:10]} already in place")
        return src
    if not (src / "manifest.txt").is_file():
        sd.mkdir(parents=True, exist_ok=True)
        with open(sd / f"{k}.lock", "a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if not (src / "manifest.txt").is_file():
                mb = merge_base(base, root)
                say(f"refhash: no baseline for merge-base {mb[:10]}: saving it (24 builds, in a temporary worktree)")
                save_baseline(k, mb, root)
        prune(root)
    else:
        say(f"refhash: baseline for merge-base {merge_base(base, root)[:10]} from the store")
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dest)
    os.utime(src)
    return src


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("fetch", "key", "list"))
    ap.add_argument("--base", default=os.environ.get("REFHASH_BASE", "origin/main"))
    a = ap.parse_args(argv)
    if a.cmd == "key":
        print(key(a.base))
    elif a.cmd == "list":
        sd = store_dir()
        for p in sorted(sd.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True) if sd.is_dir() else ():
            if (p / "manifest.txt").is_file():
                print(f"{p.name[:12]}  {(p / 'COMMIT').read_text().strip()[:10] if (p / 'COMMIT').is_file() else '?'}")
    else:
        fetch(a.base)
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""The ColdFire port built once per source state, shared by every worktree.

    python3 tools/emu/port_store.py install [DEST]     # out/emu by default
    python3 tools/emu/port_store.py key                # the key, in this tree
    python3 tools/emu/port_store.py tree               # out/emu's CMake tree, built in place if absent
    python3 tools/emu/port_store.py pgo                # the PGO + LTO build, kept beside the plain one (minutes)

A fresh worktree's first `make reach RUN=1` built the port in the
worktree (69 s) and again in each new shard (125 s for three, 11 Oct
2026). The store is <git common dir>/octabam-port/<key>/: the executables
one `cmake --build` of tools/emu/ot_emu produces, built once under an
flock into a private tree and moved into place, then copied (never
linked: AGENTS.md, out/emu's CMake cache names its own tree) into DEST
with the source stamp reach.port_is_stale reads.

The key is a sha256 over the port's sources (reach.port_digest), every
file tools/emu/ot_emu/CMakeLists.txt names outside its own directory, each
vendored core's commit and working-tree diff (dsp56300 carries
tools/patches/dsp56300.patch as uncommitted changes), the host
architecture and the compiler's version. `make emu-cf` still builds in the
tree, incrementally, for work on the port itself.

The PGO + LTO build (`pgo`, `make emu-pgo`) is kept beside the plain one and
`install` prefers it. When the store has none for a source state, `install`
copies the plain build at once and starts the PGO build detached (`pgo-bg`,
nice 10, one at a time on the machine, nothing waits for it; a failure holds
off retries for 30 minutes). `OCTABAM_PGO=0` keeps the plain build and starts
nothing; there is also nothing to train on without a project (OT_PROJECT or
~/.octabam_project). Measure timings with `OCTABAM_PGO=0`, or the training run
shares the machine for its 5 minutes.
"""
import fcntl
import hashlib
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/verify"))
SRC = ROOT / "tools/emu/ot_emu"
VENDORED = ("vendor/mc68k", "vendor/dsp56300")


def _run(*args, cwd=ROOT):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True).stdout


def outside_sources(src=SRC):
    """The files CMakeLists.txt names by a path leaving its directory."""
    text = (src / "CMakeLists.txt").read_text()
    out = set()
    for rel in re.findall(r"(\.\./[\w./-]+\.(?:cpp|cc|c|hpp|h))\b", text):
        p = (src / rel).resolve()
        if p.is_file():
            out.add(p)
    return sorted(out)


def host_arch():
    import check_shards
    return check_shards.host_arch()


def key(root=ROOT):
    import reach
    h = hashlib.sha256()
    h.update(reach.port_digest(root / "tools/emu/ot_emu").encode())
    for p in outside_sources(root / "tools/emu/ot_emu"):
        h.update(str(p.relative_to(root.resolve())).encode()); h.update(b"\0"); h.update(p.read_bytes())
    for d in VENDORED:
        h.update(d.encode())
        h.update(_run("git", "rev-parse", "HEAD", cwd=root / d).encode())
        h.update(_run("git", "diff", "--binary", cwd=root / d).encode())
    h.update(host_arch().encode())
    h.update(_run("c++", "--version").splitlines()[0].encode() if _run("c++", "--version") else b"")
    return h.hexdigest()


def store_dir(root=ROOT):
    common = _run("git", "rev-parse", "--path-format=absolute", "--git-common-dir", cwd=root).strip()
    return pathlib.Path(common) / "octabam-port"


def built(k, root=ROOT):
    """The store's directory for key `k`, building it first if absent."""
    d = store_dir(root) / k
    if (d / "ot_emu").is_file():
        return d
    d.parent.mkdir(parents=True, exist_ok=True)
    with open(d.parent / f"{k}.lock", "a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if (d / "ot_emu").is_file():
            return d             # another process built it while this one waited
        work = pathlib.Path(tempfile.mkdtemp(prefix=f"{k[:12]}.", dir=d.parent))
        build = work / "build"
        arch = host_arch()
        for cmd in (["cmake", "--fresh", "-B", str(build), "-S", str(root / "tools/emu/ot_emu"),
                     f"-DCMAKE_OSX_ARCHITECTURES={arch}"],
                    ["cmake", "--build", str(build), "-j8"]):
            r = subprocess.run(cmd, cwd=root, capture_output=True, text=True)
            if r.returncode:
                shutil.rmtree(work, ignore_errors=True)
                raise SystemExit(f"port_store: {' '.join(cmd)} failed ({r.returncode})\n{r.stdout[-1500:]}{r.stderr[-1500:]}")
        staged = work / "bin"
        staged.mkdir()
        for f in build.iterdir():
            if f.is_file() and os.access(f, os.X_OK) and (f.name == "ot_emu" or f.name.startswith("ot_")):
                shutil.copy2(f, staged / f.name)
        os.replace(staged, d)
        shutil.rmtree(work, ignore_errors=True)
    return d


PGO_SCRIPT = "tools/emu/ot_emu/pgo.sh"


def pgo_dir(k, root=ROOT):
    """Where the PGO build of key `k` lives: the key and the ritual's own
    bytes, so a change to pgo.sh builds it again."""
    sh = hashlib.sha256((root / PGO_SCRIPT).read_bytes()).hexdigest()[:10]
    return store_dir(root) / f"{k}-pgo-{sh}"


def training_card(work, root=ROOT):
    """A card for the PGO training run, staged from the local project (the
    tone project of usb_sig_project: eight tracks playing, so the cores and
    the audio path run). Returns (card, set, project)."""
    sys.path[:0] = [str(root / "tools/verify"), str(root / "tools/harness"), str(root / "tools")]
    import gate_cache
    import verify_usb_post
    project = gate_cache.project_dir()
    if project is None or not project.is_dir():
        raise SystemExit("port_store: the PGO training needs a project (OT_PROJECT or ~/.octabam_project)")
    args = verify_usb_post.stage(project, work)
    return pathlib.Path(args[args.index("--card") + 1]), args[args.index("--set") + 1], args[args.index("--project") + 1]


def pgo(root=ROOT, say=print):
    """The PGO + LTO build of this tree's sources (tools/emu/ot_emu/pgo.sh:
    an instrumented build, three training runs, the optimised build), kept in
    the store beside the plain one. Bit-exact to the plain build by
    construction and by the oracle; 13% faster with the DSP cores, 28%
    without (Tim Hastie, M5, 12 Sep). Minutes; run once per source state."""
    k = key(root)
    d = pgo_dir(k, root)
    if (d / "ot_emu").is_file():
        return d
    d.parent.mkdir(parents=True, exist_ok=True)
    with open(d.parent / f"{d.name}.lock", "a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if (d / "ot_emu").is_file():
            return d
        work = pathlib.Path(tempfile.mkdtemp(prefix=f"{k[:12]}-pgo.", dir=d.parent))
        card, setname, projname = training_card(work / "card", root)
        say(f"port_store: PGO build of {k[:12]} (an instrumented build, three training runs, the optimised build)")
        r = subprocess.run(["bash", str(root / PGO_SCRIPT), "--dest", str(work / "build"), "--gen", str(work / "gen"),
                            "--prof", str(work / "prof"), "--card", str(card), "--set", setname,
                            "--project", projname, "--image", str(root / "out/raw/section_3_MAIN_OS.bin")],
                           cwd=root, capture_output=True, text=True)
        (work / "pgo.log").write_text(r.stdout + r.stderr)
        if r.returncode:
            raise SystemExit(f"port_store: pgo.sh failed ({r.returncode}), log {work / 'pgo.log'}\n{r.stdout[-1200:]}{r.stderr[-1200:]}")
        staged = work / "bin"
        staged.mkdir()
        for f in (work / "build").iterdir():
            if f.is_file() and os.access(f, os.X_OK) and (f.name == "ot_emu" or f.name.startswith("ot_")):
                shutil.copy2(f, staged / f.name)
        shutil.copy2(work / "prof/ot_emu.profdata", staged / "ot_emu.profdata")
        shutil.copy2(work / "pgo.log", staged / "pgo.log")
        os.replace(staged, d)
        shutil.rmtree(work, ignore_errors=True)
    return d


PGO_RETRY_S = 1800        # after a failed PGO build, the next attempt for that source state


def spawn(argv, **kw):
    """Start a detached child (a function so a test can replace it)."""
    return subprocess.Popen(argv, **kw)


def pgo_background(root=ROOT, say=print):
    """Start the PGO build for this tree's sources detached, unless the store
    has it, a build failed within PGO_RETRY_S, OCTABAM_PGO=0, or there is no
    project to train on. Never waits: the child (`pgo-bg`) takes the
    machine-wide lock without blocking, so only one runs on the machine and a
    second `install` just returns. Returns True when a child was started."""
    if os.environ.get("OCTABAM_PGO") == "0":
        return False
    k = key(root)
    d = pgo_dir(k, root)
    if (d / "ot_emu").is_file():
        return False
    sd = store_dir(root)
    failed = sd / f"{d.name}.failed"
    if failed.is_file() and time.time() - failed.stat().st_mtime < PGO_RETRY_S:
        return False
    sys.path[:0] = [str(root / "tools/verify")]
    import gate_cache
    project = gate_cache.project_dir()
    if project is None or not project.is_dir():
        return False
    sd.mkdir(parents=True, exist_ok=True)
    log = open(sd / f"pgo-{k[:12]}.log", "a")
    spawn(["nice", "-n", "10", sys.executable, str(root / "tools/emu/port_store.py"), "pgo-bg"],
          cwd=root, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    say(f"port_store: starting the PGO build for {k[:12]} in the background (about 5 min at nice 10; later installs take it)")
    return True


def pgo_bg(root=ROOT):
    """The detached child: one PGO build at a time on the machine. A failure
    leaves a marker that holds off retries for PGO_RETRY_S."""
    sd = store_dir(root)
    sd.mkdir(parents=True, exist_ok=True)
    with open(sd / "pgo-running.lock", "a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            print("port_store: another PGO build is running; not starting this one")
            return 0
        k = key(root)
        d = pgo_dir(k, root)
        try:
            pgo(root)
            print(f"port_store: PGO build for {k[:12]} done: {d}")
            return 0
        except BaseException as e:           # SystemExit from pgo(), a vanished worktree, ...
            (sd / f"{d.name}.failed").write_text(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {e}\n")
            print(f"port_store: PGO build for {k[:12]} failed: {e}")
            return 1


def install(dest=None, root=ROOT, say=print):
    """The port for this tree's sources into `dest` (out/emu), from the store:
    the PGO build when the store has one (OCTABAM_PGO=0 asks for the plain
    one), else the plain build."""
    import reach
    dest = pathlib.Path(dest or root / "out/emu")
    k = key(root)
    d = pgo_dir(k, root)
    if os.environ.get("OCTABAM_PGO") == "0" or not (d / "ot_emu").is_file():
        d = built(k, root)
    dest.mkdir(parents=True, exist_ok=True)
    for f in d.iterdir():
        if not (f.name == "ot_emu" or f.name.startswith("ot_")) or f.suffix == ".profdata":
            continue
        tmp = dest / f".{f.name}.tmp"
        shutil.copy2(f, tmp)
        os.replace(tmp, dest / f.name)
    reach.stamp_port(root / "tools/emu/ot_emu", dest / pathlib.Path(reach.PORT_STAMP).name)
    return dest, d


TREE_FILES = ("CMakeFiles/ot_emu.dir/flags.make", "CMakeFiles/ot_emu.dir/link.txt")


def ensure_tree(root=ROOT):
    """out/emu's CMake build tree, built in place when absent. The store
    copies executables only, so a tree that came from `install` (every shard
    and every fresh worktree since #671) has no CMakeFiles, and a harness
    that recompiles ot_emu with an injected probe (ab_source_probe,
    benchmark_analog_bd) reads flags.make and link.txt and the libraries the
    link line names. Such a harness calls this first. Returns the build dir."""
    build = root / "out/emu"
    if all((build / f).is_file() for f in TREE_FILES):
        return build
    cache = build / "CMakeCache.txt"
    own = cache.is_file() and f"CMAKE_HOME_DIRECTORY:INTERNAL={(root / 'tools/emu/ot_emu').resolve()}" in cache.read_text()
    for cmd in (["cmake"] + ([] if own else ["--fresh"]) + ["-B", str(build), "-S", str(root / "tools/emu/ot_emu"),
                                                             f"-DCMAKE_OSX_ARCHITECTURES={host_arch()}"],
                ["cmake", "--build", str(build), "-j8"]):
        r = subprocess.run(cmd, cwd=root, capture_output=True, text=True)
        if r.returncode:
            raise SystemExit(f"port_store: {' '.join(cmd)} failed ({r.returncode})\n{r.stdout[-1500:]}{r.stderr[-1500:]}")
    return build


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv.pop(0) if argv else "install"
    if cmd == "key":
        print(key())
        return 0
    if cmd == "tree":
        print(ensure_tree())
        return 0
    if cmd == "pgo":
        print(f"port_store: {pgo()}")
        return 0
    if cmd == "pgo-bg":
        return pgo_bg()
    if cmd == "install":
        dest, d = install(argv[0] if argv else None)
        pgo_build = "-pgo-" in d.name
        print(f"port_store: {dest}/ot_emu from {d}" + ("" if pgo_build else "  (the plain build)"))
        if not pgo_build:
            pgo_background()
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())

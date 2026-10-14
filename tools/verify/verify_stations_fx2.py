#!/usr/bin/env python3
"""The stations with SLOTS = FX1+FX2: an FX2 instance renders exactly what an FX1 instance does.

    python3 tools/verify/verify_stations_fx2.py

Builds remix `stations-fx2` (each station's SLOTS pinned to FX1+FX2), dumps
payload A, and renders each station through dsp_host at the FX1 position
(`-r7 1 -alloc 0`) and the FX2 position (`-r7 2 -alloc 1`) with the same
input and the same knobs: defaults, the module's `dear` extremes, and every
value of its MODE slot. The two renders must be bit-identical, and the FX2
render must differ from the dry input (the station is live, not the dry
pass the default build gives). With the default SLOTS the old gates
(`verify_spectrum`, `verify_character`, `verify_modulation`) prove the dry
pass.

What it cannot see: dsp_host places the FX2 slot by its own model of the
dispatcher (AGENTS.md); the real allocator's bases are measured under the
port.
"""
import os, pathlib, struct, subprocess, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1])); import toolpath  # noqa: E402,F401
from remix import registry  # noqa: E402
import send_probe  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
os.chdir(ROOT)
HOST = "vendor/dsp56300/build/source/dsp_host/dsp_host"
REMIX = sys.argv[1] if len(sys.argv) > 1 else "stations-fx2"
IMAGE, MEM = "out/mainos_bus.bin", "out/dsp/_stations_fx2_A.mem"
TMP = pathlib.Path("out/_stfx2"); TMP.mkdir(parents=True, exist_ok=True)
FRAMES, N = 15, 6000
fails = 0


def check(label, ok, detail=""):
    global fails
    fails += 0 if ok else 1
    print(f"  [{'ok' if ok else 'FAIL'}] {label}{'  ' + detail if detail else ''}")


if not pathlib.Path(HOST).exists():
    print("  [SKIP] verify_stations_fx2: no dsp_host (scripts/setup.sh)"); sys.exit(0)
env = dict(os.environ, REMIX=REMIX, XBUS="1", SPEC="1"); env.setdefault("BUILD", "0")
r = subprocess.run([sys.executable, "tools/build/build_bus.py"], env=env, capture_output=True, text=True)
if r.returncode:
    sys.exit(f"verify_stations_fx2: building {REMIX} failed:\n{(r.stdout + r.stderr)[-1500:]}")
send_probe.dump_mem(IMAGE, MEM, "A")
mods = {m.key: m for m in registry.selected(registry.remix(REMIX))}
send_id = registry.by_key("SEND").menu.fx2_id

# a tone plus a little noise, mono Q23 (dsp_host feeds one stream to both channels)
import math, random
random.seed(7)
src = [int(0.35 * 8388607 * math.sin(2 * math.pi * 440 * i / 44100) * (0.5 + 0.5 * math.sin(2 * math.pi * 3 * i / 44100))
           + 0.05 * 8388607 * (random.random() - 0.5)) for i in range(N)]
(TMP / "in.raw").write_bytes(b"".join(struct.pack("<i", s) for s in src))


def render(init, proc, params, slot):
    r7, alloc = {"fx1": ("1", "0"), "fx2": ("2", "1")}[slot]
    cmd = [HOST, "-mem", MEM, "-init", f"{init:x}", "-proc", f"{proc:x}", "-inst", "1", "-r7", r7, "-alloc", alloc,
           "-inmask", "1", "-frames", str(FRAMES), "-blocks", str(N // FRAMES), "-in", str(TMP / "in.raw"),
           "-out", str(TMP / "out.raw"), "-params", ",".join(str(x) for x in params)]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode:
        sys.exit(f"dsp_host failed ({slot}, {params}):\n{p.stdout}\n{p.stderr}")
    d = (TMP / "out.raw").read_bytes()
    return struct.unpack(f"<{len(d) // 4}i", d)


for key in ("SPECTRUM", "CHARACTER", "MODULATION"):
    m = mods[key]
    init, proc = send_probe.entry_points(MEM, m.menu.fx2_id)
    if (init, proc) == send_probe.entry_points(MEM, send_id):
        sys.exit(f"{key} (id 0x{m.menu.fx2_id:02x}) resolves to SEND's entry points: not in the dump")
    names = {p.name.decode().strip("\0"): i for i, p in enumerate(m.params) if p.name}
    base = [(p.default or 0) for p in m.params]
    sets = {"defaults": list(base)}
    ext = list(base)
    for k, v in (m.dear or {}).items():
        ext[names[k]] = v
    sets["dear"] = ext
    if m.mode_slot is not None:
        n = m.params[m.mode_slot].count or 1
        for mode in range(n):
            s = list(ext); s[m.mode_slot] = mode
            sets[f"mode {mode}"] = s
    for label, pv in sets.items():
        a, b = render(init, proc, pv, "fx1"), render(init, proc, pv, "fx2")
        check(f"{key} {label}: FX2 instance == FX1 instance, bit for bit", a == b,
              "" if a == b else f"{sum(x != y for x, y in zip(a, b))} of {len(a)} words differ")
    dry = list(src) * 1
    out = render(init, proc, sets["dear"], "fx2")
    live = any(out[2 * i] != src[i] for i in range(N))
    check(f"{key}: the FX2 render at the extremes is not the dry input", live)

print(f"verify_stations_fx2: {'PASS' if not fails else f'FAIL ({fails})'}")
sys.exit(1 if fails else 0)

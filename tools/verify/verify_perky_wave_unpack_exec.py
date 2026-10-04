#!/usr/bin/env python3
"""Execute PERKY's packed-wave DSP decoder over all 1024 synthetic samples."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import re
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
PERKY = ROOT / "modules/perky"
V = ROOT / "vendor/dsp56300"
OUT = ROOT / "out/perky/wave-unpack"
sys.path.insert(0, str(PERKY))
import noise_tone_tables as packed  # noqa:E402


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

fab = load_module("perky_wave_unpack_fab", ROOT / "tools/perky/fabricate_noise_tone_fixtures.py")
ASM = V / "build/source/dsp_host/dsp_asm"
DIS = V / "build/source/disassemble/dsp56kDisassemble"
HOST = OUT / "bd909_host"
HOST_SRC = ROOT / "tools/harness/bd909_host/bd909_host.cpp"
ORG = 0x3000
TABLE_BASE = 0x0795
LINE = re.compile(r"^([0-9a-f]{6}): (\S+)(?:\s+(.*?))?\s*; [0-9a-f]{6}(?: [0-9a-f]{6})?$")


def fail(msg: str):
    raise SystemExit("verify-perky-wave-unpack-exec: " + msg)


def build_host():
    libs = [V/"build/source/dsp56kEmu/libdsp56kEmu.a", V/"build/source/dsp56kBase/libdsp56kBase.a", V/"build/source/asmjit/libasmjit.a"]
    missing = [p for p in [ASM, DIS, *libs] if not p.exists()]
    if missing: fail("run `make setup` first; missing " + ", ".join(map(str, missing)))
    OUT.mkdir(parents=True, exist_ok=True)
    if HOST.exists() and HOST.stat().st_mtime > HOST_SRC.stat().st_mtime: return
    subprocess.run(["c++","-O3","-DNDEBUG","-std=gnu++17","-DASMJIT_STATIC","-DDSP56300_DEBUGGER=0",f"-I{V}/source",f"-I{V}/source/asmjit/src",str(HOST_SRC),str(libs[0]),str(libs[1]),str(libs[2]),"-lpthread","-o",str(HOST)],check=True,capture_output=True)


def assemble():
    OUT.mkdir(parents=True, exist_ok=True)
    binary, symbols = OUT/"wave.bin", OUT/"wave.sym"
    r = subprocess.run([str(ASM),"-in",str(PERKY/"noise_tone_wave_unpack.asm"),"-org",f"{ORG:x}","-out",str(binary),"-list","-sym",str(symbols)],capture_output=True,text=True)
    if r.returncode: fail("assembler failed:\n" + r.stdout[-4000:] + r.stderr[-2000:])
    labels = {q[0]:int(q[1],16) for q in (line.split() for line in symbols.read_text().splitlines()) if len(q)==2}
    entry = labels.get("pk_wave_unpack_probe")
    if entry is None: fail("missing pk_wave_unpack_probe")
    d = subprocess.run([str(DIS),"-in",str(binary),"-pc",f"{ORG:x}","-le"],capture_output=True,text=True,check=True)
    typed = {int(m.group(1),16):m.group(2) for m in map(LINE.match,r.stdout.splitlines()) if m}
    actual = {int(m.group(1),16):m.group(2) for m in map(LINE.match,d.stdout.splitlines()) if m}
    for a,mn in typed.items():
        if actual.get(a) != mn: fail(f"P:{a:06x} typed {mn}, decoded {actual.get(a)}")
    return binary, entry


def main():
    build_host(); binary, entry = assemble()
    wave_values = [[x & 0xFFFF for x in w] for w in fab.waves()]
    table = packed.pack_waves(zip(fab.WAVE_ADDRESSES, wave_values))
    if TABLE_BASE + len(table.words) != 0x0A40:
        fail("synthetic wave payload no longer ends exactly at Y:0x0a40")
    data = OUT/"wave.data"; script = OUT/"wave.script"; raw = OUT/"wave.raw"; meter = OUT/"wave.meter"
    state = [0]*64; state[40] = 0
    data.write_text("X 200 " + " ".join(f"{x:06x}" for x in state) + f"\nY {TABLE_BASE:x} " + " ".join(f"{x:06x}" for x in table.words) + "\n")
    script.write_text((" ".join(["0"]*12+["-1"]) + "\n") * 64)
    subprocess.run([str(HOST),"-code",str(binary),"-org",f"{ORG:x}","-entry",f"{entry:x}","-data",str(data),"-script",str(script),"-out",str(raw),"-meter",str(meter),"-frames","16"],check=True,capture_output=True,text=True)
    got = list(struct.unpack(f"<{raw.stat().st_size//4}i",raw.read_bytes()))
    expected_samples = [((v - 0x10000) if v & 0x8000 else v) for wave in wave_values for v in wave]
    expected = [s for s in expected_samples for _ in (0,1)]
    if got != expected:
        at = next(i for i,(a,b) in enumerate(zip(got,expected)) if a!=b)
        fail(f"audio word {at}: {got[at]} != {expected[at]}")
    counts = [int(x) for x in meter.read_text().split()]
    print(f"PERKY packed wave decoder executable gate: OK (1024 samples; Y:{TABLE_BASE:04x}..0a3f; {len(table.words)} words; max {max(counts)} instr/16 samples)")

if __name__ == "__main__": main()

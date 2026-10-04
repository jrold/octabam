#!/usr/bin/env python3
"""Execute one persistent PERKY packed-envelope cache across curve switches."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
PERKY = ROOT / "modules/perky"
V = ROOT / "vendor/dsp56300"
OUT = ROOT / "out/perky/envelope-cache-exec"
sys.path.insert(0, str(PERKY))

import noise_tone_envelope_cache as cachemod  # noqa:E402
from noise_tone_tables import pack_envelope  # noqa:E402

ASM = V / "build/source/dsp_host/dsp_asm"
DIS = V / "build/source/disassemble/dsp56kDisassemble"
HOST = OUT / "bd909_host"
HOST_SRC = ROOT / "tools/harness/bd909_host/bd909_host.cpp"
ORG = 0x2C00
ENV1_Y = 0x0A40
ENV2_Y = 0x0CC6
LINE = re.compile(
    r"^([0-9a-f]{6}): (\S+)(?:\s+(.*?))?\s*; [0-9a-f]{6}(?: [0-9a-f]{6})?$"
)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


fab = load_module(
    "perky_env_cache_exec_fab",
    ROOT / "tools/perky/fabricate_noise_tone_fixtures.py",
)


def fail(msg: str) -> None:
    raise SystemExit("verify-perky-envelope-cache-exec: " + msg)


def decoded(text: str):
    return {
        int(m.group(1), 16): (m.group(2), (m.group(3) or "").strip())
        for m in map(LINE.match, text.splitlines())
        if m
    }


def build_host() -> None:
    libs = [
        V / "build/source/dsp56kEmu/libdsp56kEmu.a",
        V / "build/source/dsp56kBase/libdsp56kBase.a",
        V / "build/source/asmjit/libasmjit.a",
    ]
    missing = [p for p in [ASM, DIS, *libs] if not p.exists()]
    if missing:
        fail("run `make setup` first; missing " + ", ".join(map(str, missing)))
    OUT.mkdir(parents=True, exist_ok=True)
    if HOST.exists() and HOST.stat().st_mtime > HOST_SRC.stat().st_mtime:
        return
    subprocess.run(
        [
            "c++", "-O3", "-DNDEBUG", "-std=gnu++17", "-DASMJIT_STATIC",
            "-DDSP56300_DEBUGGER=0", f"-I{V}/source", f"-I{V}/source/asmjit/src",
            str(HOST_SRC), str(libs[0]), str(libs[1]), str(libs[2]), "-lpthread",
            "-o", str(HOST),
        ],
        check=True,
        capture_output=True,
    )


WRAPPER = r"""
pk_env_cache_sequence:
        lua     (r5+$40),r4
        move    #>$1,a
        move    a1,x:(r5+$41)
        jsr     pk_envelope_packed7_cached
        move    x:(r5+$51),a
        move    a1,y:(r5+$50)
        move    x:(r4),a
        move    a1,y:(r5+$51)

        move    #>$2,a
        move    a1,x:(r5+$41)
        jsr     pk_envelope_packed7_cached
        move    x:(r5+$51),a
        move    a1,y:(r5+$52)
        move    x:(r4),a
        move    a1,y:(r5+$53)

        move    #>$1,a
        move    a1,x:(r5+$41)
        jsr     pk_envelope_packed7_cached
        move    x:(r5+$51),a
        move    a1,y:(r5+$54)
        move    x:(r4),a
        move    a1,y:(r5+$55)
        rts
"""


def combined_source() -> str:
    return (
        WRAPPER
        + "\n"
        + (PERKY / "noise_tone_envelope_packed7.asm").read_text()
        + "\n\n"
        + (PERKY / "noise_tone_envelope.asm").read_text()
        + "\n"
    )


def assemble():
    OUT.mkdir(parents=True, exist_ok=True)
    src = OUT / "envelope_cache_exec.asm"
    binary = OUT / "envelope_cache_exec.bin"
    symbols = OUT / "envelope_cache_exec.sym"
    src.write_text(combined_source())
    r = subprocess.run(
        [
            str(ASM), "-in", str(src), "-org", f"{ORG:x}",
            "-out", str(binary), "-list", "-sym", str(symbols),
        ],
        capture_output=True,
        text=True,
    )
    if r.returncode:
        fail("assembler failed:\n" + r.stdout[-5000:] + r.stderr[-3000:])
    labels = {
        q[0]: int(q[1], 16)
        for q in (line.split() for line in symbols.read_text().splitlines())
        if len(q) == 2
    }
    entry = labels.get("pk_env_cache_sequence")
    if entry is None:
        fail("assembler emitted no pk_env_cache_sequence symbol")

    d = subprocess.run(
        [str(DIS), "-in", str(binary), "-pc", f"{ORG:x}", "-le"],
        capture_output=True,
        text=True,
        check=True,
    )
    typed, actual = decoded(r.stdout), decoded(d.stdout)
    if not typed or len(actual) < len(typed) * 0.9:
        fail("no usable disassembly to compare")
    for addr, (mnemonic, operands) in typed.items():
        dm, dops = actual.get(addr, ("?", ""))
        if dm != mnemonic:
            fail(f"P:{addr:06x} typed {mnemonic} {operands} but decodes {dm} {dops}")
    return binary, entry


def main() -> None:
    env1 = fab.envelope_linear()
    env2 = fab.envelope_ease()
    p1 = pack_envelope(env1)
    p2 = pack_envelope(env2)
    if p1.delta_bits != 7 or p2.delta_bits != 7:
        fail("synthetic packed envelope widths drifted from 7/7")

    # Fixed state 2 means the raw envelope state machine does not mutate the
    # envelope value; the three calls differ only in the shaped-table read.
    index = 5 * 16 + 7
    fraction = 0x155
    raw_value = (index << 10) | fraction
    low = raw_value & 0xFFFF
    high = (raw_value >> 16) & 0xFFFF

    xwords = [0] * 81
    xwords[40] = 2            # envelope state
    xwords[41] = 1            # wrapper overwrites 1 -> 2 -> 1
    xwords[45] = low
    xwords[46] = high
    xwords[64] = 0xFFFF       # one persistent cache begins invalid

    OUT.mkdir(parents=True, exist_ok=True)
    data = OUT / "cache.data"
    script = OUT / "cache.script"
    raw = OUT / "cache.raw"
    state_path = OUT / "cache.state"
    data.write_text(
        "X 200 " + " ".join(f"{x:06x}" for x in xwords) + "\n"
        + "Y 200 " + " ".join("000000" for _ in range(64)) + "\n"
        + f"Y {ENV1_Y:x} " + " ".join(f"{x:06x}" for x in p1.words) + "\n"
        + f"Y {ENV2_Y:x} " + " ".join(f"{x:06x}" for x in p2.words) + "\n"
    )
    script.write_text(" ".join(["0"] * 12 + ["-1"]) + "\n")

    build_host()
    binary, entry = assemble()
    subprocess.run(
        [
            str(HOST), "-code", str(binary), "-org", f"{ORG:x}",
            "-entry", f"{entry:x}", "-data", str(data), "-script", str(script),
            "-out", str(raw), "-state", str(state_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    dumped = [int(x, 16) for x in state_path.read_text().split()]
    if len(dumped) != 128:
        fail(f"state dump has {len(dumped)} words, expected 128")
    y = dumped[64:128]

    c = cachemod.EnvelopeCache()
    want1 = cachemod.envelope_at_cached(p1, index, c, curve_id=0)
    key1 = c.key
    want2 = cachemod.envelope_at_cached(p2, index, c, curve_id=1)
    key2 = c.key
    want3 = cachemod.envelope_at_cached(p1, index, c, curve_id=0)
    key3 = c.key

    # DSP kernel interpolates between index and index+1, so compute the exact
    # expected shaped outputs with the same u16 linear interpolation law.
    def interp(table, curve_id):
        cc = cachemod.EnvelopeCache()
        first = cachemod.envelope_at_cached(table, index, cc, curve_id=curve_id)
        second = cachemod.envelope_at_cached(table, (index + 1) & 0x7FF, cc, curve_id=curve_id)
        return (first + (((second - first) * fraction) >> 10)) & 0xFFFF

    expected = [interp(p1, 0), key1, interp(p2, 1), key2, interp(p1, 0), key3]
    got = [y[i] & 0xFFFF for i in range(50, 56)]
    if got != expected:
        fail(f"curve-switch sequence got {got}, expected {expected}")
    if expected[1:] == [expected[1]] * 5:
        fail("test fixture failed to distinguish cache-key transitions")

    print(
        "PERKY packed-envelope cache executable gate: OK "
        f"(index {index}; curve0 key {key1:04x} -> curve1 {key2:04x} -> curve0 {key3:04x}; "
        "one persistent 17-word cache)"
    )


if __name__ == "__main__":
    main()

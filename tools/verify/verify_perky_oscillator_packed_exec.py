#!/usr/bin/env python3
"""Execute PERKY's packed-Y oscillator against the exact word-model oracle.

This is the shipping-accessor version of verify_perky_oscillator_exec.py.  The
DSP code reads all four synthetic 256-sample waves from the 683-word packed
stream at Y:$07a5, while the oracle reads the same values from ordinary byte
arrays.  Phase mutation, strict wrap semantics, deferred table switching and
the returned signed-16 sample must remain identical.
"""
from __future__ import annotations

import importlib.util
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
PERKY = ROOT / "modules/perky"
V = ROOT / "vendor/dsp56300"
OUT = ROOT / "out/perky/oscillator-packed"
sys.path.insert(0, str(PERKY))

from noise_tone_tables import pack_waves  # noqa:E402
from noise_tone_word_model import U32, WordState, render_oscillator  # noqa:E402

ASM = V / "build/source/dsp_host/dsp_asm"
DIS = V / "build/source/disassemble/dsp56kDisassemble"
HOST = OUT / "bd909_host"
HOST_SRC = ROOT / "tools/harness/bd909_host/bd909_host.cpp"
ORG = 0x0100  # isolated kernels fit the short-call region; shipping gate tests high P
YBASE = 0x07a5
BASE = 0x2C
LINE = re.compile(
    r"^([0-9a-f]{6}): (\S+)(?:\s+(.*?))?\s*; [0-9a-f]{6}(?: [0-9a-f]{6})?$"
)


def fail(msg: str) -> None:
    raise SystemExit("verify-perky-oscillator-packed-exec: " + msg)


def load_module(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        fail(f"cannot import {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


fab = load_module(
    "perky_oscillator_packed_fab",
    ROOT / "tools/perky/fabricate_noise_tone_fixtures.py",
)
IDS = tuple(fab.WAVE_ADDRESSES)
VALUES = tuple(tuple(v & 0xFFFF for v in wave) for wave in fab.waves())
PACKED = pack_waves(zip(IDS, VALUES))


def wave_bytes(values) -> bytes:
    out = bytearray()
    for value in values:
        out += bytes((value & 0xFF, (value >> 8) & 0xFF))
    return bytes(out)


WAVES = {address: wave_bytes(values) for address, values in zip(IDS, VALUES)}


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


def substituted_source() -> str:
    src = (PERKY / "noise_tone_oscillator_packed.asm").read_text()
    for i, address in enumerate(IDS):
        src = src.replace(f"@W{i}L@", f"${address & 0xFFFF:04x}")
        src = src.replace(f"@W{i}H@", f"${(address >> 16) & 0xFFFF:04x}")
    if "@W" in src:
        fail("wave identity substitution left an unresolved token")
    return src


def assemble():
    OUT.mkdir(parents=True, exist_ok=True)
    source = OUT / "oscillator_packed.asm"
    binary = OUT / "oscillator_packed.bin"
    symbols = OUT / "oscillator_packed.sym"
    source.write_text(substituted_source())
    r = subprocess.run(
        [
            str(ASM), "-in", str(source), "-org", f"{ORG:x}",
            "-out", str(binary), "-list", "-sym", str(symbols),
        ],
        capture_output=True,
        text=True,
    )
    if r.returncode:
        fail("assembler failed:\n" + r.stdout[-4000:] + r.stderr[-2000:])
    labels = {
        q[0]: int(q[1], 16)
        for q in (line.split() for line in symbols.read_text().splitlines())
        if len(q) == 2
    }
    entry = labels.get("pk_osc_packed_probe")
    if entry is None:
        fail("assembler emitted no pk_osc_packed_probe symbol")

    d = subprocess.run(
        [str(DIS), "-in", str(binary), "-pc", f"{ORG:x}", "-le"],
        capture_output=True,
        text=True,
        check=True,
    )
    typed, actual = decoded(r.stdout), decoded(d.stdout)
    if not typed or len(actual) < len(typed) * .9:
        fail("no usable disassembly to compare")
    for addr, (mnemonic, operands) in typed.items():
        dm, dops = actual.get(addr, ("?", ""))
        if dm != mnemonic:
            fail(
                f"P:{addr:06x} typed {mnemonic} {operands} "
                f"but decodes {dm} {dops}"
            )
    return binary, entry


def limbs(value: int) -> tuple[int, int]:
    u = U32.from_int(value)
    return u.lo, u.hi


def oracle(phase: int, inc: int, current: int, nxt: int):
    state = WordState(bytearray(0x120))
    state.set_u32(BASE + 4, U32.from_int(phase))
    state.set_u32(BASE + 8, U32.from_int(inc))
    state.set_u32(BASE + 0x0C, U32.from_int(current))
    state.set_u32(BASE + 0x10, U32.from_int(nxt))
    sample = render_oscillator(state, BASE, WAVES)
    return (
        state.u32(BASE + 4),
        state.u32(BASE + 0x0C),
        sample & 0xFFFF,
    )


def run(binary, entry, tag, phase, inc, current, nxt):
    words = [0] * 100
    words[0x40], words[0x41] = limbs(phase)
    words[0x42], words[0x43] = limbs(inc)
    words[0x44], words[0x45] = limbs(current)
    words[0x46], words[0x47] = limbs(nxt)

    data = OUT / f"{tag}.data"
    script = OUT / f"{tag}.script"
    raw = OUT / f"{tag}.raw"
    state_path = OUT / f"{tag}.state"
    data.write_text(
        "X 200 " + " ".join(f"{x:06x}" for x in words) + "\n"
        + f"Y {YBASE:x} " + " ".join(f"{x:06x}" for x in PACKED.words) + "\n"
    )
    script.write_text(" ".join(["0"] * 12 + ["-1"]) + "\n")

    subprocess.run(
        [
            str(HOST), "-code", str(binary), "-org", f"{ORG:x}",
            "-entry", f"{entry:x}", "-data", str(data), "-script", str(script),
            "-out", str(raw), "-state", str(state_path), "-state-words", "100",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    dumped = [int(x, 16) for x in state_path.read_text().split()]
    if len(dumped) < 64:
        fail(f"{tag}: truncated state dump")
    return (
        U32(dumped[0x40] & 0xFFFF, dumped[0x41] & 0xFFFF),
        U32(dumped[0x44] & 0xFFFF, dumped[0x45] & 0xFFFF),
        dumped[0x48] & 0xFFFF,
    )


def check_u32(tag: str, got: U32, want: U32) -> None:
    if got != want:
        fail(f"{tag}: got {got.unsigned():08x}, want {want.unsigned():08x}")


def main() -> None:
    if len(PACKED.words) != 683:
        fail(f"synthetic four-wave payload is {len(PACKED.words)} words, expected 683")
    build_host()
    binary, entry = assemble()

    # These hit the exact-threshold/no-wrap edge, threshold+1 wrap, local
    # index 255 -> 0 interpolation, modulo-u32 addition, negative phases, and
    # deferred switches among every one of the four packed wave identities.
    cases = [
        (0x00000000, 0x00000000, IDS[0], IDS[0]),
        (0x00000000, 0x00000FFF, IDS[1], IDS[1]),
        (0x000FE000, 0x00000ABC, IDS[2], IDS[2]),
        (0x000FF000, 0x00001000, IDS[0], IDS[1]),
        (0x000FF001, 0x00001000, IDS[0], IDS[1]),
        (0x000FFFFF, 0x00000002, IDS[1], IDS[2]),
        (0x000FEABC, 0x00000000, IDS[2], IDS[2]),
        (0x000FFABC, 0x00000000, IDS[3], IDS[3]),
        (0x00100000, 0x00000001, IDS[3], IDS[0]),
        (0x7FFFFFFF, 0x00000001, IDS[0], IDS[3]),
        (0xFFFFFFFF, 0x00000000, IDS[1], IDS[2]),
        (0xFFFFFFFE, 0x00000003, IDS[2], IDS[2]),
        (0x000FFFF0, 0x00000020, IDS[3], IDS[3]),
        (0x000FFFF0, 0x00000020, IDS[0], IDS[2]),
        (0x000FFFF0, 0x00000020, IDS[2], IDS[1]),
        (0x000FFFF0, 0x00000020, IDS[1], IDS[3]),
    ]

    checked = 0
    for i, case in enumerate(cases):
        want_phase, want_current, want_sample = oracle(*case)
        got_phase, got_current, got_sample = run(binary, entry, f"osc-packed-{i}", *case)
        check_u32(f"case {i} phase", got_phase, want_phase)
        check_u32(f"case {i} current", got_current, want_current)
        if got_sample != want_sample:
            fail(
                f"case {i} sample: got {got_sample:04x}, "
                f"want {want_sample:04x}"
            )
        checked += 3

    print(
        "PERKY packed-Y oscillator executable gate: OK "
        f"({len(cases)} states, {checked} exact outputs, {len(PACKED.words)} Y words)"
    )


if __name__ == "__main__":
    main()

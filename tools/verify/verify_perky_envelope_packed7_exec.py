#!/usr/bin/env python3
"""Execute the one-cache packed-Y PERKY envelope wrapper against the oracle."""
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
OUT = ROOT / "out/perky/envelope-packed7"
sys.path.insert(0, str(PERKY))

from noise_tone_tables import pack_envelope  # noqa:E402
from noise_tone_word_model import U32, WordState, render_envelope  # noqa:E402

ASM = V / "build/source/dsp_host/dsp_asm"
DIS = V / "build/source/disassemble/dsp56kDisassemble"
HOST = OUT / "bd909_host"
HOST_SRC = ROOT / "tools/harness/bd909_host/bd909_host.cpp"
ORG = 0x2C00
BASE = 0x74
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
    "perky_envelope_packed7_fab",
    ROOT / "tools/perky/fabricate_noise_tone_fixtures.py",
)


def fail(msg: str) -> None:
    raise SystemExit("verify-perky-envelope-packed7-exec: " + msg)


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


def combined_source() -> str:
    return (
        (PERKY / "noise_tone_envelope_packed7.asm").read_text()
        + "\n\n"
        + (PERKY / "noise_tone_envelope.asm").read_text()
        + "\n"
    )


def assemble():
    OUT.mkdir(parents=True, exist_ok=True)
    src = OUT / "envelope_packed7.asm"
    binary = OUT / "envelope_packed7.bin"
    symbols = OUT / "envelope_packed7.sym"
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
    entry = labels.get("pk_envelope_packed7_probe")
    if entry is None:
        fail("assembler emitted no pk_envelope_packed7_probe symbol")

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


def u16_blob(values) -> bytes:
    return struct.pack(f"<{len(values)}H", *(int(v) & 0xFFFF for v in values))


ENV1_VALUES = fab.envelope_linear()
ENV2_VALUES = fab.envelope_ease()
ENV1 = u16_blob(ENV1_VALUES)
ENV2 = u16_blob(ENV2_VALUES)
PACK1 = pack_envelope(ENV1_VALUES)
PACK2 = pack_envelope(ENV2_VALUES)


def limbs(value: int) -> tuple[int, int]:
    u = U32.from_int(value)
    return u.lo, u.hi


def oracle(case):
    env_state, shape, flag4, flag6, flag7, value, hold, attack, decay = case
    state = WordState(bytearray(0x120))
    state.set_byte(BASE, env_state)
    state.set_byte(BASE + 1, shape)
    state.set_byte(BASE + 4, flag4)
    state.set_byte(BASE + 6, flag6)
    state.set_byte(BASE + 7, flag7)
    state.set_u32(BASE + 0x0C, U32.from_int(value))
    state.set_u32(BASE + 0x10, U32.from_int(hold))
    state.set_u16(BASE + 0x20, attack)
    state.set_u16(BASE + 0x22, decay)
    output = render_envelope(state, BASE, ENV1, ENV2)
    return state.byte(BASE), state.u32(BASE + 0x0C), output


def run(binary: Path, entry: int, tag: str, case):
    env_state, shape, flag4, flag6, flag7, value, hold, attack, decay = case
    words = [0] * 81
    words[40] = env_state & 0xFF
    words[41] = shape & 0xFF
    words[42] = flag4 & 0xFF
    words[43] = flag6 & 0xFF
    words[44] = flag7 & 0xFF
    words[45], words[46] = limbs(value)
    words[47], words[48] = limbs(hold)
    words[49] = attack & 0xFFFF
    words[50] = decay & 0xFFFF
    words[64] = 0xFFFF              # one curve-aware cache starts invalid

    data = OUT / f"{tag}.data"
    script = OUT / f"{tag}.script"
    raw = OUT / f"{tag}.raw"
    state_path = OUT / f"{tag}.state"
    data.write_text(
        "X 200 " + " ".join(f"{x:06x}" for x in words) + "\n"
        + f"Y {ENV1_Y:x} " + " ".join(f"{x:06x}" for x in PACK1.words) + "\n"
        + f"Y {ENV2_Y:x} " + " ".join(f"{x:06x}" for x in PACK2.words) + "\n"
    )
    script.write_text(" ".join(["0"] * 12 + ["-1"]) + "\n")
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
    if len(dumped) < 64:
        fail(f"{tag}: truncated state dump")
    return (
        dumped[40] & 0xFF,
        U32(dumped[45] & 0xFFFF, dumped[46] & 0xFFFF),
        dumped[51] & 0xFFFF,
    )


def check_u32(tag: str, got: U32, want: U32) -> None:
    if got != want:
        fail(
            f"{tag}: got {got.unsigned():08x} ({got.signed()}), "
            f"want {want.unsigned():08x} ({want.signed()})"
        )


def main() -> None:
    if PACK1.delta_bits != 7 or PACK2.delta_bits != 7:
        fail(f"synthetic curves are {PACK1.delta_bits}/{PACK2.delta_bits} bits, expected 7/7")
    if len(PACK1.words) != 646 or len(PACK2.words) != 646:
        fail("synthetic packed curve footprint drifted")

    build_host()
    binary, entry = assemble()

    # env, shape, flag4, flag6, flag7, value, hold, attack, decay
    # Includes state transitions plus index/cache/block boundaries and 2047->0.
    cases = [
        (0, 0, 0, 0, 0, 0x00012345, 0, 0, 0),
        (0, 0, 1, 0, 0, 0x00012345, 0, 0, 0),
        (1, 0, 0, 0, 0, 0x000FF000, 0, 0x0FFF, 0),
        (1, 0, 0, 1, 0, 0x000FF000, 0, 0x1000, 0),
        (1, 1, 0, 0, 0, 0x000FFFFE, 0, 1, 0),
        (1, 2, 1, 0, 0, 0x000FF000, 0, 0x1000, 0),
        (3, 1, 0, 0, 0, 0x000F0000, 0, 0, 0),
        (4, 2, 0, 0, 0, 0x00010000, 0, 0, 0x0100),
        (4, 1, 0, 0, 0, 0x00000010, 0, 0, 0x0020),
        (2, 1, 0, 0, 0, 0x00000000, 0, 0, 0),
        (2, 1, 0, 0, 0, (15 << 10) | 0x3FF, 0, 0, 0),
        (2, 1, 0, 0, 0, (16 << 10) | 0x001, 0, 0, 0),
        (2, 1, 0, 0, 0, (31 << 10) | 0x200, 0, 0, 0),
        (2, 1, 0, 0, 0, (32 << 10) | 0x200, 0, 0, 0),
        (2, 1, 0, 0, 0, 0x001FFFFF, 0, 0, 0),
        (2, 2, 0, 0, 0, 0x000ABCDE, 0, 0, 0),
        (2, 2, 0, 0, 0, (15 << 10) | 0x155, 0, 0, 0),
        (2, 2, 0, 0, 0, (16 << 10) | 0x155, 0, 0, 0),
        (2, 2, 0, 0, 0, 0x001FFFFF, 0, 0, 0),
        (2, 7, 0, 0, 0, 0x000ABCDE, 0, 0, 0),
    ]

    for i, case in enumerate(cases):
        want_state, want_value, want_output = oracle(case)
        got_state, got_value, got_output = run(binary, entry, f"envp-{i}", case)
        if got_state != want_state:
            fail(f"case {i} state: got {got_state}, want {want_state}")
        check_u32(f"case {i} value", got_value, want_value)
        if got_output != want_output:
            fail(f"case {i} output: got {got_output:04x}, want {want_output:04x}")

    print(
        "PERKY packed-Y envelope executable gate: OK "
        f"({len(cases)} transition/interpolation cases; one 17-word cache; "
        "646+646 Y words; state/value/output exact)"
    )


if __name__ == "__main__":
    main()

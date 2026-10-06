#!/usr/bin/env python3
"""Assemble and exhaustively execute the Simple Drum frequency converter."""
from __future__ import annotations

from pathlib import Path
import re
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[2]
PERKY = ROOT / "modules/perky"
V = ROOT / "vendor/dsp56300"
OUT = ROOT / "out/perky/simple-drum-frequency"
ASM = V / "build/source/dsp_host/dsp_asm"
DIS = V / "build/source/disassemble/dsp56kDisassemble"
HOST = OUT / "bd909_host"
HOST_SRC = ROOT / "tools/harness/bd909_host/bd909_host.cpp"
ORG = 0x0100
INPUT_BASE = 0x1000
LINE = re.compile(r"^([0-9a-f]{6}): (\S+)(?:\s+(.*?))?\s*; [0-9a-f]{6}(?: [0-9a-f]{6})?$")


def fail(message: str) -> "NoReturn":
    raise SystemExit("verify-perky-simple-drum-frequency-exec: " + message)


def native_frequency(frequency: int) -> int:
    frequency &= 0xFFFFFFFF
    shifted_bits = (frequency << 20) & 0xFFFFFFFF
    shifted = shifted_bits - 0x100000000 if shifted_bits & 0x80000000 else shifted_bits
    product = shifted * 0x057619F1
    high = product >> 32
    return (high >> 10) - (shifted >> 31)


def build_host() -> None:
    libs = [
        V / "build/source/dsp56kEmu/libdsp56kEmu.a",
        V / "build/source/dsp56kBase/libdsp56kBase.a",
        V / "build/source/asmjit/libasmjit.a",
    ]
    missing = [path for path in [ASM, DIS, *libs] if not path.exists()]
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


def assemble() -> tuple[Path, int]:
    OUT.mkdir(parents=True, exist_ok=True)
    binary = OUT / "frequency.bin"
    symbols = OUT / "frequency.sym"
    source = PERKY / "simple_drum_frequency.asm"
    result = subprocess.run(
        [str(ASM), "-in", str(source), "-org", f"{ORG:x}", "-out", str(binary),
         "-list", "-sym", str(symbols)],
        capture_output=True,
        text=True,
    )
    if result.returncode:
        fail("assembler failed:\n" + result.stdout[-4000:] + result.stderr[-2000:])

    labels = {
        parts[0]: int(parts[1], 16)
        for parts in (line.split() for line in symbols.read_text().splitlines())
        if len(parts) == 2
    }
    entry = labels.get("pk_simple_frequency_probe")
    if entry is None:
        fail("assembler emitted no pk_simple_frequency_probe symbol")

    dis = subprocess.run(
        [str(DIS), "-in", str(binary), "-pc", f"{ORG:x}", "-le"],
        capture_output=True,
        text=True,
        check=True,
    )
    typed = {int(m.group(1), 16): m.group(2) for m in map(LINE.match, result.stdout.splitlines()) if m}
    actual = {int(m.group(1), 16): m.group(2) for m in map(LINE.match, dis.stdout.splitlines()) if m}
    if not typed:
        fail("assembler listing contained no typed instructions")
    for address, mnemonic in typed.items():
        if actual.get(address) != mnemonic:
            fail(f"P:{address:06x} typed {mnemonic}, decoded {actual.get(address)}")
    return binary, entry


def main() -> None:
    build_host()
    binary, entry = assemble()

    inputs = list(range(4096))
    expected = [native_frequency(value) for value in inputs]
    if min(expected) != -44739 or max(expected) != 44717:
        fail("Python native oracle range drifted")

    state = [0] * 100
    data = OUT / "frequency.data"
    script = OUT / "frequency.script"
    raw = OUT / "frequency.raw"
    meter = OUT / "frequency.meter"
    data.write_text(
        "X 200 " + " ".join(f"{value:06x}" for value in state) + "\n"
        + f"Y {INPUT_BASE:x} " + " ".join(f"{value:06x}" for value in inputs) + "\n"
    )
    # bd909_host calls the DSP source entry for one 16-sample block per line.
    script.write_text((" ".join(["0"] * 12 + ["-1"]) + "\n") * (4096 // 16))
    subprocess.run(
        [
            str(HOST), "-code", str(binary), "-org", f"{ORG:x}",
            "-entry", f"{entry:x}", "-data", str(data), "-script", str(script),
            "-out", str(raw), "-meter", str(meter), "-frames", "16",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    got = list(struct.unpack(f"<{raw.stat().st_size // 4}i", raw.read_bytes()))
    want = [sample for value in expected for sample in (value, value)]
    if got != want:
        limit = min(len(got), len(want))
        at = next((i for i in range(limit) if got[i] != want[i]), limit)
        if at == limit:
            fail(f"output length {len(got)} != expected {len(want)}")
        fail(
            f"input {at // 2}: got audio word {got[at]}, expected {want[at]} "
            f"(pair index {at})"
        )

    counts = [int(value) for value in meter.read_text().split()]
    print(
        "PERKY Simple Drum frequency executable gate: PASS "
        f"(4096/4096 exact native results; range -44739..44717; "
        f"max {max(counts)} instr/16 samples)"
    )


if __name__ == "__main__":
    main()

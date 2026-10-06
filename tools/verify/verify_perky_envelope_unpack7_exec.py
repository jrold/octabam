#!/usr/bin/env python3
"""Execute the synthetic 7-bit packed-envelope DSP decoder over both curves."""
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
OUT = ROOT / "out/perky/envelope-unpack7"
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


fab = load_module(
    "perky_env_unpack_fab",
    ROOT / "tools/perky/fabricate_noise_tone_fixtures.py",
)
ASM = V / "build/source/dsp_host/dsp_asm"
DIS = V / "build/source/disassemble/dsp56kDisassemble"
HOST = OUT / "bd909_host"
HOST_SRC = ROOT / "tools/harness/bd909_host/bd909_host.cpp"
ORG = 0x0100  # standalone low-P decoder; shipping high-P gate is separate
ENV1_BASE = 0x0A50
ENV2_BASE = 0x0CD6
LINE = re.compile(
    r"^([0-9a-f]{6}): (\S+)(?:\s+(.*?))?\s*; [0-9a-f]{6}(?: [0-9a-f]{6})?$"
)


def fail(msg: str) -> None:
    raise SystemExit("verify-perky-envelope-unpack7-exec: " + msg)


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


def decoded(text: str):
    return {
        int(m.group(1), 16): (m.group(2), (m.group(3) or "").strip())
        for m in map(LINE.match, text.splitlines())
        if m
    }


def assemble():
    OUT.mkdir(parents=True, exist_ok=True)
    binary, symbols = OUT / "env7.bin", OUT / "env7.sym"
    r = subprocess.run(
        [
            str(ASM), "-in", str(PERKY / "noise_tone_envelope_unpack7.asm"),
            "-org", f"{ORG:x}", "-out", str(binary), "-list", "-sym", str(symbols),
        ],
        capture_output=True,
        text=True,
    )
    if r.returncode:
        fail("assembler failed:\n" + r.stdout[-5000:] + r.stderr[-3000:])
    labels = {
        row[0]: int(row[1], 16)
        for row in (line.split() for line in symbols.read_text().splitlines())
        if len(row) == 2
    }
    entry = labels.get("pk_env_unpack7_probe")
    if entry is None:
        fail("missing pk_env_unpack7_probe")

    d = subprocess.run(
        [str(DIS), "-in", str(binary), "-pc", f"{ORG:x}", "-le"],
        capture_output=True,
        text=True,
        check=True,
    )
    typed, actual = decoded(r.stdout), decoded(d.stdout)
    if not typed:
        fail("assembler produced no parseable listing")
    for address, (mnemonic, operands) in typed.items():
        if mnemonic == "nop" and address not in actual and binary.read_bytes()[(address-ORG)*3:(address-ORG)*3+3] == bytes(3):
            continue
        dm, dop = actual.get(address, ("?", ""))
        if dm != mnemonic:
            fail(
                f"P:{address:06x} typed {mnemonic} {operands}, decoded {dm} {dop}"
            )
    return binary, entry


def words_line(space: str, address: int, words) -> str:
    return f"{space} {address:x} " + " ".join(f"{int(x)&0xFFFFFF:06x}" for x in words)


def run_curve(binary: Path, entry: int, selector: int, env1, env2):
    tag = f"curve{selector+1}"
    data, script = OUT / f"{tag}.data", OUT / f"{tag}.script"
    raw, meter = OUT / f"{tag}.raw", OUT / f"{tag}.meter"
    xstate = [0] * 100
    xstate[0x39] = selector
    xstate[0x40] = 0
    data.write_text(
        "\n".join((
            words_line("X", 0x200, xstate),
            words_line("Y", ENV1_BASE, env1.words),
            words_line("Y", ENV2_BASE, env2.words),
        )) + "\n"
    )
    script.write_text((" ".join(["0"] * 12 + ["-1"]) + "\n") * 128)
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
    audio = list(struct.unpack(f"<{raw.stat().st_size//4}i", raw.read_bytes()))
    counts = [int(x) for x in meter.read_text().split()]
    return audio, counts


def main() -> None:
    build_host()
    binary, entry = assemble()
    values = (fab.envelope_linear(), fab.envelope_ease())
    tables = tuple(packed.pack_envelope(v) for v in values)
    if [t.delta_bits for t in tables] != [7, 7]:
        fail("synthetic curves no longer use the 7-bit decoder canary")
    if [len(t.words) for t in tables] != [646, 646]:
        fail("synthetic packed envelope size drifted")
    if ENV1_BASE + len(tables[0].words) != ENV2_BASE:
        fail("env1 no longer ends exactly at env2 base")
    if ENV2_BASE + len(tables[1].words) != 0x0F5C:
        fail("env2 no longer ends exactly after Y:0x0f5b")

    max_instr = 0
    for selector in (0, 1):
        got, counts = run_curve(binary, entry, selector, *tables)
        expected = [sample for sample in values[selector] for _channel in (0, 1)]
        if got != expected:
            at = next(i for i, (a, b) in enumerate(zip(got, expected)) if a != b)
            fail(
                f"curve {selector+1} audio word {at}: DSP {got[at]} != oracle {expected[at]}"
            )
        max_instr = max(max_instr, max(counts))

    print(
        "PERKY packed envelope decoder executable gate: OK "
        "(2 x 128 blocks / 4096 values; shipping Y:0a50..0f5b; "
        f"max {max_instr} instructions/block)"
    )


if __name__ == "__main__":
    main()

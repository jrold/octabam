#!/usr/bin/env python3
"""Execute Simple Drum envelope DSP paths against the qualified Python model."""
from __future__ import annotations

from pathlib import Path
import re
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
PERKY = ROOT / "modules/perky"
V = ROOT / "vendor/dsp56300"
OUT = ROOT / "out/perky/simple-drum-envelope"
sys.path.insert(0, str(PERKY))

import simple_drum_compact as compact  # noqa:E402
import simple_drum_tables as packed  # noqa:E402

ASM = V / "build/source/dsp_host/dsp_asm"
DIS = V / "build/source/disassemble/dsp56kDisassemble"
HOST = OUT / "bd909_host"
HOST_SRC = ROOT / "tools/harness/bd909_host/bd909_host.cpp"
ORG = 0x0100
TABLE_BASE = 0x09A5
LINE = re.compile(r"^([0-9a-f]{6}): (\S+)(?:\s+(.*?))?\s*; [0-9a-f]{6}(?: [0-9a-f]{6})?$")


def fail(message: str) -> "NoReturn":
    raise SystemExit("verify-perky-simple-drum-envelope-exec: " + message)


def u32_words(value: int) -> tuple[int, int]:
    value &= 0xFFFFFFFF
    return value & 0xFFFF, (value >> 16) & 0xFFFF


def env_words(*, state: int, shape: int, flag4: int = 0, flag6: int = 1,
              trigger: int = 0, value: int = 0, hold: int = 1,
              attack: int = 0x2AAA, decay: int = 40) -> list[int]:
    vlo, vhi = u32_words(value)
    hlo, hhi = u32_words(hold)
    return [state, shape, flag4, flag6, trigger, vlo, vhi, hlo, hhi, attack, decay]


def make_curve() -> tuple[list[int], bytes]:
    values = []
    for i in range(1024):
        # Deliberately nonlinear and with both rising/falling local deltas while
        # staying u16; index 1024 is an exact duplicate of 1023 as in v1.2.1.
        values.append((i * 61 + (i * i * 7) + ((i >> 3) * 123)) & 0xFFFF)
    full = values + [values[-1]] * (2048 - len(values))
    blob = struct.pack("<2048H", *full)
    return values, blob


def oracle(initial: list[int], curve_blob: bytes) -> tuple[list[int], list[int]]:
    words = [0] * compact.WORDS_PER_VOICE
    words[compact.AMP_ENV:compact.AMP_ENV + compact.ENV_WORDS] = initial
    voice = compact.CompactSimpleDrum(words)
    outputs = []
    for _ in range(16):
        outputs.append(
            compact._render_envelope(
                voice,
                compact.AMP_ENV,
                curve_blob if initial[compact.ENV_SHAPE] == 1 else None,
                None,
            )
        )
    final = voice.words[compact.AMP_ENV:compact.AMP_ENV + compact.ENV_WORDS]
    return outputs, final


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
        ], check=True, capture_output=True,
    )


def assemble() -> tuple[Path, int]:
    OUT.mkdir(parents=True, exist_ok=True)
    binary, symbols = OUT / "envelope.bin", OUT / "envelope.sym"
    result = subprocess.run(
        [str(ASM), "-in", str(PERKY / "simple_drum_envelope.asm"),
         "-org", f"{ORG:x}", "-out", str(binary), "-list", "-sym", str(symbols)],
        capture_output=True, text=True,
    )
    if result.returncode:
        fail("assembler failed:\n" + result.stdout[-5000:] + result.stderr[-3000:])
    labels = {
        parts[0]: int(parts[1], 16)
        for parts in (line.split() for line in symbols.read_text().splitlines())
        if len(parts) == 2
    }
    entry = labels.get("pk_simple_envelope_probe")
    if entry is None:
        fail("missing pk_simple_envelope_probe")
    dis = subprocess.run(
        [str(DIS), "-in", str(binary), "-pc", f"{ORG:x}", "-le"],
        capture_output=True, text=True, check=True,
    )
    typed = {int(m.group(1), 16): m.group(2) for m in map(LINE.match, result.stdout.splitlines()) if m}
    actual = {int(m.group(1), 16): m.group(2) for m in map(LINE.match, dis.stdout.splitlines()) if m}
    if not typed:
        fail("assembler listing contained no typed instructions")
    for address, mnemonic in typed.items():
        if actual.get(address) != mnemonic:
            fail(f"P:{address:06x} typed {mnemonic}, decoded {actual.get(address)}")
    return binary, entry


def run_case(binary: Path, entry: int, tag: str, initial: list[int], table_words):
    words = [0] * 100
    words[0x40:0x40 + compact.ENV_WORDS] = initial
    data = OUT / f"{tag}.data"
    script = OUT / f"{tag}.script"
    raw = OUT / f"{tag}.raw"
    state = OUT / f"{tag}.state"
    data.write_text(
        "X 200 " + " ".join(f"{value & 0xFFFFFF:06x}" for value in words) + "\n"
        + f"Y {TABLE_BASE:x} " + " ".join(f"{value:06x}" for value in table_words) + "\n"
    )
    script.write_text(" ".join(["0"] * 12 + ["-1"]) + "\n")
    subprocess.run(
        [str(HOST), "-code", str(binary), "-org", f"{ORG:x}",
         "-entry", f"{entry:x}", "-data", str(data), "-script", str(script),
         "-out", str(raw), "-state", str(state), "-frames", "16"],
        check=True, capture_output=True, text=True,
    )
    pcm = list(struct.unpack(f"<{raw.stat().st_size // 4}i", raw.read_bytes()))
    dumped = [int(value, 16) for value in state.read_text().split()]
    final = [dumped[0x40 + i] & 0xFFFF for i in range(compact.ENV_WORDS)]
    return pcm, final


def main() -> None:
    build_host()
    binary, entry = assemble()
    curve, curve_blob = make_curve()
    table_words = packed.pack_u16(curve)
    if len(table_words) != 683:
        fail(f"packed curve uses {len(table_words)} words, expected 683")

    cases = [
        env_words(state=1, shape=0, attack=0x2AAA, decay=40),
        env_words(state=1, shape=1, attack=0x5555, decay=99),
        env_words(state=1, shape=0, value=0x000FF000, attack=0x5555, decay=8),
        env_words(state=1, shape=1, value=0x000F7000, attack=0x5555, decay=52),
        env_words(state=4, shape=0, value=0x00005000, decay=428),
        env_words(state=4, shape=1, value=0x00050000, decay=1040),
        env_words(state=0, shape=0, trigger=1, hold=0, attack=0x2AAA, decay=40),
        env_words(state=0, shape=1, flag4=1, trigger=0, hold=0, attack=0x5555, decay=99),
        env_words(state=3, shape=0, trigger=0, hold=1, value=0x000FFFFF, decay=40),
        env_words(state=3, shape=1, trigger=0, hold=0, value=0x000FFFFF, decay=99),
        env_words(state=4, shape=0, trigger=1, value=0x00070000, decay=8),
        env_words(state=4, shape=1, trigger=1, value=0x00070000, decay=52),
    ]

    samples = 0
    for index, initial in enumerate(cases):
        want, want_state = oracle(initial.copy(), curve_blob)
        got, got_state = run_case(binary, entry, f"case-{index:02d}", initial, table_words)
        stereo = [value for value in want for _ in (0, 1)]
        if got != stereo:
            limit = min(len(got), len(stereo))
            at = next((i for i in range(limit) if got[i] != stereo[i]), limit)
            fail(
                f"case {index} output {at}: got "
                f"{got[at] if at < len(got) else 'EOF'}, want "
                f"{stereo[at] if at < len(stereo) else 'EOF'}"
            )
        if got_state != want_state:
            fail(f"case {index} final state {got_state!r} != {want_state!r}")
        samples += len(want)

    print(
        "PERKY Simple Drum envelope executable gate: PASS "
        f"({len(cases)} state cases, {samples} exact outputs + final 11-word state; "
        "linear AMP and packed shaped PITCH)"
    )


if __name__ == "__main__":
    main()

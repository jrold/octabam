#!/usr/bin/env python3
"""Assemble/execute Simple Drum oscillator and compare exact PCM/final state."""
from __future__ import annotations

from pathlib import Path
import re
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
PERKY = ROOT / "modules/perky"
V = ROOT / "vendor/dsp56300"
OUT = ROOT / "out/perky/simple-drum-oscillator"
sys.path.insert(0, str(PERKY))
import simple_drum_tables as packed  # noqa:E402

ASM = V / "build/source/dsp_host/dsp_asm"
DIS = V / "build/source/disassemble/dsp56kDisassemble"
HOST = OUT / "bd909_host"
HOST_SRC = ROOT / "tools/harness/bd909_host/bd909_host.cpp"
ORG = 0x0100
TABLE_BASE = 0x07A5
WAVES = (0x080222A0, 0x080226A0, 0x080228A0)
LINE = re.compile(r"^([0-9a-f]{6}): (\S+)(?:\s+(.*?))?\s*; [0-9a-f]{6}(?: [0-9a-f]{6})?$")


def fail(message: str) -> "NoReturn":
    raise SystemExit("verify-perky-simple-drum-oscillator-exec: " + message)


def s16(value: int) -> int:
    value &= 0xFFFF
    return value - 0x10000 if value & 0x8000 else value


def s32(value: int) -> int:
    value &= 0xFFFFFFFF
    return value - 0x100000000 if value & 0x80000000 else value


def make_waves() -> list[list[int]]:
    out = []
    for wave in range(3):
        values = []
        for i in range(256):
            # Deterministic, discontinuous enough to exercise interpolation,
            # signed endpoints and the index-255 wrap to sample zero.
            value = ((i * (379 + wave * 73) + i * i * (11 + wave * 3)
                      + wave * 0x2468) & 0xFFFF)
            values.append(value)
        out.append(values)
    return out


def render(state: list[int], waves: list[list[int]], count: int = 16):
    phase, increment, current, next_wave = state
    pcm = []
    for _ in range(count):
        phase = (phase + increment) & 0xFFFFFFFF
        if s32(phase) > 0x00100000:
            phase = (phase - 0x00100000) & 0xFFFFFFFF
            if next_wave != current:
                current = next_wave
        try:
            ordinal = WAVES.index(current)
        except ValueError as exc:
            raise AssertionError(f"oracle got unknown wave 0x{current:08x}") from exc
        index = (phase >> 12) & 0xFF
        fraction = phase & 0xFFF
        a = s16(waves[ordinal][index])
        b = s16(waves[ordinal][(index + 1) & 0xFF])
        sample = s16(a + (((b - a) * fraction) >> 12))
        pcm.append(sample)
    return pcm, [phase, increment, current, next_wave]


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
    binary, symbols = OUT / "oscillator.bin", OUT / "oscillator.sym"
    result = subprocess.run(
        [str(ASM), "-in", str(PERKY / "simple_drum_oscillator.asm"),
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
    entry = labels.get("pk_simple_oscillator_probe")
    if entry is None:
        fail("missing pk_simple_oscillator_probe")
    dis = subprocess.run(
        [str(DIS), "-in", str(binary), "-pc", f"{ORG:x}", "-le"],
        capture_output=True, text=True, check=True,
    )
    typed = {int(m.group(1), 16): m.group(2) for m in map(LINE.match, result.stdout.splitlines()) if m}
    actual = {int(m.group(1), 16): m.group(2) for m in map(LINE.match, dis.stdout.splitlines()) if m}
    if not typed:
        fail("assembler listing contained no typed instructions")
    for address, mnemonic in typed.items():
        if mnemonic == "nop" and address not in actual and binary.read_bytes()[(address-ORG)*3:(address-ORG)*3+3] == bytes(3):
            continue
        if actual.get(address) != mnemonic:
            fail(f"P:{address:06x} typed {mnemonic}, decoded {actual.get(address)}")
    return binary, entry


def limbs(value: int) -> tuple[int, int]:
    value &= 0xFFFFFFFF
    return value & 0xFFFF, (value >> 16) & 0xFFFF


def run_case(binary: Path, entry: int, tag: str, initial: list[int], table_words):
    words = [0] * 100
    for offset, value in enumerate(initial):
        lo, hi = limbs(value)
        words[0x40 + 2 * offset] = lo
        words[0x41 + 2 * offset] = hi
    data = OUT / f"{tag}.data"
    script = OUT / f"{tag}.script"
    raw = OUT / f"{tag}.raw"
    state = OUT / f"{tag}.state"
    data.write_text(
        "X 200 " + " ".join(f"{value:06x}" for value in words) + "\n"
        + f"Y {TABLE_BASE:x} " + " ".join(f"{value:06x}" for value in table_words) + "\n"
    )
    script.write_text(" ".join(["0"] * 12 + ["-1"]) + "\n")
    subprocess.run(
        [str(HOST), "-code", str(binary), "-org", f"{ORG:x}",
         "-entry", f"{entry:x}", "-data", str(data), "-script", str(script),
         "-out", str(raw), "-state", str(state), "-state-words", "100", "-frames", "16"],
        check=True, capture_output=True, text=True,
    )
    got_pcm = list(struct.unpack(f"<{raw.stat().st_size // 4}i", raw.read_bytes()))
    dumped = [int(value, 16) for value in state.read_text().split()]
    def u32(at):
        return (dumped[at] & 0xFFFF) | ((dumped[at + 1] & 0xFFFF) << 16)
    final = [u32(0x40), u32(0x42), u32(0x44), u32(0x46)]
    return got_pcm, final


def main() -> None:
    build_host()
    binary, entry = assemble()
    waves = make_waves()
    table_words = packed.pack_u16(value for wave in waves for value in wave)
    if len(table_words) != 512:
        fail(f"three packed waves use {len(table_words)} words, expected 512")

    cases = [
        # No wrap / each current wave.
        [0x00000000, 0x00000123, WAVES[0], WAVES[0]],
        [0x00054321, 0x00000B17, WAVES[1], WAVES[1]],
        [0x000ABCDF, 0x000000AE, WAVES[2], WAVES[2]],
        # Deferred switch occurs only after strict > 0x100000 wrap.
        [0x000FF000, 0x00000100, WAVES[0], WAVES[1]],
        [0x00100000, 0x00000000, WAVES[1], WAVES[2]],
        [0x000FFFFF, 0x00000002, WAVES[2], WAVES[0]],
        # Negative increments exercise exact modulo-u32 add and signed wrap test.
        [0x00080000, 0xFFFFFFAB, WAVES[0], WAVES[2]],
        [0x00000020, 0xFFFFFFD5, WAVES[1], WAVES[0]],
        [0xFFF00020, 0x00000015, WAVES[2], WAVES[1]],
        # Index 255 / adjacent-sample wrap inside each table.
        [0x000FE123, 0x00000000, WAVES[0], WAVES[0]],
        [0x000FEABC, 0x00000000, WAVES[1], WAVES[1]],
        [0x000FEFFF, 0x00000000, WAVES[2], WAVES[2]],
        # Limb carry paths.
        [0x0000FFF0, 0x00000030, WAVES[0], WAVES[0]],
        [0x000FFFF0, 0x00010030, WAVES[1], WAVES[2]],
    ]

    checked = 0
    for index, initial in enumerate(cases):
        want_pcm, want_final = render(initial.copy(), waves)
        got_pcm, got_final = run_case(binary, entry, f"case-{index:02d}", initial, table_words)
        stereo = [sample for sample in want_pcm for _ in (0, 1)]
        if got_pcm != stereo:
            limit = min(len(got_pcm), len(stereo))
            at = next((i for i in range(limit) if got_pcm[i] != stereo[i]), limit)
            fail(
                f"case {index} PCM word {at}: got "
                f"{got_pcm[at] if at < len(got_pcm) else 'EOF'}, want "
                f"{stereo[at] if at < len(stereo) else 'EOF'}"
            )
        if got_final != want_final:
            fail(
                f"case {index} final state {[hex(x) for x in got_final]} != "
                f"{[hex(x) for x in want_final]}"
            )
        checked += len(want_pcm)

    print(
        "PERKY Simple Drum oscillator executable gate: PASS "
        f"({len(cases)} state cases, {checked} exact samples + final phase/current/next)"
    )


if __name__ == "__main__":
    main()

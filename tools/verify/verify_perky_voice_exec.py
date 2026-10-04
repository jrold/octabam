#!/usr/bin/env python3
"""Execute the first complete composed PERKY Noise/Tone DSP voice.

The correctness glue composes the five individually executable-gated kernels.
It intentionally uses their unpacked synthetic table layouts and copies the
41-word compact voice through each probe ABI.  That overhead is temporary: the
purpose of this gate is to prove complete-render order/state before inlining.

For each case this gate requires exact agreement with noise_tone_compact.py for
16 PCM samples, every compact voice word, and all four RNG limbs.  It also
prints P-word size and executed instructions/block so optimization starts from
a measured baseline.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import random
import re
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
PERKY = ROOT / "modules" / "perky"
V = ROOT / "vendor" / "dsp56300"
OUT = ROOT / "out" / "perky" / "voice"
sys.path.insert(0, str(PERKY))

import noise_tone_compact as compact  # noqa: E402
import noise_tone_word_model as word  # noqa: E402

ASM = V / "build/source/dsp_host/dsp_asm"
DIS = V / "build/source/disassemble/dsp56kDisassemble"
HOST = OUT / "bd909_host"
HOST_SRC = ROOT / "tools/harness/bd909_host/bd909_host.cpp"
ORG = 0x5000
STATE = 0x200
FRAMES = 16
ID0 = 0x11112222
ID1 = 0x33334444
LINE = re.compile(
    r"^([0-9a-f]{6}): (\S+)(?:\s+(.*?))?\s*; [0-9a-f]{6}(?: [0-9a-f]{6})?$"
)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot import {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


fab = load_module(
    "perky_voice_fixture_fab",
    ROOT / "tools/perky/fabricate_noise_tone_fixtures.py",
)


def fail(msg: str) -> None:
    raise SystemExit("verify-perky-voice-exec: " + msg)


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
    paths = [
        PERKY / "noise_tone_voice_glue.asm",
        PERKY / "noise_tone_math.asm",
        PERKY / "noise_tone_filter.asm",
        PERKY / "noise_tone_oscillator.asm",
        PERKY / "noise_tone_envelope.asm",
        PERKY / "noise_tone_mix.asm",
    ]
    return "\n\n".join(path.read_text() for path in paths) + "\n"


def assemble():
    OUT.mkdir(parents=True, exist_ok=True)
    src = OUT / "voice.asm"
    binary = OUT / "voice.bin"
    symbols = OUT / "voice.sym"
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
    if "pk_voice_probe" not in labels:
        fail("assembler emitted no pk_voice_probe symbol")

    d = subprocess.run(
        [str(DIS), "-in", str(binary), "-pc", f"{ORG:x}", "-le"],
        capture_output=True,
        text=True,
        check=True,
    )
    typed, actual = decoded(r.stdout), decoded(d.stdout)
    if not typed or len(actual) < len(typed) * 0.9:
        fail("no usable disassembly to compare")
    mismatches = []
    for addr, (mnemonic, operands) in typed.items():
        dm, dops = actual.get(addr, ("?", ""))
        # Same explicitly-audited assembler quirk used by Octabam proper: a
        # typed mpy may decode mpysu. Our kernels use mpyuu instead, so any
        # occurrence here is unexpected and remains a hard failure.
        if dm != mnemonic:
            mismatches.append((addr, mnemonic, operands, dm, dops))
    if mismatches:
        addr, sm, sop, dm, dop = mismatches[0]
        fail(f"P:{addr:06x} typed {sm} {sop} but decodes {dm} {dop}")
    return binary, labels["pk_voice_probe"]


def s16_blob(values: list[int]) -> bytes:
    return struct.pack(f"<{len(values)}h", *values)


def u16_blob(values: list[int]) -> bytes:
    return struct.pack(f"<{len(values)}H", *(v & 0xFFFF for v in values))


def synthetic_tables():
    ws = fab.waves()
    waves = {
        ID0: s16_blob(ws[0]),
        ID1: s16_blob(ws[1]),
    }
    return waves, u16_blob(fab.envelope_linear()), u16_blob(fab.envelope_ease())


def put32(raw: bytearray, off: int, value: int) -> None:
    struct.pack_into("<I", raw, off, value & 0xFFFFFFFF)


def put16(raw: bytearray, off: int, value: int) -> None:
    struct.pack_into("<H", raw, off, value & 0xFFFF)


def make_voice(r: random.Random, mode: int) -> compact.CompactVoice:
    controls = tuple(r.randrange(4096) for _ in range(4))
    raw = fab.synthetic_state(mode, controls, 16)
    raw[6] = r.randrange(1, 256)

    for base in (0x2C, 0xC4):
        put32(raw, base + 4, r.randrange(0x00100001))
        put32(raw, base + 8, r.randrange(1, 0x40000))
        put32(raw, base + 0x0C, r.choice((ID0, ID1)))
        put32(raw, base + 0x10, r.choice((ID0, ID1)))

    put16(raw, 0x60, r.randrange(5))
    put16(raw, 0x62, r.randrange(5))
    put16(raw, 0x70, r.randrange(0x10000))

    e = 0x74
    raw[e] = r.choice((0, 1, 2, 3, 4))
    raw[e + 1] = r.randrange(3)
    raw[e + 4] = r.randrange(2)
    raw[e + 6] = r.randrange(2)
    raw[e + 7] = r.randrange(2)
    put32(raw, e + 0x0C, r.randrange(0x100000))
    put32(raw, e + 0x10, r.choice((0, r.getrandbits(32))))
    put16(raw, e + 0x20, r.randrange(1, 0x10000))
    put16(raw, e + 0x22, r.randrange(1, 0x10000))

    f = 0x9C
    put16(raw, f + 0x0C, r.randrange(0x10000))
    put16(raw, f + 0x0E, r.randrange(0x10000))
    put32(raw, f + 0x10, r.randrange(-32767, 32768))
    put32(raw, f + 0x14, r.randrange(-32767, 32768))
    put32(raw, f + 0x18, r.randrange(-32767, 32768))
    return compact.CompactVoice.from_arm(raw)


def table_words(blob: bytes, signed: bool) -> list[int]:
    fmt = "h" if signed else "H"
    return [x & 0xFFFF for x in struct.unpack(f"<{len(blob)//2}{fmt}", blob)]


def write_data(path: Path, voice: compact.CompactVoice, low: int, high: int,
               waves, env1: bytes, env2: bytes) -> None:
    y = [0] * 64
    y[:compact.WORDS_PER_VOICE] = voice.words
    lr, hr = word.U32.from_int(low), word.U32.from_int(high)
    y[41:45] = [lr.lo, lr.hi, hr.lo, hr.hi]
    lines = [
        "X 200 " + " ".join("000000" for _ in range(64)),
        "Y 200 " + " ".join(f"{v & 0xFFFFFF:06x}" for v in y),
        "X 3000 " + " ".join(f"{v:06x}" for v in table_words(waves[ID0], True)),
        "X 3100 " + " ".join(f"{v:06x}" for v in table_words(waves[ID1], True)),
        "X 3200 " + " ".join(f"{v:06x}" for v in table_words(env1, False)),
        "X 3a00 " + " ".join(f"{v:06x}" for v in table_words(env2, False)),
    ]
    path.write_text("\n".join(lines) + "\n")


def run_case(binary: Path, entry: int, case: int, initial: compact.CompactVoice,
             low: int, high: int, waves, env1: bytes, env2: bytes):
    data = OUT / f"case-{case}.data"
    script = OUT / f"case-{case}.script"
    raw = OUT / f"case-{case}.raw"
    state = OUT / f"case-{case}.state"
    meter = OUT / f"case-{case}.meter"
    write_data(data, initial, low, high, waves, env1, env2)
    script.write_text(" ".join(["0"] * 12 + ["-1"]) + "\n")

    r = subprocess.run(
        [
            str(HOST), "-code", str(binary), "-org", f"{ORG:x}",
            "-entry", f"{entry:x}", "-data", str(data), "-script", str(script),
            "-out", str(raw), "-state", str(state), "-meter", str(meter),
            "-frames", str(FRAMES),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    audio = list(struct.unpack(f"<{raw.stat().st_size//4}i", raw.read_bytes()))
    dumped = [int(x, 16) for x in state.read_text().split()]
    if len(dumped) != 128:
        fail(f"case {case}: state dump has {len(dumped)} words, expected 128")
    instructions = int(meter.read_text().strip())
    return audio, dumped[64:128], instructions, r.stdout.strip()


def main() -> None:
    build_host()
    binary, entry = assemble()
    waves, env1, env2 = synthetic_tables()
    r = random.Random(0x504B5956)
    instruction_counts = []

    for case in range(24):
        initial = make_voice(r, case & 2)
        oracle_voice = compact.CompactVoice(list(initial.words))
        low, high = r.getrandbits(32), r.getrandbits(32)
        oracle_rng = word.WordRng.from_ints(low, high)
        want = compact.render_block(
            oracle_voice, FRAMES, waves, oracle_rng, env1, env2
        )

        audio, ystate, instructions, _stdout = run_case(
            binary, entry, case, initial, low, high, waves, env1, env2
        )
        expected_audio = [sample for sample in want for _channel in (0, 1)]
        if audio != expected_audio:
            at = next(i for i, (a, b) in enumerate(zip(audio, expected_audio)) if a != b)
            fail(
                f"case {case}: audio word {at}: DSP {audio[at]} != oracle {expected_audio[at]}"
            )
        got_voice = [v & 0xFFFF for v in ystate[:compact.WORDS_PER_VOICE]]
        if got_voice != oracle_voice.words:
            at = next(i for i, (a, b) in enumerate(zip(got_voice, oracle_voice.words)) if a != b)
            fail(
                f"case {case}: compact word {at}: DSP {got_voice[at]:04x} "
                f"!= oracle {oracle_voice.words[at]:04x}"
            )
        expected_rng = [
            oracle_rng.low.lo, oracle_rng.low.hi,
            oracle_rng.high.lo, oracle_rng.high.hi,
        ]
        got_rng = [v & 0xFFFF for v in ystate[41:45]]
        if got_rng != expected_rng:
            fail(f"case {case}: RNG {got_rng} != oracle {expected_rng}")
        instruction_counts.append(instructions)

    pwords = binary.stat().st_size // 3
    print(
        "PERKY complete DSP voice executable gate: OK "
        f"(24 x {FRAMES}-sample blocks, {pwords} P words, "
        f"instructions/block min {min(instruction_counts)}, "
        f"mean {sum(instruction_counts)/len(instruction_counts):.1f}, "
        f"max {max(instruction_counts)})"
    )


if __name__ == "__main__":
    main()

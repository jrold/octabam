#!/usr/bin/env python3
"""Execute the complete PERKY voice with only its oscillator switched to packed Y.

The complete glue is not duplicated.  This gate rewrites its two calls from the
already-proven raw-table `pk_osc_probe` to `pk_osc_packed_probe` in the scratch
assembly it builds, then concatenates the same math/filter/envelope/mixer
kernels.  Envelope tables remain unpacked here on purpose: a failure is thereby
isolated to the packed wave accessor.

For every case PCM, all 41 compact words and the four RNG limbs must exactly
match noise_tone_compact.py.
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
OUT = ROOT / "out" / "perky" / "voice-packed-wave"
sys.path.insert(0, str(PERKY))

import noise_tone_compact as compact  # noqa:E402
import noise_tone_word_model as word  # noqa:E402
from noise_tone_tables import pack_waves  # noqa:E402

ASM = V / "build/source/dsp_host/dsp_asm"
DIS = V / "build/source/disassemble/dsp56kDisassemble"
HOST = OUT / "bd909_host"
HOST_SRC = ROOT / "tools/harness/bd909_host/bd909_host.cpp"
ORG = 0x5000
STATE = 0x200
WAVE_Y = 0x0795
FRAMES = 16
IDS = (0x11112222, 0x33334444, 0x55556666, 0x77778888)
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
    "perky_voice_packed_wave_fixture_fab",
    ROOT / "tools/perky/fabricate_noise_tone_fixtures.py",
)


def fail(msg: str) -> None:
    raise SystemExit("verify-perky-voice-packed-wave-exec: " + msg)


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


def packed_osc_source() -> str:
    src = (PERKY / "noise_tone_oscillator_packed.asm").read_text()
    for i, address in enumerate(IDS):
        src = src.replace(f"@W{i}L@", f"${address & 0xFFFF:04x}")
        src = src.replace(f"@W{i}H@", f"${(address >> 16) & 0xFFFF:04x}")
    if "@W" in src:
        fail("packed oscillator has unresolved wave identity token")
    return src


def combined_source() -> str:
    glue = (PERKY / "noise_tone_voice_glue.asm").read_text()
    hits = glue.count("jsr     pk_osc_probe")
    if hits != 2:
        fail(f"complete glue has {hits} raw oscillator calls, expected exactly 2")
    glue = glue.replace("jsr     pk_osc_probe", "jsr     pk_osc_packed_probe")
    pieces = [
        glue,
        (PERKY / "noise_tone_math.asm").read_text(),
        (PERKY / "noise_tone_filter.asm").read_text(),
        packed_osc_source(),
        (PERKY / "noise_tone_envelope.asm").read_text(),
        (PERKY / "noise_tone_mix.asm").read_text(),
    ]
    return "\n\n".join(pieces) + "\n"


def assemble():
    OUT.mkdir(parents=True, exist_ok=True)
    src = OUT / "voice_packed_wave.asm"
    binary = OUT / "voice_packed_wave.bin"
    symbols = OUT / "voice_packed_wave.sym"
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
    for addr, (mnemonic, operands) in typed.items():
        dm, dops = actual.get(addr, ("?", ""))
        if dm != mnemonic:
            fail(f"P:{addr:06x} typed {mnemonic} {operands} but decodes {dm} {dops}")
    return binary, labels["pk_voice_probe"]


def s16_blob(values) -> bytes:
    return struct.pack(f"<{len(values)}h", *values)


def u16_blob(values) -> bytes:
    return struct.pack(f"<{len(values)}H", *(v & 0xFFFF for v in values))


def synthetic_tables():
    ws = fab.waves()
    waves = {address: s16_blob(values) for address, values in zip(IDS, ws)}
    packed = pack_waves(
        (address, [v & 0xFFFF for v in values])
        for address, values in zip(IDS, ws)
    )
    if len(packed.words) != 683:
        fail(f"four-wave stream is {len(packed.words)} words, expected 683")
    return waves, packed, u16_blob(fab.envelope_linear()), u16_blob(fab.envelope_ease())


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
        put32(raw, base + 0x0C, r.choice(IDS))
        put32(raw, base + 0x10, r.choice(IDS))

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


def table_words(blob: bytes) -> list[int]:
    return [x & 0xFFFF for x in struct.unpack(f"<{len(blob)//2}H", blob)]


def write_data(path: Path, voice: compact.CompactVoice, low: int, high: int,
               packed, env1: bytes, env2: bytes) -> None:
    y = [0] * 64
    y[:compact.WORDS_PER_VOICE] = voice.words
    lr, hr = word.U32.from_int(low), word.U32.from_int(high)
    y[41:45] = [lr.lo, lr.hi, hr.lo, hr.hi]
    lines = [
        "X 200 " + " ".join("000000" for _ in range(64)),
        "Y 200 " + " ".join(f"{v & 0xFFFFFF:06x}" for v in y),
        f"Y {WAVE_Y:x} " + " ".join(f"{v:06x}" for v in packed.words),
        "X 3200 " + " ".join(f"{v:06x}" for v in table_words(env1)),
        "X 3a00 " + " ".join(f"{v:06x}" for v in table_words(env2)),
    ]
    path.write_text("\n".join(lines) + "\n")


def run_case(binary: Path, entry: int, case: int, initial: compact.CompactVoice,
             low: int, high: int, packed, env1: bytes, env2: bytes):
    data = OUT / f"case-{case}.data"
    script = OUT / f"case-{case}.script"
    raw = OUT / f"case-{case}.raw"
    state = OUT / f"case-{case}.state"
    meter = OUT / f"case-{case}.meter"
    write_data(data, initial, low, high, packed, env1, env2)
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
    waves, packed, env1, env2 = synthetic_tables()
    r = random.Random(0x504B5057)
    instruction_counts = []

    for case in range(32):
        initial = make_voice(r, case & 2)
        oracle_voice = compact.CompactVoice(list(initial.words))
        low, high = r.getrandbits(32), r.getrandbits(32)
        oracle_rng = word.WordRng.from_ints(low, high)
        want = compact.render_block(
            oracle_voice, FRAMES, waves, oracle_rng, env1, env2
        )

        audio, ystate, instructions, _stdout = run_case(
            binary, entry, case, initial, low, high, packed, env1, env2
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
        "PERKY complete voice + packed-Y wave gate: OK "
        f"(32 x {FRAMES}-sample blocks, {pwords} P words, "
        f"instructions/block min {min(instruction_counts)}, "
        f"mean {sum(instruction_counts)/len(instruction_counts):.1f}, "
        f"max {max(instruction_counts)})"
    )


if __name__ == "__main__":
    main()

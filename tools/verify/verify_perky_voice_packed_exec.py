#!/usr/bin/env python3
"""Execute the complete PERKY Noise/Tone voice on the full packed-Y layout.

This is the first end-to-end DSP gate in which BOTH table families use the
shipping representation simultaneously:

  Y:$0795..$0a3f  four packed waves (683 words)
  Y:$0a40..$0cc5  packed envelope 1 (646 words)
  Y:$0cc6..$0f4b  packed envelope 2 (646 words)

The existing complete voice glue is not duplicated. In the scratch assembly
this gate replaces exactly two raw oscillator calls with pk_osc_packed_probe
and exactly one raw envelope call with pk_envelope_packed7_probe. The packed
envelope wrapper still calls the already-proven raw envelope kernel with shape
forced linear for state transitions; only curve output shaping is replaced.

For every case the DSP must match the raw-table compact oracle in stereo PCM,
all 41 compact voice words, and all four RNG limbs.
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
PERKY = ROOT / "modules/perky"
V = ROOT / "vendor/dsp56300"
OUT = ROOT / "out/perky/voice-packed"
sys.path.insert(0, str(PERKY))

import noise_tone_compact as compact  # noqa:E402
import noise_tone_word_model as word  # noqa:E402
from noise_tone_tables import pack_envelope, pack_waves  # noqa:E402

ASM = V / "build/source/dsp_host/dsp_asm"
DIS = V / "build/source/disassemble/dsp56kDisassemble"
HOST = OUT / "bd909_host"
HOST_SRC = ROOT / "tools/harness/bd909_host/bd909_host.cpp"
ORG = 0x5000
FRAMES = 16
WAVE_Y = 0x0795
ENV1_Y = 0x0A40
ENV2_Y = 0x0CC6
IDS = (0x11112222, 0x33334444, 0x55556666, 0x77778888)
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
    "perky_voice_packed_fab",
    ROOT / "tools/perky/fabricate_noise_tone_fixtures.py",
)


def fail(msg: str) -> None:
    raise SystemExit("verify-perky-voice-packed-exec: " + msg)


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
    osc_hits = glue.count("jsr     pk_osc_probe")
    env_hits = glue.count("jsr     pk_envelope_probe")
    if osc_hits != 2:
        fail(f"complete glue has {osc_hits} raw oscillator calls, expected 2")
    if env_hits != 1:
        fail(f"complete glue has {env_hits} raw envelope calls, expected 1")
    glue = glue.replace("jsr     pk_osc_probe", "jsr     pk_osc_packed_probe")
    glue = glue.replace("jsr     pk_envelope_probe", "jsr     pk_envelope_packed7_probe")
    pieces = [
        glue,
        (PERKY / "noise_tone_math.asm").read_text(),
        (PERKY / "noise_tone_filter.asm").read_text(),
        packed_osc_source(),
        (PERKY / "noise_tone_envelope_packed7.asm").read_text(),
        (PERKY / "noise_tone_envelope.asm").read_text(),
        (PERKY / "noise_tone_mix.asm").read_text(),
    ]
    return "\n\n".join(pieces) + "\n"


def assemble():
    OUT.mkdir(parents=True, exist_ok=True)
    src = OUT / "voice_packed.asm"
    binary = OUT / "voice_packed.bin"
    symbols = OUT / "voice_packed.sym"
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
    entry = labels.get("pk_voice_probe")
    if entry is None:
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
    return binary, entry


def s16_blob(values) -> bytes:
    return struct.pack(f"<{len(values)}h", *(max(-32768, min(32767, int(v))) for v in values))


def u16_blob(values) -> bytes:
    return struct.pack(f"<{len(values)}H", *(int(v) & 0xFFFF for v in values))


def synthetic_tables():
    wave_values = fab.waves()
    raw_waves = {
        address: s16_blob(values)
        for address, values in zip(IDS, wave_values)
    }
    packed_waves = pack_waves(
        (address, [v & 0xFFFF for v in values])
        for address, values in zip(IDS, wave_values)
    )
    env1_values = fab.envelope_linear()
    env2_values = fab.envelope_ease()
    packed_env1 = pack_envelope(env1_values)
    packed_env2 = pack_envelope(env2_values)
    if len(packed_waves.words) != 683:
        fail(f"wave payload is {len(packed_waves.words)} words, expected 683")
    if (packed_env1.delta_bits, packed_env2.delta_bits) != (7, 7):
        fail("synthetic envelope widths drifted from 7/7")
    if (len(packed_env1.words), len(packed_env2.words)) != (646, 646):
        fail("synthetic envelope payload sizes drifted from 646/646")
    return (
        raw_waves,
        u16_blob(env1_values),
        u16_blob(env2_values),
        packed_waves,
        packed_env1,
        packed_env2,
    )


def put32(raw: bytearray, off: int, value: int) -> None:
    struct.pack_into("<I", raw, off, value & 0xFFFFFFFF)


def put16(raw: bytearray, off: int, value: int) -> None:
    struct.pack_into("<H", raw, off, value & 0xFFFF)


def make_voice(r: random.Random, case: int) -> compact.CompactVoice:
    mode = 2 if case & 1 else 0
    controls = tuple(r.randrange(4096) for _ in range(4))
    raw = fab.synthetic_state(mode, controls, 16)
    raw[6] = r.randrange(1, 256)

    for base in (0x2C, 0xC4):
        put32(raw, base + 4, r.choice((r.randrange(0x100001), r.randrange(0xF0000, 0x100001))))
        put32(raw, base + 8, r.randrange(1, 0x40000))
        put32(raw, base + 0x0C, r.choice(IDS))
        put32(raw, base + 0x10, r.choice(IDS))

    put16(raw, 0x60, r.randrange(5))
    put16(raw, 0x62, r.randrange(5))
    put16(raw, 0x70, r.randrange(0x10000))

    e = 0x74
    raw[e] = r.choice((0, 1, 2, 3, 4))
    raw[e + 1] = case % 3             # linear, curve 1, curve 2
    raw[e + 4] = r.randrange(2)
    raw[e + 6] = r.randrange(2)
    raw[e + 7] = r.randrange(2)
    # Force cache/block-edge traffic often inside the 16-sample render.
    idx = r.randrange(128) * 16 + r.choice((14, 15, 0, 1))
    value = min(0xFFFFF, (idx << 10) | r.randrange(0x400))
    put32(raw, e + 0x0C, r.choice((value, 0x0FFFFE, 0x0FFFFF, r.randrange(0x100000))))
    put32(raw, e + 0x10, r.choice((0, r.getrandbits(32))))
    put16(raw, e + 0x20, r.randrange(1, 0x10000))
    put16(raw, e + 0x22, r.randrange(1, 0x10000))

    f = 0x9C
    put16(raw, f + 0x0C, r.randrange(0x10000))
    put16(raw, f + 0x0E, r.randrange(0x10000))
    put32(raw, f + 0x10, r.randrange(-32767, 32768))
    put32(raw, f + 0x14, r.randrange(-32767, 32768))
    put32(raw, f + 0x18, r.randrange(-32767, 32768))
    put32(raw, 0xF8, r.randrange(0x1000))
    return compact.CompactVoice.from_arm(raw)


def write_data(path: Path, voice: compact.CompactVoice, low: int, high: int,
               packed_waves, packed_env1, packed_env2) -> None:
    x = [0] * 81
    x[64] = 0xFFFF                    # single curve-aware cache invalid key
    y = [0] * 64
    y[:compact.WORDS_PER_VOICE] = voice.words
    lr, hr = word.U32.from_int(low), word.U32.from_int(high)
    y[41:45] = [lr.lo, lr.hi, hr.lo, hr.hi]
    lines = [
        "X 200 " + " ".join(f"{v & 0xFFFFFF:06x}" for v in x),
        "Y 200 " + " ".join(f"{v & 0xFFFFFF:06x}" for v in y),
        f"Y {WAVE_Y:x} " + " ".join(f"{v:06x}" for v in packed_waves.words),
        f"Y {ENV1_Y:x} " + " ".join(f"{v:06x}" for v in packed_env1.words),
        f"Y {ENV2_Y:x} " + " ".join(f"{v:06x}" for v in packed_env2.words),
    ]
    path.write_text("\n".join(lines) + "\n")


def run_case(binary: Path, entry: int, case: int, initial: compact.CompactVoice,
             low: int, high: int, packed_waves, packed_env1, packed_env2):
    data = OUT / f"case-{case}.data"
    script = OUT / f"case-{case}.script"
    raw = OUT / f"case-{case}.raw"
    state = OUT / f"case-{case}.state"
    meter = OUT / f"case-{case}.meter"
    write_data(data, initial, low, high, packed_waves, packed_env1, packed_env2)
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
    return audio, dumped[64:128], int(meter.read_text().strip()), r.stdout.strip()


def main() -> None:
    build_host()
    binary, entry = assemble()
    raw_waves, env1, env2, packed_waves, packed_env1, packed_env2 = synthetic_tables()
    r = random.Random(0x504B4655)
    instruction_counts = []

    for case in range(36):
        initial = make_voice(r, case)
        oracle_voice = compact.CompactVoice(list(initial.words))
        low, high = r.getrandbits(32), r.getrandbits(32)
        oracle_rng = word.WordRng.from_ints(low, high)
        want = compact.render_block(
            oracle_voice, FRAMES, raw_waves, oracle_rng, env1, env2
        )

        audio, ystate, instructions, _stdout = run_case(
            binary, entry, case, initial, low, high,
            packed_waves, packed_env1, packed_env2,
        )
        expected_audio = [sample for sample in want for _channel in (0, 1)]
        if audio != expected_audio:
            at = next(i for i, (a, b) in enumerate(zip(audio, expected_audio)) if a != b)
            fail(
                f"case {case} shape {case % 3}: audio word {at}: "
                f"DSP {audio[at]} != oracle {expected_audio[at]}"
            )
        got_voice = [v & 0xFFFF for v in ystate[:compact.WORDS_PER_VOICE]]
        if got_voice != oracle_voice.words:
            at = next(i for i, (a, b) in enumerate(zip(got_voice, oracle_voice.words)) if a != b)
            fail(
                f"case {case} shape {case % 3}: compact word {at}: "
                f"DSP {got_voice[at]:04x} != oracle {oracle_voice.words[at]:04x}"
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
        "PERKY complete full-packed voice gate: OK "
        f"(36 x {FRAMES}-sample blocks; linear + both curves; "
        f"1975 Y table words; one 17-word envelope cache; {pwords} P words; "
        f"instructions/block min {min(instruction_counts)}, "
        f"mean {sum(instruction_counts)/len(instruction_counts):.1f}, "
        f"max {max(instruction_counts)})"
    )


if __name__ == "__main__":
    main()

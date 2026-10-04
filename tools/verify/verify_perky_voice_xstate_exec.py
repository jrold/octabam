#!/usr/bin/env python3
"""Execute PERKY's complete packed renderer with persistent state in X.

This is the source-seam ABI gate. It uses the same memory *shape* as shipping:
41 compact words + one 17-word cache in X, shared RNG in X, one reusable
64-word X scratch block, and all static tables in packed private Y.

The harness uses X:$0300 for the test voice and X:$0200 for scratch so its
state dumper can inspect the result; the renderer itself receives those bases
in r6/r5 exactly as the live seam will receive X:$38xx/X:$3900. The RNG remains
at its shipping absolute address X:$38e8..$38eb.
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
OUT = ROOT / "out/perky/voice-xstate"
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
SCRATCH_X = 0x0200
VOICE_X = 0x0300
RNG_X = 0x38E8
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
    "perky_voice_xstate_fab",
    ROOT / "tools/perky/fabricate_noise_tone_fixtures.py",
)


def fail(msg: str) -> None:
    raise SystemExit("verify-perky-voice-xstate-exec: " + msg)


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


PROBE = r"""
pk_voice_xstate_probe:
        move    #>$ffffff,m0
        move    #>$ffffff,m1
        move    #>$ffffff,m2
        move    #>$ffffff,m3
        move    #>$ffffff,m4
        move    #>$ffffff,m5
        move    #>$ffffff,m6
        move    #>$000200,r5
        move    #>$000300,r6
        move    #>$10,n7
        move    #$0,r0
        jsr     pk_voice_xstate

        ; Copy mutated persistent state into the harness-visible X:$0200
        ; window without changing r5. The state dumper emits X:r5 first.
        move    #>$000300,r1
        move    #>$000200,r2
        do      #$29,pkvxp_copy_done
        move    x:(r1)+,a
        move    a1,x:(r2)+
pkvxp_copy_done:
        nop
        move    x:>$38e8,a
        move    a1,x:(r2)+
        move    x:>$38e9,a
        move    a1,x:(r2)+
        move    x:>$38ea,a
        move    a1,x:(r2)+
        move    x:>$38eb,a
        move    a1,x:(r2)+
        rts
"""


def combined_source() -> str:
    pieces = [
        PROBE,
        (PERKY / "noise_tone_voice_xstate_glue.asm").read_text(),
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
    src = OUT / "voice_xstate.asm"
    binary = OUT / "voice_xstate.bin"
    symbols = OUT / "voice_xstate.sym"
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
    entry = labels.get("pk_voice_xstate_probe")
    if entry is None:
        fail("assembler emitted no pk_voice_xstate_probe symbol")

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
    raw_waves = {address: s16_blob(values) for address, values in zip(IDS, wave_values)}
    packed_waves = pack_waves(
        (address, [v & 0xFFFF for v in values])
        for address, values in zip(IDS, wave_values)
    )
    env1_values = fab.envelope_linear()
    env2_values = fab.envelope_ease()
    packed_env1 = pack_envelope(env1_values)
    packed_env2 = pack_envelope(env2_values)
    if len(packed_waves.words) != 683:
        fail("packed wave footprint drifted")
    if (packed_env1.delta_bits, packed_env2.delta_bits) != (7, 7):
        fail("synthetic envelope widths drifted")
    return (
        raw_waves, u16_blob(env1_values), u16_blob(env2_values),
        packed_waves, packed_env1, packed_env2,
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
    raw[e + 1] = case % 3
    raw[e + 4] = r.randrange(2)
    raw[e + 6] = r.randrange(2)
    raw[e + 7] = r.randrange(2)
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
    scratch = [0] * 64
    persistent = list(voice.words) + [0xFFFF] + [0] * 16
    if len(persistent) != 58:
        fail(f"persistent test voice is {len(persistent)} words, expected 58")
    lr, hr = word.U32.from_int(low), word.U32.from_int(high)
    rng = [lr.lo, lr.hi, hr.lo, hr.hi]
    lines = [
        f"X {SCRATCH_X:x} " + " ".join(f"{v:06x}" for v in scratch),
        f"X {VOICE_X:x} " + " ".join(f"{v & 0xFFFFFF:06x}" for v in persistent),
        f"X {RNG_X:x} " + " ".join(f"{v:06x}" for v in rng),
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
    return audio, dumped[:64], int(meter.read_text().strip()), r.stdout.strip()


def main() -> None:
    build_host()
    binary, entry = assemble()
    raw_waves, env1, env2, packed_waves, packed_env1, packed_env2 = synthetic_tables()
    r = random.Random(0x504B5853)
    instruction_counts = []

    for case in range(36):
        initial = make_voice(r, case)
        oracle_voice = compact.CompactVoice(list(initial.words))
        low, high = r.getrandbits(32), r.getrandbits(32)
        oracle_rng = word.WordRng.from_ints(low, high)
        want = compact.render_block(oracle_voice, FRAMES, raw_waves, oracle_rng, env1, env2)

        audio, xstate, instructions, _stdout = run_case(
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
        got_voice = [v & 0xFFFF for v in xstate[:compact.WORDS_PER_VOICE]]
        if got_voice != oracle_voice.words:
            at = next(i for i, (a, b) in enumerate(zip(got_voice, oracle_voice.words)) if a != b)
            fail(
                f"case {case}: compact word {at}: DSP {got_voice[at]:04x} "
                f"!= oracle {oracle_voice.words[at]:04x}"
            )
        got_rng = [v & 0xFFFF for v in xstate[41:45]]
        expected_rng = [
            oracle_rng.low.lo, oracle_rng.low.hi,
            oracle_rng.high.lo, oracle_rng.high.hi,
        ]
        if got_rng != expected_rng:
            fail(f"case {case}: RNG {got_rng} != oracle {expected_rng}")
        instruction_counts.append(instructions)

    pwords = binary.stat().st_size // 3
    print(
        "PERKY shipping X-state voice gate: OK "
        f"(36 x {FRAMES}-sample blocks; 58-word voice + 64-word shared scratch; "
        f"full packed Y; {pwords} P words; probe instructions/block min "
        f"{min(instruction_counts)}, mean {sum(instruction_counts)/len(instruction_counts):.1f}, "
        f"max {max(instruction_counts)})"
    )


if __name__ == "__main__":
    main()

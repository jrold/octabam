#!/usr/bin/env python3
"""Execute the complete synthetic PERKY control -> Noise/Tone audio path.

This is the last pre-hardware sound gate.  It assembles the SAME generated
synthetic synth source used by ``build_machine_canary.py``, then enters it
through a tiny test wrapper which mirrors the live seam's control mapping and
sample-accurate one-sample trigger policy:

    12 PK/Y1 control words -> pk_synth_apply_controls
    -> 58-word persistent voice -> pk_voice_xstate -> stereo source PCM

The test deliberately does not model stock AMP/FX; those remain downstream of
the already-qualified source seam.  What it proves here is that the firmware's
actual generated synth source makes non-zero audio, every published control can
change the rendered result, an untriggered mid-voice parameter change is heard,
and the shared RNG/cache continue to evolve without spilling beyond the voice.

The mapping is still explicitly SYNTHETIC DEVELOPMENT behavior, not a claim of
PĒRKONS control-law equivalence.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import re
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
PERKY = ROOT / "modules/perky"
VENDOR = ROOT / "vendor/dsp56300"
OUT = ROOT / "out/perky/controlled-voice"
ASM = VENDOR / "build/source/dsp_host/dsp_asm"
DIS = VENDOR / "build/source/disassemble/dsp56kDisassemble"
HOST = OUT / "bd909_host"
HOST_SRC = ROOT / "tools/harness/bd909_host/bd909_host.cpp"
ORG = 0x5000
FRAMES = 16
VOICE_X = 0x0200
SCRATCH_X = 0x0300
EVENT_X = 0x0364
RNG_X = 0x38E8
TABLE_Y = 0x07a5
CYCLE_METER = False
LINE = re.compile(
    r"^([0-9a-f]{6}): (\S+)(?:\s+(.*?))?\s*; [0-9a-f]{6}(?: [0-9a-f]{6})?$"
)


def fail(message: str) -> "NoReturn":
    raise SystemExit("verify-perky-controlled-voice-exec: " + message)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        fail(f"cannot import {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


fabricate = load_module(
    "perky_controlled_voice_fabricate",
    ROOT / "tools/perky/fabricate_noise_tone_fixtures.py",
)
payload_builder = load_module(
    "perky_controlled_voice_payload",
    ROOT / "tools/perky/build_noise_tone_payload.py",
)
source_builder = load_module(
    "perky_controlled_voice_source",
    ROOT / "tools/perky/build_noise_tone_synth_source.py",
)


WRAPPER = r"""
; Harness entry for the generated synth source. The host writes twelve panel
; values at X:$100..$10b and the event offset at X:$10c. Pointing r4 at $f8
; makes those values appear exactly as PK/Y1 record words 8..19.
pk_controlled_voice_exec:
        move    #>$0000f8,r4
        move    #>$000200,r6
        jsr     pk_synth_apply_controls

        move    #>$000300,r5
        move    #>$ffffff,m0
        move    #>$ffffff,m1
        move    #>$ffffff,m2
        move    #>$ffffff,m3
        move    #>$ffffff,m4
        move    #>$ffffff,m5
        move    #>$ffffff,m6
        move    #$0,r0

        ; Default to no trigger. A valid 0..15 event is reproduced exactly as
        ; the live seam: prefix, one triggered sample, suffix.
        clr     a
        move    a1,x:(r6+$5)
        move    x:>$00010c,a
        cmp     #>$ffffff,a
        beq     pkcve_full
        tst     a
        blt     pkcve_full
        cmp     #>$10,a
        bge     pkcve_full
        move    a1,x:>$000364
        tst     a
        beq     pkcve_trigger
        move    a1,n7
        jsr     pk_voice_xstate

pkcve_trigger:
        move    #>$1,a
        move    a1,x:(r6+$5)
        move    #>$1,n7
        jsr     pk_voice_xstate
        clr     a
        move    a1,x:(r6+$5)

        move    #>$f,a
        move    x:>$000364,x0
        sub     x0,a
        tst     a
        beq     pkcve_finish
        move    a1,n7
        jsr     pk_voice_xstate
        bra     pkcve_finish

pkcve_full:
        move    #>$10,n7
        jsr     pk_voice_xstate

pkcve_finish:
        ; Expose the fixed-address shared RNG in otherwise-unused harness words
        ; immediately after the 58-word voice. The shipping renderer itself
        ; never writes these four relative words.
        move    x:>$38e8,a
        move    a1,x:(r6+$3a)
        move    x:>$38e9,a
        move    a1,x:(r6+$3b)
        move    x:>$38ea,a
        move    a1,x:(r6+$3c)
        move    x:>$38eb,a
        move    a1,x:(r6+$3d)
        rts
"""


def decoded(text: str):
    return {
        int(m.group(1), 16): (m.group(2), (m.group(3) or "").strip())
        for m in map(LINE.match, text.splitlines())
        if m
    }


def build_host() -> None:
    libs = [
        VENDOR / "build/source/dsp56kEmu/libdsp56kEmu.a",
        VENDOR / "build/source/dsp56kBase/libdsp56kBase.a",
        VENDOR / "build/source/asmjit/libasmjit.a",
    ]
    missing = [p for p in (ASM, DIS, *libs) if not p.exists()]
    if missing:
        fail("run `make setup` first; missing " + ", ".join(map(str, missing)))
    OUT.mkdir(parents=True, exist_ok=True)
    if HOST.exists() and HOST.stat().st_mtime > HOST_SRC.stat().st_mtime:
        return
    subprocess.run(
        [
            "c++", "-O3", "-DNDEBUG", "-std=gnu++17", "-DASMJIT_STATIC",
            "-DDSP56300_DEBUGGER=0", f"-I{VENDOR}/source",
            f"-I{VENDOR}/source/asmjit/src", str(HOST_SRC),
            str(libs[0]), str(libs[1]), str(libs[2]), "-lpthread",
            "-o", str(HOST),
        ],
        check=True,
        capture_output=True,
    )


def words(path: Path) -> list[int]:
    return [int(line.strip(), 16) & 0xFFFFFF for line in path.read_text().splitlines() if line.strip()]


def build_source_and_assets() -> tuple[str, list[int], list[int]]:
    raw = OUT / "synthetic-source"
    packed = OUT / "packed"
    raw.mkdir(parents=True, exist_ok=True)
    fabricate.emit_tables(raw)
    layout = payload_builder.build(raw, packed)
    if layout.get("synthetic") is not True:
        fail("controlled-voice fixture lost synthetic provenance")
    if layout.get("total_words") != 1975:
        fail(f"packed Y payload is {layout.get('total_words')} words, expected 1975")
    xi = layout.get("x_init", {})
    if xi.get("words") != 236 or xi.get("base_word") != 0x3800:
        fail(f"packed X initializer geometry drifted: {xi!r}")

    state = words(packed / "state_init.words")
    tables = words(packed / "tables.words")
    if len(state) != 236 or len(tables) != 1975:
        fail(f"asset word counts drifted: X={len(state)} Y={len(tables)}")

    source = source_builder.generate(packed / "layout.json")
    if source.count("pk_synth_apply_controls:") != 1:
        fail("generated synth source does not contain exactly one control mapper")
    if source.count("pk_voice_xstate:") != 1:
        fail("generated synth source does not contain exactly one complete voice")
    if source.count("@CONT@") != 1:
        fail("generated source continuation marker count drifted")
    # The live seam is not entered by this harness, but the whole generated
    # image still has to assemble, so resolve its payload-A continuation.
    source = source.replace("@CONT@", "$000426")
    return source_builder.force_long_local_jsr(WRAPPER) + "\n" + source, state, tables


def assemble(source_text: str) -> tuple[Path, int]:
    OUT.mkdir(parents=True, exist_ok=True)
    src = OUT / "controlled_voice.asm"
    binary = OUT / "controlled_voice.bin"
    symbols = OUT / "controlled_voice.sym"
    src.write_text(source_text)
    r = subprocess.run(
        [
            str(ASM), "-in", str(src), "-org", f"{ORG:x}",
            "-out", str(binary), "-list", "-sym", str(symbols),
        ],
        capture_output=True,
        text=True,
    )
    if r.returncode:
        fail("assembler failed:\n" + r.stdout[-6000:] + r.stderr[-3000:])
    labels = {
        q[0]: int(q[1], 16)
        for q in (line.split() for line in symbols.read_text().splitlines())
        if len(q) == 2
    }
    entry = labels.get("pk_controlled_voice_exec")
    if entry is None:
        fail("assembler emitted no pk_controlled_voice_exec symbol")

    d = subprocess.run(
        [str(DIS), "-in", str(binary), "-pc", f"{ORG:x}", "-le"],
        capture_output=True,
        text=True,
        check=True,
    )
    typed, actual = decoded(r.stdout), decoded(d.stdout)
    if not typed or len(actual) < len(typed) * 0.9:
        fail("no usable disassembly to compare")
    encoded = binary.read_bytes()
    for address, (mnemonic, operands) in typed.items():
        if mnemonic == "nop" and address not in actual:
            offset = (address - ORG) * 3
            if encoded[offset:offset + 3] == bytes(3):
                continue
        dm, dops = actual.get(address, ("?", ""))
        if dm != mnemonic:
            fail(
                f"P:{address:06x} typed {mnemonic} {operands} "
                f"but decodes {dm} {dops}"
            )
    return binary, entry


def knob_row(*, tune: int = 64, decay: int = 64, env: int = 64,
             mix: int = 64, mode: int = 0, junk: int = 0) -> tuple[int, ...]:
    row = [junk & 0x7F] * 12
    row[0] = tune & 0x7F
    row[1] = decay & 0x7F
    row[2] = env & 0x7F
    row[3] = mix & 0x7F
    row[6] = mode & 0x7F
    return tuple(row)


def write_data(path: Path, state_init: list[int], table_words: list[int]) -> list[int]:
    voice = list(state_init[:58])
    if len(voice) != 58:
        fail("state initializer does not contain one complete 58-word voice")
    rng = list(state_init[-4:])
    if len(rng) != 4:
        fail("state initializer does not contain four RNG limbs")
    visible = voice + [0] * 6
    path.write_text(
        f"X {VOICE_X:x} " + " ".join(f"{v:06x}" for v in visible) + "\n"
        + f"X {SCRATCH_X:x} " + " ".join(["000000"] * 100) + "\n"
        + f"X {EVENT_X:x} 000000\n"
        + f"X {RNG_X:x} " + " ".join(f"{v:06x}" for v in rng) + "\n"
        + f"Y {TABLE_Y:x} " + " ".join(f"{v:06x}" for v in table_words) + "\n"
    )
    return rng


def run(binary: Path, entry: int, tag: str, state_init: list[int], table_words: list[int],
        blocks: list[tuple[tuple[int, ...], int]]) -> tuple[list[list[int]], list[list[int]], list[int]]:
    data = OUT / f"{tag}.data"
    script = OUT / f"{tag}.script"
    raw = OUT / f"{tag}.raw"
    state = OUT / f"{tag}.state"
    meter = OUT / f"{tag}.meter"
    initial_rng = write_data(data, state_init, table_words)
    script.write_text(
        "\n".join(
            " ".join(str(v) for v in (*knobs, trig))
            for knobs, trig in blocks
        ) + "\n"
    )
    r = subprocess.run(
        [
            str(HOST), "-code", str(binary), "-org", f"{ORG:x}",
            "-entry", f"{entry:x}", "-data", str(data), "-script", str(script),
            "-out", str(raw), "-state", str(state), "-meter", str(meter),
            "-cycle-meter", "1" if CYCLE_METER else "0",
            "-frames", str(FRAMES),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    ints = list(struct.unpack(f"<{raw.stat().st_size // 4}i", raw.read_bytes()))
    if len(ints) != len(blocks) * FRAMES * 2:
        fail(f"{tag}: audio has {len(ints)} words for {len(blocks)} blocks")
    audio: list[list[int]] = []
    for b in range(len(blocks)):
        chunk = ints[b * FRAMES * 2:(b + 1) * FRAMES * 2]
        left, right = chunk[0::2], chunk[1::2]
        if left != right:
            fail(f"{tag}: block {b} source renderer is not mono-equal stereo")
        audio.append(left)

    state_rows: list[list[int]] = []
    for line in state.read_text().splitlines():
        row = [int(x, 16) & 0xFFFFFF for x in line.split()]
        if len(row) != 128:
            fail(f"{tag}: state row has {len(row)} words, expected 128")
        state_rows.append(row[:64])
    if len(state_rows) != len(blocks):
        fail(f"{tag}: {len(state_rows)} state rows for {len(blocks)} blocks")

    meters = [int(x) for x in meter.read_text().split()]
    if len(meters) != len(blocks):
        fail(f"{tag}: {len(meters)} meter rows for {len(blocks)} blocks")
    return audio, state_rows, initial_rng


def flatten(blocks: list[list[int]]) -> list[int]:
    return [sample for block in blocks for sample in block]


def energy(blocks: list[list[int]]) -> int:
    return sum(abs(v) for v in flatten(blocks))


def require_audible(tag: str, block: list[int]) -> None:
    nonzero = [v for v in block if v != 0]
    if len(nonzero) < 8:
        fail(f"{tag}: only {len(nonzero)}/{len(block)} non-zero samples")
    if len(set(block)) < 5:
        fail(f"{tag}: only {len(set(block))} distinct sample values")


def require_different(tag: str, a: list[list[int]], b: list[list[int]]) -> None:
    if flatten(a) == flatten(b):
        fail(f"{tag}: control change produced bit-identical PCM")


def u32(row: list[int], off: int) -> int:
    return (row[off] & 0xFFFF) | ((row[off + 1] & 0xFFFF) << 16)


def main() -> None:
    build_host()
    source, state_init, tables = build_source_and_assets()
    binary, entry = assemble(source)

    baseline = knob_row()
    base_audio, base_state, initial_rng = run(
        binary, entry, "baseline", state_init, tables, [(baseline, 0)]
    )
    require_audible("baseline triggered block", base_audio[0])
    if base_state[0][41] != 0xFFFF:
        fail("analytic synthetic curve unexpectedly modified the packed cache")
    curved_init = list(state_init)
    curved_init[2] = 2
    _, curved_states, _ = run(binary, entry, "packed-curve-cache", curved_init, tables, [(baseline, 0)])
    if curved_states[0][41] == 0xFFFF:
        fail("packed curve2 render left its envelope cache invalid")
    final_rng = base_state[0][58:62]
    if final_rng == initial_rng:
        fail("baseline render did not advance shared RNG")
    if base_state[0][62:64] != [0, 0]:
        fail("complete voice wrote beyond its 58-word allocation")

    # Immediate controls: same initial state + same trigger, one axis changed.
    immediate = (
        ("TUNE", knob_row(tune=0), knob_row(tune=127)),
        ("MIX", knob_row(mix=0), knob_row(mix=127)),
        ("MODE", knob_row(mode=0), knob_row(mode=2)),
    )
    for name, lo, hi in immediate:
        alo, _slo, _ = run(binary, entry, f"{name.lower()}-lo", state_init, tables, [(lo, 0)])
        ahi, _shi, _ = run(binary, entry, f"{name.lower()}-hi", state_init, tables, [(hi, 0)])
        require_different(name, alo, ahi)

    # ENV/DECAY can express themselves over the envelope trajectory rather
    # than necessarily in sample zero, so compare several blocks from the same
    # fresh trigger.
    for name, lo, hi in (
        ("ENV", knob_row(env=0), knob_row(env=127)),
        ("DECAY", knob_row(decay=0), knob_row(decay=127)),
    ):
        low_script = [(lo, 0)] + [(lo, -1)] * 31
        high_script = [(hi, 0)] + [(hi, -1)] * 31
        alo, slo, _ = run(binary, entry, f"{name.lower()}-lo-tail", state_init, tables, low_script)
        ahi, shi, _ = run(binary, entry, f"{name.lower()}-hi-tail", state_init, tables, high_script)
        require_different(name + " trajectory", alo, ahi)
        if name == "DECAY":
            # Larger DECAY knob maps to a smaller decrement, so after the same
            # 32 blocks its envelope value must not be lower than the short
            # setting. This checks the intended temporary mapping direction.
            short_value = u32(slo[-1], 6)
            long_value = u32(shi[-1], 6)
            if long_value < short_value:
                fail(
                    f"DECAY tail direction reversed: long={long_value:08x} "
                    f"short={short_value:08x}"
                )

    # Elektron-style live change: two runs are identical through block 2. On
    # block 3 one run keeps the sound fixed while the other changes TUNE/MIX/
    # MODE without retriggering. The histories must match before the change and
    # diverge exactly when the new control record arrives.
    fixed_script = [(baseline, 0), (baseline, -1), (baseline, -1)]
    changed = knob_row(tune=100, mix=104, mode=2)
    changed_script = [(baseline, 0), (baseline, -1), (changed, -1)]
    af, _sf, _ = run(binary, entry, "live-fixed", state_init, tables, fixed_script)
    ac, _sc, _ = run(binary, entry, "live-changed", state_init, tables, changed_script)
    if af[:2] != ac[:2]:
        fail("live-change control runs diverged before the parameter change")
    if af[2] == ac[2]:
        fail("untriggered live control change did not alter the sounding voice")

    all_audio = [base_audio]
    print(
        "PERKY controlled complete voice executable gate: PASS "
        f"(audible baseline energy={energy(base_audio):,}; "
        "TUNE/MIX/MODE immediate PCM changes; ENV/DECAY trajectory changes; "
        "untriggered live change audible; cache/RNG/allocation checks passed)"
    )


if __name__ == "__main__":
    main()

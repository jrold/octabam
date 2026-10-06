#!/usr/bin/env python3
"""Execute PERKY's synthetic five-control DSP mapper against a Python oracle.

This is the executable companion to ``verify_perky_control_mapper.py``.  The
host's twelve scripted knob values land at X:$100..$10b; the tiny wrapper points
r4 at X:$0f8 so those values are seen by ``pk_synth_apply_controls`` exactly as
PK/Y1 record words 8..19, and points r6 at X:$200, the host's dumped state
block.

The mapper is a DEVELOPMENT-CANARY control law, not a claim of PĒRKONS sonic
identity.  This gate proves only that the DSP56300 implementation performs that
explicit temporary mapping exactly and does not clobber unrelated compact
voice words.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
PERKY = ROOT / "modules/perky"
V = ROOT / "vendor/dsp56300"
OUT = ROOT / "out/perky/control-mapper"
ASM = V / "build/source/dsp_host/dsp_asm"
DIS = V / "build/source/disassemble/dsp56kDisassemble"
HOST = OUT / "bd909_host"
HOST_SRC = ROOT / "tools/harness/bd909_host/bd909_host.cpp"
ORG = 0x2800
STATE = 0x200
LINE = re.compile(
    r"^([0-9a-f]{6}): (\S+)(?:\s+(.*?))?\s*; [0-9a-f]{6}(?: [0-9a-f]{6})?$"
)


def fail(msg: str) -> None:
    raise SystemExit("verify-perky-control-mapper-exec: " + msg)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        fail(f"cannot import {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


fab = load_module(
    "perky_control_mapper_fab",
    ROOT / "tools/perky/fabricate_noise_tone_fixtures.py",
)
IDS = tuple(int(x) & 0xFFFFFFFF for x in fab.WAVE_ADDRESSES)
if len(IDS) != 4 or len(set(IDS)) != 4:
    fail(f"synthetic fixture exposes invalid wave identities {IDS!r}")


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


def source_text() -> str:
    body = (PERKY / "synthetic_control_map.asm").read_text()
    for i, address in enumerate(IDS):
        body = body.replace(f"@W{i}L@", f"${address & 0xFFFF:04x}")
        body = body.replace(f"@W{i}H@", f"${(address >> 16) & 0xFFFF:04x}")
    if "@W" in body:
        fail("wave identity substitution left an unresolved marker")
    wrapper = """; executable test wrapper\npk_control_mapper_exec:\n        move    #>$0000f8,r4\n        move    #>$000200,r6\n        jsr     >pk_synth_apply_controls\n        rts\n\n"""
    return wrapper + body


def assemble():
    OUT.mkdir(parents=True, exist_ok=True)
    source = OUT / "control_mapper.asm"
    binary = OUT / "control_mapper.bin"
    symbols = OUT / "control_mapper.sym"
    source.write_text(source_text())
    r = subprocess.run(
        [
            str(ASM), "-in", str(source), "-org", f"{ORG:x}",
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
    entry = labels.get("pk_control_mapper_exec")
    mapper = labels.get("pk_synth_apply_controls")
    if entry is None or mapper is None:
        fail(f"missing symbols: entry={entry!r} mapper={mapper!r}")

    d = subprocess.run(
        [str(DIS), "-in", str(binary), "-pc", f"{ORG:x}", "-le"],
        capture_output=True,
        text=True,
        check=True,
    )
    typed, actual = decoded(r.stdout), decoded(d.stdout)
    if not typed or len(actual) < len(typed) * .9:
        fail("no usable disassembly to compare")
    for addr, (mnemonic, operands) in typed.items():
        dm, dops = actual.get(addr, ("?", ""))
        if dm != mnemonic:
            fail(
                f"P:{addr:06x} typed {mnemonic} {operands} "
                f"but decodes {dm} {dops}"
            )
    return binary, entry


def sentinel_state() -> list[int]:
    return [(0x005000 + i) & 0xFFFFFF for i in range(64)]


OWNED = {
    10, 11,
    25, 26, 27, 28, 29, 30,
    33, 34, 35, 36, 37, 38,
    39, 40,
}


def oracle(knobs: tuple[int, ...], before: list[int]) -> list[int]:
    if len(knobs) != 12:
        raise AssertionError(len(knobs))
    out = list(before)
    tune, decay, env, mix, mode = (
        knobs[0] & 0x7F,
        knobs[1] & 0x7F,
        knobs[2] & 0x7F,
        knobs[3] & 0x7F,
        knobs[6] & 0xFF,
    )
    out[25] = 0x1000 + (tune << 8)
    out[26] = 0
    out[33] = 0x0C00 + (tune << 7)
    out[34] = 0
    out[11] = 0x0200 + ((0x7F - decay) << 5)
    out[10] = 0x0800 + (env << 7)
    out[39] = mix << 5
    out[40] = 0

    m = 0 if mode == 0 else 1 if mode == 1 else 2
    a, b = ((0, 1), (1, 2), (2, 3))[m]
    for base, identity in ((27, IDS[a]), (29, IDS[a]), (35, IDS[b]), (37, IDS[b])):
        out[base] = identity & 0xFFFF
        out[base + 1] = (identity >> 16) & 0xFFFF
    return out


def run(binary: Path, entry: int, cases: list[tuple[int, ...]]) -> list[list[int]]:
    before = sentinel_state()
    data = OUT / "mapper.data"
    script = OUT / "mapper.script"
    raw = OUT / "mapper.raw"
    state_path = OUT / "mapper.state"
    data.write_text(
        f"X {STATE:x} " + " ".join(f"{x:06x}" for x in before) + "\n"
    )
    script.write_text(
        "\n".join(" ".join(str(x) for x in (*case, -1)) for case in cases) + "\n"
    )
    subprocess.run(
        [
            str(HOST), "-code", str(binary), "-org", f"{ORG:x}",
            "-entry", f"{entry:x}", "-data", str(data), "-script", str(script),
            "-out", str(raw), "-state", str(state_path), "-frames", "1",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    rows = []
    for line in state_path.read_text().splitlines():
        words = [int(x, 16) & 0xFFFFFF for x in line.split()]
        if len(words) < 64:
            fail(f"truncated state row: {len(words)} words")
        rows.append(words[:64])
    if len(rows) != len(cases):
        fail(f"host emitted {len(rows)} state rows for {len(cases)} cases")
    return rows


def main() -> None:
    build_host()
    binary, entry = assemble()

    cases = [
        (0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
        (127, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
        (64, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
        (0, 127, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
        (0, 64, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
        (0, 0, 127, 0, 0, 0, 0, 0, 0, 0, 0, 0),
        (0, 0, 64, 0, 0, 0, 0, 0, 0, 0, 0, 0),
        (0, 0, 0, 127, 0, 0, 0, 0, 0, 0, 0, 0),
        (0, 0, 0, 64, 0, 0, 0, 0, 0, 0, 0, 0),
        (31, 47, 59, 71, 83, 97, 0, 109, 113, 17, 23, 29),
        (31, 47, 59, 71, 83, 97, 1, 109, 113, 17, 23, 29),
        (31, 47, 59, 71, 83, 97, 2, 109, 113, 17, 23, 29),
        (127, 127, 127, 127, 127, 127, 2, 127, 127, 127, 127, 127),
    ]

    got_rows = run(binary, entry, cases)
    before = sentinel_state()
    checks = 0
    for i, (case, got) in enumerate(zip(cases, got_rows)):
        want = oracle(case, before)
        for word, (g, w) in enumerate(zip(got, want)):
            if g != w:
                owner = "owned" if word in OWNED else "UNOWNED"
                fail(
                    f"case {i} X:{STATE + word:04x} word {word} ({owner}): "
                    f"got {g:06x}, want {w:06x}; knobs={case!r}"
                )
            checks += 1

    print(
        "PERKY synthetic five-control mapper executable gate: OK "
        f"({len(cases)} cases, {checks} exact state-word checks, "
        "unowned compact voice words preserved)"
    )


if __name__ == "__main__":
    main()

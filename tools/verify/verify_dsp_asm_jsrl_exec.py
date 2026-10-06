#!/usr/bin/env python3
"""Execute one DSP56300 long JSR through Octabam's ``jsrl`` pseudo-op.

This isolates the assembler-wrapper extension from PERKY's synthesis/control
code. If this gate passes, a two-word long call emitted above P:$0fff reaches
its target, returns to its caller, and preserves the host's outer return.
"""
from __future__ import annotations

from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
V = ROOT / "vendor/dsp56300"
OUT = ROOT / "out/perky/jsrl-smoke"
ASM = V / "build/source/dsp_host/dsp_asm"
HOST = OUT / "bd909_host"
HOST_SRC = ROOT / "tools/harness/bd909_host/bd909_host.cpp"
ORG = 0x2800
STATE = 0x0200


def fail(msg: str) -> None:
    raise SystemExit("verify-dsp-asm-jsrl-exec: " + msg)


def build_host() -> None:
    libs = [
        V / "build/source/dsp56kEmu/libdsp56kEmu.a",
        V / "build/source/dsp56kBase/libdsp56kBase.a",
        V / "build/source/asmjit/libasmjit.a",
    ]
    missing = [p for p in [ASM, *libs] if not p.exists()]
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


def main() -> None:
    build_host()
    OUT.mkdir(parents=True, exist_ok=True)
    src = OUT / "jsrl_smoke.asm"
    binary = OUT / "jsrl_smoke.bin"
    symbols = OUT / "jsrl_smoke.sym"
    data = OUT / "jsrl_smoke.data"
    script = OUT / "jsrl_smoke.script"
    raw = OUT / "jsrl_smoke.raw"
    state = OUT / "jsrl_smoke.state"

    src.write_text(
        """pk_jsrl_exec:\n"
        "        jsrl    pk_jsrl_callee\n"
        "        rts\n"
        "\n"
        "pk_jsrl_callee:\n"
        "        move    #>$001234,a\n"
        "        move    a1,x:(r5+$0)\n"
        "        rts\n"
    )
    r = subprocess.run(
        [
            str(ASM), "-in", str(src), "-org", f"{ORG:x}",
            "-out", str(binary), "-list", "-sym", str(symbols),
        ],
        capture_output=True,
        text=True,
    )
    if r.returncode:
        fail("assembler failed:\n" + r.stdout[-3000:] + r.stderr[-2000:])

    labels = {
        p[0]: int(p[1], 16)
        for p in (line.split() for line in symbols.read_text().splitlines())
        if len(p) == 2
    }
    entry = labels.get("pk_jsrl_exec")
    callee = labels.get("pk_jsrl_callee")
    if entry is None or callee is None:
        fail(f"missing symbols: entry={entry!r} callee={callee!r}")
    if entry < 0x1000 or callee < 0x1000:
        fail(f"gate no longer exercises long-address calls: entry={entry:06x} callee={callee:06x}")

    before = [0x005000 + i for i in range(64)]
    data.write_text(f"X {STATE:x} " + " ".join(f"{v:06x}" for v in before) + "\n")
    script.write_text(" ".join(["0"] * 12 + ["-1"]) + "\n")
    rr = subprocess.run(
        [
            str(HOST), "-code", str(binary), "-org", f"{ORG:x}",
            "-entry", f"{entry:x}", "-data", str(data), "-script", str(script),
            "-out", str(raw), "-state", str(state), "-frames", "1",
        ],
        capture_output=True,
        text=True,
    )
    if rr.returncode:
        fail("host execution failed:\n" + rr.stdout[-2000:] + rr.stderr[-2000:])

    rows = state.read_text().splitlines()
    if len(rows) != 1:
        fail(f"host emitted {len(rows)} state rows, expected 1")
    words = [int(x, 16) & 0xFFFFFF for x in rows[0].split()[:64]]
    if len(words) != 64:
        fail(f"state dump has {len(words)} X words, expected 64")
    if words[0] != 0x001234:
        fail(
            f"callee did not write marker through long call: X:{STATE:04x}="
            f"{words[0]:06x}, expected 001234"
        )
    if words[1:] != before[1:]:
        at = next(i for i, (a, b) in enumerate(zip(words[1:], before[1:]), 1) if a != b)
        fail(f"long-call smoke clobbered X:{STATE + at:04x}: {words[at]:06x} != {before[at]:06x}")

    print(
        "DSP assembler jsrl executable gate: PASS "
        f"(P:{entry:04x} -> P:{callee:04x} -> return; marker 001234 observed)"
    )


if __name__ == "__main__":
    main()

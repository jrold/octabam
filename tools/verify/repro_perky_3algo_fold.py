#!/usr/bin/env python3
"""Minimal, self-contained reproducer for the composed Fold silence.

This deliberately does NOT use the composed gate. It builds the two sources
with a byte-identical probe body and the fixture the standalone gate uses, so
the two runs differ in exactly one thing: the source under test.

    standalone source  ->  -1, -2, -4, -6, -9, -13   (correct)
    composed source    ->   0,  0,  0,  0,  0,   0   (silent)

The single most important detail is the cache-invalidate line the standalone
gate writes:

    X 3964 ffffff

`pk_simple_base` names its second-difference cache by ABSOLUTE address
(r4 = 0x3964) and `pk_simple_delta_at` reads it through r4; seeding the
sentinel forces a block decode. Without that line BOTH sources render zeros,
which is how this was mistaken for a harness difference for several rounds.

Run with no arguments; exits non-zero if the composed source is not silent
(which would mean the defect has been fixed and this diagnostic should be
retired) or if the standalone reference is not correct.
"""
from __future__ import annotations

import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tools/perky"),
                str(ROOT / "modules/perky")]

import build_dsp_3algo_source as composed  # noqa:E402
import fold_drum_compact as fold  # noqa:E402
import simple_drum_tables as tables  # noqa:E402
from build_noise_tone_synth_source import (  # noqa:E402
    force_long_local_jsr, relativize_local_conditionals)

OUT = ROOT / "out/perky/dsp-3algo"
ASSETS = ROOT / "out/perky/simple-drum-assets"
HOST = OUT / "bd909_host"
PERKY = composed.PERKY
CASE = ROOT / "out/perky/engine-fixtures/engine-1-mode-1-corner-0"
FRAMES = 256
D = "$"

# EXACTLY the standalone gate's probe body (the `jsr` form; the composed probe
# substitutes the long form, because the composition sits above the short-jsr
# range).
PROBE = (
    f"pk_fold_probe:\n"
    f" move #>{D}200,r6\n"
    f" move #>{D}3900,r5\n"
    f" jsr pk_simple_base\n"
    f" jsr pk_fold_voice\n"
    f" move x:>{D}38e8,a\n move a1,x:>{D}240\n"
    f" move x:>{D}38e9,a\n move a1,x:>{D}241\n"
    f" move x:>{D}38ea,a\n move a1,x:>{D}242\n"
    f" move x:>{D}38eb,a\n move a1,x:>{D}243\n"
    f" rts\n")


def die(message: str) -> "NoReturn":
    raise SystemExit("repro-perky-3algo-fold: " + message)


def standalone_source() -> str:
    """The exact source `verify_perky_fold_drum_exec.py` assembles."""
    parts = [(PERKY / "fold_drum_voice.asm").read_text()]
    for name, label in (("envelope", "pk_simple_envelope"),
                        ("frequency", "pk_simple_frequency"),
                        ("oscillator", "pk_simple_oscillator")):
        text = (PERKY / f"simple_drum_{name}.asm").read_text()
        text = text[text.index("\n" + label + ":"):]
        text = text.replace("#>$0009a5,r1", "#>$000c50,r1")
        text = text.replace("#>$0007a5,r1", "#>$000a50,r1")
        parts.append(text)
    parts.append((PERKY / "simple_drum_delta.asm").read_text())
    parts.append("\npknv_noise:"
                 + (PERKY / "noise_tone_voice_native_xstate.asm")
                 .read_text().split("\npknv_noise:", 1)[1])
    parts.append((PERKY / "noise_tone_math.asm").read_text())
    return force_long_local_jsr(relativize_local_conditionals(
        PROBE + "\n" + "\n".join(parts)))


def fixture() -> tuple[list[int], str, list[int]]:
    state = fold.FoldDrum1.from_arm(
        (CASE / "wrapper-window-before.bin").read_bytes()[0xc4:0xc4 + 0xf4]).words
    waves = tables.pack_u16(
        v for name in ("wave_080222a0.bin", "wave_080226a0.bin",
                       "wave_080228a0.bin")
        for v in struct.unpack("<256H", (ASSETS / name).read_bytes()))
    env = tables.pack_u16(
        struct.unpack("<2048H", (ASSETS / "envelope1.bin").read_bytes())[:1024])
    pitch = tables.pack_pitch_basis(
        struct.unpack("<4096H", (ASSETS / "pitch.bin").read_bytes())).words
    lines = (
        "X 200 " + " ".join(f"{v:06x}" for v in state) + "\n"
        + "Y a50 " + " ".join(f"{v:06x}" for v in waves) + "\n"
        + "Y c50 " + " ".join(f"{v:06x}" for v in env) + "\n"
        + "Y efb " + " ".join(f"{v:06x}" for v in pitch) + " 000000\n"
        # THE LINE THAT MATTERS. Without it both sources render silence.
        + "X 3964 ffffff\n"
        + "X 38e8 0 0 0 0\n")
    want = list(struct.unpack("<256h", (CASE / "arm-pcm.bin").read_bytes()))
    return state, lines, want


def run(tag: str, source: str, org: int) -> list[int]:
    asm, binary, sym = (OUT / f"repro_{tag}.{ext}"
                        for ext in ("asm", "bin", "sym"))
    asm.write_text(source)
    result = subprocess.run(
        [str(composed.ASM), "-in", str(asm), "-org", format(org, "x"),
         "-out", str(binary), "-sym", str(sym)],
        capture_output=True, text=True)
    if result.returncode:
        die(f"{tag}: dsp_asm failed:\n{result.stdout[-2000:]}")
    labels = {p[0]: int(p[1], 16)
              for p in map(str.split, sym.read_text().splitlines()) if len(p) == 2}
    _, data_lines, _ = fixture()
    data = OUT / f"repro_{tag}.data"
    data.write_text(data_lines)
    script = OUT / "repro.script"
    script.write_text(" ".join(["0"] * 12 + ["-1"]) + "\n")
    pcm = OUT / f"repro_{tag}.raw"
    result = subprocess.run(
        [str(HOST), "-code", str(binary), "-org", format(org, "x"),
         "-entry", format(labels["pk_fold_probe"], "x"), "-data", str(data),
         "-script", str(script), "-out", str(pcm),
         "-state", str(OUT / f"repro_{tag}.state"), "-state-words", "68",
         "-frames", str(FRAMES), "-meter", str(OUT / f"repro_{tag}.meter"),
         "-cycle-meter", "1"],
        capture_output=True, text=True)
    if result.returncode:
        die(f"{tag}: dsp_host failed:\n{result.stderr[-2000:]}")
    return [struct.unpack(f"<{2 * FRAMES}i", pcm.read_bytes())[i]
            for i in range(0, 12, 2)]


def main() -> None:
    _, _, want = fixture()
    print(f"fixture expectation : {want[:6]}")
    reference = run("standalone", standalone_source(), 0x2800)
    print(f"standalone source   : {reference}")
    if reference != want[:6]:
        die("the STANDALONE reference is not correct -- this diagnostic's "
            "fixture has drifted, fix it before reading anything else")
    composed_probe = (PROBE.replace("jsr pk_simple_base", "jsrl pk_simple_base")
                           .replace("jsr pk_fold_voice", "jsrl pk_fold_voice"))
    composed_out = run("composed",
                       composed_probe + "\n"
                       + composed.normalize(composed.compose())
                       .replace("@CONT@", "$000426"), 0x1000)
    print(f"composed source     : {composed_out}")
    print()
    if composed_out == want[:6]:
        die("the composed source now renders the fixture correctly -- the "
            "defect is FIXED; retire this diagnostic and remove it from the "
            "known-failing list")
    print("repro-perky-3algo-fold: REPRODUCED (standalone correct, composed "
          "silent from an identical probe and fixture)")


if __name__ == "__main__":
    main()

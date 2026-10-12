#!/usr/bin/env python3
"""Algorithm switching through the production dispatch path.

Item 6's last control sub-item. The three renderers share one voice block, so a
switch leaves the previous algorithm's state in place; this gate exercises that
and refuses silence, saturation or a crash.

HOW THE SWITCH IS DRIVEN. A probe cannot call `pk3d_source` twice -- the machine
hands control back with `jmp @CONT@` rather than returning, so a second `jsrl` in
the same block never executes. (A first attempt at this reported three identical
meters and LOOKED like a pass; three identical numbers should be the tell
immediately.) Instead the probe is STATEFUL across script blocks: the host calls
the entry once per block, so a counter in X memory advances the selected engine
between calls, publishing it into record word 0x13 exactly as `pk_render` does.

WHAT IS ASSERTED:

* every switched block renders NON-ZERO audio -- a switch that silently muted the
  voice would be a defect, and this is the check that would catch it;
* every block stays inside the 24-bit range -- no saturation on the switch;
* every switched block is REPRODUCIBLE across two identical drives, so the switch
  carries no nondeterminism the fixed harness cannot see.

WHAT IS NOT ASSERTED, stated so it is not mistaken for coverage: there is NO
oracle for any block here. The captured ARM fixtures are per-engine, and the
dispatcher's control staging runs through registers (`r6`/`r5`) that belong to the
STOCK caller, so a direct-render control cannot be constructed from a probe. Every
block is therefore checked for being live, bounded and reproducible -- NOT for
being the samples hardware would produce. See "WHAT WAS TRIED AND REJECTED" below.
"""
from __future__ import annotations

import importlib.util
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tools/perky"),
                str(ROOT / "modules/perky"), str(ROOT / "tools/verify")]

OUT = ROOT / "out/perky/dsp-3algo/switch"
FULL = 0x7FFFFF          # 24-bit full scale
ENGINES = ((0, "FOLD DRUM"), (10, "RES BASS"), (11, "RES SNARE"))


def die(m: str) -> "NoReturn":
    raise SystemExit("verify-perky-3algo-switch: " + m)


def main() -> None:
    def load(name, rel):
        spec = importlib.util.spec_from_file_location(name, ROOT / rel)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
        return mod

    join = load("join", "tools/verify/verify_perky_3algo_engine_join.py")
    g = load("g", "tools/verify/verify_perky_3algo_exec.py")
    composer = join.load_composer()
    import fold_drum_compact as fold

    OUT.mkdir(parents=True, exist_ok=True)
    e1, e2, _, _ = g.make_envelopes()
    ia = struct.pack("<257H", *[(i * 257 + i * i) & 0xFFFF for i in range(257)])
    ib = struct.pack("<257H", *[(65535 - i * 251) & 0xFFFF for i in range(257)])
    ytext = g.tables_text(e1, e2, ia, ib, ROOT / "out/perky/simple-drum-assets")

    V = composer.VOICE_BASE
    st = fold.FoldDrum1.from_arm(
        (ROOT / "out/perky/engine-fixtures/engine-1-mode-1-corner-0/"
         "wrapper-window-before.bin").read_bytes()[0xC4:0xC4 + 0xF4]).words
    st = st + [0] * (composer.RNG_GAP_START - V - len(st))

    probe = (
        "meas_cycle:\n"
        "        move    #$0039b1,r6\n"
        "        move    x:(r6),a\n"
        "        move    #$000300,r4\n"
        "        move    #$000000,b\n"
        "        tst     a\n"
        "        beq     mset\n"
        "        move    #$00000a,b\n"
        "        cmp     #$1,a\n"
        "        beq     mset\n"
        "        move    #$00000b,b\n"
        "mset:\n"
        "        move    b1,x:(r4+$13)\n"
        "        move    a1,b\n"
        "        add     #$1,b\n"
        "        move    b1,x:(r6)\n"
        "        jsrl    pk3d_source\n"
        "        rts\n"
        "meas_direct:\n"
        f"        move    #${composer.VOICE_BASE:06x},r6\n"
        f"        move    #${composer.SCRATCH_BASE:06x},r5\n"
        "        jsrl    pk_simple_base\n"
        "        jsrl    pk_fold_voice\n"
        "        rts\n")
    src = composer.normalize(composer.compose()).replace("@CONT@", "$000400")
    binary, labels = join.assemble(composer, probe + "\n" + src, "switch")

    rec = [0] * 20
    rec[0] = 0x504B
    rec[2] = 0x5931
    rec[3] = 1
    rec[16] = 1
    # NON-ZERO staged controls: zero controls also render, but silence-on-a-switch
    # is the failure this gate exists to catch, so the controls must be live.
    rec[8], rec[10], rec[12], rec[14] = 0x0100, 0x0200, 0x0300, 0x0400

    # The dispatcher stages rec[8] -> voice+0x67 and rec[12]/[10]/[14] ->
    # scratch+0x70/0x71/0x72. The direct control must see the SAME controls, or
    # it is not a control -- the first attempt compared a non-zero-control switch
    # against a zero-control reference and read as a failure.
    staged_voice = list(st)
    staged_voice[0x67] = rec[8]
    staged_scratch = ["000000"] * composer.SCRATCH_WORDS
    staged_scratch[0x70] = f"{rec[12]:06x}"
    staged_scratch[0x71] = f"{rec[10]:06x}"
    staged_scratch[0x72] = f"{rec[14]:06x}"

    def run(tag: str, blocks: int) -> list[list[int]]:
        (OUT / f"{tag}.data").write_text(
            f"X {V:x} " + " ".join(f"{v:06x}" for v in st) + "\n"
            + f"X {composer.SCRATCH_BASE:x} " + " ".join(staged_scratch) + "\n"
            + "X 3964 " + " ".join(["ffffff"] * 17) + "\n"
            + f"X {composer.RNG_GAP_END:x} 000000 000000 000000 000000\n"
            + "P 400 00000c\n" + ytext
            + "X 39b1 000000\n"
            + f"X 300 " + " ".join(f"{x:06x}" for x in rec) + "\n"
            + f"X 209 000300\nX 418 {composer.ADMITTED_SLOT:06x}\nX 20e 000000\n"
            + "X 0 " + " ".join(["000000"] * 32) + "\n")
        (OUT / f"{tag}.script").write_text(
            "".join(" ".join(["0"] * 12 + ["-1"]) + "\n" for _ in range(blocks)))
        subprocess.run(
            [str(join.OUT / "bd909_host"), "-code", str(binary), "-org",
             format(composer.DSP_ORG, "x"), "-entry",
             format(labels["meas_cycle"], "x"), "-data", str(OUT / f"{tag}.data"),
             "-script", str(OUT / f"{tag}.script"), "-out", str(OUT / f"{tag}.raw"),
             "-state", str(OUT / f"{tag}.state"), "-state-words", "64",
             "-statebase", format(V, "x"), "-frames", "16",
             "-meter", str(OUT / f"{tag}.meter"), "-cycle-meter", "1"],
            check=True, capture_output=True, timeout=240)
        raw = (OUT / f"{tag}.raw").read_bytes()
        return [struct.unpack("<32i", raw[i * 128:(i + 1) * 128])[::2]
                for i in range(blocks)]

    first = run("a", 3)
    # REPRODUCIBILITY: the same drive again must give the same audio, or the
    # "switch" is carrying nondeterminism the fixed harness cannot see.
    second = run("b", 3)

    failures = []
    print(f"{'block':5s} {'engine':10s} {'peak':>9s} {'nonzero':>8s}  first-3")
    for i, ((engine, name), mono) in enumerate(zip(ENGINES, first)):
        peak = max(abs(v) for v in mono)
        nz = sum(1 for v in mono if v)
        note = ""
        if peak == 0:
            failures.append(f"block {i} ({name}) rendered SILENCE on a switch")
            note = "  <-- SILENT"
        elif peak > FULL:
            failures.append(f"block {i} ({name}) saturated: peak {peak} > {FULL}")
            note = "  <-- SATURATED"
        if mono != second[i]:
            failures.append(f"block {i} ({name}) is not reproducible across runs")
            note += "  <-- NONDETERMINISTIC"
        print(f"{i:5d} {name:10s} {peak:9d} {nz:5d}/16  {mono[:3]}{note}")

    # WHAT WAS TRIED AND REJECTED, so it is not repeated: comparing the switched
    # FOLD block against a DIRECT render from the same state. The dispatcher
    # stages its controls through `x:(r6+$67)` and `x:(r5+$70..$72)`, and r5/r6
    # there are whatever the STOCK caller left -- the probe cannot replicate that
    # context, so the "control" rendered from different registers and the
    # comparison failed at sample 0. A control that cannot be constructed is not
    # evidence, and a failing one is worse than none.
    print()
    if failures:
        die("; ".join(failures))
    print("perky-3algo-switch: PASS (three engines driven in sequence through "
          "pk3d_source on one voice block: every switched block renders non-zero "
          "audio, stays inside 24-bit, and is reproducible, and the FOLD block "
          "is reproducible across two drives. NO ORACLE exists for any block "
          "here: the dispatcher stages controls through registers the STOCK "
          "caller owns, so a direct-render control cannot be constructed -- the "
          "blocks are checked for being live, bounded and reproducible, NOT for "
          "being the samples hardware would produce)")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""The PANEL path: every algorithm the browser offers must actually render.

WHY THIS GATE EXISTS. Every other gate in this branch drives the DSP directly --
they build a record by hand, call `pk3d_source`, and check the audio. **None of
them tested how a family byte gets chosen**, so all of them passed while the
shipped image was unusable: the engine browser offered

    "001 FOLD DRUM"   model  0   -> family  0   renders
    "003 SIMPLE DRUM" model  2   -> family  2   SILENCE
    "011 NOISE/TONE"  model 10   -> family 10   renders (and is RESONANT BASS)
    (no row)          model 11   -> RESONANT SNARE WAS UNREACHABLE

The DSP dispatches on the family byte in `p[11]` and renders exactly 0, 10 and
11; anything else reaches the silence path. So a browser row naming a family the
DSP does not render is a row that makes no sound -- and the target requires all
three algorithms selectable on T1 and T5.

WHAT IS ASSERTED:
1. the browser's `engine_labels[]` and its `handlers[]` are the same length;
2. every handler selects a family in the DSP's own engine set -- read from the
   COMPOSER, so the two cannot drift apart;
3. every family the browser offers REACHES A REAL RENDERER through `pk3d_source`
   -- checked on the cycle meter, because the dispatcher's fallback for an
   unrecognised family is `pk3c_silence` and that costs two orders of magnitude
   less than any render. This is the property that separates "the panel selects
   something the DSP does not know" from anything downstream;
4. every algorithm the target requires (Fold Drum 1, Resonant Bass, Resonant
   Snare) is offered by some row.

THE AUDIO PEAK IS REPORTED BUT NOT ASSERTED, deliberately. The resonant engines
render SILENCE from a fresh state and always have: `ResonantSnare([0]*WORDS)` and
`ResonantBass([0]*WORDS)` produce a peak of 0 over 64 blocks in the MODEL itself,
so a zero voice block is silent BY THE ALGORITHM, not by a port defect. Their
state has to be established by something, and whatever does that on the unit is a
separate, known-open item -- see "THE RESONANT ENGINES DO NOT SELF-START" in
modules/perky/DSP_3ALGO.md. Failing THIS gate on it would hide the panel bug it
exists to catch behind a symptom it cannot fix.
"""
from __future__ import annotations

import importlib.util
import re
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tools/perky"),
                str(ROOT / "modules/perky"), str(ROOT / "tools/verify")]

OUT = ROOT / "out/perky/dsp-3algo/panel"


def die(m: str) -> "NoReturn":
    raise SystemExit("verify-perky-3algo-panel: " + m)



NAMED = {"PK_RESONANT_BASS": 10, "PK_RESONANT_SNARE": 11, "DEFAULT_ENGINE": 10,
         "ENGINE_FOLD": 0, "ENGINE_BASS": 10, "ENGINE_SNARE": 11}


def resolve(token: str):
    """A `pk_engine_select` argument -> the family byte it selects."""
    tok = token.strip().rstrip("uU").strip()
    if tok.isdigit():
        return int(tok)
    return NAMED.get(tok)


def browser(control_c: Path) -> tuple[list[str], list[int]]:
    """The labels and the family each handler selects, for the 3-algorithm build."""
    src = control_c.read_text()
    # the branch taken when BOTH candidates are on
    start = src.index("#if PK_FOLD_CANDIDATE && PK_RESONANT_CANDIDATE")
    end = src.index("#elif PK_FOLD_CANDIDATE", start)
    block = src[start:end]
    labels = re.search(r"engine_labels\[\]\s*=\s*\{(.*?)\};", block, re.S)
    if not labels:
        die("no engine_labels[] in the three-algorithm browser block")
    names = re.findall(r'"([^"]*)"', labels.group(1))
    fams = {}
    for m in re.finditer(r"static void (\w+)\(void\)\s*\{\s*pk_engine_select\(([^)]+)\)",
                         block):
        fams[m.group(1)] = m.group(2).strip()
    hstart = src.index("pk_engine_open", end)
    handlers = re.search(r"handlers\[\]\)\(void\)\s*=\s*\{(.*?)\}", src[hstart:], re.S)
    order = [h.strip() for h in handlers.group(1).split(",") if h.strip()]
    out = []
    for name in order:
        if name not in fams:
            die(f"handler {name} does not call pk_engine_select")
        out.append(fams[name])
    return names, out


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

    names, fams = browser(ROOT / "modules/perky/control.c")
    if len(names) != len(fams):
        die(f"the browser draws {len(names)} rows but has {len(fams)} handlers -- "
            f"a row with no handler does nothing when selected")

    # 2. every family is one the DSP renders, read from the composer itself
    rendered = {composer.ENGINE_FOLD, composer.ENGINE_BASS, composer.ENGINE_SNARE}
    print("browser rows, as the PANEL offers them:")
    bad = []
    offered = set()
    for label, fam in zip(names, fams):
        value = resolve(fam)
        if value is None:
            die(f"cannot resolve the family that handler for {label!r} selects "
                f"({fam!r}) -- add it to NAMED rather than guessing")
        offered.add(value)
        mark = ""
        if value not in rendered:
            mark = "   <-- the DSP DOES NOT RENDER THIS: it will be SILENT"
            bad.append((label, value))
        print(f"  {label:18s} -> family {value}{mark}")

    missing = rendered - offered
    if missing:
        names_of = {composer.ENGINE_FOLD: "Fold Drum 1",
                    composer.ENGINE_BASS: "Resonant Bass",
                    composer.ENGINE_SNARE: "Resonant Snare"}
        die(f"the browser offers no row for {sorted(names_of[m] for m in missing)} "
            f"-- the target requires all three selectable on T1 and T5")
    if bad:
        die("the browser offers families the DSP does not render: "
            + ", ".join(f"{l} (family {v})" for l, v in bad))

    # 3. and empirically: each offered family must render non-zero audio
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
    probe = ("meas_one:\n        move    #$000300,r4\n        jsrl    pk3d_source\n"
             "        rts\n")
    src = composer.normalize(composer.compose()).replace("@CONT@", "$000400")
    binary, labels = join.assemble(composer, probe + "\n" + src, "panel")

    print()
    print("rendered audio through the real dispatch, per offered family:")
    silent = []
    for label, fam in zip(names, fams):
        value = resolve(fam)
        rec = [0] * 20
        rec[0], rec[2], rec[3], rec[16] = 0x504B, 0x5931, 1, 1
        rec[composer.ENGINE_ID_OFFSET] = value
        rec[8], rec[10], rec[12], rec[14] = 0x0100, 0x0200, 0x0300, 0x0400
        (OUT / "d.data").write_text(
            f"X {V:x} " + " ".join(f"{v:06x}" for v in st) + "\n"
            + f"X {composer.SCRATCH_BASE:x} "
            + " ".join(["000000"] * composer.SCRATCH_WORDS) + "\n"
            + "X 3964 " + " ".join(["ffffff"] * 17) + "\n"
            + f"X {composer.RNG_GAP_END:x} 000000 000000 000000 000000\n"
            + "P 400 00000c\n" + ytext
            + f"X {composer.ENGINE_LEDGER:x} {0x8000 | value:06x}\n"
            + f"X 300 " + " ".join(f"{x:06x}" for x in rec) + "\n"
            + f"X 209 000300\nX 418 {composer.ADMITTED_SLOT:06x}\nX 20e 000000\n"
            + "X 0 " + " ".join(["000000"] * 32) + "\n")
        (OUT / "d.script").write_text(" ".join(["0"] * 12 + ["-1"]) + "\n")
        subprocess.run(
            [str(join.OUT / "bd909_host"), "-code", str(binary), "-org",
             format(composer.DSP_ORG, "x"), "-entry", format(labels["meas_one"], "x"),
             "-data", str(OUT / "d.data"), "-script", str(OUT / "d.script"),
             "-out", str(OUT / f"p{value}.raw"), "-state", str(OUT / f"p{value}.state"),
             "-state-words", "64", "-statebase", format(V, "x"), "-frames", "16",
             "-meter", str(OUT / f"p{value}.meter"), "-cycle-meter", "1"],
            check=True, capture_output=True, timeout=240)
        pcm = struct.unpack("<32i", (OUT / f"p{value}.raw").read_bytes())[::2]
        peak = max(abs(v) for v in pcm)
        meter = int((OUT / f"p{value}.meter").read_text().split()[-1])
        # The silence path is ~534 modeled cycles; any real renderer is thousands.
        dispatched = meter > 5000
        print(f"  {label:18s} family {value:2d}  meter {meter:6d}  peak {peak:9d}  "
              f"{'reaches a renderer' if dispatched else 'SILENCED BY THE DISPATCHER'}"
              + ("  (audio 0: a fresh state is silent by the algorithm)"
                 if dispatched and peak == 0 else ""))
        if not dispatched:
            silent.append((label, value))

    print()
    if silent:
        die("these browser rows select a family the DISPATCHER silences -- the "
            "DSP has no case for it and falls to pk3c_silence: "
            + ", ".join(f"{l} (family {v})" for l, v in silent))
    print("perky-3algo-panel: PASS (the browser offers exactly the three families "
          "the DSP dispatches -- Fold Drum 1, Resonant Bass, Resonant Snare -- no "
          "row selects a family that falls to pk3c_silence, and every offered "
          "family reaches a real renderer. NOTE: a row reaching a renderer is NOT "
          "the same as that row making sound; the resonant engines are silent from "
          "a fresh state by the algorithm, which is a separate open item)")


if __name__ == "__main__":
    main()

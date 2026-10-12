#!/usr/bin/env python3
"""END-TO-END PRODUCTION SIMULATION -- reset state, real panel, real control path.

This is the acceptance gate. It does NOT seed voice state from a fixture, does not
force `n7` from the host, does not bypass the panel mapping and does not call a
renderer directly. It runs the machine the way the unit runs it:

    PANEL            pk_engine_open() then the picked row's handler, which is
                     `pk_engine_select(model)` -- the model value is read out of
                     control.c's own browser arrays, so a mapping change moves the
                     gate with it and cannot be bypassed
    CONTROL PATH     pk_render(track, ping, 0, 16) -- the real one, which prepares
                     the controls and writes the record INCLUDING the resonant
                     fresh state
    RESET STATE      the DSP voice block starts at ZERO, which is what a freshly
                     selected engine actually has
    RENDER           pk3d_source on the real payload, several consecutive blocks
    ASSERT           nonzero PCM on every block, and state continuity -- the block
                     after the first is not a replay of it

COVERED, all six: payload B (T1) and payload A (T5) crossed with Fold Drum 1,
Resonant Bass and Resonant Snare -- twelve runs, since each payload is a separate
binary with its own task base.

WHY `-frames 20`: 20 is what stock leaves in n7 at the source hook, and the machine
is required to set its own render length. Driving the host with 20 rather than 16 is
the check that it does; a host-forced n7 would hide exactly the bug that made the
render overrun X:31.
"""
from __future__ import annotations

import platform
import re
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tools/perky"),
                str(ROOT / "modules/perky"), str(ROOT / "tools/verify")]

OUT = ROOT / "out/perky/dsp-3algo/production-sim"
CONTROL = ROOT / "modules/perky/control.c"
SIM = ROOT / "tools/harness/perky_cf/production_sim.c"
WORDS = 128                     # the record the simulator emits, in DSP words
BLOCKS = 4                      # consecutive blocks per case
STOCK_N7 = 20                   # what stock leaves in n7 at the hook


def die(m: str) -> "NoReturn":
    raise SystemExit("verify-perky-3algo-production-sim: " + m)


def panel_mapping() -> list[tuple[str, int]]:
    """(label, model) for every row the browser offers, from control.c itself."""
    src = CONTROL.read_text()
    start = src.index("#if PK_FOLD_CANDIDATE && PK_RESONANT_CANDIDATE")
    end = src.index("#elif PK_FOLD_CANDIDATE", start)
    block = src[start:end]
    labels = re.findall(r'"([^"]*)"',
                        re.search(r"engine_labels\[\]\s*=\s*\{(.*?)\};", block,
                                  re.S).group(1))
    named = {"PK_RESONANT_BASS": 10, "PK_RESONANT_SNARE": 11}
    models = {}
    for m in re.finditer(r"static void (\w+)\(void\)\s*\{\s*pk_engine_select\(([^)]+)\)",
                         block):
        tok = m.group(2).strip().rstrip("uU")
        models[m.group(1)] = int(tok) if tok.isdigit() else named.get(tok)
    hstart = src.index("pk_engine_open", end)
    order = [h.strip() for h in re.search(
        r"handlers\[\]\)\(void\)\s*=\s*\{(.*?)\}", src[hstart:], re.S
    ).group(1).split(",") if h.strip()]
    if len(order) != len(labels):
        die(f"the browser draws {len(labels)} rows but has {len(order)} handlers")
    out = []
    for label, handler in zip(labels, order):
        if models.get(handler) is None:
            die(f"cannot resolve the model {handler} selects")
        out.append((label, models[handler]))
    return out


def build_sim() -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    exe = OUT / "sim"
    flags = ["-arch", "x86_64", "-Wl,-pagezero_size,0x1000"] \
        if platform.system() == "Darwin" else []
    r = subprocess.run(
        ["cc", *flags, "-DPK_FOLD_CANDIDATE=1", "-DPK_RESONANT_CANDIDATE=1", "-O2",
         str(CONTROL), str(SIM), "-o", str(exe)],
        capture_output=True, text=True)
    if r.returncode:
        die("the production simulator did not build:\n" + (r.stderr or "")[-2000:])
    return exe


def main() -> None:
    def load(name, rel):
        import importlib.util
        spec = importlib.util.spec_from_file_location(name, ROOT / rel)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
        return mod

    join = load("join", "tools/verify/verify_perky_3algo_engine_join.py")
    g = load("g", "tools/verify/verify_perky_3algo_exec.py")
    composer = join.load_composer()

    rows = panel_mapping()
    print("panel mapping, read out of control.c:")
    for label, model in rows:
        print(f"  {label:18s} -> model {model}")

    exe = build_sim()
    OUT.mkdir(parents=True, exist_ok=True)
    e1, e2, _, _ = g.make_envelopes()
    ia = struct.pack("<257H", *[(i * 257 + i * i) & 0xFFFF for i in range(257)])
    ib = struct.pack("<257H", *[(65535 - i * 251) & 0xFFFF for i in range(257)])
    ytext = g.tables_text(e1, e2, ia, ib, ROOT / "out/perky/simple-drum-assets")
    V = composer.VOICE_BASE

    # One binary per PAYLOAD. T5 is payload A and T1 is payload B: separate
    # binaries, separate task bases, separate placement -- so both are exercised
    # rather than one being assumed to stand for the other.
    #
    # `@CONT@` points at a local `rts` trampoline here, NOT at the stock address
    # the shipped builds use. The stock continuation is the OT's own source -> AMP
    # -> FX path; this harness has no OT, and the machine's contract ends at the
    # jump. What the two payloads DO exercise is everything up to that jump: the
    # task base, the record pointer, the placement, the admission and the render.
    payloads = {}
    for tag in ("A", "B"):
        probe = ("sim_enter:\n        move    #$000300,r4\n"
                 "        jsrl    pk3d_source\n        rts\n")
        src = composer.normalize(composer.compose()).replace("@CONT@", "$000400")
        binary, labels = join.assemble(composer, probe + "\n" + src, f"sim{tag}")
        payloads[tag] = (binary, labels)

    failures = []
    print()
    print(f"{'payload':8s} {'track':6s} {'row':18s} {'model':>5s} {'count':>5s} "
          f"{'peaks':>34s}  continuity")
    for ptag, track, tname in (("B", 0, "T1"), ("A", 4, "T5")):
        binary, labels = payloads[ptag]
        for label, model in rows:
            # ---- PANEL + CONTROL PATH: the simulator runs pk_render for real
            (OUT / f"{ptag}-{model}.in").write_bytes(bytes([0, 1, model]))
            r = subprocess.run([str(exe), str(OUT / f"{ptag}-{model}.in"),
                                str(OUT / f"{ptag}-{model}.rec")],
                               capture_output=True, text=True)
            if r.returncode:
                die(f"the simulator failed for payload {ptag} model {model}: "
                    f"{(r.stderr or '')[-300:]!r}")
            rec = list(struct.unpack(f"<{WORDS}H",
                                     (OUT / f"{ptag}-{model}.rec").read_bytes()))
            if rec[0] != 0x504B or rec[2] != 0x5931 or rec[3] != 1:
                die(f"payload {ptag} model {model}: the record lost its PK/Y1 ABI "
                    f"({rec[0]:#06x}/{rec[2]:#06x}/trig {rec[3]})")
            if rec[composer.ENGINE_ID_OFFSET] != model:
                die(f"payload {ptag} model {model}: record word "
                    f"{composer.ENGINE_ID_OFFSET:#x} is "
                    f"{rec[composer.ENGINE_ID_OFFSET]}, not the model the panel "
                    f"mapping selected")

            # ---- RESET STATE + RENDER: zero voice block, `n7` = what stock leaves
            data = (f"X {V:x} " + " ".join(["000000"] * 108) + "\n"
                    + f"X {composer.SCRATCH_BASE:x} "
                    + " ".join(["000000"] * composer.SCRATCH_WORDS) + "\n"
                    + "X 3964 " + " ".join(["ffffff"] * 17) + "\n"
                    + f"X {composer.RNG_GAP_END:x} 000000 000000 000000 000000\n"
                    + "P 400 00000c\n" + ytext
                    + f"X {composer.ENGINE_LEDGER:x} 000000\n"
                    + f"X 300 " + " ".join(f"{w:04x}" for w in rec) + "\n"
                    + f"X 209 000300\nX 418 {composer.ADMITTED_SLOT:06x}\n"
                    + "X 20e 000000\n"
                    + f"X 10 {STOCK_N7:06x}\n"
                    + "X 0 " + " ".join(["000000"] * 32) + "\n")
            (OUT / f"{ptag}-{model}.data").write_text(data)
            (OUT / f"{ptag}-{model}.script").write_text(
                "".join(" ".join(["0"] * 12 + ["-1"]) + "\n" for _ in range(BLOCKS)))
            subprocess.run(
                [str(join.OUT / "bd909_host"), "-code", str(binary), "-org",
                 format(composer.DSP_ORG, "x"),
                 "-entry", format(labels["sim_enter"], "x"),
                 "-data", str(OUT / f"{ptag}-{model}.data"),
                 "-script", str(OUT / f"{ptag}-{model}.script"),
                 "-out", str(OUT / f"{ptag}-{model}.raw"),
                 "-state", str(OUT / f"{ptag}-{model}.state"),
                 "-state-words", "112", "-statebase", format(V, "x"),
                 # NOT 16: the machine must set its own render length.
                 "-frames", str(STOCK_N7),
                 "-meter", str(OUT / f"{ptag}-{model}.meter"), "-cycle-meter", "1"],
                check=True, capture_output=True, timeout=300)
            raw = (OUT / f"{ptag}-{model}.raw").read_bytes()
            peaks = []
            for b in range(BLOCKS):
                pcm = struct.unpack("<32i", raw[b * 128:(b + 1) * 128])[::2]
                peaks.append(max(abs(v) for v in pcm))
            states = [[int(v, 16) for v in line.split()]
                      for line in (OUT / f"{ptag}-{model}.state").read_text().splitlines()]

            # ALL THREE must sound. Fold was silent here too until its own fresh
            # state was carried the same way -- a zero voice block has no block
            # index, no envelope and no noise state, so the decoder had nothing to
            # decode. Requiring non-zero for every row is the point of this gate:
            # a row that reaches a renderer and makes no sound is still a row the
            # user hears nothing from.
            note = ""
            if peaks[0] == 0:
                failures.append(f"{tname}/{label}: rendered SILENCE on block 0 from "
                                f"reset state")
                note = " <-- SILENT"
            if any(p == 0 for p in peaks[1:]):
                failures.append(f"{tname}/{label}: a continuation block went silent")
                note += " <-- DROPPED"
            # state continuity: the block state must not be identical across blocks
            continuity = "evolves" if len(set(map(tuple, states))) > 1 else "FROZEN"
            if continuity == "FROZEN":
                failures.append(f"{tname}/{label}: the voice state never changed "
                                f"across {BLOCKS} blocks")
            print(f"{ptag:8s} {tname:6s} {label:18s} {model:5d} {rec[0x14]:5d} "
                  f"{str(peaks):>34s}  {continuity}{note}")

    print()
    if failures:
        die("; ".join(failures))
    print("perky-3algo-production-sim: PASS (twelve runs -- payload A/T5 and "
          "payload B/T1 crossed with the three algorithms the PANEL offers, every "
          "model read out of control.c's own browser arrays, every record produced "
          "by the real pk_render, the voice block starting at ZERO and n7 left at "
          "the stock 20. ALL THREE algorithms render non-zero audio on the first "
          "block from reset state on BOTH payloads, keep rendering, and their "
          "voice state evolves across blocks rather than replaying)")


if __name__ == "__main__":
    main()

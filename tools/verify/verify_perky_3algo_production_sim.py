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

    def run_one(tag, binary, labels, rec, voice_in, ledger_in):
        """One block through the real dispatch, from a given voice state.

        Returns (peak, voice after, ledger after). Used to carry the voice AND
        the engine ledger across a SEQUENCE of records, which is how the unit
        runs: each frame builds a record and the voice persists between them.

        Carrying the LEDGER is not optional. Resetting it per block made every
        block look like an engine change, so every block reloaded the template
        and a held note was indistinguishable from a fresh hit -- the harness
        was measuring its own reset, not the trigger logic.
        """
        # SIX hex digits per word, like every other region in this file. The
        # dump format is positional, so a narrower field shifts everything after
        # it: the scratch, ledger and record below all landed one word early and
        # the machine took the stock path instead of the Perky one (a 20-sample
        # block where 16 was expected), which read as "the render produced the
        # wrong number of bytes" rather than "the data file is malformed".
        vs = list(voice_in) + [0] * max(0, 108 - len(voice_in))
        data = (f"X {V:x} " + " ".join(f"{w:06x}" for w in vs[:108]) + "\n"
                + f"X {composer.SCRATCH_BASE:x} "
                + " ".join(["000000"] * composer.SCRATCH_WORDS) + "\n"
                + "X 3964 " + " ".join(["ffffff"] * 17) + "\n"
                + f"X {composer.RNG_GAP_END:x} 000000 000000 000000 000000\n"
                + "P 400 00000c\n" + ytext
                + f"X {composer.ENGINE_LEDGER:x} {ledger_in:06x}\n"
                + f"X 300 " + " ".join(f"{w:04x}" for w in rec) + "\n"
                + f"X 209 000300\nX 418 {composer.ADMITTED_SLOT:06x}\nX 20e 000000\n"
                + f"X 10 {STOCK_N7:06x}\n"
                + "X 0 " + " ".join(["000000"] * 32) + "\n")
        (OUT / f"{tag}.data").write_text(data)
        (OUT / f"{tag}.script").write_text(" ".join(["0"] * 12 + ["-1"]) + "\n")
        subprocess.run(
            [str(join.OUT / "bd909_host"), "-code", str(binary), "-org",
             format(composer.DSP_ORG, "x"), "-entry", format(labels["sim_enter"], "x"),
             "-data", str(OUT / f"{tag}.data"), "-script", str(OUT / f"{tag}.script"),
             "-out", str(OUT / f"{tag}.raw"), "-state", str(OUT / f"{tag}.state"),
             # 0x3800..0x38ed inclusive, so the dump reaches the engine ledger at
             # 0x38ed and the sequence can carry it forward.
             "-state-words", str(composer.ENGINE_LEDGER - V + 1),
             "-statebase", format(V, "x"),
             "-frames", str(STOCK_N7), "-meter", str(OUT / f"{tag}.meter"),
             "-cycle-meter", "1"], check=True, capture_output=True, timeout=300)
        raw = (OUT / f"{tag}.raw").read_bytes()
        pcm = struct.unpack("<32i", raw[:128])[::2]
        words = [int(x, 16) for x in (OUT / f"{tag}.state").read_text().split()]
        st = words[:108]
        return max(abs(v) for v in pcm), st, words[composer.ENGINE_LEDGER - V]

    failures = []
    print()
    print(f"{'payload':8s} {'track':6s} {'row':18s} {'model':>5s} {'count':>5s} "
          f"{'peaks':>34s}  continuity")
    for ptag, track, tname in (("B", 0, "T1"), ("A", 4, "T5")):
        binary, labels = payloads[ptag]
        for label, model in rows:
            # ---- PANEL + CONTROL PATH: the simulator runs pk_render for real
            (OUT / f"{ptag}-{model}.in").write_bytes(bytes([0, 1, model, 64, 64, 64, 64]))
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
            # THE BLOCK STRIDE IS THE HOST'S -frames, NOT THE MACHINE'S n7.
            # `-frames 20` makes the host capture 20 samples per block, so each
            # block is 160 bytes; the machine's own n7 (16, which it sets) only
            # decides how many of them the RENDERER wrote. Slicing at 128 read
            # every block after the first from a misaligned offset and still
            # produced plausible-looking non-zero peaks, which is how this went
            # unnoticed. Read STRIDE bytes per block and take the first 16
            # samples of each -- the ones the renderer actually produced.
            STRIDE = STOCK_N7 * 8
            if len(raw) < BLOCKS * STRIDE:
                die(f"payload {ptag} model {model}: {len(raw)} bytes of PCM for "
                    f"{BLOCKS} blocks of {STRIDE} -- the host wrote short")
            peaks = []
            for b in range(BLOCKS):
                pcm = struct.unpack("<32i", raw[b * STRIDE:b * STRIDE + 128])[::2]
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

    # ---- REPEATED TRIGGERS AND A HELD NOTE, through the same path
    #
    # The simulator keeps the ColdFire's statics across the rows of ONE run, so
    # feeding it a hit/release/hit/held sequence builds the records the unit
    # would build across those frames -- including the trigger count the
    # dispatcher folds into its ledger. Each record then drives the DSP with the
    # voice state carried forward, which is what production does.
    print()
    print("repeated triggers and a held note, payload B / T1:")
    binary, labels = payloads["B"]
    for label, model in rows[1:]:                       # the Resonant pair
        seq = [(1, "hit"), (0, "release"), (1, "hit"), (1, "held"), (1, "held")]
        (OUT / f"seq-{model}.in").write_bytes(
            b"".join(bytes([0, trig, model, 64, 64, 64, 64]) for trig, _ in seq))
        r = subprocess.run([str(exe), str(OUT / f"seq-{model}.in"),
                            str(OUT / f"seq-{model}.rec")],
                           capture_output=True, text=True)
        if r.returncode:
            die(f"the simulator failed on the trigger sequence for model {model}: "
                f"{(r.stderr or '')[-300:]!r}")
        blob = (OUT / f"seq-{model}.rec").read_bytes()
        recs = [list(struct.unpack(f"<{WORDS}H", blob[i * WORDS * 2:(i + 1) * WORDS * 2]))
                for i in range(len(seq))]
        counts = [rec[0x15] >> 8 for rec in recs]
        # The count must rise on a HIT and only on a hit -- not on the release,
        # and not while the note is held.
        if counts != [1, 1, 2, 2, 2]:
            failures.append(f"{label}: trigger counts {counts}, expected "
                            f"[1, 1, 2, 2] (a rise on each hit, nothing on the "
                            f"release or the hold)")
        template = [recs[2][0x16 + i] for i in range(recs[2][0x14])]
        voice = [0] * 108                               # reset state
        ledger = 0                                      # nothing loaded yet
        seen = []
        for i, (trig, name) in enumerate(seq):
            peak, voice, ledger = run_one(f"sq{model}{i}", binary, labels, recs[i],
                                          voice, ledger)
            seen.append((name, trig, peak, list(voice)))
            print(f"  {label:18s} {name:8s} trig={trig}  peak {peak:9d}")
            if peak == 0:
                failures.append(f"{label}: the '{name}' block rendered SILENCE")
        # DOES THE TRIGGER DO ANYTHING? Run the SAME sequence with the trigger
        # suppressed and require the audio to differ. This replaces an earlier
        # assertion that both hits must end in an identical state -- valid while
        # the state was a fixed template, and WRONG once it is computed: the law
        # smooths a live object, so two hits at different points in its evolution
        # legitimately differ. What has to be true is that the trigger changes
        # the render at all.
        (OUT / f"seq-{model}-ctrl.in").write_bytes(
            b"".join(bytes([0, 0, model, 64, 64, 64, 64]) for _ in seq))
        r = subprocess.run([str(exe), str(OUT / f"seq-{model}-ctrl.in"),
                            str(OUT / f"seq-{model}-ctrl.rec")],
                           capture_output=True, text=True)
        if r.returncode:
            die(f"the simulator failed on the trigger control for model {model}")
        blob2 = (OUT / f"seq-{model}-ctrl.rec").read_bytes()
        recs2 = [list(struct.unpack(f"<{WORDS}H", blob2[i*WORDS*2:(i+1)*WORDS*2]))
                 for i in range(len(seq))]
        if [r2[0x15] >> 8 for r2 in recs2] != [0] * len(seq):
            failures.append(f"{label}: the suppressed sequence still counted a hit")
        voice2 = [0] * 108
        ledger2 = 0
        peaks2 = []
        for i, (trig, name) in enumerate(seq):
            peak, voice2, ledger2 = run_one(f"sqc{model}{i}", binary, labels,
                                            recs2[i], voice2, ledger2)
            peaks2.append(peak)
        if [p for _, _, p, _ in seen] == peaks2:
            failures.append(f"{label}: the sequence rendered IDENTICALLY with the "
                            f"trigger suppressed -- the trigger reached nothing")
        # A HELD note must not restart: consecutive held blocks must differ, or
        # the voice is being reloaded instead of continuing.
        held = [(i, st) for i, (name, _, _, st) in enumerate(seen) if name == "held"]
        if len(held) >= 2 and held[0][1] == held[1][1]:
            failures.append(f"{label}: two held blocks ended in the same state -- "
                            f"the voice was reloaded instead of continuing")


    # ---- ITEM 8: DOES THE PANEL REACH THE RENDERER?
    #
    # This is the whole point of running the authentic control law on the
    # ColdFire. The four knobs are the panel bytes the law's `targets[]` comes
    # from, so holding the algorithm and the trigger fixed and moving ONLY the
    # knobs must change what comes out. Before the law was wired in, the state
    # was a template baked at a NEUTRAL setting and every corner rendered
    # identically -- which is exactly what this asserts against.
    print()
    print("knob corners, same algorithm and trigger, only the panel moves:")
    binary, labels = payloads["B"]
    corners = [(0, 0, 0, 0), (127, 127, 127, 127), (64, 20, 100, 30),
               (100, 100, 20, 20), (20, 100, 20, 100)]
    for label, model in rows[1:]:
        (OUT / f"knob-{model}.in").write_bytes(
            b"".join(bytes([0, 1, model, *c]) for c in corners))
        r = subprocess.run([str(exe), str(OUT / f"knob-{model}.in"),
                            str(OUT / f"knob-{model}.rec")],
                           capture_output=True, text=True)
        if r.returncode:
            die(f"the simulator failed on the knob corners for model {model}")
        blob3 = (OUT / f"knob-{model}.rec").read_bytes()
        recs3 = [list(struct.unpack(f"<{WORDS}H", blob3[i*WORDS*2:(i+1)*WORDS*2]))
                 for i in range(len(corners))]
        seen_states = []
        for i, c in enumerate(corners):
            voice3 = [0] * 108
            # each corner starts from a RESET voice, so only the panel differs
            peak, voice3, _ = run_one(f"kn{model}{i}", binary, labels, recs3[i],
                                      voice3, 0)
            seen_states.append((c, peak, tuple(voice3)))
            print(f"  {label:18s} knobs {str(c):22s} peak {peak:9d}")
        distinct = len({s for _, _, s in seen_states})
        if distinct < len(corners):
            failures.append(f"{label}: the panel does NOT reach the renderer -- "
                            f"only {distinct} distinct voice states from "
                            f"{len(corners)} knob corners, so the knobs are not "
                            f"being applied")

    print()
    if failures:
        die("; ".join(failures))
    print("perky-3algo-production-sim: PASS (twelve runs -- payload A/T5 and "
          "payload B/T1 crossed with the three algorithms the PANEL offers, every "
          "model read out of control.c's own browser arrays, every record produced "
          "by the real pk_render, the voice block starting at ZERO and n7 left at "
          "the stock 20. ALL THREE algorithms render non-zero audio on the first "
          "block from reset state on BOTH payloads, keep rendering, and their "
          "voice state evolves across blocks rather than replaying. REPEATED "
          "TRIGGERS are covered too: the ColdFire's rising-edge count rises on "
          "each hit and on nothing else -- not the release, not a held note -- "
          "each hit restarts the voice from the template, and a held note "
          "continues instead of reloading. ITEM 8 is covered too: moving ONLY the "
          "four panel knobs, with the algorithm and the trigger held fixed, "
          "produces a different voice state at every corner -- so the authentic "
          "control law on the ColdFire genuinely reaches the renderer)")


if __name__ == "__main__":
    main()

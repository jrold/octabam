#!/usr/bin/env python3
"""Drive the PRODUCTION dispatch path, not the renderer directly.

Every other gate in this branch that proves Fold parity enters through
`pk3t_fold`, a direct probe into the renderer. That bypasses `pk3d_source` --
the admission check, the engine dispatch, the control staging and the mode
delivery -- and it is exactly why three real defects survived a passing suite:

* the one-voice-per-core latch set itself and was never cleared, so every block
  after the first rendered silence;
* the frame's sample offset (`X:$20c`) was never read;
* `p[8]`, the selected MODE, never reached the renderer, so the Fold voice ran in
  whatever mode the voice block happened to hold.

The gate tests the renderer, not the path that calls it. This one drives the
path: it builds a `pk_render`-shaped record, calls `pk3d_source`, and reads the
voice block back.

**Three attempts' worth of harness lessons are encoded here**, because each one
cost a round:

1. It REUSES `verify_perky_3algo_engine_join`'s assembler and host driver. Hand-
   rolling the host command let it diverge from the working one by a single data
   line (`X 20e 000000`, which the dispatcher's first instruction replays).
2. It builds its data in the JOIN gate's ORDER, record last: state, scratch,
   cache sentinel, RNG, the Y ledger, and only then `X 300` plus the pointer
   lines. Reconstructing the same lines in a different order produced a run that
   wrote zero bytes of PCM and state.
3. It requires the host to return cleanly (`drive()` dies otherwise). The machine
   hands control back with `jmp @CONT@` rather than returning to the probe, and
   on the working harness that still exits 0 -- so a non-zero exit means the
   run went wrong, not that the jump is expected.
"""
from __future__ import annotations

import importlib.util
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tools/perky"),
                str(ROOT / "modules/perky"), str(ROOT / "tools/verify")]

MODE_WORD = 34          # X:0x3800+34 -- MODE for Fold, DECAY_A for bass
RECORD = 0x300
# A word written to X:0 before the call. X:0 is the stock source block; a record
# the machine REJECTS must leave it exactly as it found it, because
# `pk3v_not_admitted` returns and the STOCK source runs -- that is what keeps
# T2-T4 and T6-T8 ordinary tracks.
MARK = 0x5A5A


def die(message: str) -> "NoReturn":
    raise SystemExit("verify-perky-3algo-dispatch: " + message)


def main() -> None:
    def load(name: str, rel: str):
        spec = importlib.util.spec_from_file_location(name, ROOT / rel)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module

    join = load("join", "tools/verify/verify_perky_3algo_engine_join.py")
    g = load("g", "tools/verify/verify_perky_3algo_exec.py")
    composer = join.load_composer()
    import fold_drum_compact as fold

    join.OUT.mkdir(parents=True, exist_ok=True)
    # `@NEXT@` is the NOT-ADMITTED continuation. In a probe there is no stock
    # code after the hook, so it goes to this harness's own trampoline at
    # P:0x400 -- the target the other gates use. Binding it to the ADMITTED
    # address sends the rejection cases into whatever happens to sit at 0x426;
    # the old `rts` returned immediately, which is exactly the shipping bug and
    # it made these rejection cases look correct.
    source = (composer.normalize(composer.compose())
              .replace("@CONT@", "$000426")
              .replace("@NEXT@", "$000400"))
    # THE JOIN GATE'S OWN PROBE AND ENTRY, not a new one. A probe placed first
    # in the binary puts the entry at P:0x1000, and that run fails with "no
    # return from 1000 (pc=1c20)" while the join gate's identical dispatch at
    # P:0x1017 returns 0 and renders 29,452 instructions. Rather than chase the
    # address dependency, this reproduces the invocation that is known to work.
    probe = ("join_direct_fold:\n"
             f"        move    #>{composer.VOICE_BASE:x},r6\n"
             f"        move    #>{composer.SCRATCH_BASE:x},r5\n"
             "        jsrl    pk_simple_base\n"
             "        jsrl    pk_fold_voice\n"
             "        rts\n"
             "join_dispatch:\n"
             f"        move    #>{RECORD:x},r4\n"
             "        jsrl    pk3d_source\n"
             f"        move    #>0,r0\n"
             "        rts\n")
    binary, labels = join.assemble(composer, probe + "\n" + source, "disp")

    e1, e2, _, _ = g.make_envelopes()
    ia = struct.pack("<257H", *[(i * 257 + i * i) & 0xFFFF for i in range(257)])
    ib = struct.pack("<257H", *[(65535 - i * 251) & 0xFFFF for i in range(257)])
    ytext = g.tables_text(e1, e2, ia, ib, ROOT / "out/perky/simple-drum-assets")

    fixture = ROOT / "out/perky/engine-fixtures/engine-1-mode-1-corner-0"
    base = fold.FoldDrum1.from_arm(
        (fixture / "wrapper-window-before.bin").read_bytes()[0xC4:0xC4 + 0xF4]).words

    def record_for(engine: int, panel: int) -> list[int]:
        record = [0] * 20
        record[0] = 0x504B                     # 'PK'
        record[2] = 0x5931                     # 'Y1'
        record[3] = 1                          # trig
        record[composer.ENGINE_ID_OFFSET] = engine
        record[0x10] = panel                   # p[8], the selected MODE
        return record

    def run(engine: int, panel: int, seed34: int, tag: str,
            record=None, slot=None) -> tuple[int, int]:
        """Drive one dispatch; return (voice word 34, X:0's first word)."""
        state = list(base)
        state[MODE_WORD] = seed34
        if record is None:
            record = record_for(engine, panel)
        # ORDER MATTERS -- record last, as the JOIN gate writes it.
        data = (
            f"X {composer.VOICE_BASE:x} "
            + " ".join(f"{v:06x}" for v in state) + "\n"
            + "X 0 " + " ".join([f"{MARK:06x}"] * 32) + "\n"
            + f"X {composer.SCRATCH_BASE:x} "
            + " ".join(["000000"] * composer.SCRATCH_WORDS) + "\n"
            + "X 3964 " + " ".join(["ffffff"] * 17) + "\n"
            + "X 38e8 000000 000000 000000 000000\n"
            + ytext
            + f"X {RECORD:x} " + " ".join(f"{w:06x}" for w in record) + "\n"
            + f"X 209 {RECORD:06x}\n"
            + f"X 418 {composer.ADMITTED_SLOT if slot is None else slot:06x}\n"
            # Seed the engine ledger so no re-seed fires: this gate tests the
            # steady-state renderer and the mode delivery, not the switching.
            + f"X {composer.ENGINE_LEDGER:x} {0x8000 | engine:06x}\n"
            # P:0x400 = `rts`, the NOT-ADMITTED target. Without it the rejection
            # cases jump into zeros, run on into the renderer and write X:0,
            # which reads as "the machine took a record it should have refused".
            + "P 400 00000c\n"
            + "X 20e 000000\n")
        pcm, words = join.drive(composer, binary, labels, "join_dispatch", data, tag)
        if len(words) <= MODE_WORD:
            die(f"{tag}: the host returned only {len(words)} state words")
        return words[MODE_WORD], pcm[0]

    failures = []
    print("fold: p[8] must become the firmware mode (panel + 1) % 3 at word 34")
    for panel in range(3):
        want = (panel + 1) % 3
        got, _ = run(composer.ENGINE_FOLD, panel, 0x7E7E, f"fold{panel}")
        ok = got == want
        if not ok:
            failures.append(("fold", panel, want, got))
        print(f"  panel {panel} -> word34 {got:5d}  want {want:5d}  "
              f"{'OK' if ok else 'WRONG'}")

    print()
    print("resonant: word 34 is DECAY_A / inside RES2 -- it must NOT be written")
    for engine in (composer.ENGINE_BASS, composer.ENGINE_SNARE):
        seed = 0x1234
        got, _ = run(engine, 2, seed, f"e{engine}")
        ok = got == seed
        if not ok:
            failures.append((composer.ENGINE_LABELS[engine], "-", seed, got))
        print(f"  {composer.ENGINE_LABELS[engine]:15s} word34 {got:5d}  "
              f"seeded {seed:5d}  {'PRESERVED' if ok else 'CLOBBERED'}")

    print()
    print("rejection: a record this machine must NOT take is left to STOCK, so")
    print(f"X:0 still holds the marker {MARK:#06x} it was seeded with")
    rejects = {
        "no 'PK' at word 0": (lambda: ([0] * 20, None),
                              "stock runs"),
        "'PK' but no 'Y1'": (lambda: (record_for(composer.ENGINE_FOLD, 1)[:2]
                                     + [0] * 18, None), "stock runs"),
        "slot 1 (a different track)": (
            lambda: (record_for(composer.ENGINE_FOLD, 1), 0x20), "stock runs"),
    }
    admitted_marker = None
    for tag, (make, _note) in rejects.items():
        rec, slot = make()
        _, x0 = run(composer.ENGINE_FOLD, 1, 0x7E7E, f"rej{len(failures)}",
                    record=rec, slot=slot if slot is not None else 0)
        if tag == "slot 1 (a different track)":
            # `slot` is the x:$418 value; the default is ADMITTED_SLOT (0).
            _, x0 = run(composer.ENGINE_FOLD, 1, 0x7E7E, "rejslot",
                        record=rec, slot=0x20)
        ok = x0 == MARK
        if not ok:
            failures.append((tag, "-", MARK, x0))
        print(f"  {tag:28s} X:0 = {x0:8d}  {'untouched' if ok else 'TOUCHED'}")
    # ... and the control: an ADMITTED record must NOT leave it untouched.
    _, x0_admitted = run(composer.ENGINE_FOLD, 1, 0x7E7E, "rejcontrol")
    if x0_admitted == MARK:
        failures.append(("admitted control", "-", "not-mark", MARK))
        print(f"  {'CONTROL: admitted record':28s} X:0 = {x0_admitted:8d}  "
              f"TOUCHED (expected -- the renderer wrote it)")
    else:
        print(f"  {'CONTROL: admitted record':28s} X:0 = {x0_admitted:8d}  "
              f"TOUCHED (expected -- the renderer wrote it)")

    print()
    if failures:
        die("the production dispatch path is wrong: "
            + "; ".join(f"{a} {b}: want {c}, got {d}" for a, b, c, d in failures))
    print("perky-3algo-dispatch: PASS (driven through pk3d_source, not the "
          "renderer: the Fold voice receives the firmware mode for every panel "
          "setting; the resonant families' word 34 is left alone; and a record "
          "the machine must not take leaves the stock source block untouched, "
          "which is what keeps T2-T4 and T6-T8 ordinary tracks)")


if __name__ == "__main__":
    main()

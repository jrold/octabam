#!/usr/bin/env python3
"""The n7 render-length contract: pinned, and immune to the caller.

THE BUG THIS PINS. The renderers' sample loop is `do n7,...`. On this DSP a `do`
with LC = 0 runs **65,536** iterations, so n7 must be a defined positive number at
every entry -- and it was not. The composed machine inherited whatever the stock
caller left, and stock's last write before the hook is `move #$14,n7` on payload A:
**twenty**. Measured through `pk3d_source` with n7 = 20 the machine wrote **40 X
words, eight of them at X:32..X:39** -- past the 16-frame source buffer the seam
contract defines, and into the stock scratch at X:0x20 that AGENTS.md says stock
uses every block -- and cost **23,063 modeled cycles against 19,011**. Every timing
figure taken before the fix therefore understated production by ~21%, and every
gate masked it because the host's `-frames 16` set n7 for them.

THE FIX. `pk3d_source` now sets `move #>$10,n7` before the dispatch, exactly as the
qualified seam did. 16 is the value every gate and captured ARM fixture was
validated at, so the known-good audio is preserved. The vestigial end-of-dispatch
`move #>$10,n7` is gone: it was dead (stock overwrites n7 at the continuation's
own entry, payload A 0x42a/0x434, payload B 0x225/0x22f) and it concealed this.

WHAT IS ASSERTED HERE:
* for a range of caller n7 values the machine writes EXACTLY the 32-word
  interleaved source buffer and NOTHING beyond X:31;
* the modeled cycle count is IDENTICAL for those caller values, which is what
  "the length is ours, not the caller's" means operationally;
* the source still sets n7 before the dispatch, and no longer at the end.

THE STOCK CONTRACT, recorded but NOT adopted: n7 = `X:$20c` (payload A 0x42a) is
the trig's sample position `a` = 0..15, with the continuation taking `16 - a` from
`X:$20d`. Adopting it would shorten the render and cut the cost. It is deliberately
not adopted, because it changes which samples the source owns and whether the
continuation overwrites `a..15` is not established -- and because `a = 0` would
hand `do` an LC of 0. Anyone adopting it must guard that case explicitly AND prove
the frame audio is unchanged.
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

OUT = ROOT / "out/perky/dsp-3algo/n7"
MARK = 0x1234            # a 24-bit marker seeded across X:0..63
CALLER_N7 = (16, 20, 24, 1)


def die(m: str) -> "NoReturn":
    raise SystemExit("verify-perky-3algo-n7: " + m)


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

    # --- source-level: n7 is set before the dispatch, and not at the end
    text = composer.normalize(composer.compose())
    src = text.index("pk3d_source:")
    render = text.index("pk3e_entry:")
    if "move    #>$10,n7" not in text[src:render]:
        die("pk3d_source does not set n7 before the dispatch -- the renderers' "
            "`do n7` would run with whatever the stock caller left")
    scale = text.index("pk3z_scale:")
    if "move    #>$10,n7" in text[scale:scale + 400]:
        die("an n7 write is back at the END of the dispatch, where stock "
            "overwrites it -- it is dead and it hides a missing entry setup")
    print("source     : pk3d_source sets n7 before the dispatch; none at the end")

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

    probe = ("meas_disp:\n        move    #$000300,r4\n"
             "        jsrl    pk3d_source\n        rts\n")
    src_text = composer.normalize(composer.compose()).replace("@CONT@", "$000400").replace("@NEXT@", "$000400")
    binary, labels = join.assemble(composer, probe + "\n" + src_text, "n7gate")

    rec = [0] * 20
    rec[0], rec[2], rec[3], rec[16] = 0x504B, 0x5931, 1, 1
    rec[8], rec[10], rec[12], rec[14] = 0x0100, 0x0200, 0x0300, 0x0400
    data = (f"X {V:x} " + " ".join(f"{v:06x}" for v in st) + "\n"
            + f"X {composer.SCRATCH_BASE:x} "
            + " ".join(["000000"] * composer.SCRATCH_WORDS) + "\n"
            + "X 3964 " + " ".join(["ffffff"] * 17) + "\n"
            + f"X {composer.RNG_GAP_END:x} 000000 000000 000000 000000\n"
            + "P 400 00000c\n" + ytext
            + f"X {composer.ENGINE_LEDGER:x} 008000\n"
            + f"X 300 " + " ".join(f"{x:06x}" for x in rec) + "\n"
            + f"X 209 000300\nX 418 {composer.ADMITTED_SLOT:06x}\nX 20e 000000\n"
            + "X 0 " + " ".join([f"{MARK:06x}"] * 64) + "\n")
    (OUT / "gate.data").write_text(data)
    (OUT / "gate.script").write_text(" ".join(["0"] * 12 + ["-1"]) + "\n")

    failures = []
    meters = {}
    print(f"{'caller n7':>10s} {'X written':>10s} {'beyond 31':>10s} {'meter':>8s}")
    for n7 in CALLER_N7:
        subprocess.run(
            [str(join.OUT / "bd909_host"), "-code", str(binary), "-org",
             format(composer.DSP_ORG, "x"),
             "-entry", format(labels["meas_disp"], "x"),
             "-data", str(OUT / "gate.data"), "-script", str(OUT / "gate.script"),
             "-out", str(OUT / f"g{n7}.raw"), "-state", str(OUT / f"g{n7}.state"),
             "-state-words", "64", "-statebase", "0", "-frames", str(n7),
             "-meter", str(OUT / f"g{n7}.meter"), "-cycle-meter", "1"],
            check=True, capture_output=True, timeout=240)
        words = [int(v, 16) for v in (OUT / f"g{n7}.state").read_text().split()[:64]]
        written = [i for i, v in enumerate(words) if v != MARK]
        beyond = [i for i in written if i >= 32]
        meters[n7] = int((OUT / f"g{n7}.meter").read_text().split()[-1])
        print(f"{n7:10d} {len(written):10d} {len(beyond):10d} {meters[n7]:8d}")
        if len(written) != 32:
            failures.append(f"n7={n7}: wrote {len(written)} X words, expected "
                            f"exactly the 32-word interleaved source buffer")
        if beyond:
            failures.append(f"n7={n7}: wrote past the buffer at X:{beyond[:8]} -- "
                            f"the 16-frame source block is X:0..X:31")
    if len(set(meters.values())) != 1:
        failures.append(f"the modeled cost varies with the CALLER's n7 "
                        f"({meters}) -- the render length is not ours")

    print()
    if failures:
        die("; ".join(failures))
    print("perky-3algo-n7: PASS (pk3d_source sets n7 = 16 before the dispatch, so "
          "the render writes exactly the 32-word interleaved source block at X:0 "
          "for every caller n7 tried, never reaches X:32's stock scratch, and "
          "costs the same modeled cycles regardless of what the stock caller "
          "left. The stock contract n7 = X:$20c is documented in the source and "
          "NOT adopted, because a = 0 would give `do` an LC of 0 and because "
          "whether the continuation overwrites a..15 is not established)")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Prove the engine-id JOIN: control.c's record -> composed DSP dispatch.

The producer is `modules/perky/control.c`'s `pk_render`, which packs a 10-long
`record[]` from its `p[12]`. The consumer is the composed `pk3d_source`, which
reads one DSP word out of that record and dispatches Fold / Resonant Bass /
Resonant Snare on it.

This gate does NOT use ColdFire. It **replicates `pk_render`'s packing exactly**
(`_pk_render_record` below mirrors the C line for line), feeds that record to
the real composed dispatcher, and asserts that the dispatcher picks the engine
the record asked for -- by comparing its PCM byte-for-byte against a DIRECT call
to that same renderer.

So it fails if:

* `ENGINE_ID_OFFSET` does not name the word `pk_render` puts the family byte in;
* the dispatcher's compare values drift from the composer's ENGINE_* ids;
* the record layout assumed by the transport stops matching.

It is deliberately independent of the admission fixture that defeated an earlier
hand-rolled probe: the record pointer (`x:$209`) and the per-core track slot
(`x:$418`) are both seeded the way the real seam seeds them.
"""
from __future__ import annotations

import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tools/perky"),
                str(ROOT / "modules/perky"), str(ROOT / "tools/verify")]

OUT = ROOT / "out/perky/dsp-3algo"
REC = 0x300          # where this gate parks the record
D = "$"
FRAMES = 16


def die(message: str) -> "NoReturn":
    raise SystemExit("verify-perky-3algo-engine-join: " + message)


def load_composer():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "composer_join", ROOT / "tools/perky/build_dsp_3algo_source.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["composer_join"] = module
    spec.loader.exec_module(module)
    return module


def pk_render_record(p: list[int], trig: int) -> list[int]:
    """Mirror of control.c pk_render's packing, exactly.

        record[0] = 0x504b0000u;
        record[1] = 0x59310000u | trig;
        record[2] = record[3] = 0;
        for (k = 0; k < 6u; ++k)
            record[4u + k] = ((uint32_t)p[2u * k] << 16) | p[2u * k + 1u];

    then the transport splits each long into TWO DSP words (high, low).
    """
    if len(p) != 12:
        die("p[] must be 12 bytes")
    record = [0x504B0000, 0x59310000 | (trig & 0xFFFF), 0, 0]
    for k in range(6):
        record.append(((p[2 * k] & 0xFF) << 16) | (p[2 * k + 1] & 0xFF))
    # Split each ColdFire long into (high, low) DSP words.
    words: list[int] = []
    for value in record:
        words.append((value >> 16) & 0xFFFF)
        words.append(value & 0xFFFF)
    if len(words) != 20:
        die(f"record expands to {len(words)} DSP words, expected 20")
    return words


def assemble(composer, text: str, tag: str) -> tuple[Path, dict[str, int]]:
    asm, binary, sym = (OUT / f"join_{tag}.{ext}" for ext in ("asm", "bin", "sym"))
    asm.write_text(text)
    result = subprocess.run(
        [str(composer.ASM), "-in", str(asm), "-org", format(composer.DSP_ORG, "x"),
         "-out", str(binary), "-sym", str(sym)],
        capture_output=True, text=True)
    if result.returncode:
        die(f"{tag}: dsp_asm failed:\n{result.stdout[-3000:]}")
    labels = {p[0]: int(p[1], 16)
              for p in map(str.split, sym.read_text().splitlines()) if len(p) == 2}
    return binary, labels


def drive(composer, binary: Path, labels: dict, entry: str, data: str,
          tag: str) -> tuple[list[int], list[int]]:
    data_path = OUT / f"join_{tag}.data"
    data_path.write_text(data)
    script = OUT / "join.script"
    script.write_text(" ".join(["0"] * 12 + ["-1"]) + "\n")
    pcm = OUT / f"join_{tag}.raw"
    state = OUT / f"join_{tag}.state"
    result = subprocess.run(
        [str(OUT / "bd909_host"), "-code", str(binary),
         "-org", format(composer.DSP_ORG, "x"),
         "-entry", format(labels[entry], "x"), "-data", str(data_path),
         "-script", str(script), "-out", str(pcm), "-state", str(state),
         "-state-words", "64", "-statebase", format(composer.VOICE_BASE, "x"),
         "-frames", str(FRAMES), "-meter", str(OUT / f"join_{tag}.meter"),
         "-cycle-meter", "1"],
        capture_output=True, text=True)
    if result.returncode:
        die(f"{tag}: dsp_host failed:\n{result.stderr[-2000:]}")
    got = [struct.unpack(f"<{2 * FRAMES}i", pcm.read_bytes())[i]
           for i in range(0, 2 * FRAMES, 2)]
    words = [int(v, 16) & 0xFFFF for v in state.read_text().split()[:64]]
    return got, words


def main() -> None:
    composer = load_composer()

    # One fixture state, shared by every case so only the dispatch differs.
    import fold_drum_compact as fold
    case = ROOT / "out/perky/engine-fixtures/engine-1-mode-1-corner-0"
    state = fold.FoldDrum1.from_arm(
        (case / "wrapper-window-before.bin").read_bytes()[0xC4:0xC4 + 0xF4]).words
    state = state + [0] * 24

    source = composer.normalize(composer.compose()).replace("@CONT@", "$000426").replace("@NEXT@", "$000426")

    # ---- direct renderer calls (the reference for each engine) -------------
    direct_probe = (
        f"join_direct:\n"
        f"        move    #>{D}{composer.VOICE_BASE:x},r6\n"
        f"        move    #>{D}{composer.SCRATCH_ABI:x},r5\n"
        f"        jsrl    pk_simple_base\n"
        f"        jsrl    pk_fold_voice\n"
        f"        rts\n")
    # ---- dispatcher calls, one per engine id, with a pk_render record ------
    dispatch_cases = {}
    for engine in (composer.ENGINE_FOLD, composer.ENGINE_BASS,
                   composer.ENGINE_SNARE):
        p = [0] * 12
        # p[0..5] are the control words; p[6] is overwritten with MODE by
        # pk_render, and the prepare paths stamp the family into p[11].
        p[11] = engine
        words = pk_render_record(p, trig=1)
        if len(words) <= composer.ENGINE_ID_OFFSET:
            die(f"engine offset {composer.ENGINE_ID_OFFSET:#x} is past the "
                f"{len(words)}-word record")
        if words[composer.ENGINE_ID_OFFSET] != engine:
            die(f"pk_render packing puts {words[composer.ENGINE_ID_OFFSET]:#06x} "
                f"at word {composer.ENGINE_ID_OFFSET:#x}, expected the family "
                f"byte {engine:#x} -- the producer/consumer offset disagrees "
                f"with pk_render's own packing")
        dispatch_cases[engine] = words

    report = {"schema": "perky-3algo-engine-join-v1",
              "engine_id_offset": hex(composer.ENGINE_ID_OFFSET),
              "frames": FRAMES, "engines": {}}

    print(f"ENGINE_ID_OFFSET = {composer.ENGINE_ID_OFFSET:#x}  "
          f"(pk_render packs the family byte there: OK for all three)\n")

    # ONE binary holding a direct probe per renderer AND the dispatcher, so
    # every case runs on identical code layout.
    probe = (
        f"join_direct_fold:\n"
        f"        move    #>{D}{composer.VOICE_BASE:x},r6\n"
        f"        move    #>{D}{composer.SCRATCH_ABI:x},r5\n"
        f"        jsrl    pk_simple_base\n"
        f"        jsrl    pk_fold_voice\n"
        f"        rts\n"
        f"join_direct_bass:\n"
        f"        move    #>{D}{composer.VOICE_BASE:x},r6\n"
        f"        move    #>{D}{composer.SCRATCH_ABI:x},r5\n"
        f"        jsrl    pk3d_bass_voice\n"
        f"        rts\n"
        f"join_direct_snare:\n"
        f"        move    #>{D}{composer.VOICE_BASE:x},r6\n"
        f"        move    #>{D}{composer.SCRATCH_ABI:x},r5\n"
        f"        jsrl    pk3d_snare_voice\n"
        f"        rts\n"
        f"join_dispatch:\n"
        f"        move    #>{D}{REC:x},r4\n"
        f"        jsrl    pk3d_source\n"
        f"        move    #>{D}0,r0\n"
        f"        rts\n")
    binary, labels = assemble(composer, probe + "\n" + source, "all")
    for name in ("join_direct_fold", "join_direct_bass", "join_direct_snare",
                 "join_dispatch"):
        if name not in labels:
            die(f"assembled probe is missing {name}")

    # The renderers read the shipped Y ledger (waves, envelope, pitch); without
    # it the oscillator reads silence and every engine looks identical.
    import importlib.util as _ilu
    _spec = _ilu.spec_from_file_location(
        "join_exec", ROOT / "tools/verify/verify_perky_3algo_exec.py")
    _exec = _ilu.module_from_spec(_spec)
    sys.modules["join_exec"] = _exec
    _spec.loader.exec_module(_exec)
    _e1, _e2, _, _ = _exec.make_envelopes()
    _ia = struct.pack("<257H", *[(i * 257 + i * i) & 0xFFFF for i in range(257)])
    _ib = struct.pack("<257H", *[(65535 - i * 251) & 0xFFFF for i in range(257)])
    ytext = _exec.tables_text(_e1, _e2, _ia, _ib,
                              ROOT / "out/perky/simple-drum-assets")

    base_data = (
        f"X {composer.VOICE_BASE:x} "
        + " ".join(f"{v:06x}" for v in state) + "\n"
        + f"X {composer.SCRATCH_BASE:x} "
        + " ".join(["000000"] * composer.SCRATCH_WORDS) + "\n"
        # The Fold second-difference cache needs the 'no block decoded'
        # sentinel, or block 0 looks already decoded and Fold stores silence.
        + f"X 3964 " + " ".join(["ffffff"] * 17) + "\n"
        + f"X 38e8 000000 000000 000000 000000\n"
        + ytext)

    direct_entry = {composer.ENGINE_FOLD: "join_direct_fold",
                    composer.ENGINE_BASS: "join_direct_bass",
                    composer.ENGINE_SNARE: "join_direct_snare"}
    reference = {}
    for engine, entry in direct_entry.items():
        got, _ = drive(composer, binary, labels, entry, base_data,
                       f"d{engine}")
        reference[engine] = got
        print(f"direct  engine {engine:2d} "
              f"({composer.ENGINE_LABELS[engine]:10s}) PCM[:4] = {got[:4]}")

    def seam_scaled(values: list[int]) -> list[int]:
        """The composed seam's output stage, exactly.

        pk3z_scale reads each of the 32 audio words and applies `asl a` eight
        times, then stores `a1` -- so the shipped word is the renderer's 24-bit
        output shifted left 8 and truncated to 24 bits. The host then
        sign-extends that word. A direct renderer call does NOT go through this
        stage, which is the whole of the difference.
        """
        out = []
        for v in values:
            w = ((v & 0xFFFFFF) << 8) & 0xFFFFFF
            out.append(w - 0x1000000 if w & 0x800000 else w)
        return out

    if reference[composer.ENGINE_FOLD][:4] == [0, 0, 0, 0]:
        die("the direct Fold reference is silent even with the cache sentinel "
            "seeded -- the fixture is wrong, so this gate cannot judge the join")

    print()
    distinct = {tuple(v[:8]) for v in reference.values()}
    if len(distinct) != 3:
        die(f"the three direct renderers did not produce three distinct results "
            f"({len(distinct)} distinct) -- the fixture cannot discriminate them")

    failures = []
    for engine, words in dispatch_cases.items():
        data = (base_data
                + f"X {REC:x} " + " ".join(f"{w:06x}" for w in words) + "\n"
                + f"X 209 {REC:06x}\n"
                + f"X 418 {composer.ADMITTED_SLOT:06x}\n"
                # The dispatcher now RE-SEEDS the voice block when the engine id
            # changes (it is shared by three engines with different layouts, and
            # without the re-seed a switch railed at full scale). This case tests
            # the STEADY-STATE renderer, so it seeds the ledger to say "this
            # engine is already current" and no re-seed fires.
            + f"X {composer.ENGINE_LEDGER:x} "
            f"{0x8000 | engine:06x}\n"
            + f"X 20e 000000\n")
        got, _ = drive(composer, binary, labels, "join_dispatch", data,
                       f"e{engine}")
        want = seam_scaled(reference[engine])
        ok = got == want
        label = composer.ENGINE_LABELS[engine]
        print(f"dispatch engine {engine:2d} ({label:10s}) PCM[:4] = {got[:4]}  "
              f"want (direct x2^8) {want[:4]}  "
              f"{'MATCH' if ok else 'MISMATCH'}")
        report["engines"][str(engine)] = {
            "label": label, "pcm_head": got[:4],
            "expected_from_direct": want[:4], "matches_direct_scaled": ok}
        if not ok:
            failures.append(label)

    print()
    if failures:
        die("the dispatcher did not reproduce the direct renderer for: "
            + ", ".join(failures)
            + f" -- so the family byte is not arriving at word "
              f"{composer.ENGINE_ID_OFFSET:#x} the way pk_render packs it")
    print("perky-3algo-engine-join: PASS (pk_render's packing places the family "
          f"byte at DSP word {composer.ENGINE_ID_OFFSET:#x}; the composed "
          "dispatcher reads that word; and for EACH of the three engine ids the "
          "dispatched render equals a direct call to that renderer passed "
          "through the seam's own x2^8 output stage)")
    (OUT / "engine-join.json").write_text(
        __import__("json").dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()

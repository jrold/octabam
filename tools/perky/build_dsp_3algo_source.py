#!/usr/bin/env python3
"""Compose the reduced two-voice / three-algorithm Perky DSP machine.

The reduced target (``PERKY_DSP_2VOICE_TARGET.md``) exposes exactly three
synthesis algorithms on Octatrack tracks 1 and 5:

* Fold Drum 1      -- the qualified ``fold_drum_voice.asm`` renderer,
* Resonant Bass    -- the qualified ``resonant_dsp.py`` bass recipe,
* Resonant Snare   -- the qualified ``resonant_dsp.py`` snare recipe.

Track 1 is served by DSP payload B (its core carries tracks 1-4) and track 5
by payload A (tracks 5-8), so there is exactly one Perky source slot per core.

This module composes the three already-gated renderers into ONE source with
every shared body emitted once: the exact ``pk_u32_*`` low32 arithmetic, the
RNG/noise stream, the hardware noise sample-and-hold helper, the shared
envelope renderer (``pk_noise_hat_envelope``), the common envelope interpolation
tables and the Fold/Simple primitive set. The result is the real shipping
composition -- its linked P footprint is what ``measure()`` reports, never the
sum of the standalone probes.

The generated source keeps ``@CONT@`` unresolved; ``build_bus`` applies the
normal PERKY A/B continuation substitution. ``DSP_ORG`` is the P base the
composed code is assembled at.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
PERKY = ROOT / "modules/perky"
ASM = ROOT / "vendor/dsp56300/build/source/dsp_host/dsp_asm"

DSP_ORG = 0x1000

# Reduced machine: the only three algorithms, and the only two capable tracks.
ENGINE_FOLD = 0
ENGINE_BASS = 10
ENGINE_SNARE = 11
ENGINE_LABELS = {
    ENGINE_FOLD: "FOLD DRUM",
    ENGINE_BASS: "RES BASS",
    ENGINE_SNARE: "RES SNARE",
}
# x:$418 is stock's per-core track position. Payload A carries tracks 5-8 and
# payload B tracks 1-4; the reduced machine admits ONLY the first slot of each
# core, which is track 5 on A and track 1 on B.
ADMITTED_SLOT = 0x00

# ---------------------------------------------------------------------------
# Private X map (per core). Voice state is shared between the three algorithms:
# only one of them can ever be selected on a track, so they reuse one block.
VOICE_BASE = 0x3800
VOICE_BYTES = 108            # Resonant Snare's 101-word object plus guard
VOICE_STRIDE = VOICE_BYTES
VOICES = 4
RNG_BASE = VOICE_BASE + VOICES * VOICE_STRIDE          # $3954
EVENT_OFFSET = RNG_BASE + 4                            # $3958
ADMIT_LATCH = EVENT_OFFSET + 1                         # $3959
SCRATCH_BASE = 0x3900
SCRATCH_WORDS = 188

# Algorithm tag + last-applied record word kept inside each voice block, past
# the largest renderer object, so an algorithm switch can detect a stale state.
TAG_OFFSET = 102        # engine id this voice block was initialised for
APPLIED_OFFSET = 103    # last record word 4 (control word) applied

# ---------------------------------------------------------------------------
# Y table layout. All absolute bases are payload-relative and rewritten per
# payload by build_bus (the stock tables shift by sixteen between A and B).
Y_ENV1 = 0x2000         # 1025 u16, packed 3-in-2 -> 683 DSP words
Y_ENV2 = 0x2280         # same
Y_INTERP_A = 0x2500     # 257 u16 direct
Y_INTERP_B = 0x2600     # 257 u16 direct
Y_WAVES = 0x07A5        # three 256-point Fold/Simple waves, 512 DSP words
Y_SIMPLE_ENV = 0x0A50   # 1024-point direct amplitude envelope, 683 words
Y_PITCH = 0x0EFB        # 67-word packed pitch basis
Y_TOTAL_END = Y_INTERP_B + 257

ENV1_WORDS = 683
ENV2_WORDS = 683
WAVE_WORDS = 512
SIMPLE_ENV_WORDS = 683
PITCH_WORDS = 67

# Generated composite label prefix; avoids every existing PERKY label.
P = "pk3d_"   # composer dispatch namespace


def die(msg: str) -> "NoReturn":
    raise SystemExit("build-dsp-3algo-source: " + msg)


def _read(name: str) -> str:
    path = PERKY / name
    if not path.exists():
        die(f"missing {path}")
    return path.read_text()


def _section(name: str, body: str) -> str:
    return f"; ===== BEGIN {name} =====\n{body}\n; ===== END {name} =====\n"


_RESONANT_CACHE: dict[str, str] = {}
# Largest per-family variable count; pre-seeding both families to it makes the
# shared decoder cores address identical r4 slots (see resonant_dsp.source).
VARIABLE_FLOOR = 38


def resonant_bodies() -> tuple[str, str]:
    """Bass and snare recipes with their private helper labels renamed.

    ``resonant_dsp.source`` emits the whole family body (entry, sample loop,
    decay core, resonator core, noise, envelope renderer and math helpers).
    Both families share those helpers almost verbatim, so the composer keeps
    ONE copy: every label this function returns is prefixed per family and the
    duplicate helpers are stripped before composition.
    """
    import sys
    sys.path.insert(0, str(PERKY))
    import resonant_dsp as recipe
    for family in ("bass", "snare"):
        if family not in _RESONANT_CACHE:
            text, _ = recipe.source(family, core_variables_fixed=True,
                                           interp_a=Y_INTERP_A, interp_b=Y_INTERP_B)
            _RESONANT_CACHE[family] = text
    return _RESONANT_CACHE["bass"], _RESONANT_CACHE["snare"]


def split_resonant(text: str, family: str) -> tuple[str, str, str]:
    """Return (family voice, shared resonator/decay core, shared tail).

    A recipe is laid out voice -> ``pk_resonant_decay`` -> ``pk_resonant_core``
    -> ``pk_resonant_noise`` -> envelope -> math. The first three bodies are
    *identical instruction sequences* for bass and snare (only the decoder's
    variable-slot names differ), and the tail is shared verbatim. The composer
    therefore keeps ONE copy of each and points both voices at it.
    """
    voice = "pk_resonant_" + family + "_voice:"
    if text.count("\n" + voice) != 1:
        die(f"{family}: expected exactly one voice entry")
    head, rest = text.split("\n" + voice, 1)
    head = "\n" + voice + rest
    head = head.split("\npk_resonant_decay:", 1)
    if len(head) != 2:
        die(f"{family}: expected exactly one shared decay core")
    voice_text, cores = head
    cores = "\npk_resonant_decay:" + cores
    cores, tail = cores.split("\npk_resonant_noise:", 1)
    return voice_text, cores, "\npk_resonant_noise:" + tail


def family_prefix(family: str) -> str:
    """A namespace that is not a prefix of the other family's namespace.

    ``dsp_asm`` resolves a label by PREFIX, so ``pk3_bass_`` and ``pk3_bass``
    must never both exist. One distinct letter per family cannot collide.
    """
    return "pk3" + family[0] + "_"


def rename_family(text: str, family: str) -> str:
    """Namespace every family-local label so the two recipes can coexist."""
    prefix = family_prefix(family)
    labels = re.findall(r"(?m)^([A-Za-z0-9_]+):", text)
    for label in sorted(set(labels), key=len, reverse=True):
        if label.startswith("pk3"):
            continue
        text = re.sub(rf"(?<![A-Za-z0-9_]){re.escape(label)}(?![A-Za-z0-9_])",
                      prefix + label, text)
    return text


def extra_body() -> str:
    """Shared primitives the resonant recipes do not carry themselves."""
    parts = [
        _read("noise_tone_voice_native_xstate.asm").split("\npknv_noise:", 1)[1],
        _read("noise_tone_math.asm"),
    ]
    return "\npknv_noise:" + "\n".join(parts)


def fold_body() -> str:
    """Fold Drum 1 plus the Simple Drum primitives it composes."""
    parts = [_read("fold_drum_voice.asm")]
    for name, label in (("envelope", "pk_simple_envelope"),
                        ("frequency", "pk_simple_frequency"),
                        ("oscillator", "pk_simple_oscillator")):
        text = _read(f"simple_drum_{name}.asm")
        text = text[text.index("\n" + label + ":"):]
        parts.append(text)
    parts.append(_read("simple_drum_delta.asm"))
    return "\n".join(parts)


def compose(env1_base: int = Y_ENV1, env2_base: int = Y_ENV2,
            interp_a: int = Y_INTERP_A, interp_b: int = Y_INTERP_B) -> str:
    """Build the composed shipping source text (with @CONT@ unresolved)."""
    bass_text, snare_text = resonant_bodies()
    bass_voice, bass_cores, bass_tail = split_resonant(bass_text, "bass")
    snare_voice, snare_cores, snare_tail = split_resonant(snare_text, "snare")

    # Both recipes emit the decoder cores as the same instruction sequence; the
    # only textual difference is how their local labels are numbered (bass and
    # snare reach the decoder-generator with different label counters). Rewrite
    # both to a canonical numbering and require exact equality, then keep ONE
    # copy. Anything else -- a different guard, a different shift, a different
    # slot -- fails the build rather than being silently deduplicated.
    def canon(text: str) -> str:
        mapping: dict[str, str] = {}

        def repl(match: re.Match[str]) -> str:
            return mapping.setdefault(match.group(1),
                                      f"pkr_label_{len(mapping):05d}")

        return re.sub(r"\b(pkr_label_\d+)\b", repl, text)

    if canon(bass_cores) != canon(snare_cores):
        die("resonant resonator/decay cores are not instruction-identical; "
            "deduplication would not be exact")
    if canon(bass_tail) != canon(snare_tail):
        die("resonant shared tails are not instruction-identical")
    cores = bass_cores
    # The tail ends in the same exact low32/RNG helper block that
    # ``resident_primitives`` carries once for Fold and for the envelope
    # renderer. Keeping both emitted every helper twice; measure the boundary
    # and drop the duplicate instead.
    marker = "\npk_u32_add:"
    if bass_tail.count(marker) != 1:
        die("resonant tail does not expose exactly one shared math block")
    tail = bass_tail.split(marker, 1)[0]
    # ``pk_math_probe`` is the standalone dispatcher the isolated limb probes
    # call; the shipping renderers call ``pk_u32_*`` directly. Drop the copy
    # that came in with the resonant recipe -- the primitives section keeps
    # the one the standalone gates and out-of-image probes still exercise.
    probe_start = tail.find("\npk_math_probe:")
    probe_end = tail.find("\n; Exact modulo-2^32 add.")
    if probe_start < 0 or probe_end < 0 or probe_end < probe_start:
        die("could not locate the standalone math dispatcher in the shared tail")
    tail = tail[:probe_start] + "\n" + tail[probe_end + 1:]
    # The envelope renderer carries its two table bases as absolute
    # immediates. Substitute the shipping addresses; the renderer's own label
    # remains the branch target, so no new forward branch is introduced.
    if tail.count("#>$000c51,r1") != 1 or tail.count("#>$0009a5,r1") != 1:
        die("envelope renderer's embedded table bases moved")
    tail = tail.replace("#>$000c51,r1", f"#>${env2_base:06x},r1")
    tail = tail.replace("#>$0009a5,r1", f"#>${env1_base:06x},r1")

    b = rename_family(bass_voice, "bass")
    s = rename_family(snare_voice, "snare")

    # Point both voices at the single copies of the shared cores and helpers.
    for family, text in (("bass", b), ("snare", s)):
        pass
    b = b.replace(f"{family_prefix('bass')}pk_resonant_decay", "pk_resonant_decay")
    b = b.replace(f"{family_prefix('bass')}pk_resonant_core", "pk_resonant_core")
    b = b.replace(f"{family_prefix('bass')}pk_resonant_noise", "pk_resonant_noise")
    b = b.replace(f"{family_prefix('bass')}pk_noise_hat_envelope", "pk_noise_hat_envelope")
    b = b.replace(f"{family_prefix('bass')}pk_u32_", "pk_u32_")
    s = s.replace(f"{family_prefix('snare')}pk_resonant_decay", "pk_resonant_decay")
    s = s.replace(f"{family_prefix('snare')}pk_resonant_core", "pk_resonant_core")
    s = s.replace(f"{family_prefix('snare')}pk_resonant_noise", "pk_resonant_noise")
    s = s.replace(f"{family_prefix('snare')}pk_noise_hat_envelope", "pk_noise_hat_envelope")
    s = s.replace(f"{family_prefix('snare')}pk_u32_", "pk_u32_")
    b = b.replace(f"{family_prefix('bass')}pk_resonant_bass_voice:", f"{P}bass_voice:")
    s = s.replace(f"{family_prefix('snare')}pk_resonant_snare_voice:", f"{P}snare_voice:")
    if f"{P}bass_voice:" not in b or f"{P}snare_voice:" not in s:
        die("resonant entry points were not renamed")

    text = "\n".join([
        "; Composed reduced Perky DSP machine: Fold Drum 1 + Resonant Bass +",
        "; Resonant Snare, one algorithm per track, one Perky track per core.",
        f"{P}source:",
        "        move    a,x:>$20e               ; replay displaced stock op",
        "        move    x:>$418,b               ; this core's track slot",
        "        tst     b",
        "        bne     pk3v_not_admitted",
        "        move    x:>$209,r4              ; current source record",
        "        move    #>$00504b,x0",
        "        move    x:(r4),b",
        "        and     #>$ffff,b",
        "        cmp     x0,b",
        "        bne     pk3v_not_admitted",
        "        move    #>$005931,x0",
        "        move    x:(r4+$2),b",
        "        and     #>$ffff,b",
        "        cmp     x0,b",
        "        bne     pk3v_not_admitted",
        "        bra     pk3v_hit",
        "pk3v_not_admitted:",
        "        rts                             ; stock/other source runs",
        "pk3v_hit:",
        "        ; One Perky voice per core: the first admitted PERKY record wins",
        "        ; for the whole frame; every later one renders silence.",
        "        move    x:>$" + format(ADMIT_LATCH, "x") + ",a",
        "        tst     a",
        "        bne     pk3c_silence",
        "        move    #>$1,a",
        "        move    a1,x:>$" + format(ADMIT_LATCH, "x"),
        "        ; Consume the same FLEX ring slot advance as the qualified seam.",
        "        move    x:>$20b,a",
        "        add     #>$80,a",
        "        move    a,x:>$20b",
        "        ; Engine id lives in record word 3 (p[11]).",
        "        move    x:(r4+$6),b",
        "        and     #>$ffff,b",
        "        move    b1,x0                   ; x0 = engine id",
        "        move    x:>$" + format(EVENT_OFFSET, "x") + ",a",
        "        move    a,x:>$" + format(EVENT_OFFSET, "x"),
        "        move    #>$003800,r6            ; this core has exactly one voice",
        "        move    #>$" + format(SCRATCH_BASE, "x") + ",r5",
        "        move    #>$ffffff,m0",
        "        move    #>$ffffff,m1",
        "        move    #>$ffffff,m2",
        "        move    #>$ffffff,m3",
        "        move    #>$ffffff,m4",
        "        move    #>$ffffff,m5",
        "        move    #>$ffffff,m6",
        "        move    #$0,r0                  ; stock source buffer X:0",
        "        ; Record words 4..7 carry this block's prepared controls.",
        "        move    x:(r4+$8),a",
        "        move    a1,x:(r6+$" + format(APPLIED_OFFSET, "x") + ")",
        "        move    x:(r4+$a),b",
        "        move    x:(r4+$c),a",
        "        move    a1,x:(r5+$70)",
        "        move    b1,x:(r5+$71)",
        "        move    x:(r4+$e),a",
        "        move    a1,x:(r5+$72)",
        "        ; Dispatch on the masked engine id.",
        "        move    x0,a",
        "        cmp     #>$" + format(ENGINE_FOLD, "x") + ",a",
        '        beq     pk3e_entry',
        "        cmp     #>$" + format(ENGINE_BASS, "x") + ",a",
        '        beq     pk3n_entry',
        "        cmp     #>$" + format(ENGINE_SNARE, "x") + ",a",
        '        beq     pk3a_entry',
        '        bra     pk3c_silence',
        'pk3e_entry:',
        "        jsrl    pk_simple_base",
        "        jsrl    pk_fold_voice",
        '        bra     pk3i_finish',
        'pk3n_entry:',
        "        jsrl    " + P + "bass_voice",
        '        bra     pk3i_finish',
        'pk3a_entry:',
        "        jsrl    " + P + "snare_voice",
        'pk3i_finish:',
        '        bra     pk3z_scale',
        'pk3c_silence:',
        "        move    #>$ffffff,m0",
        "        move    #$0,r0",
        "        clr     a",
        "        do      #$20,pk3y_silence_done",
        "        move    a1,x:(r0)+",
        'pk3y_silence_done:',
        "        nop",
        'pk3z_scale:',
        "        move    #$0,r0",
        "        do      #$20,pk3x_scaled",
        "        move    x:(r0),a",
        "        asl     a",
        "        asl     a",
        "        asl     a",
        "        asl     a",
        "        asl     a",
        "        asl     a",
        "        asl     a",
        "        asl     a",
        "        move    a1,x:(r0)+",
        'pk3x_scaled:',
        "        nop",
        "        move    #>$10,n7",
        "        move    ssh,x0",
        "        jmp     @CONT@",
        "",
        _section("resonant_bass.asm", b),
        _section("resonant_snare.asm", s),
        _section("resident_cores.asm", cores),
        _section("resident_tail.asm", tail),
        _section("fold_drum_1.asm", fold_body()),
        _section("resident_primitives.asm", extra_body()),
    ])
    return text


def normalize(text: str) -> str:
    """Mechanical passes every composed PERKY source needs."""
    import sys
    sys.path.insert(0, str(ROOT / "tools/perky"))
    from build_noise_tone_synth_source import (
        force_long_local_jsr,
        relativize_local_conditionals,
    )
    text = relativize_local_conditionals(text)
    text = force_long_local_jsr(text)
    labels = re.findall(r"(?m)^([A-Za-z0-9_]+):", text)
    for shorter in labels:
        for longer in labels:
            if shorter != longer and longer.startswith(shorter):
                die(f"assembler label prefix collision: {shorter} / {longer}")
    return text


def measure(text: str, out: Path) -> int:
    if not ASM.exists():
        die(f"missing {ASM}; run `make setup` before measuring")
    out.parent.mkdir(parents=True, exist_ok=True)
    temp = out.with_suffix(".measure.asm")
    binary = out.with_suffix(".measure.bin")
    temp.write_text(text.replace("@CONT@", "$000426"))
    result = subprocess.run([str(ASM), "-in", str(temp), "-org", format(DSP_ORG, "x"),
                             "-out", str(binary)],
                            capture_output=True, text=True)
    if result.returncode:
        die("DSP assembler failed:\n" + result.stdout[-6000:] + result.stderr[-3000:])
    size = binary.stat().st_size
    if size % 3:
        die(f"assembled binary is {size} bytes, not whole DSP words")
    return size // 3


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path,
                    default=ROOT / "out/perky/dsp-3algo/perky_3algo.asm")
    ap.add_argument("--measure", action="store_true")
    args = ap.parse_args()
    text = normalize(compose())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text)
    words = measure(text, args.out) if args.measure else 0
    print(f"reduced Perky DSP source: {args.out} ({len(text):,} bytes)"
          + (f"; {words} composed P words" if words else ""))
    if args.measure:
        (args.out.parent / "layout.json").write_text(json.dumps({
            "schema": "perky-dsp-3algo-v1",
            "p_words": words, "p_org": DSP_ORG,
            "engines": {str(k): v for k, v in ENGINE_LABELS.items()},
            "admitted_slot": ADMITTED_SLOT,
            "voice_base": VOICE_BASE, "voice_bytes": VOICE_BYTES,
            "scratch_base": SCRATCH_BASE, "scratch_words": SCRATCH_WORDS,
            "y": {"env1": Y_ENV1, "env2": Y_ENV2, "interp_a": Y_INTERP_A,
                  "interp_b": Y_INTERP_B, "waves": Y_WAVES,
                  "simple_env": Y_SIMPLE_ENV, "pitch": Y_PITCH},
        }, indent=2) + "\n")


if __name__ == "__main__":
    main()

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
# WHERE THE ENGINE ID LIVES IN THE FLEX RECORD -- DERIVED, NOT GUESSED.
#
# control.c's pk_render builds p[12] (p[0..5] from the DSP control words,
# p[6..11] from the track's page slots) and packs it into record[10]:
#
#     record[0] = 0x504b0000u;  record[1] = 0x59310000u | trig;
#     record[2] = record[3] = 0;
#     for (k = 0; k < 6; ++k)
#         record[4+k] = ((uint32_t)p[2k] << 16) | p[2k+1];
#
# The transport splits each ColdFire long into TWO DSP words (high, low), so the
# words the DSP addresses as x:(r4+N) are:
#
#     N : 0     1     2     3      4  5  6  7 | 8   9   10  11  12  13  14  15  16  17  18  19
#         'PK'  0    'Y1'  trig    0  0  0  0 | p0  p1  p2  p3  p4  p5  p6  p7  p8  p9  p10 p11
#
# That mapping is CONFIRMED by the qualified seam itself, which reads
#     move x:(r4),b    / cmp #>$00504b      -> word 0 = 'PK'
#     move x:(r4+$2),b / cmp #>$005931      -> word 2 = 'Y1'
#     move x:(r4+$3),b                      -> word 3 = the trigger flag
# (modules/perky/probe_glue.asm). All three line up, so the rest of the table
# can be trusted.
#
# p[11] is the FAMILY byte: pk_fold_prepare stamps 0, pk_simple_prepare stamps 2,
# and the engine chooser (pk_engine_select) persists the selected model into the
# page slot that feeds p[11] in the first place. p[11] therefore carries the
# selection end to end, and it lands at DSP word 19.
ENGINE_ID_OFFSET = 0x13

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
# The shared RNG stream is a FIXED absolute address: the RNG/noise helper every
# renderer calls stores its two u32 limbs at X:$38e8..$38eb, which is part of
# the qualified PERKY2 source layout and is not a register-relative slot. A
# composer that moved it would silently give every renderer a different stream,
# so it stays where the helper puts it and the ledger below starts after it.
RNG_BASE = 0x38E8                                      # $38e8..$38eb
# The voice block stops at RNG_GAP_START; the RNG limbs start at RNG_GAP_END.
# A gate seeds both regions instead of relying on an implied zero run.
RNG_GAP_START = VOICE_BASE + VOICE_BYTES               # $386c
RNG_GAP_END = RNG_BASE
EVENT_OFFSET = RNG_BASE + 4                            # $38ec
ADMIT_LATCH = EVENT_OFFSET + 1                         # $38ed
ENGINE_LEDGER = ADMIT_LATCH     # last engine id, tagged 0x8000; free since the latch was removed
SCRATCH_BASE = 0x3900
# The ONE scratch base every body in this machine is written against: the
# shared low32/RNG arithmetic carries `x:(r5-$40)`-style displacements, so the
# caller advances r5 by 0x40 before entering any renderer. SCRATCH_BASE stays
# the address of the scratch BLOCK (that is what gets seeded and dumped);
# SCRATCH_ABI is the register value the bodies expect.
SCRATCH_ABI = SCRATCH_BASE + 0x40
SCRATCH_WORDS = 188

# Algorithm tag + last-applied record word kept inside each voice block, past
# the largest renderer object, so an algorithm switch can detect a stale state.
TAG_OFFSET = 102        # engine id this voice block was initialised for
APPLIED_OFFSET = 103    # last record word 4 (control word) applied

# ---------------------------------------------------------------------------
# Y table layout. All absolute bases are payload-relative and rewritten per
# payload by build_bus (the stock tables shift by sixteen between A and B).
# The Fold/Simple bodies carry their table bases as ABSOLUTE immediates
# (``pk_simple_envelope`` -> X's shape-0 curve, ``pk_simple_oscillator`` ->
# the wave stream, ``pk_simple_base`` -> the packed pitch basis), so their
# addresses are fixed by the qualified renderer and the ledger has to fit
# around them rather than the other way round.
Y_WAVES = 0x07A5        # three 256-point Fold/Simple waves, 512 DSP words
Y_SIMPLE_ENV = 0x0C50   # shape-0 direct amplitude curve, 683 words
Y_PITCH = 0x0EFB        # 68-word packed pitch basis (+1 padding)
# The resonant recipes read their two curve banks and two interpolation tables
# through composer-supplied bases, so these four are the composer's choice.
Y_ENV1 = 0x2000         # 1025 u16, packed 3-in-2 -> 683 DSP words
Y_ENV2 = 0x2280         # same
Y_INTERP_A = 0x2500     # 257 u16 direct
Y_INTERP_B = 0x2600     # 257 u16 direct
Y_TOTAL_END = Y_INTERP_B + 257

ENV1_WORDS = 683
ENV2_WORDS = 683
WAVE_WORDS = 512
SIMPLE_ENV_WORDS = 683
PITCH_WORDS = 68

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


def extra_body(shared) -> str:
    """Only what the resonant tail does not already carry.

    The tail already holds the centered low32/RNG/envelope helper block, so
    re-emitting ``noise_tone_math.asm`` here would define every helper twice --
    and, because that copy is uncentered, it would silently take over. The
    noise sample-and-hold helper is the one body the tail lacks.
    """
    body = "\npknv_noise:" + _read("noise_tone_voice_native_xstate.asm").split(
        "\npknv_noise:", 1)[1]
    if "\npknv_refresh:" in shared:
        die("the resonant tail unexpectedly carries the noise helper")
    return body


def centre_displacements(text: str) -> str:
    """Rewrite the uncentred displacements of a body into the centred form.

    ``dsp_source_layout.center_scratch`` does TWO things: it subtracts 0x40 from
    every ``x:(r5+$N)``, and it inserts a prologue that advances r5 by 0x40 at
    the entry label. The pair is address-preserving. This helper does only the
    first half, because in this composition r5 is advanced ONCE by the caller
    (the dispatcher, and every gate probe) rather than by each body -- the Fold
    path is entered twice per block (`pk_simple_base` then `pk_fold_voice`) and
    two prologues would leave r5 0x80 high on the second entry.
    """
    def address(match):
        displacement = int(match.group(1), 16) - 0x40
        if not -64 <= displacement <= 63:
            die(f"centre_displacements: displacement {displacement} is out of "
                f"the -64..63 range the addressing mode allows ({match[0]})")
        return "x:(r5%s$%x)" % ("+" if displacement >= 0 else "-",
                                abs(displacement))
    return re.sub(r"x:\(r5\+\$([0-9a-f]+)\)", address, text)


def strip_scratch_prologue(text: str) -> str:
    """Remove the r5-advance prologue `center_scratch` inserted.

    The resonant recipes carry it; in this composition the caller advances r5
    instead, so leaving it in would advance r5 twice.
    """
    pattern = re.compile(r"[ \t]*move[ \t]+r5,a\n"
                         r"[ \t]*add[ \t]+#>\$40,a\n"
                         r"[ \t]*move[ \t]+a1,r5\n")
    return pattern.sub("", text)


def fold_body() -> str:
    """Fold Drum 1 plus the Simple Drum primitives, on the CENTRED convention.

    The composed machine runs every algorithm against ONE scratch convention,
    and it is the CENTRED one: the shared low32/RNG/envelope helper block the
    resonant tail carries uses ``x:(r5-$40)``-style displacements, so any body
    that reaches it must have r5 advanced by 0x40. The Fold/Simple bodies are
    written uncentred, so their displacements are translated here.

    The advance itself is done ONCE by the caller (the dispatcher, and every
    gate probe) -- see ``centre_displacements``. Leaving the bodies uncentred
    made the Fold voice and the shared math disagree about which word
    ``x:(r5+n)`` names, which is the fault this function exists to prevent.
    """
    parts = [_read("fold_drum_voice.asm")]
    for name, label in (("envelope", "pk_simple_envelope"),
                        ("frequency", "pk_simple_frequency"),
                        ("oscillator", "pk_simple_oscillator")):
        text = _read(f"simple_drum_{name}.asm")
        text = text[text.index("\n" + label + ":"):]
        if name == "envelope":
            # `simple_drum_envelope.asm` reads its shape-0 amplitude curve from
            # the STANDALONE build's literal `Y:$09a5`, whose meaning is
            # "wherever that build put the curve". This composition places it
            # at Y_SIMPLE_ENV, and 0x9a5 is INSIDE the shipped wave region
            # (Y_WAVES = 0x7a5, 768 words -> 0x7a5..0xaa4), so leaving the
            # literal alone makes the envelope reader decode WAVE DATA as its
            # curve. The standalone gates have always made this substitution
            # (`build_dsp_3algo.py`'s fold/Simple-Drum path); the composer did
            # not, so the composed machine ran a wrong envelope.
            count = text.count("#>$0009a5,r1")
            if count != 1:
                die("fold envelope: expected exactly one #>$0009a5,r1 "
                    f"reference, found {count}")
            text = text.replace("#>$0009a5,r1", f"#>${Y_SIMPLE_ENV:06x},r1")
        parts.append(text)
    parts.append(_read("simple_drum_delta.asm"))
    return centre_displacements("\n".join(parts))


DISPATCH_ENTRY = "\n".join([
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
        "        ; ONE PERKY VOICE PER CORE, WITHOUT A LATCH.",
        "        ;",
        "        ; x:$418 is this core's track slot and only slot 0 is admitted",
        "        ; (verified against the stock walk, which steps it 0x20 -> 0x80",
        "        ; over the core's four tracks), so at most ONE track per core",
        "        ; can reach here -- and the target gives each core exactly one",
        "        ; Perky-capable track, so in fact exactly one record per core",
        "        ; can pass the PK/Y1 test at all.",
        "        ;",
        "        ; There used to be a latch at x:$38ed here: set to 1 on the first",
        "        ; admission and NEVER CLEARED, so the first admitted block set it",
        "        ; and every later entry took the silence path -- the Perky track",
        "        ; rendered one block and then silence forever. It guarded a case",
        "        ; that cannot arise, and its only observable effect was that.",
        "        ; Removed rather than cleared, because there is no once-per-block",
        "        ; hook to clear it from: the machine is installed only at the",
        "        ; per-track source site.",
        "        ; Consume the same FLEX ring slot advance as the qualified seam.",
        "        move    x:>$20b,a",
        "        add     #>$80,a",
        "        move    a,x:>$20b",
        "        ; Engine id: low half of the record word at ENGINE_ID_OFFSET.",
        "        move    x:(r4+$" + format(ENGINE_ID_OFFSET, "x") + "),b",
        "        and     #>$ffff,b",
        "        move    b1,x0                   ; x0 = engine id",
        "        ; --- RE-SEED THE VOICE BLOCK WHEN THE ENGINE CHANGES ---------",
        "        ; The three engines SHARE X:0x3800 with DIFFERENT layouts: word",
        "        ; 34 is MODE for Fold, DECAY_A for Resonant Bass and inside RES2",
        "        ; for Resonant Snare. A switch therefore hands the new engine",
        "        ; the old engine's fields as if they were its own. MEASURED",
        "        ; without this: Fold -> Bass railed at full-scale negative",
        "        ; (-8388608 = -2^23, clipped) on the first block, and Fold ->",
        "        ; Snare rendered silence. Both violate the target's \"switch",
        "        ; algorithms safely ... survive algorithm changes between",
        "        ; events\".",
        "        ;",
        "        ; The stored id is TAGGED with 0x8000 so a boot word of zero can",
        "        ; never match a real engine id: the first dispatch after boot",
        "        ; therefore re-seeds too, which is what we want.",
        "        ;",
        "        ; r0/m0 and x1 are free here -- the block below re-sets r0, r5,",
        "        ; r6 and m0..m6 before anything reads them.",
        "        move    x0,a",
        "        add     #>$8000,a               ; the tagged engine id",
        "        move    a,x1",
        "        move    x:>$" + format(ENGINE_LEDGER, "x") + ",b",
        "        cmp     x1,b",
        "        beq     pk3s_same",
        "        move    #>$" + format(VOICE_BASE, "x") + ",r0",
        "        move    #>$ffffff,m0",
        "        clr     a",
        "        do      #$6c,pk3s_zeroed",
        "        move    a1,x:(r0)+",
        "pk3s_zeroed:",
        "        ; ... then load the engine's AUTHENTIC FRESH STATE, which the",
        "        ; ColdFire carries in the record's spare words.",
        "        ;",
        "        ; A zero voice block is silent BY THE ALGORITHM -- the reference",
        "        ; model's `ResonantSnare([0]*WORDS)` peaks at 0 over 64 blocks -- so",
        "        ; clearing alone left the resonant engines silent, which is exactly",
        "        ; what the unit did. The words come from the v1.2.1 init/update/",
        "        ; trigger recovery at a neutral control setting; see",
        "        ; modules/perky/resonant_fresh.h for the provenance.",
        "        ;",
        "        ;   record word 0x14 = the word count (0 for a non-resonant engine)",
        "        ;   record word 0x16 = the first of `count` dense words",
        "        ;",
        "        ; The `tst`/`beq` guard is NOT decoration: on this DSP a `do` with",
        "        ; LC = 0 runs 65,536 iterations.",
        "        ; r1 is built from r4, the record pointer: word 0x16 is an OFFSET,",
        "        ; not an address, and writing `#$0016,r1` set r1 to 0x16 and the",
        "        ; copy read 0x300 words below the record. lua's displacement is",
        "        ; bounded to +-63 and 0x16 is inside it, so this is the safe form.",
        "        move    x:(r4+$14),a",
        "        move    a1,n1",
        "        tst     a",
        "        beq     pk3s_stored",
        "        move    #>$" + format(VOICE_BASE, "x") + ",r0",
        "        move    r4,r1",
        "        lua     (r1+$16),r1",
        "        do      n1,pk3s_copied",
        "        move    x:(r1)+,b",
        "        move    b1,x:(r0)+",
        "pk3s_copied:",
        "pk3s_stored:",
        "        move    x1,b",
        "        move    b1,x:>$" + format(ENGINE_LEDGER, "x"),
        "pk3s_same:",
        "        move    x:>$" + format(EVENT_OFFSET, "x") + ",a",
        "        move    a,x:>$" + format(EVENT_OFFSET, "x"),
        "        move    #>$003800,r6            ; this core has exactly one voice",
        # r5 is the ONE scratch base; the centred convention every body
        # in this machine uses expects it advanced by 0x40 here.
        "        move    #>$" + format(SCRATCH_BASE + 0x40, "x") + ",r5",
        "        move    #>$ffffff,m0",
        "        move    #>$ffffff,m1",
        "        move    #>$ffffff,m2",
        "        move    #>$ffffff,m3",
        "        move    #>$ffffff,m4",
        "        move    #>$ffffff,m5",
        "        move    #>$ffffff,m6",
        "        move    #$0,r0                  ; stock source buffer X:0",
        "        ; n7 IS THE RENDER LENGTH AND MUST BE SET HERE, NOT ASSUMED.",
        "        ;",
        "        ; The renderers' sample loop is `do n7,...`, and on this DSP a `do`",
        "        ; with LC = 0 runs 65,536 iterations, so n7 must be a defined",
        "        ; positive number at every entry. It was NOT: the composed machine",
        "        ; inherited whatever the stock caller left, and stock's last write",
        "        ; before the hook is `move #$14,n7` on payload A -- TWENTY. Measured",
        "        ; through pk3d_source with n7 = 20 the machine writes 40 X words,",
        "        ; eight of them at X:32..X:39, past the 16-frame source buffer and",
        "        ; into the stock scratch at X:0x20 that stock uses every block; the",
        "        ; render also cost 23,063 modeled cycles against 19,011 at n7 = 16,",
        "        ; so every timing figure taken before this fix UNDERSTATED",
        "        ; production by about 21%.",
        "        ;",
        "        ; 16 is the value every gate and captured ARM fixture was validated",
        "        ; at, so pinning it preserves the known-good audio while making the",
        "        ; length explicit.",
        "        ;",
        "        ; THE STOCK CONTRACT IS n7 = X:$20c (payload A 0x42a), the trig's",
        "        ; sample position a = 0..15, with the continuation taking 16 - a",
        "        ; from X:$20d. Adopting it would shorten the render and cut the",
        "        ; cost, but it is NOT adopted here deliberately: it changes which",
        "        ; samples the source owns, and whether the continuation overwrites",
        "        ; a..15 is not established. Anyone adopting it must guard a = 0",
        "        ; explicitly AND prove the frame audio is unchanged. See",
        "        ; tools/verify/verify_perky_3algo_n7.py.",
        "        move    #>$10,n7",
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
        "        ; DELIVER THE MODE. `pk_render` publishes the selected panel mode",
        "        ; in record byte 8 (record word 0x10) and the Fold voice reads the",
        "        ; FIRMWARE mode from X:0x3800+34 -- the qualified transport gate",
        "        ; pins `[1,2,0][record[8]] == words[34]`, which is",
        "        ; (panel + 1) % 3. Nothing else writes that word, so without this",
        "        ; the voice runs in whatever mode the RAM happened to hold.",
        "        ;",
        "        ; FOLD ONLY. Word 34 is MODE here but DECAY_A for Resonant Bass",
        "        ; and inside RES2 for Resonant Snare, so writing it on those paths",
        "        ; would corrupt the decay block.",
        "        ;",
        "        ; r4 is re-loaded first: `pk_simple_base` points r4 at the",
        "        ; second-difference cache, so it no longer addresses the record.",
        "        move    x:>$209,r4",
        "        move    x:(r4+$10),a            ; a = the panel mode (0..2)",
        "        add     #>$1,a                  ; (panel + 1) % 3 ...",
        "        move    a,x1",
        "        move    x1,a                    ; clean a (the low-word trap)",
        "        move    #>$0,x0                 ; a move sets no flags",
        "        cmp     #>$3,a",
        "        tge     x0,a                    ; ... wrap 3 back to 0",
        "        move    a1,x:(r6+$22)           ; the Fold voice's MODE word",
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
        # NOTE: a `move #>$10,n7` used to sit HERE. It was dead -- stock
        # overwrites n7 at the continuation's own entry (payload A
        # 0x42a/0x434, payload B 0x225/0x22f) -- and it hid the fact that
        # OUR renderers read whatever n7 the stock caller left. See the
        # n7 setup in pk3d_source, and tools/verify/verify_perky_3algo_n7.py.
        "        move    ssh,x0",
        "        jmp     @CONT@",
        "",
])


def compose(env1_base: int = Y_ENV1, env2_base: int = Y_ENV2,
            interp_a: int = Y_INTERP_A, interp_b: int = Y_INTERP_B,
            *, with_source: bool = True) -> str:
    """Build the composed shipping source text (with @CONT@ unresolved).

    ``with_source=False`` omits the seam entry point and keeps the three
    renderer bodies plus every shared helper. A qualification gate then
    assembles the EXACT shipping renderers (shared cores and all) and drives
    each entry directly.
    """
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
    # The tail carries the shared low32/RNG/envelope helper block. The recipe's
    # ``center_scratch`` pass rewrote it to the CENTRED convention
    # (``r5-$40``-style) because the resonant prologues advance r5 first. The
    # composed machine runs everything against the UNCENTRED convention: the
    # caller supplies the ABI base, the Fold/Simple bodies address it directly,
    # and the noise sample-and-hold helper does too. So the helper block is
    # translated back here. Leaving it centred while the Fold body is uncentred
    # makes the two name different words for ``x:(r5+n)`` -- silence and a
    # wrong persistent state, with no error anywhere.
    if "\npk_u32_add:" not in bass_tail:
        die("resonant tail does not carry the shared low32 helper block")
    probe_start = bass_tail.find("\npk_math_probe:")
    probe_end = bass_tail.find("\n; Exact modulo-2^32 add.")
    if probe_start < 0 or probe_end < 0 or probe_end < probe_start:
        die("could not locate the standalone math dispatcher in the shared tail")
    tail = bass_tail[:probe_start] + "\n" + bass_tail[probe_end + 1:]

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

    # The resonant voices carry the r5-advance prologue their recipe's
    # center_scratch pass inserted. This composition advances r5 ONCE in the
    # caller instead (the dispatcher and every gate probe), because the Fold
    # path is entered twice per block and two prologues would leave r5 0x80
    # high on the second entry. Their displacements stay centred, so removing
    # the prologue is address-preserving once the caller has advanced.
    b = strip_scratch_prologue(b)
    s = strip_scratch_prologue(s)
    # Only the `move a1,r5` advance belongs to the ABI base and must go. Each
    # voice also derives its VARIABLES pointer with `move r5,a / add #>$40,a /
    # move a1,r4`, which must stay -- it is a derived pointer, not the base.
    base_advance = re.compile(r"move[ \t]+a1,r5")
    for name, body in (("bass", b), ("snare", s)):
        head = body.split(f"{P}{name}_voice:")[1][:120]
        if base_advance.search(head):
            die(f"{name} voice still advances r5 after its prologue was stripped")
        if not re.search(r"move[ \t]+a1,r4", head):
            die(f"{name} voice lost its variables-pointer derivation")

    # The RNG limbs are an absolute address inside the shared helper. If a
    # future edit moves them, the ledger and every gate would silently read a
    # different stream, so the composition refuses instead.
    rng_body = extra_body(bass_tail)
    for low, high in ((0x38E8, 0x38E9), (0x38EA, 0x38EB)):
        if f"x:>${low:04x}" not in rng_body or f"x:>${high:04x}" not in rng_body:
            die(f"shared RNG limbs are not at X:${low:04x}/X:${high:04x}")
    if RNG_BASE != 0x38E8:
        die("the composed RNG base no longer matches the shared helper")

    text = "\n".join([
        DISPATCH_ENTRY if with_source else "",
        _section("resonant_bass.asm", b),
        _section("resonant_snare.asm", s),
        _section("resident_cores.asm", cores),
        _section("resident_tail.asm", tail),
        _section("fold_drum_1.asm", fold_body()),
        _section("resident_primitives.asm",
                 centre_displacements(extra_body(bass_tail))),
    ])
    return drop_dead_code(text)


# ---------------------------------------------------------------------------
# DEAD CODE: 51 unreachable instructions in six blocks, removed.
#
# The production image enters the machine at exactly ONE place -- the source hook
# `pk3d_source` -- so a block no path reaches is weight in P and nothing else.
# `tools/perky/reach_3algo.py` finds them by label-level reachability from that
# entry (label-level, not address-level: an earlier address-tracking version
# drifted from the assembler's layout and pruned the whole Resonant half of the
# dispatcher, reporting the demonstrably-live `pk3d_snare_voice` as dead). Its
# 51-instruction answer matches the 51 established long before by actually
# removing them and confirming 15/15 Fold ARM parity, so the SET is trusted.
#
# Each group begins immediately after an `rts`, which is the structural reason no
# fallthrough reaches it -- the trap that broke an earlier name-based attempt
# (`drop_unreached()`), where routines reachable by FALLTHROUGH were removed and
# the Fold renderer stopped working.
#
# WHY THIS IS SHIPPED NOW: the instrumented hardware build (`perky-dsp-3algo-hwtest`)
# adds CF METER's 206-word DSP insert and was 35 words over the region. The 67
# words here fit it, and they make the shipping build smaller too. Unreachable
# code cannot change behaviour, and every gate is re-run to prove it.
DEAD_BLOCKS = ("pk_u32_sub", "pk_sub_no_borrow", "pk_u32_asr",
               "pk_u32_shift_sign_ready", "pk_noise_step", "pk_noise_refresh")


def drop_dead_code(text: str) -> str:
    """Remove the unreachable blocks, with the comment block above each."""
    lines = text.splitlines()
    dead = set(DEAD_BLOCKS)
    keep = [True] * len(lines)
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        if s.endswith(":") and s[:-1] in dead:
            # walk back over the contiguous comment block that documents it
            j = i
            while j > 0 and lines[j - 1].strip().startswith(";"):
                j -= 1
            # forward to the last non-blank line before the next label
            k = i
            while k + 1 < len(lines) and not (
                    lines[k + 1].strip() and not lines[k + 1][0].isspace()
                    and lines[k + 1].strip().endswith(":")):
                k += 1
            for n in range(j, k + 1):
                keep[n] = False
            i = k
        i += 1
    return "\n".join(l for l, k in zip(lines, keep) if k) + "\n"


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

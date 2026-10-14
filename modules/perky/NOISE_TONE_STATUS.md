# Noise/Tone (ALGO 3) — what actually ships, and what is still unproven

> **Historical Noise/Tone milestone, not current firmware instructions.** This document
> records an earlier PERKY development state and retains its original
> measurements, commits and failure analysis as evidence. The working MKII
> release is [PERKY4S](PERKY4S_RELEASE.md) (DSP, T1/T5,
> Fold1/Fold2/Simple/Complex, 12 retained stock FX). Its production shared-P
> budget has **zero free words**. Do not continue the old "next step" or flash
> plan here as if it were the present project status.


**Measured on the shipping `perky-2voice-milestone` tree. Read this before calling
Noise/Tone finished.**

## What ships: the `_native` (authentic) bodies, not the old synthetic path

`tools/perky/build_noise_tone_synth_source.py` composes Noise/Tone from a piece list
(`PIECES`) and **substitutes an authentic body into every container piece**:

| container piece (ABI) | body actually composed |
|---|---|
| `noise_tone_filter.asm` | `noise_tone_filter_native.asm` |
| `noise_tone_mix.asm` | `noise_tone_mix_native.asm` |
| `noise_tone_oscillator_packed.asm` | `noise_tone_oscillator_native.asm` |
| `noise_tone_envelope_packed7.asm` | `noise_tone_envelope_native7.asm` |
| `noise_tone_voice_xstate_glue.asm` | `noise_tone_voice_native_xstate.asm` |
| `noise_tone_envelope.asm` | `noise_tone_envelope_native.asm` |

(`noise_tone_math.asm` and the remaining glue are composed as-is.)

**So the shipping ALGO 3 is the native/authentic implementation, not the preserved
PERKY2 synthetic-control path.** The composer says so in its own error strings —
*"native shipping fast path requires the qualified synthetic wave identities"* — and
**guards the substitution with SHA-256 pins** on the wave identities and on the
linear envelope curve (`envelope1.bin` must be
`8136fff8a23fc148c79bbc3a55927ff23cadeff8623adeef2d91e7d15fd4d33b`, or the build
dies). A substitution that required an unqualified input could not silently ship.

`noise_tone_envelope_authentic.asm` exists in the tree but is **not** referenced by
the shipping composer.

## What is reference-qualified

`tools/verify/verify_perky_noise_tone_original_dsp_exec.py` passes, **and passes with
`--firmware`**, i.e. against the original ARM captures — and the firmware run covers
*more* cases than the default, so the captures were genuinely added rather than the
run being reduced:

```
(no --firmware)  shared: PASS  512 consecutive blocks; exact stereo PCM/state/RNG; 1471 P words
                 wave2 : PASS  256 consecutive blocks; exact stereo PCM/state/RNG; 1222 P words
(--firmware)     shared: PASS  656 consecutive blocks; exact stereo PCM/state/RNG; 1471 P words
                 wave2 : PASS  304 consecutive blocks; exact stereo PCM/state/RNG; 1222 P words
```

Reference provenance it is checked against: PĒRKONS v1.2.1 image
`adcdbc4a2c660ffb6477f202211ae3cb70170bfe6ddfaecc3df0e4cb7db398c6`,
PerkyBits `605cfd05d9dcdc0d0caa955297556a26ea257f82`.

## RETRACTION: the gap claimed below was NOT a gap

**An earlier revision of this document said the composed shipping source was not
tied to the reference by any gate, and that this was the milestone's open acceptance
condition. That was WRONG, and the error is corrected here rather than deleted.**

The gate exists: **`tools/verify/verify_perky_shipping_voice_exec.py`**, run and
PASSING in this tree, together with its caller
`tools/verify/verify_perky_synth_source_exec.py`. Its own docstring states the
property exactly:

> generates the ACTUAL shipping synth source, prepends the harness entry stub, and
> runs the existing 36 x 16-sample exact PCM/state/RNG comparison over that generated
> source. If this gate passes, the renderer text executed in the emulator is the same
> renderer text the firmware builder later places in the donor region.

and it is explicit that the naive alternative would NOT have been equivalent —
"firmware does not ship that text" because the composer deduplicates the common u32
helpers, lowers local conditional jumps to relative branches, and converts internal
calls to explicit long JSRs.

MEASURED, both exit 0:
```
PERKY X-state assembly ABI: PASS (62 persistent accesses within words 0..57;
   32 decimal/hex annotations exact; cache key word 41=$29; scratch high-water $63)
PERKY shipping X-state voice gate: OK (36 x 16-sample blocks; 58-word voice +
   100-word shared scratch; full packed Y; 1668 P words; probe instructions/block
   min 8713, mean 12575.8, max 22808)
PERKY generated synth source: PASS (1623/3441 P words in full donor, FREE 1818;
   SPRING-only 1063: not yet)
```

WHAT I GOT WRONG: I saw that
`verify_perky_noise_tone_original_dsp_exec.py` builds `recipe.shared_source` and
concluded, because no OTHER file called the composer in a gate, that nothing tied the
composed text to the reference. I checked whether the authentic gate assembles the
composed source and stopped there, instead of searching for a gate that already did.
The lesson is the repository's own: a negative result needs the question "what would
have proved this, and does it already exist under another name?"

SO: **ALGO 3 IS REFERENCE-QUALIFIED AS SHIPPED.**
  * shipping implementation identified: native/authentic bodies, SHA-pinned — MEASURED
  * original recipe vs ARM captures — MEASURED (gate passes, with --firmware)
  * SHIPPING COMPOSED SOURCE vs the voice oracle — MEASURED (this gate, 36 blocks,
    exact PCM/state/RNG)

Note the last line of the synth-source gate, which is directly relevant to the FX
milestone: it already models restoring a single stock effect, reporting the
full-donor program at 1623 P words with 1818 FREE, and "SPRING-only 1063: not yet".
That is a Noise/Tone-only program, not the four-engine machine (3051 words), so it
does not by itself settle the FX placement question -- but it is the existing
machinery for asking it.

## The gap I claimed (WRONG -- retained only to show what was checked)

**That gate does not assemble the shipping composed source.** It builds
`recipe.shared_source` / `recipe.wave2_source` from
`modules/perky/noise_tone_original_dsp.py`, a *separate recipe module*, and executes
the result. So what is proven is:

> the ORIGINAL RECIPE is bit-exact to the ARM captures.

What is **not** proven, and is what the milestone's acceptance condition actually
requires, is:

> the SHIPPING COMPOSED SOURCE (`build_noise_tone_synth_source.py` → `multi.asm`)
> is bit-exact to that same reference.

The evidence that it *should* be is strong — every container piece receives an
explicitly `_native` body, and the inputs are SHA-pinned — but **"should be" is not
"is"**, and this repository has been burned by exactly that substitution. The
`noise_tone_compact` word-model and the compact/packed ABI exist between the recipe
and the composed form, and nothing currently cross-checks them.

**Closing it:** assemble the *composed* Noise/Tone (the `PIECES` path, including the
`compact_piece` wrappers) and compare its PCM/state/RNG against the same ARM captures
the recipe gate uses, for all 3 MODEs, at the reachable knob corners, over
continuation blocks. Then ALGO 3 is reference-qualified **as shipped** and not merely
"by construction".

## A realtime number to carry forward — measured, not inferred

The authentic Noise/Tone recipe gate reports **worst 40,738 modeled cycles per
16-sample block** for the shared path (wave2: 15,945). The frame window is 72,512 and
the budget rule in use is `2*modeled + 16*1410 <= 72,512`, i.e. an allowance of
23,040 modeled cycles per block — **so Noise/Tone is well over the allowance on its
own.** 40,738 + 22,560 stock continuation = 63,298, which fits the window with about
9,200 to spare, and the engine does produce output on hardware (the user confirms
this). So it is not a blocker — **but it is the tightest engine in the pool by a wide
margin, and it deserves a realtime gate of its own rather than being assumed safe.**

## Status

* **shipping implementation identified:** native/authentic, SHA-pinned — MEASURED
* **original recipe reference-qualified against ARM:** MEASURED (gate passes)
* **shipping composed source reference-qualified:** **DONE** — see the retraction above
* **realtime:** measured over the per-engine allowance; fits the frame; unproven
  against a dedicated gate

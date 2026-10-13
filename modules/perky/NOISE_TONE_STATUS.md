# Noise/Tone (ALGO 3) — what actually ships, and what is still unproven

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

## THE GAP — and it is a real one

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
* **shipping composed source reference-qualified:** **NOT DONE** — this is the gap
* **realtime:** measured over the per-engine allowance; fits the frame; unproven
  against a dedicated gate

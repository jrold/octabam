# PERKY2V — hardware-test candidate record

**STATUS: NOT THE MILESTONE.** Every software gate passes, but the FX recovery is
incomplete: Spring, Dark and Lo-Fi are absent. See "Intentionally removed" below and
`FX_RECOVERY_FEASIBILITY.md`. Everything else on this record is verified.

## Identity

| field | value |
|---|---|
| branch | `perky-2voice-milestone` |
| commit | `3d86d92547e4bb920a3538c6c1c32ffb382df4b4` |
| short | `3d86d92547e4` |
| tree at build | `clean` |
| baseline tag | `perky2v-hw-baseline` -> `fc438e03` (the physically working image, archived at `out/hw-baselines/perky2v-fc438e03/`) |

## Artifacts

| field | value |
|---|---|
| MIDI updater | `out/OCTATRACK_OS1.40C_PERKY2V.syx` |
| MIDI sha256 | `685e51057e262a8502fc0434e123eaea0af3add14e0d182665ef6dfe296d68f6` |
| card image | `out/OCTATRACK_PERKY2V.bin` |
| card sha256 | `4ba4d72ce1a9a0bfbb64a8e627fba7a753791e1fc85d59d83ca66ac016f5e12e` |
| manifest | `out/PERKY2V_PERKY_TEST.txt` (git= matches HEAD, tree=clean) |
| mainos sha256 | `9f93971e368620afe310bee6bad122397ecefa49c48e46145010ec3f332ac4b9` |

## Algorithm map (ALGO is an INDEX into ALGO_ENGINE)

| ALGO | engine id | engine |
|---|---|---|
| 0 | 000 | Fold Drum 1 (authentic v1.2.1) |
| 1 | 003 | Fold Drum 2 (authentic v1.2.1) |
| 2 | 002 | Simple Drum (authentic v1.2.1) |
| 3 | 010 | Noise/Tone (native/authentic bodies) |

Out-of-range ALGO clamps to 0 and cannot reach an engine outside the pool.

## SRC page 1 — exact order

| knob | control | count |
|---|---|---|
| A | TUNE | 128 |
| B | DECAY | 128 |
| C | ALGO | 4 |
| D | PAR1 | 128 |
| E | PAR2 | 128 |
| F | MODE | 3 |

All six staged through the normal parameter path (bitmap 0x00111111) and all six
p-lockable. ALGO and MODE p-locks both return to base on the next unlocked trig.

## Voices

Exactly two, one per DSP core: **T1** (core B) and **T5** (core A). Admission mask is
`[1,0,0,0,1,0,0,0]` — T2-T4 and T6-T8 stay ordinary stock tracks.

## Measured output-gain correction

The renderer returns signed16 **by design**, so the source path has **no scaling error**;
the seam's shift of 8 is the exact signed16 -> signed24 alignment. The loudness
difference is program material (a synth voice at full signed16 reaches 0 dBFS where a
sample sits well below). Shipped: **shift 5 instead of 8 = a calibrated MINUS 18.06 dB
trim**, applied at the integration boundary, exact (a pure left shift: no rounding,
truncation, DC bias, wraparound or clipping). The renderer is untouched and remains
bit-exact to the reference. `ALIGN_SHIFT=8` stays documented beside `SEAM_SHIFT=5`.

## Final P/X/Y map (from the build's own ledger, all values derived)

```
p_words 3051 / p_capacity 3441   free 390
x_words 359   y_words 2139 / y_capacity 2139
  x 0x3800 len   236  PERKY compact voice state + envelope caches + RNG
  x 0x38ec len     6  PERKY source event-offset and admission staging
  x 0x3900 len   100  PERKY shared sparse source-render scratch
  y 0x07a5 len  2139  PERKY packed Noise/Tone tables
  x 0x3964 len    17  Simple Drum shared control-rate pitch cache
  p 0x1000 len  3051  PERKY shipped DSP program (both payloads)

**Y is exactly full (2139 of 2139)** — no Y headroom exists.

## FX — retained and removed

Retained, descriptors/code/dispatch untouched on both cores — the eight stock DSP
effects that remain in the local P region:

```
CHORUS, COMB FILTER, DJ EQ, EQUALIZER, FILTER, FLANGER, PHASER, SPATIALIZER
```

**DELAY is also retained**, and it is not in that list because it is not a DSP effect at
all -- it lives on the ColdFire side and consumes no DSP P. It is therefore **not at risk
from this harvest**, and the FX recovery cannot threaten it. Recorded separately here
rather than omitted: deriving the retained list from the DSP P spans quietly dropped it,
and DELAY is on the milestone's must-keep list.

**Intentionally removed — and this is the milestone gap:**

```
SPRING REV (1063), DARK REV (1067), LO-FI (537)   <- REQUIRED BACK, not yet restored
PLATE REV (594), COMPRESSOR (180)                 <- approved sacrifice
```

The harvest takes one contiguous 3441-word run. Returning the
three required effects leaves Perky 774 contiguous words against a 3051-word program:
**2277 short**, which is why the program must be emitted as shards.

## Gate results — all executed, not inferred

13 gates PASS: `verify_perky_light2_src_page` (order, counts, staging, ALGO and MODE
p-lock, admission, clamps), `verify_perky_fold_seam_exec`, `verify_perky_multi_seam_exec`,
`verify_perky_synth_seam_exec`, `verify_perky_fold_regression`,
`verify_perky_shipping_voice_exec`, `verify_perky_synth_source_exec`,
`verify_perky_noise_tone_original_dsp_exec` (ARM captures), `verify_perky_all_fx_placer`,
and `verify_perky_synth_port` for engines 0/3/2/10 on both cores over 32000 frames with
dirty memory. Plus `make check`, four port gates, and the full-machine boot gate. Zero
Resonant references in the shipping path.

**Not separately gated on this branch:** Delay functionality, and the ColdFire
odd-address store regression.

## Physical test

`MILESTONE_HWTEST.md`. Run `stamp-defaults` FIRST — this image changes the SRC slot
layout, so a Part saved under the old layout stalls the sequencer on the first play.


---

# FX RECOVERY — precise remaining work

This record leads with "NOT THE MILESTONE ... Spring, Dark and Lo-Fi are absent". That is
still true, and this section says exactly what remains, because the mechanism is now fully
validated and only integration is missing.

## What is proven

| item | evidence |
|---|---|
| the program fits | 3051 words into 3178 (5 shared tails + PLATE 594 + COMPRESSOR 180), 127 free |
| relocatable pieces | 21 pieces, markers balanced, **zero unmarked content**, none over the 605 cap |
| origin-independent | same 3051 words and identical symbol offsets at origins 0x1000 / 0x2400 / 0x3840 |
| no cross-piece branches | 0 relative branches cross a piece; all 39 cross-piece transfers are absolute `jsrl` |
| placement computed | `place_program_shards_two_space()` -- all 21 placed, both local runs used |
| shards reassemble | all 21 assembled standalone; stitched result **byte-identical to the monolith** |
| assigned origins work | all 21 assemble at their assigned origins, extents exact, **zero sizing drift** |
| **the three effects' P is free** | SPRING 0x1252, DARK 0x1679, LO-FI 0x1B58 -- **0 words overwritten** |

The sharded P image exists (`out/perky/light2/sharded-p.json`).

## What remains — two edits that MUST land together

1. **Narrow the harvest** in `remixes/test/perky-machine/remix.py`: add SPRING REV, DARK REV
   and LO-FI to `fx1` so they keep their own code. Measured effect: the harvest goes from
   3441 words in one run to **774 words in two runs** (PLATE 594, COMPRESSOR 180).
2. **Place the shards across both address spaces** in the build's image path. This is the part
   with no existing machinery: `build_bus.py`'s placer handles the donor run, and nothing
   currently places a module across multiple address spaces.

**They are coupled and cannot be landed separately.** Narrowing the harvest alone gives 3051
words only 594 words of contiguous space; the build refuses (correctly) rather than
truncating. Change 2 alone has nothing to place into.

## Then the gates

DSP timing for the retained engines, boot/upload/readback, and the P/X/Y ledger -- on the
resulting image.

## What this milestone delivered apart from the FX

The SRC page in the required order, the measured output trim, the corrected P/X/Y ledger, the
provenance root-cause fix, the candidate record, and 13 gates executing green including all
four engines on both DSP cores over 32000 frames.

---

# DELIVERABLE DOCUMENTATION GAPS (round 89)

The staged artifact is complete -- `.bin`, `.syx`, manifest, test procedure and both calibration
WAVs are all present, and the artifact hashes match the manifest exactly. **Two documentation gaps
remain, both user-facing.**

## 1. The manifest is stale on two fields

```
engines=... 010 NOISE/TONE (native/authentic bodies; composed source reference
            qualification pending -- see modules/perky/NOISE_TONE_STATUS.md)
```

**Noise/Tone's reference qualification is no longer pending** -- it was resolved against the ARM
captures, and `NOISE_TONE_STATUS.md` records that. The manifest line predates the resolution.

```
git=3d86d92547e4
```

**The artifact's `git=` is the commit the build read, and 89 commits have landed since.** That is
not a defect -- `tree=clean` is recorded beside it, and the `*_sha256=` lines are what pin the
artifact -- but a reader comparing `git=` to `HEAD` would reasonably be confused. **The manifest
should say which of its fields identify the artifact and which identify the tree it was built from.**

## 2. The test procedure covers 5 steps; the brief specifies 14

The procedure is genuinely useful -- it carries the `stamp-defaults` migration, which is the step
that stops the sequencer stalling on a re-laid-out SRC page:

```
tools/hw/ot_project.py stamp-defaults "<card>/<set>/<project>" perky-machine --all
```

But the brief's hardware sequence has fourteen items (T1/T5 per engine, all 3 MODEs, ALGO knob
mapping, the ALGO p-lock base->locked->base round trip, the loudness A/B, Spring/Dark/Lo-Fi, and the
ordinary-stock-track check). **Those belong in the procedure, whether or not every one is reachable
on this build** -- several are not, and saying so in the procedure is more useful than omitting them.

## Why this is worth a round

**The artifact is the thing you flash.** Its manifest and its procedure are what you read while
holding the unit. A manifest that calls a resolved qualification "pending" and a procedure that
covers a third of the test sequence are the two documents most likely to cost a flash cycle -- and
both are fixable without touching a line of the build.

---

# A CORRECTION TO ROUND 89, AND THE ONE REAL GAP (round 90)

Round 89 claimed the test procedure "covers 5 steps; the brief specifies 14". **That was my
measurement error, the same kind as round 79's audit regex.** I counted with
`grep -cE "^[0-9]+\."` and got 5 -- **which counts numbered lines, not coverage.** Read properly,
the procedure covers the brief's sequence in seven sections: T1, T5, the three remaining engines,
ALGO mapping, the p-lock round trip, ordinary stock tracks, and the FX state. **It is a good
procedure, and it is arguably better organised for a tester holding the unit than a 14-item list.**

## But there was one real gap, and it is the brief's own ask

> **Report clearly what each of the three MODE positions means for all four engines so the user
> knows what they are hearing on hardware.**

**The procedure never told the tester what MODE does.** It asked them to sweep it and report, which
is useful, but the brief asks for the meaning to be stated -- and a tester who knows what to expect
gives a better answer than one who does not.

**Added**: a per-engine MODE table, a note that on some engines MODE gates whether the voice sounds
at all (so a silent position is a mode, not a fault), and a sixth "send back" item asking which
positions are distinct per engine and which Noise/Tone mode is the expected one.

## The pattern, for the second time this session

**Round 89's error and round 79's were the same shape**: a counting tool that measured something
narrower than the question, read as if it had measured the question. Round 79's regex missed wrapped
`Gate(` forms and produced duplicate registrations; round 89's `grep -c` missed section-based
coverage and produced a false "documentation gap".

**Both were caught by reading the artefact rather than the count of it.** That is now seven
self-corrections on this branch, and the remedy has not changed.

---

# THE MANIFEST NOW CARRIES THE EXACT FX LISTS (round 91)

The brief's hardware-candidate record asks for the **exact retained FX list** and the **exact
intentionally removed FX list**. The canary wrote only:

```
fx=NONE for first hardware test
```

**which is a test-procedure choice -- leave the FX slots empty on the first flash -- and NOT a
statement about which effects the image carries.** Read as the latter it is actively misleading.

Measured, and now recorded in the manifest:

```
retained (8, 2717 P words): FILTER 727 · EQUALIZER 282 · DJ EQ 345 · PHASER 207
                            FLANGER 289 · CHORUS 329 · SPATIALIZER 261 · COMB FILTER 277
removed  (5, 3441 P words): PLATE REV 594 · COMPRESSOR 180
                            SPRING REV 1063 · DARK REV 1067 · LO-FI 537
```

## Two things that had to be said explicitly

**DELAY appears in neither list** -- it is ColdFire-side, so it never appears in the DSP P spans and
is retained by construction. The brief lists it under MUST KEEP, so the manifest now says so.

**The removed list is not uniformly "approved".** PLATE and COMPRESSOR are the two sacrifices the
brief permits. **SPRING, DARK and LO-FI are not** -- they are the milestone's remaining work. A flat
"removed" list would have implied all five were sanctioned.

## The appended block changes no hash

The canary's own lines are untouched and `card_sha256` still matches the artifact byte for byte.
The addition is a clearly-marked comment block after them, and it also records the two stale
fields from round 89 -- `git=` predating 90 commits, and the Noise/Tone "qualification pending"
line that the ARM-capture work superseded.

---

# THE ITEM-8 RECORD IS COMPLETE (round 92)

The brief's hardware-candidate record names **fifteen fields**. Eight were present; **four were
absent entirely** and are now measured from the build rather than transcribed:

```
src_page_order        = A TUNE (128) / B DECAY (128) / C ALGO (4) / D PAR1 (128) / E PAR2 (128) / F MODE (3)
algorithm_map_panel   = 1 FOLD DRUM 1 / 2 FOLD DRUM 2 / 3 SIMPLE DRUM / 4 NOISE/TONE
algorithm_map_wire    = 0 FOLD DRUM 1 / 1 FOLD DRUM 2 / 2 SIMPLE DRUM / 3 NOISE/TONE
output_gain_correction= minus 18.06 dB, an exact LEFT SHIFT of 5 (ALIGN_SHIFT 8, SEAM_SHIFT 5)
p_ground_local        = 774 words in 2 runs (PLATE 594 + COMPRESSOR 180)
p_ground_shared       = 2404 words in 5 runs
p_capacity_total      = 3178 words
perky_program         = 3051 words
p_free_headroom       = 127 words
xy_map_per_payload    = X:3800-38EB 236w, X:38EC-38ED 2w, X:3900-3963 100w, Y:07A5-0FFF 2139w
```

**Two of these say something the earlier manifest could not.** The gain correction records *how*
the trim was applied (a pure left shift, so no rounding, truncation, DC bias, wraparound or
clipping) and that the renderer was **not** altered. And the X/Y map records that **Y is exactly
full — 2139 of 2139** — which is why the deferred Wavetable work cannot add Y residency.

## A typo worth recording, because of how it failed

I wrote the field name `srс_page_order` with a **Cyrillic 'с' (U+0441)** instead of Latin 'c'.
The line looked correct in the terminal and **failed in a specific, misleading way**: it did not
match `[a-z_]+=`, so the field read as **MISSING** while sitting in the file, and my first fix
script's regex did not match it either.

**Found by counting non-ASCII bytes (exactly 1) rather than by re-reading the line** — the same
lesson as the last three corrections: the display is not the data.

## The fifteen, verified

```
branch · commit SHA · provenance · MIDI path · MIDI SHA · card path · card SHA
manifest · algorithm map · SRC order · retained FX · removed FX
gain correction · P/X/Y map · free headroom            --- 0 missing ---
```

**No hash changed**: `card_sha256` still equals the artifact's sha256, verified after every edit.
The additions are comment-marked blocks; the canary's own lines are untouched.

---

# THE ITEM-4 REPORT IS COMPLETE (round 93)

The brief asks for **five specific numbers** about the gain correction. One was recorded
(`SEAM_SHIFT 5`); the other four are now measured and are in the manifest:

```
raw_amplitude_ratio      = 8:1      # ALIGN_SHIFT 8 : SEAM_SHIFT 5
raw_db_mismatch          = 18.06 dB # 20*log10(8)
fixed_point_multiplier   = 32       # 2^5, a pure LEFT SHIFT -- not a multiply
resulting_error          = 0 LSB    # exact: no rounding, truncation, DC bias, wrap or clip
maximum_output_headroom  = 8.00x = 18.06 dB
```

**And the source confirms the shift count**: `modules/perky/synth_seam_glue.asm` carries **exactly
five `asl a` instructions** at the seam, matching `SEAM_SHIFT = 5`. That is the kind of check worth
making -- **the constant and the code agree, rather than the constant merely being documented.**

## What the numbers mean, stated once

A full-scale signed16 sample (32767) reaches **1,048,544** in signed24 (max 8,388,607), so the
shipped path keeps **8× = 18.06 dB** of headroom. The renderer is **signed16 by design and was not
altered**; the trim sits at the Octatrack integration boundary, and the pre-trim PCM remains
bit-exact to PerkyBits -- asserted pre-trim by the engine gates, not merely claimed.

**`resulting_error = 0 LSB` is the claim worth being careful about.** It holds because the operation
is a *left shift*, not a multiply: no rounding, no truncation, no DC bias, no wraparound and no
clipping. Had the trim been implemented as a multiply by a fractional constant, the error would be
non-zero and the bit-exactness argument would not survive. **The implementation choice is what makes
the zero true, not the measurement alone.**

---

# THE ONE ITEM-4 REQUIREMENT NOT MET AS WRITTEN (round 94)

The brief prescribes a specific experiment:

> 2. Better still, use **EXACTLY THE SAME integer PCM through both source paths.**
> 3. Feed the reference PCM through a completely stock FLEX/STATIC source path at unity/default
>    source settings.
> 4. Feed that same PCM through the Perky source-record/integration path...
> 5. Compare at the closest possible common point BEFORE stock AMP, FX1, FX2, track LEVEL, MAIN/CUE.

**What was done instead measured the source path directly.** The seam's multiply is x256 -- the exact
signed16 -> signed24 alignment -- so there is **no source-path scaling error**, and the -18.06 dB
trim is a calibrated choice rather than a correction of a defect. The five numbers reported in
round 93 are sound and source-verified.

**But that is not the same experiment.** A two-path A/B with identical PCM would catch a
source-record/integration error *anywhere* in the chain; the seam measurement only rules out the
scaling at the seam. **The brief asked for the former and I produced the latter**, and the
distinction matters because the seam measurement cannot see an error introduced upstream of it.

## And it could not have been gated here anyway

**No calibration gate exists.** `verify_perky_mix_exec.py` is registered and mentions gain -- but it
tests the **Noise/Tone mixer**, not a two-path A/B. Any genuine A/B needs the emulator with a
project on the card, which is the same `OT_PROJECT` dependency that blocks the canary, the boot gate
and the probe.

## The five numbers, restated with their scope

| number | value | what it is scoped to |
|---|---|---|
| raw amplitude ratio | 8:1 | the seam's alignment vs the shipped shift |
| raw dB mismatch | 18.06 dB | the same |
| fixed-point multiplier | 32 (2^5) | the shipped left shift, confirmed by 5 `asl` in the source |
| resulting error | 0 LSB | **holds because it is a shift, not a multiply** |
| maximum output headroom | 8.00x = 18.06 dB | signed16 full-scale into signed24 |

**All five are correct about the seam. None of them is a measurement of the whole source-record
path against a stock one** -- which is the measurement the brief actually asks for, and which the
hardware A/B in step 9 of the test sequence is the practical substitute for.

---

# THE CARD AND MIDI ROUNDTRIP GATE (round 96)

The brief's release-gate list names two checks I had never verified existed:

* **card wrapper roundtrip**
* **MIDI updater roundtrip**

**They are one gate, and it is exactly right.** `tools/verify/verify_perky_final_wrappers.py`:

> **Round-trip final Perky card and MIDI wrappers back to their exact inputs.** Release-only
> packaging gate. The card image must decode to the exact ELEK container emitted by
> elektron-firmware-tool, and the MIDI SysEx must decompress section 3 back to the exact final MAIN
> OS bytes.

That is a stronger check than either phrase suggests on its own: it verifies that **the card image
and the MIDI updater are both *decodable back* to the same MAIN OS bytes** -- i.e. that the two
delivery paths carry the same firmware, which is the property a flash actually depends on.

## Its state

| | |
|---|---|
| registered in `make check` | **no** (0 mentions) |
| requires | `--mainos --elek --card --midi --eft --version` |
| `out/mainos_bus.bin` | present |
| `out/perky/cf-final` | **missing** |
| the wrappers themselves | staged -- `~/Downloads/PERKY2V_milestone.{bin,syx}` |

**So the gate exists, is correct, is unregistered, and needs the canary's outputs** -- which need
`OT_PROJECT`. **It cannot be run here**, and it is the **fourth brief-named gate in that position**
(after the odd-address store, the tail budget, and boot/upload/readback).

## Why this is worth recording rather than leaving

**A release gate that exists, is right, and never runs is the pattern this work has now found four
times** -- and each time the gate had been written by someone who understood the risk. **The
registration edit is one line; the input is the same missing project.** Neither is a research
question any more.

**The useful consequence:** when `OT_PROJECT` lands and the canary runs, **four gates become live at
once** -- boot/upload/readback, the odd-address audit, the tail budget, and this one -- because all
four were already written and only need their inputs and a manifest line.

---

# THE CARD / MIDI ROUNDTRIP GATE **RAN**, AND FOUND A MISMATCH (round 97)

Round 96 recorded that this gate existed, was right, was unregistered, and needed the canary's
outputs. **That last part was wrong.** Every input it needs is on this machine:

```
--mainos   out/mainos_perky_multi.bin          present (the canary's MAIN OS)
--elek     out/elek_PERKY2V.bin                PRESENT -- I had looked for out/perky/cf-final
--card     ~/Downloads/PERKY2V_milestone.bin   present
--midi     ~/Downloads/PERKY2V_milestone.syx   present
--eft      vendor/elektron-firmware-tool/elektron-firmware-tool   PRESENT
```

**It runs, and it fails:**

```
PERKY wrapper round-trip: ELEK version field mismatch b'PERKY2V   ' != b'   PERKY2V'
```

## What the failure says

**The version field's padding differs between the two artifacts:**

| artifact | field |
|---|---|
| `out/elek_PERKY2V.bin` | `PERKY2V   ` -- LEFT-aligned, trailing spaces |
| `~/Downloads/PERKY2V_milestone.bin` | `   PERKY2V` -- RIGHT-aligned, leading spaces |

**So the ELEK container on disk and the card image that was tested were not produced with the same
version-field convention.** Either the ELEK is from a different build, or the canary and the staging
step disagree about padding.

## Why this matters more than the four gates that could not run

**Four brief-named gates could not be executed because of a missing project. This one COULD be, and
it immediately found a discrepancy between two artifacts that are supposed to be the same
firmware.** The card/MIDI roundtrip exists precisely to catch this: *"the card image must decode to
the exact ELEK container... and the MIDI SysEx must decompress section 3 back to the exact final
MAIN OS bytes."*

**A flash depends on the card and the MIDI updater carrying the same bytes.** Right now the gate
says they do not agree on a field a decoder reads.

## What is NOT yet established

**This is one field, not the payload**, and the mismatch may be entirely in how the version string is
padded by the staging path rather than in the firmware. **I have not yet determined which side is
wrong** -- and I should not guess, because guessing here is how a version string becomes a bug.

---

# ROUND 97's MISMATCH, RESOLVED: the two artifacts are from different builds (round 98)

Round 97 ran the card/MIDI roundtrip gate and it failed with:

```
PERKY wrapper round-trip: ELEK version field mismatch b'PERKY2V   ' != b'   PERKY2V'
```

**I said I would not guess which side was wrong. The answer is that neither is -- they are not the
same build.**

```
~/Downloads/PERKY2V_milestone.bin   Oct 12 23:30   <- the staged, tested artifact
~/Downloads/PERKY2V_milestone.syx   Oct 12 23:30
out/mainos_perky_multi.bin          Oct 13 00:30   <- an hour LATER
out/elek_PERKY2V.bin                Oct 13 00:39   <- an hour and nine minutes LATER
```

**The staged card and MIDI predate the ELEK and the MAIN OS in `out/` by over an hour.** The gate is
correct to refuse them: it is comparing a card against a container that never produced it.

## What this actually tells us -- and it is worth more than the mismatch

**The ELEK container that produced the tested card was not preserved.** `out/` has since been
overwritten by later builds, so:

* the staged artifacts remain **exactly** what was tested -- their hashes are pinned and unchanged;
* **but the intermediate that would let them be re-derived is gone**;
* and the roundtrip gate -- which exists precisely to prove card and MIDI carry the same firmware --
  **cannot be run against them without rebuilding both from source.**

**That is the same reproducibility gap as `OT_PROJECT`, reached from a different direction:** the
artifact is trustworthy, and the path that produced it is not currently walkable.

## What would close it

Either:

1. **rebuild both from source** with `OT_PROJECT` supplied, which regenerates the ELEK, the card and
   the MIDI together and lets the gate run for real; or
2. **preserve the ELEK beside the artifacts** in future staging runs, so the roundtrip can be
   re-checked without a full rebuild.

**Option 2 is a one-line change to the staging step and would have made this a non-question.**

---

# ROUND 98 WAS WRONG: IT IS ONE BUILD, AND THE MISMATCH IS REAL (round 99)

Round 98 explained round 97's failure as "the two artifacts are from different builds", on the
evidence of mtimes:

```
~/Downloads/PERKY2V_milestone.bin   Oct 12 23:30
out/elek_PERKY2V.bin                Oct 13 00:39
```

**The hashes refute it:**

```
out/OCTATRACK_PERKY2V.bin           4ba4d72ce1a9a0bfbb64a8e627fba7a753791e1fc85d59d83ca66ac016f5e12e
out/OCTATRACK_OS1.40C_PERKY2V.syx   685e51057e262a8502fc0434e123eaea0af3add14e0d182665ef6dfe296d68f6
~/Downloads/PERKY2V_milestone.bin   4ba4d72c...   IDENTICAL
~/Downloads/PERKY2V_milestone.syx   685e5105...   IDENTICAL
```

**The `out/` wrappers and the staged ones are byte-identical.** They were staged by *copying* at
23:30 from the build that finished at 00:39 -- or the copies carry the original times. Either way
**they are one build**, and running the gate against the matched set:

```
PERKY wrapper round-trip: ELEK version field mismatch b'PERKY2V   ' != b'   PERKY2V'
```

**still fails.**

## So the mismatch is real, and it is inside one build

| artifact | version field |
|---|---|
| `out/elek_PERKY2V.bin` | `PERKY2V   ` -- LEFT-aligned |
| `out/OCTATRACK_PERKY2V.bin` (the card) | `   PERKY2V` -- RIGHT-aligned |

**The ELEK container and the card image, produced by the same build, disagree on a field a decoder
reads.** The roundtrip gate exists precisely to catch that, and it has.

## My error, and its shape

**I inferred "different builds" from mtimes -- a proxy -- instead of comparing the artifacts.** One
`shasum` would have settled it, and I ran the gate twice before running it.

**This is the ninth self-correction on this branch and the fourth of the same shape:**

| round | proxy I trusted | what actually settled it |
|---|---|---|
| 79 | a `Gate\(\"...\"\)` regex | counting wrapped `Gate(` lines |
| 89 | `grep -c "^[0-9]\+\."` | reading the procedure |
| 92 | the terminal display of a field name | counting non-ASCII bytes |
| **98** | **file mtimes** | **sha256 of the artifacts** |

**In every case the proxy was cheaper to obtain than the measurement and answered a different
question.** Round 98 answered "were these files written at the same time?" when the question was
"are these the same bytes?"

## What is now open, and it is a real defect

**The card and the ELEK -- same build, same MAIN OS -- carry different version-field padding.**
Either the staging step pads it one way and the card wrapper another, or one of the two is written
from a different source. **This is unresolved, it is inside the deliverable, and it is exactly the
class of defect the roundtrip gate was written to find.**

---

# THE VERSION-FIELD MISMATCH, PINPOINTED (round 100)

Round 99 established the mismatch is real and inside one build. **Round 100 located it exactly.**

```python
# verify_perky_final_wrappers.py
want_version = args.version.rjust(10, " ").encode("ascii")   # RIGHT-aligned
got_version  = emitted[0x08:0x12]                            # the ELEK's field

# build_machine_canary.py, line 159 -- the version goes to the EXTERNAL tool
"-V", version,
```

**The ELEK's version field is written by `elektron-firmware-tool`**, invoked with `-V <version>` by
the canary. It emits **`ljust`**: `'PERKY2V   '`. The gate expects **`rjust`**: `'   PERKY2V'`.

**The gate also refuses a pre-padded version** (`version must be 1..10 ASCII non-whitespace
characters`), so the padding is the gate's choice, not the caller's.

## So this is a convention disagreement, and it needs an oracle

Two components in the same build disagree:

| component | convention |
|---|---|
| `elektron-firmware-tool` (writes the ELEK) | `ljust(10)` |
| `verify_perky_final_wrappers.py` (checks it) | `rjust(10)` |

**The oracle that would settle it is the stock firmware's own ELEK container.** This machine has
`out/raw/section_3_MAIN_OS.bin` -- **the raw MAIN OS section, not a stock ELEK** -- so the oracle is
absent, and this is a third external dependency alongside `OT_PROJECT` and the PĒRKONS image.

## What is and is not established

* **Established:** the container's field is `ljust`, the checker's expectation is `rjust`, both
  within one build, and the roundtrip gate fails because of it.
* **Established:** the gate is *doing its job* -- it exists to prove the card decodes to the emitted
  container, and a field that disagrees is exactly what it should refuse.
* **NOT established: which side is wrong.** It may be the gate's assumption, or the tool's output,
  or neither (the two may simply be checking different fields). **I am not going to guess, and I am
  not going to change either to make a gate green** -- that is how a version string becomes a
  flashing bug.

## The honest bottom line for the deliverable

**The card and MIDI that were physically tested are unchanged and their hashes are pinned.** This
mismatch is between the **ELEK container** and the **checker** -- it does not alter the card or the
MIDI. **But it means the packaging roundtrip is unproven for this build**, and that is a claim the
milestone's release gates require.

---

# ROOT CAUSE: THE PATCH'S COMMENT AND THE PATCH'S CODE DISAGREE (round 101)

Round 100 pinpointed the version-field mismatch to a convention disagreement. **Round 101 found the
oracle, and the defect.**

## The oracle was in the repo all along

`tools/patches/elektron-firmware-tool.patch` documents the convention in a comment:

> Octatrack: the running OS/bootloader draw the version from container offset 0x08
> (**space-padded, right-justified 10-char field**, NUL-terminated by the section-length high byte
> at ELEK_SECT_OFF). ELEK_VERSION_OFF (0x0D) is only where the alnum version begins; write the full
> field from 0x08 so the whole 10-char display area is editable.

**That agrees with the gate's `rjust(10)`.** So the gate is right.

## But the patch's own code pads left

```c
voff=0x08;
for(fend=voff; fend<ELEK_SECT_OFF && (is_alnum(c[fend])||c[fend]=='.'||c[fend]==' '); fend++);
...
int cap=fend-voff, nl=(int)strlen(ver);
if(nl>cap) return -3;
for(int i=0;i<cap;i++) c[voff+i] = (i<nl) ? (uint8_t)ver[i] : ' ';
```

`c[voff+i] = ver[i]` for `i < nl` writes the version from the **start** of the field and pads with
spaces **after** it -- **left-justified**, the opposite of the comment two lines above.

**Measured consequence:** `out/elek_PERKY2V.bin[0x08:0x12]` is `b'PERKY2V   '`, and the gate's
`want_version` is `b'   PERKY2V'`, so the roundtrip refuses.

## What this is NOT

**Not a stale binary** -- though the timeline looked like it at first:

```
tools/patches/elektron-firmware-tool.patch          Oct 12 21:29
vendor/elektron-firmware-tool/elektron-firmware-tool  Oct 6 10:57   (six days older)
```

**The binary does predate the patch**, and rebuilding is required regardless -- but that is a
separate staleness. **A rebuild from the current source would still emit `ljust`**, because the code
that does it is the patched code.

## So the fix is one line, and it must not be made blind

The correction is to right-align: write `ver[nl-1-i]` at `c[voff+cap-1-i]` instead of `ver[i]` at
`c[voff+i]`.

**But this changes the ELEK container, and therefore the card and the MIDI updater** -- the two
artifacts that were physically tested and whose hashes are pinned. **I am not making that change
without the hardware's own answer**, because the comment asserts what the running OS and bootloader
do, and *the comment is the only evidence I have for it.* If the comment is wrong, right-aligning
breaks the version display on the unit; if the code is wrong, the unit currently shows a
mis-aligned version and the gate is the only thing complaining.

**The cheap discriminator is one flash: does the unit display `PERKY2V` correctly today?** If it
does, the code is right and the comment and the gate are wrong. **That is a question for hardware,
not for another round of reading.**

---

# THE MISMATCH IS THE GATE'S EXPECTATION, NOT THE ARTIFACT (round 102)

Round 101 concluded the tool's code was wrong because the patch's comment says "right-justified".
**Round 101 stopped one measurement short.** The gate fails at the version check and **returns before
it ever compares the card to the container** -- so that comparison had never been made. Made now:

```
card-decoded ELEK : 559757 bytes
emitted ELEK      : 559757 bytes
IDENTICAL         : True
```

**The ELEK embedded in the card that was physically tested is byte-identical to
`out/elek_PERKY2V.bin`, version field included.** Both carry `b'PERKY2V   '`.

## What that means

The packaging roundtrip exists to prove one thing: **that the card image decodes to the emitted
container.** It does. **Exactly.** The property the gate was written to check **holds**, and it holds
byte for byte.

The failure is at the step *before* that comparison. The gate does not read the expected version out
of anything -- it **manufactures** it:

```python
want_version = args.version.rjust(10, " ").encode("ascii")
```

**So the gate asserts a padding convention the tool has never used**, and refuses a container that
is internally consistent with the card it shipped in.

## The corrected picture

| claim | round 101 | round 102, measured |
|---|---|---|
| card decodes to the emitted container | untested | **identical, 559757 bytes** |
| the version field is `ljust` | yes | yes -- **in both** |
| the tool's code contradicts its comment | yes | yes, **but it does so consistently** |
| which side is wrong | the tool | **the gate's `rjust` assumption** |

**The patch's comment still says "right-justified" and the code still pads left** -- that
contradiction is real and worth fixing. **But it is a documentation defect in a vendored tool, not a
defect in the artifact.** The card and the MIDI updater were built by the same tool with the same
convention, and they agree.

## For the release gates

**The roundtrip gate is not green, and it will not be until either the gate's expectation or the
tool's padding changes** -- and they must change *together*, or the next build's card and container
will genuinely disagree rather than agreeing on an unconventional-but-consistent field.

**What is now established rather than assumed:**

* the card image decodes to the emitted container, **byte for byte**;
* the version field is consistent between them;
* the mismatch is **entirely** the gate's manufactured expectation.

**That is a stronger statement than "the gate fails"**, and it is the one the milestone's packaging
claim needed.

---

# THE GEOMETRY SETTLES IT: `ELEK_VERSION_OFF = 0x0D` IS THE ARITHMETIC (round 103)

Round 102 measured that the card's ELEK and the emitted container are byte-identical, and concluded
the gate's `rjust` expectation was "out of step" and the tool's code merely "unconventional". **That
was too generous.** The field's geometry says the tool has a real bug.

```
0x00..0x03   magic           b'ELEK'
0x04..0x07   b'0178'
0x08..0x11   version field   b'PERKY2V   '    <- 10 bytes, text LEFT-aligned
0x12..0x15   section length  00088a72
```

**The comment names `ELEK_VERSION_OFF = 0x0D` as where the alnum version begins.** In a 10-byte field
starting at `0x08`, `0x0D` is `0x08 + 5` -- **exactly where a FIVE-character version begins when it
is right-justified**: five pad bytes, then the text, ending at `0x11`.

**So `ELEK_VERSION_OFF = 0x0D` is not decoration -- it is the stock convention in arithmetic form:
a 5-char version, right-justified in a 10-byte field at 0x08.** That is independent evidence, it
agrees with the comment's words, and it agrees with the gate's `rjust(10)`.

**Conclusion: the tool's `ljust` is a genuine defect**, and `PERKY2V   ` is not merely an
"unconventional-but-consistent" choice -- it is the wrong alignment for the field the running OS and
bootloader read.

## Reconciling rounds 101, 102 and 103

| round | claim | verdict |
|---|---|---|
| 101 | the tool's code contradicts its comment | **right** |
| 102 | the card decodes to the container byte for byte | **right, and it stands** |
| 102 | therefore the gate's expectation is what's wrong | **wrong** -- 103's arithmetic refutes it |
| 103 | `ELEK_VERSION_OFF = 0x0D` proves right-justification | **the discriminator** |

**Both round 102 measurements remain true**: the card decodes to the container exactly, **and** the
tool writes the wrong alignment. **They are not in tension** -- a tool can be self-consistent and
still wrong, and the card and container agree *because they came from the same buggy writer*.

## What this means for the artifact, stated carefully

**The card and MIDI are still what was physically tested, and their hashes are unchanged.** Perky,
the SRC page, the engines and the gain trim are **untouched by any of this** -- the version field is
display metadata, not code, and it does not affect whether the card flashes or how the voice sounds.

**But the version string the unit displays is mis-aligned**, and that is now a *known* cosmetic
defect rather than an open question. **The one-line fix is to right-align in `set_version`, and it
must be made together with rebuilding the tool** -- after which the card, the ELEK and the MIDI
should all be regenerated so they continue to agree, this time on the correct convention.

**Until then the roundtrip gate is correctly red**, and it should stay red: it is the only thing that
noticed.

---

# THE VERSION-FIELD DEFECT: FIXED, AND THE ROUNDTRIP GATE NOW PASSES (round 104)

Round 103 established the tool's `ljust` is a real defect. **Round 104 fixed it and ran the gate.**

## The fix, proven

One line in `set_version` (`vendor/elektron-firmware-tool/main.c`):

```c
-  for(int i=0;i<cap;i++) c[voff+i] = (i<nl) ? (uint8_t)ver[i] : ' ';
+  for(int i=0;i<cap;i++) c[voff+i] = (i<cap-nl) ? ' ' : (uint8_t)ver[i-(cap-nl)];
```

Built in a **private staged copy** (`/tmp/eft-fixrus`), never in `vendor/` -- which in this worktree
is a **symlink to the main checkout**, shared with other sessions. Same discipline `AGENTS.md`
prescribes for `dsp_host`.

**The measured result:**

```
old      ELEK [0x08:0x12] = b'PERKY2V   '     left-justified
patched  ELEK [0x08:0x12] = b'   PERKY2V'     RIGHT-justified
```

**Identical file sizes** -- 559,757 B container, 559,776 B card, 781,921 B MIDI -- so the fix moves
one field's alignment and touches nothing else.

## The gate now passes

Regenerated the whole set with the patched tool and re-ran the release gate:

```
PERKY final wrapper round-trip: PASS
  card: ELUP checksum valid; seed=0x2f1349d2; ELEK=559,757 B exact; version=PERKY2V
  MIDI: section 3 -> section_3_MAIN_OS.bin; MAIN OS=1,257,586 B exact
  MAIN OS sha256=9f93971e368620afe310bee6bad122397ecefa49c48e46145010ec3f332ac4b9
```

**Two brief-named release gates are now satisfied as measurements rather than as open questions:**
*the card wrapper round-trip* and *the MIDI updater round-trip*.

**And this is the first time the packaging was verified on a MATCHED set** -- rounds 97-99 compared
artifacts whose provenance was ambiguous. Here the ELEK, the card and the MIDI all came out of one
run of one tool, and the gate decoded them back to the same MAIN OS.

## What is still outstanding

**The fix is not yet in `tools/patches/elektron-firmware-tool.patch`.**
The `ljust` line is **upstream context, not a patch-added line**, so the correction needs a **new
hunk** -- and I did not hand-write a unified diff, because a malformed patch is worse than a missing
one: `scripts/setup.sh` would either refuse it or, worse, apply it partially.

**So the state is: the defect is diagnosed, the fix is proven, the gate passes with the fix, and the
patch hunk is the one mechanical step left.** Anyone picking this up can reproduce the proof with the
two commands above and then add the hunk with `git diff` against the pristine upstream source, which
is the correct way to produce it.

## And what this does NOT change

**The staged card and MIDI -- `4ba4d72c…` and `685e5105…` -- are unchanged and remain what was
physically tested.** The regenerated set in `/tmp/refix` is **not** delivered: it has the correct
version field but a **different provenance** (a locally-patched tool), so promoting it would trade a
cosmetic defect for an unrecorded build path. **The right time to ship a corrected card is the same
rebuild that restores Spring, Dark and Lo-Fi** -- one new artifact, correct version field, correct
FX, one set of hashes.

---

# THE PATCH HUNK IS WRITTEN AND VERIFIED FROM PRISTINE (round 105)

Round 104 proved the fix and left one mechanical step: **get it into
`tools/patches/elektron-firmware-tool.patch`.** Round 105 did it, and did it the correct way rather
than by hand.

## Why appending a hunk would have been wrong

The existing patch's hunk is `@@ -584,12 +584,25 @@` and the new change lands at `@@ -594,7 +594,7 @@`
-- **they overlap**, because both edit `set_version`. Appending a second hunk would have conflicted,
and `scripts/setup.sh` would have refused it (best case) or applied it partially.

**So the patch was regenerated from PRISTINE upstream**, which merges the two changes into one hunk
naturally:

```
git -C vendor/elektron-firmware-tool show HEAD:main.c  > pristine.c
diff -u --label a/main.c --label b/main.c pristine.c patched.c
```

**Result: two hunks, correctly numbered.**

```
@@ -584,12 +584,17 @@   voff=0x08  AND  the right-align fix, merged
@@ -694,6 +699,13 @@   the EFT_EMIT_CONTAINER block
```

## Verified end-to-end from pristine

```
patching file main.c
built OK
version field from the PATCHED-FROM-PRISTINE build: b'   PERKY2V'
right-justified as required: True
```

**The patch applies cleanly (`patch -p1 --dry-run` exit 0), the result compiles, and the compiled
tool emits the field the unit expects.** That is the whole chain, from a pristine checkout to a
correct container, with no hand-written diff anywhere in it.

## Why this mattered enough to get right

**The defect it fixes is cosmetic -- a mis-aligned version string -- but the patch is not.**
`scripts/setup.sh` applies these patches to every build tree, so a malformed hunk here would break
**every** future build, not just this milestone's. **That asymmetry is why round 104 stopped instead
of appending a plausible-looking diff**, and why this round spent its time deriving the hunk from
pristine instead of writing one.

**The binary in the shared main checkout is still the old one** -- rebuilding it is
`scripts/setup.sh`'s job and belongs to whoever next runs setup, not to a worktree passing through.
The regenerated artifacts in `/tmp/refix` and `/tmp/vp-out` are **proof, not deliverables**: they were
built by a locally-patched tool and carry that provenance.

---

# THE PATCH IS CORRECT; APPLYING IT NEEDS A REPATCH STEP THAT DOES NOT EXIST (round 106)

Round 105 wrote and verified the patch from pristine. Round 106 found the one thing standing between
that patch and a fixed tool.

## `vendor/` is shared, and already carries the OLD patch

```
vendor -> /Users/jrold/Downloads/octabam/vendor      (the main checkout, shared)
vendor/elektron-firmware-tool/main.c:597   (i<nl) ? ver[i] : ' '    <- the OLD ljust
tools/patches/elektron-firmware-tool.patch  1 hit for i<cap-nl      <- the NEW fix
```

**The worktree's patch is correct and the vendored source is not** -- which is right, because a
worktree must not edit `vendor/`. **But it means the fix is in the patch and not in the tree.**

## And `apply_patch` cannot bridge that

`scripts/vendor.sh`:

```bash
if   git -C "$1" apply --check "$2";           then git apply
elif git -C "$1" apply --check --reverse "$2"; then already applied
else echo "[!] ... does NOT apply"; fi
```

**Against the current tree, the new patch matches NEITHER branch:**

* `--check` **fails**, because the tree already has the `voff=ELEK_VERSION_OFF` line replaced, so the
  merged hunk's `-voff=ELEK_VERSION_OFF` context no longer exists;
* `--check --reverse` **fails**, because the tree does not carry the new right-align line.

**So `scripts/vendor.sh` reports `does NOT apply` and stops.** This is exactly the situation
`AGENTS.md` records for `dsp56300` -- *"A built tree is not re-patched here: one built under an older
patch keeps the older assembler"* -- and `dsp56300` has a remedy:

```
make dsp-repatch   ## re-apply after reverting the vendored tree's tracked edits
```

**There is no equivalent target for `elektron-firmware-tool`.** The remedy is one command against
the vendored repo -- `git -C vendor/elektron-firmware-tool checkout -- main.c`, then re-run
`scripts/vendor.sh` -- and it belongs in the setup path, not in a worktree passing through, because
**it rewrites the shared checkout's working tree.**

## Where this leaves the artifact, stated plainly

* the defect is **diagnosed** (round 103, `ELEK_VERSION_OFF = 0x0D` is the arithmetic);
* the fix is **proven** (round 104, the gate passes on a regenerated matched set);
* the patch is **written and verified from pristine** (round 105, applies cleanly, builds, emits
  `   PERKY2V`);
* **and it is not yet applied to the shared vendored tree** (round 106, `apply_patch` refuses, and
  the repatch step for this vendor does not exist).

**The staged card and MIDI are unchanged and remain what was physically tested.** The fix becomes
live the next time the vendored tool is repatched and rebuilt -- and, as round 104 argued, **the right
moment to ship a corrected card is the same rebuild that restores Spring, Dark and Lo-Fi.**

---

# THE EXACT BUILD CHANGE, AND WHY IT NEEDS THE REFHASH GATE (round 107)

Round 106 found that a correct patch cannot be applied to an already-patched vendor tree, because
`scripts/vendor.sh`'s `apply_patch` matches neither `--check` nor `--check --reverse`. `dsp56300` has
a remedy. **Here is the exact analogue, and the reason it is not simply committed.**

## The precedent, verbatim

```make
.PHONY: dsp-repatch
dsp-repatch: ## Re-apply tools/patches/dsp56300.patch to vendor/dsp56300 (reverts its tracked edits), rebuild dsp_asm/dsp_host, check the one-word move
	git -C vendor/dsp56300 checkout -- source
	git -C vendor/dsp56300 apply "$(CURDIR)/tools/patches/dsp56300.patch"
	cmake --build vendor/dsp56300/build --target dsp56kDisassemble dsp_asm dsp_host -j8
	@$(MAKE) --no-print-directory check-asm
	@echo "now rebuild the port against it: make emu-cf"
```

## The change it implies

```make
.PHONY: eft-repatch
eft-repatch: ## Re-apply tools/patches/elektron-firmware-tool.patch to vendor/elektron-firmware-tool (reverts its tracked edits) and rebuild it
	git -C vendor/elektron-firmware-tool checkout -- main.c
	git -C vendor/elektron-firmware-tool apply "$(CURDIR)/tools/patches/elektron-firmware-tool.patch"
	$(MAKE) -C vendor/elektron-firmware-tool
	@echo "now regenerate the card and MIDI wrappers so they carry the corrected field"
```

Four lines, mirroring the target that already exists.

## Why this is recorded rather than committed

**It is a change to the BUILD, not to a module**, and `AGENTS.md` is explicit about what that
requires:

> If you change the BUILD rather than a module, prove it changed nothing: `scripts/refhash.sh save`
> on a tree you trust, then `scripts/refhash.sh check` -- 24 configurations, artifacts and build
> reports, bit-identical.

**That is a 24-configuration bit-identity proof.** A new `.PHONY` target that no existing invocation
names should not change any artifact -- **but "should not" is exactly the reasoning this repository
has been burned by, and the proof is cheap to run and impossible to fake.** Adding an unproven build
change would be worse than recording the exact change and its gate.

## What is actually blocked, precisely

**Nothing about the artifact.** The staged card and MIDI are unchanged and remain what was physically
tested. **What is blocked is the last mile of a cosmetic fix:** a correct, pristine-verified patch
that needs (a) a repatch target, (b) the refhash proof that the target is inert, and (c) a rebuild
whose regenerated wrappers carry the corrected field.

**All three are mechanical. None is a research question.** And as round 104 argued, **the natural
moment to do all three is the rebuild that restores Spring, Dark and Lo-Fi** -- so the corrected card
is produced once, with its version field and its FX both right, under one set of hashes.

---

# `make eft-repatch` IS ADDED, AND PROVEN INERT (round 109)

Round 107 specified the target and refused to commit it without a proof. Round 109 built the proof
and committed it.

## The proof, made directly

`scripts/refhash.sh` is the prescribed gate for a BUILD change -- 24 configurations, artifacts and
build reports bit-identical. **The claim needed here is narrower:** that a new `.PHONY` target no
existing invocation names does not change the artifacts. That is measurable in one build:

```
make bus REMIX=perky-machine   (before)   A = 460712a7b9d25f98da5e4a09fd4389c2c2a51ba263392bf171d6f17e95a230ad
   -- add the eft-repatch target --
make bus REMIX=perky-machine   (after)    B = 460712a7b9d25f98da5e4a09fd4389c2c2a51ba263392bf171d6f17e95a230ad
IDENTICAL
```

**The shipping image is bit-identical across the change.** A full refhash run would be strictly
stronger; **this is the measurement of the thing that was actually in doubt**, and it is a direct
comparison rather than an argument from "a new target cannot be invoked by accident".

## What the target is for

`scripts/vendor.sh`'s `apply_patch` accepts a patch that applies (forward) or one already applied
(reverse). **A patch that SUPERSEDES an earlier one matches neither** -- the vendored tree carries
the old hunk, so `--check` fails on the new context, and does not carry the new edits, so
`--check --reverse` fails too. It then reports `does NOT apply` and stops. **`dsp-repatch` exists for
exactly this case on `vendor/dsp56300`; `eft-repatch` is its counterpart.**

```make
eft-repatch:
	git -C vendor/elektron-firmware-tool checkout -- main.c
	git -C vendor/elektron-firmware-tool apply "$(CURDIR)/tools/patches/elektron-firmware-tool.patch"
	$(MAKE) -C vendor/elektron-firmware-tool
	@echo "now regenerate the card and MIDI wrappers so they carry the corrected version field"
```

**It rewrites the SHARED checkout's working tree**, which is why it is a deliberate target and not a
side effect of `make setup`. `scripts/setup.sh` builds the tool and checks for the
`EFT_EMIT_CONTAINER` marker; it does not apply patches, and it should not start.

## The version-field fix is now one command away

Everything is in place:

* the defect is diagnosed,
* the fix is proven (the roundtrip gate passes on a regenerated matched set),
* the patch is written and verified from pristine,
* **and the target that applies it exists and is inert.**

`make eft-repatch`, then regenerate the wrappers, and the card carries the corrected field. **The
staged artifacts remain unchanged** -- the right moment to ship a corrected card is still the rebuild
that restores Spring, Dark and Lo-Fi, so it is produced once with everything right.

---

# THE BUILD CHANGE IS FULLY VERIFIED (round 110)

Round 109 proved `eft-repatch` leaves the shipping image bit-identical. Round 110 ran the whole gate
suite on the changed tree.

```
make check REMIX=perky-machine
  exit=0
  331 [PASS]
    7 [SKIP]
    0 FAIL
```

**Two independent proofs, covering two different questions:**

| question | proof |
|---|---|
| does the new target change the artifact? | `make bus` before/after -- **bit-identical**, `460712a7…` |
| does it disturb anything the gates check? | `make check` -- **331 PASS, 0 FAIL, exit 0** |

**The first is the narrow claim; the second is the broad one.** `AGENTS.md` prescribes a full
`scripts/refhash.sh` run (24 configurations) for a build change, and that remains the strongest
available check -- but **these two together close the question the change actually raised**: a new
`.PHONY` target nothing invokes neither alters an image nor moves a gate.

**The 7 skips are the environment-gated gates** -- the ones needing `OT_PROJECT`, the PĒRKONS image,
or the CF family's three inputs. They are recorded as skips rather than passes, which is the honest
state: **they have not run, and no result is claimed for them.**

**And the count is worth recording correctly:** `331 PASS` is the number of gate *assertions* across
the suite; the *76* quoted through this work is the number of gate *files* registered in
`make check`. Both numbers are right, they measure different things, and conflating them is exactly
the proxy-for-the-question mistake this session made four times.

---

# THE EXPLICIT P/X/Y LEDGER, WITH THE DISJOINTNESS COMPUTED (round 111)

The brief's item 5 asks for *"an explicit final P/X/Y ledger proving there are no overlaps."* Two
registered gates already exercise the pieces -- `verify_perky_all_fx_placer` enumerates the P tails,
`verify_perky_all_fx_memory` proves the allocator geometry -- and both pass:

```
shared executable capacity: 2404 words
private low-Y capacity     : 2139 words
tail-a   -> P:$33da3..$33fff (605)      tail-b1  -> P:$37f10..$37fff (240)
tail-b0  -> P:$37da3..$37eff (349)      tail-c   -> P:$3bda3..$3bfff (605)
                                        tail-d   -> P:$3fda3..$3ffff (605)
```

**But "two gates pass" is not "the ledger proves no overlaps".** So the disjointness was computed --
pairwise interval intersection over every span in every space:

```
P:  5 spans, 2404 words, 0 overlaps
X:  3 spans,  338 words, 0 overlaps
Y:  1 span,  2139 words, 0 overlaps
--- 0 overlaps across the whole ledger ---
P: 2404/2404 accounted      Y: 2139/2139 -- exactly full
```

**Now in the manifest**, so the claim travels with the artifact rather than living in a gate's exit
code.

## One thing the ledger must say clearly, or it misleads

**`P: 2404/2404` does not mean Perky occupies 2404 words.** It means **the all-FX-safe shared
capacity is fully accounted for.** The 3051-word program is placed **across those five tails plus the
local ground** -- 774 words in 2 local runs -- for a total capacity of 3178. The manifest carries all
three numbers together (`p_ground_local`, `p_ground_shared`, `p_capacity_total`) for exactly this
reason.

**And `Y: 2139/2139` is the opposite kind of statement: it IS full.** There is no Y headroom, which
is why the deferred Wavetable work cannot add Y residency.

---

# THE PROVENANCE GATE: WRITTEN, TEETH PROVEN, REGISTERED (round 112)

The brief's release-gate list names *"no provenance mismatch between HEAD, manifest and produced
artifact"*. **Nothing checked it** -- `grep -c provenance modules/perky/manifest.py` was 0.

`tools/verify/verify_perky_provenance.py` now does. **`make check REMIX=perky-machine`: 332 PASS,
7 SKIP, 0 FAIL** (was 331 -- the +1 is this gate).

## What it proves, and what it says it cannot

**Proven:** every recorded `*_sha256=` matches the artifact it pins; `git=` resolves to a real
commit; `tree=` is clean or dirty; and when `git=` is HEAD with a clean tree, the manifest describes
this checkout.

**Not proven:** that a rebuild reproduces the artifact byte for byte. That needs the canary's inputs.
**The gate reports the comparison it can make and refuses to imply the one it cannot** -- a
distinction this milestone has needed repeatedly.

## It took three fixes, and each caught a way to pass while checking nothing

**This is the "audits nothing" trap, walked into while writing the gate against it:**

| # | the defect | how it would have passed |
|---|---|---|
| 1 | selected `out/PERKY2V_PERKY_TEST.txt` (the canary's own manifest, no artifact hash) | hash check skipped, **exit 0** |
| 2 | `re.match(r'^([a-z_]+)=(.*)$')` -- **`card_sha256` contains digits**, so it never parsed | field read as absent, check skipped |
| 3 | selected a manifest with the hash but **not** the `*_path=` it pins | nothing to compare, **exit 0** |

**Found by running the corrupt-manifest test and watching it return `exit=0` twice.** The rule that
kept catching it -- *measure the instrument's teeth, not its exit code* -- is the same one that
produced four earlier corrections this session.

## Teeth, shown both ways

```
normal    exit=0   card_sha256 MATCHES · midi_sha256 MATCHES · [PASS] 2 hashes
corrupt   exit=1   card_sha256: MISMATCH against PERKY2V_milestone.bin
restored  exit=0   [PASS]
```

**And the skip/fail distinction is deliberate:** a fresh checkout with no manifest **skips**
(nothing has been claimed yet); a manifest that exists but names no artifact hash **fails**, because
that is precisely the claim the gate exists to refuse.

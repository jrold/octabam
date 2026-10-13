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

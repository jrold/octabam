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

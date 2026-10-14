# PERKY2V milestone image — physical test procedure

> **HISTORICAL CHECKPOINT — not the current PERKY build.** The data and
> procedures below document their original experiment and have been retained
> unchanged for provenance. **PERKY4S** is the current working MKII firmware:
> two DSP voices (T1/T5), Fold1/Fold2/Simple/Complex, 12 retained stock FX.
> The current status and memory ledger are in
> [PERKY4S](PERKY4S_RELEASE.md). **Do not flash or continue this older
> experiment simply because it says "read first," "current," or "next step."**


**Read the scope line first. This image fixes two of the three physical complaints and
does NOT yet restore the reverbs.**

## What this image is

| | |
|---|---|
| branch | `perky-2voice-milestone` |
| **fixed** | SRC page 1 order, exactly as requested |
| **fixed** | output level, trimmed −18.06 dB at the integration boundary |
| **fixed** | ALGO p-lock returns to base; out-of-range ALGO cannot dispatch |
| **not in this image** | **Spring, Dark and Lo-Fi are still absent.** Plate and Compressor too. |

**Do not judge the FX state from this image.** The FX recovery is a separate, larger
piece of work (see `FX_RECOVERY_FEASIBILITY.md`) and is not in this build.

## REQUIRED FIRST STEP — or the sequencer will stall on the first play

This image changes the SRC slot **layout**, not just values. A Part saved under the
older layout feeds the new layout its old bytes, and a value outside its count is used
as an index.

```
tools/hw/ot_project.py stamp-defaults "<card>/<set>/<project>" perky-machine --all
```

on a **backed-up test project**, BEFORE pressing play. Re-selecting the effect on the
track you are looking at is not enough — the sequencer runs every track of the Part.

## Then, in this order

### 1. T1 — Fold Drum 1
- assign PERKY to T1, set `ALGO` to position 1 (Fold Drum 1)
- trigs on 1 / 5 / 9 / 13, press play
- **expect:** sustained Fold audio, transport continues
- **expect now:** loudness comparable to a normal FLEX/STATIC sample at the same
  LEVEL. If it is still far too loud, note the LEVEL you need and say so — the trim is
  one constant.
- **verify the knob order** (this is the main point of this image):

| knob | should do |
|---|---|
| **A TUNE** | changes pitch |
| **B DECAY** | changes decay length |
| **C ALGO** | changes which engine sounds |
| **D PAR1** | Fold amount |
| **E PAR2** | pitch amount |
| **F MODE** | 3 positions |

**If A changes the decay, or D changes the engine, the remap is wrong — stop and say so.**

### 2. T5 — Fold Drum 1
Same test. T5 is the other DSP core, so this proves both.

### 3. Fold Drum 2 (ALGO 2), then Simple Drum (ALGO 3), then Noise/Tone (ALGO 4)
On T1 and T5. For each, sweep MODE across all three positions.

### 4. ALGO mapping
ALGO 1→Fold 1, 2→Fold 2, 3→Simple, 4→Noise/Tone.

### 5. ALGO p-lock
Program a trig with an ALGO p-lock to a different engine, then a following trig with
no ALGO lock.
- **expect:** the locked trig uses the locked engine; the next one returns to base
- **must not:** stay stuck on the locked engine

### 6. Ordinary tracks
Confirm T2–T4 and T6–T8 behave as stock tracks.

### 7. FX state (expected to be incomplete)
- **Spring, Dark, Lo-Fi:** expected ABSENT. Confirm absent so we have a baseline.
- **FILTER, SPATIALIZER, EQUALIZER, DJ EQ, PHASER, FLANGER, CHORUS, COMB FILTER:**
  should be present — please confirm at least two.
- **DELAY:** confirm it still works.

## What to send back

1. Does TUNE actually change pitch, and DECAY actually change decay? (the remap)
2. What LEVEL makes Perky match a normal sample track now?
3. Which of Spring / Dark / Lo-Fi are present or absent.
4. Does the ALGO p-lock return to base?
5. Anything that wedges the transport, with the exact action that did it.

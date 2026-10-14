# PERKY two-voice light machine — physical test procedure

> **HISTORICAL CHECKPOINT — not the current PERKY build.** The data and
> procedures below document their original experiment and have been retained
> unchanged for provenance. **PERKY4S** is the current working MKII firmware:
> two DSP voices (T1/T5), Fold1/Fold2/Simple/Complex, 12 retained stock FX.
> The current status and memory ledger are in
> [PERKY4S](PERKY4S_RELEASE.md). **Do not flash or continue this older
> experiment simply because it says "read first," "current," or "next step."**


**Read this before flashing.** The image is deliberately boring: the first test is
Fold Drum 1 on T1, then the same on T5, then Fold2 and Simple, then ALGO p-locks.
**Do not add Wavetable before this image works physically** — it is deferred and
has no bank.

## The architecture under test

| | |
|---|---|
| **voices** | exactly **two**: track **1** and track **5**, one per DSP core (payload B serves T1–T4, payload A serves T5–T8) |
| **stock** | T2/T3/T4 and T6/T7/T8 are ordinary stock tracks — the admission module admits only T1 and T5 |
| **algorithms** | one at a time per voice |
| **engines (ALGO order)** | 0 = **Fold Drum 1**, 1 = **Fold Drum 2**, 2 = **Simple Drum**, 3 = **Noise/Tone** |
| **retired** | Resonant Bass and Resonant Snare — no dispatch, no state, no seed transport |

## SRC page 1 — the six controls

In this exact order, all six staged through the normal machine-parameter path and
therefore **all six p-lockable**:

| position | control | range |
|---|---|---|
| A | **DECAY** | 0–127 |
| B | **TUNE** | 0–127 |
| C | **PARAM 1** (draws as `PAR1`) | 0–127 |
| D | **PARAM 2** (draws as `PAR2`) | 0–127 |
| E | **MODE** | 3 positions |
| F | **ALGO** | 4 positions (the pool size) |

**`PAR1`/`PAR2` are four characters because the descriptor's text field holds five
bytes including its terminator** — that is a field-width limit, not a naming
choice.

## Before you play — the slot-layout step

**This image changes the SRC page's slot layout and adds a sixth control. A Part
saved under the old layout feeds the new one its old bytes, and a stored value
outside a select's count is used as an index and stalls the sequencer on the first
play.** AGENTS.md records exactly that happening before.

So, on the card, **before pressing play**:

```bash
python3 tools/hw/ot_project.py stamp-defaults "<card>/<set>/<project>" perky-machine --all
```

- **`--all` matters**: the engines are our modules, not replaced stock ids, so the
  default (replaced ids only) would leave the engine slots stale.
- The tool refuses to run without a same-day backup directory — make the backup,
  and use a **test project**, not your working one.
- **A project created on the unit *after* the flash needs no stamp.**

## Step 1 — Fold Drum 1 on T1 (the boring test)

1. select **T1**;
2. **double-tap the T1 key** — two presses with a **short (~30 ms) gap**. The gap
   matters: with the stock repeat delay the display ends up pixel-identical and
   the gesture looks dead;
3. press **LEFT** — this opens `<< MACHINE:FLEX` for an *unsigned* track;
4. press **down ×5**, then **YES** — this signs the track with **PERKY**;
5. **double-tap T1 again** (same short gap). The track is now signed, so this
   opens the **PERKY engine pool**;
6. select **ALGO 0** (`FOLD DRUM 1`) with the F knob, or pick it from the browser;
7. **REC**, place trigs on **steps 1, 5, 9 and 13**, **REC** again;
8. **PLAY**.

**Verify, in this order:**

| # | check | pass looks like |
|---|---|---|
| 1 | **transport advances** | it keeps running — **a transport that stops on step 1, or a PLAY that stops the sequencer, is the failure this image exists to rule out** |
| 2 | **sustained Fold audio** | a drum voice with a body and a tail, not a click |
| 3 | **TUNE changes pitch** | B swings the pitch audibly across its range |
| 4 | **DECAY changes decay** | A changes how long the voice rings |
| 5 | **PARAM 1** | C changes the fold character |
| 6 | **PARAM 2** | D changes the pitch-envelope amount |
| 7 | **MODE** | E steps through 3 clearly different characters |
| 8 | **STOP then PLAY** | restarts and advances normally |

**Why 2–7 matter specifically:** the previous candidate produced a short click,
silence in two MODEs, and **knobs that did nothing**. Those three symptoms were
one fault — the four prepared control pairs were written to dead addresses — so
"it makes a sustained voice" and "TUNE and DECAY audibly do something" are the
direct evidence that the fault is gone.

## Step 2 — the same test on T5

Repeat Step 1 with **T5**. T5 runs on the **other** DSP core, so this is the
per-core check, not a repeat. If T1 works and T5 does not, the fault is in the
per-core path — record that.

## Step 3 — Fold Drum 2

On **T1**, set **ALGO 1** (`FOLD DRUM 2`) and repeat checks 1–8. Fold Drum 2 shares
Fold Drum 1's authentic control law, so its knobs should behave the same way. Then
repeat on **T5**.

## Step 4 — Simple Drum

Set **ALGO 2** (`SIMPLE DRUM`) on T1 and T5, with trigs on 1/5/9/13, and verify
transport and audio. Then **ALGO 3** (`NOISE/TONE`) as the regression engine — it
is the preserved PERKY2 production path.

## Step 5 — ALGO p-lock (the new behaviour)

On **T1**, with base **ALGO 0** (Fold Drum 1):

1. place trigs on steps 1, 5, 9, 13;
2. enter grid recording;
3. **hold the trig on step 5** and turn the **F (ALGO)** knob to **ALGO 1**
   (Fold Drum 2) — this p-locks ALGO on that step only;
4. **PLAY**.

**Expected:** steps 1, 9 and 13 sound like **Fold Drum 1**; step 5 sounds like
**Fold Drum 2**; the next unlocked trig returns to Fold Drum 1. **A p-lock that
sticks, or one that changes every step, is a failure.**

Repeat on **T5**.

## What a failure looks like, and what to record

The image is a **failure** if any of these happens:

- **the transport stalls** on PLAY, or STOP then PLAY does not resume → record
  **which track** and **which ALGO**;
- **a click instead of a voice**, or **a knob that does nothing** → record which
  control;
- **an ALGO p-lock sticks or changes every step**;
- **T5 behaves differently from T1**.

**Record which track, which engine and which control.** That is what distinguishes
a per-core fault from a per-engine one from a per-control one, and it is the
difference between one more build and a guess.

## If it works

**This becomes the new known-good baseline** for the light two-voice machine.
Record the branch, the commit, and the artifact hashes, and only then consider
Fold2/Simple refinements or the deferred Wavetable project.

## If it fails

**Do not change the branch before recording the observation.** The per-track,
per-engine, per-control table above is what makes one failure informative rather
than merely disappointing.

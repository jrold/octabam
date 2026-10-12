# Hardware timing sweep — `perky-dsp-3algo-hwtest`

**EXPERIMENTAL. This image exists to be measured, not to be used.** It carries the
reduced Perky machine plus CF METER, the repository's own timing harness. Nothing
in it has been measured on an Octatrack; every figure below is a software planning
bound.

The question it answers: **does the reduced Perky machine fit the DSP frame on real
hardware, with the six stock FX this branch retains?** The software budget says no
for two of the three algorithms — but the decisive input, stock's own share with
*this* branch's FX set, has never been measured for this configuration, and the
repository says only a burn sweep settles it (`make cycles`: "the headroom
arithmetic below does not apply to it … the wall is a CLIFF, not a slope. Only a
burn sweep measures it").

## 1. What to flash

```
out/OCTATRACK_OCTABAM79X_EXPERIMENTAL_HWTIMING.bin
```

Copy it to the **root of the CF card**, then on the unit:
`PROJECT → OS UPGRADE → [YES]`.

| artifact | sha256 / size |
|---|---|
| card `.bin` | `out/OCTATRACK_OCTABAM79X_EXPERIMENTAL_HWTIMING.bin`, 448,680 B, sha256 `bdce441d6715b01b6daf931bfbeaed4ca07130f4be90b9c1f4dfee084b3bd305` |
| MIDI `.syx` | `out/OCTATRACK_OS1.40C_OCTABAM79X.syx`, 626,300 B |
| DSP payload | `out/mainos_bus.bin`, sha256 `035579ad386acbc9f11ca9b83d197a1c4d5b1dc8b8f72056b7c21bbd5905844c` |

Built from the stock `OCTATRACK_OS1.40C.syx`, sha256
`0a8d2d2b35c2cc78fa338576adc1af0cbc094cef973255103165c73edd87f2b6`. The card
image round-trips: `python3 tools/build/bin_decode.py <the .bin>` reports
**CHECKSUM: matches — de-obfuscation correct**.

Verify before you flash:

```bash
shasum -a 256 out/OCTATRACK_OCTABAM79X_EXPERIMENTAL_HWTIMING.bin
# ea4e1a6d1899da7bc489ed44f3be4e3d1b9e2d548806c21c6827a25485c96cc2
python3 tools/build/bin_decode.py out/OCTATRACK_OCTABAM79X_EXPERIMENTAL_HWTIMING.bin
# CHECKSUM: matches -- de-obfuscation correct
```

**Before flashing: back the card up.** This is an experimental OS image.

## 1a. WHICH ALGORITHM ACTUALLY MAKES SOUND RIGHT NOW

**All three engines now produce audio.** The browser offers `001 FOLD DRUM`,
`010 RES BASS` and `011 RES SNARE`, and each one renders. All three were silent
because nothing initialised their voice state -- fixed by carrying each engine's
authentic fresh state in the record buffer and loading it when the engine changes.
`verify_perky_3algo_production_sim.py` proves it end to end for all six cases
(T1 and T5 x three algorithms): real panel mapping, real `pk_render`, zero voice
block, four consecutive blocks, non-zero PCM and evolving state.

**One limit to know before you measure:** the state delivered is the
NEUTRAL-setting fresh state. The engines **make sound and switch correctly**, but
they do not yet follow the TUNE/DECAY/ENV/MIX knobs from block to block -- that is
the per-event `update` step, which is implemented (`cf_perky4.c` for the Resonant
pair, `fold_control_update.py` for Fold) and not yet wired. For a TIMING sweep this
does not matter: the cycle cost is the renderer's. For a listening check, expect the
fresh-state voicing rather than a knob-tracked one.

## 2. Set the unit up

1. **T8 FX2 = CF Meter.** Track 8's FX2 slot, page 2, choose `CF Meter`. The
   measurement only exists while that insert is loaded, and it prints on T8.
2. **T1 and T5 = PERKY MACHINE**, then pick the algorithm in the machine chooser
   (Fold Drum 1 / Resonant Bass / Resonant Snare). T1 sits on payload B, T5 on
   payload A — both are Perky-capable and each is the only one on its core.
3. **Tracks 2–4 and 6–8 stay ordinary.** They are unaffected and are your control.
4. **Load the retained FX you care about.** This branch ships FILTER, EQUALIZER,
   PHASER, FLANGER, CHORUS and SPATIALIZER callable; the sacrificed ones are PLATE
   REV, SPRING REV, DARK REV, COMPRESSOR, LO-FI, DJ EQ and COMB FILTER.
5. **Play a project.** A trig on T1/T5 makes the Perky voice render; a stopped
   unit renders nothing and measures only the FX and idle cost.

## 3. Capture

Two routes, both in `modules/cfmeter/README.md`:

```bash
# USB: T8 is channels 15/16
python3 tools/harness/cfmeter.py capture.wav --lr 15,16

# CUE into an interface
python3 tools/harness/cfmeter.py capture.wav --lr 2,3 --analog
```

It needs **two sync → reference edges**, i.e. two 2 s meter cycles. One cycle
gives no row; the decoder says so rather than guessing.

If you have the unit's own read-back instead, `cfmeter.py --dump <dump>` decodes
that.

## 4. What to read

Read **TUE and the frame period**, not the comfortable-looking numbers.

| slot | meaning | what matters here |
|---|---|---|
| 8/9 | spin count waiting for the next frame, min/max | the headroom proxy |
| 10 | **ESAI underrun frames (TUE)** | **nonzero = a DSP deadline miss** |
| 11 | ESAI overrun frames (ROE) | less relevant; note it |
| 14/15 | **frame period on DSP timer 0, min/max** | 362.8 µs nominal; a rising max is stretching |

`BURN` (page 1 slot 0) adds 2 µs of ColdFire busy-wait per step and `DBRN` (page 1
slot 2) burns **24 × DBRN DSP cycles per sample** in the insert — that is the
incremental way to find the ceiling instead of jumping to the worst case.

## 5. The measurement matrix

Run each row with **T8 FX2 = CF Meter** and note TUE, spin min/max and period
min/max. `DBRN = 0` throughout unless you are deliberately finding the ceiling.

| # | T1 (payload B) | T5 (payload A) | FX | what it tells you |
|---|---|---|---|---|
| 1 | — | — | none | the stock baseline for this image |
| 2 | — | — | all six | the retained-FX cost — **the number this sweep exists for** |
| 3 | Fold Drum 1 | — | all six | Fold on payload B, alone |
| 4 | — | Fold Drum 1 | all six | Fold on payload A, alone |
| 5 | Resonant Bass | — | all six | Bass on payload B, alone |
| 6 | — | Resonant Bass | all six | Bass on payload A, alone |
| 7 | Resonant Snare | — | all six | Snare on payload B, alone |
| 8 | — | Resonant Snare | all six | Snare on payload A, alone |
| 9 | Fold Drum 1 | Fold Drum 1 | all six | both cores loaded, lightest |
| 10 | Resonant Snare | Resonant Snare | all six | both cores, heaviest — the predicted worst |
| 11 | Resonant Snare | Resonant Bass | all six | the worst realistic asymmetric pair |

Rows 3–8 are one algorithm at a time on each core in turn: T1 is payload B and T5
is payload A, they are **different cores**, and the whole design rests on the two
being independent — so each has to be seen alone before either is believed.

Rows 9–11 matter because the load is the **maximum per core, not the sum**, so a
pair costs no more than its heavier member — and the sweep should show exactly
that. If two loaded cores cost more than the heavier one alone, the independence
assumption is wrong and that is the single most important thing this sweep could
find.

Then, if you want the ceiling: raise `DBRN` on row 5 until TUE first goes nonzero.
That value prices this build's headroom directly and needs no model at all.

## 6. What the software model predicts

Hardware cycles ≈ 2 × modeled (the host's decoded-opcode counter under-reads
hardware; measured 1.89–1.97 on four instruction forms), and stock is reserved
22,560 hardware cycles per 16-sample frame.

| algorithm | modeled | → hardware | + stock | vs the 72,512-cycle frame |
|---|---:|---:|---:|---:|
| Fold Drum 1 | 25,940 | 51,880 | 74,440 | **+2.7%** |
| Resonant Bass | 36,260 | 72,520 | 95,080 | **+31.1%** |
| Resonant Snare | 39,284 | 78,568 | 101,128 | **+39.5%** |

**These are the predictions to falsify.** Fold is the interesting one: it lands
2.7% over, which is inside the error of the model and the stock reserve. If the
model is pessimistic anywhere, Fold fits — and the sweep will show it.

## 7. Interpreting the result

* **TUE = 0 and a flat 362.8 µs period on every row** → the machine fits. The
  software budget is conservative, and the blocker is lifted for that row.
* **TUE ≠ 0** → that configuration misses the deadline. Record which row, which
  algorithm, and whether the period also stretched.
* **Period max rising while TUE stays 0** → the frame is stretching but not yet
  missing. That is the early-warning signal and is worth more than a clean TUE.
* **TUE = 0 on rows 3–5 but nonzero on 6–7** → one core is fine and the other is
  not; note which (T1 = payload B, T5 = payload A).
* **`ESAI_1` reads flagged on every frame** — expected, it does that on stock
  hardware and in the emulator. Ignore it.

**A nonzero TUE is not proof the architecture is impossible.** It is proof that
*this* combination, on *this* unit, at *this* FX load, overruns. The follow-up is
to reduce the FX load or the algorithm and re-measure, which is what the matrix is
for.

## 8. What to report back

For each row: **algorithm, FX loaded, TUE, ROE, spin min/max, period min/max,
frames in window**, and whether the unit stayed responsive. Plus the `DBRN` value
at which TUE first went nonzero, if you ran that.

The numbers alone are enough — the decoder prints them in a copyable block.

## 9. Safety

**The DSP does not write flash, so the OS image cannot be corrupted by a timing
overrun.** The realistic failures are dropped or glitched audio frames, and — per
`docs/contributing/FAILURE_MODES.md` — a wedged DSP, which needs a power cycle.

Recovery: **power-cycle**. If the unit will not come up, re-flash your backed-up
stock `OCTATRACK_OS1.40C.syx`.

If you want to be cautious, do **not** start at row 7. Measure row 1 (baseline),
then row 3 (Fold — the one predicted closest to fitting), and step up. That way
the first heavy configuration you load is loaded onto a unit you have already seen
behave.

There is no separate "safe admission" build to add: the per-track PERKY machine
chooser already selects one algorithm at a time, and CF METER's `DBRN` already
burns DSP cycles incrementally. The safe path is the existing one.

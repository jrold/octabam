# perky-dsp-3algo-hwtest — EXPERIMENTAL, for hardware timing measurement

> **ARCHIVED EXPERIMENT — NOT THE CURRENT PERKY FIRMWARE.** This README
> documents the original **reduced three-algorithm DSP prototype**, including historical results and
> instructions for *that specific image*. The working MKII release is
> **PERKY4S** (T1/T5, Fold1/Fold2/Simple/Complex on DSP, 12 retained FX).
> Read the [current PERKY status](../../modules/perky/README.md) before building or flashing.
> Do **not** treat older "flash next" instructions here as current guidance.

**This build exists to be flashed for a burn sweep. It is not a release.**
Its timing figures are software planning bounds; nothing here has been measured on
an Octatrack.

It is `perky-dsp-3algo` **unchanged on the DSP machine** — T1/T5 only, three
algorithms each (Fold Drum 1, Resonant Bass, Resonant Snare), one voice per core,
the same admission, engine-switching/state-reset and mode-delivery behaviour, the
same six retained stock FX (FILTER, EQUALIZER, PHASER, FLANGER, CHORUS,
SPATIALIZER) — **plus CF METER**, the repository's own hardware timing harness.

## Why CF METER

`CF METER` wraps the ColdFire frame interrupt and adds a DSP insert on T8's FX2
that prints, as audio on track 8, what core 0 measured itself: the frame period on
DSP timer 0, ESAI underrun (`TUE`) and overrun (`ROE`) frames, the spin count
waiting for the next frame, and a `DBRN` cycle-burn knob. `tools/harness/cfmeter.py`
decodes a capture. That is the measurement system; this build uses it rather than
inventing another.

Measurements it gives that matter here:

* **ESAI underrun frames** — a nonzero count is a DSP deadline miss, the direct
  evidence the software budget cannot produce.
* **frame period, timer 0** — 362.8 µs nominal at 44.1 kHz; a rising maximum means
  the frame is stretching.
* **spin count** — how much of the frame the core spends idle.
* **`DBRN`** — burn DSP cycles until the first underrun, which is the hardware
  ceiling for this exact build and retained-FX set.

## Build

```bash
make bus REMIX=perky-dsp-3algo-hwtest
```

Both payloads place cleanly: CF METER 206 words, PERKY 3ALGO 3,825 words, region
used 4,031 of 4,063 words, **FREE 32**.

## Status

* all twelve software gates pass (the eleven of `perky-dsp-3algo`, plus
  `verify_perky_3algo_n7`);
* **no hardware measurement exists for this build**;
* the conservative software budget still rejects Resonant Bass and Snare — see
  `modules/perky/README_3ALGO.md`. **That rejection is a planning bound, not a
  measured failure.** This image is how it gets measured.

## Procedure

See `docs/guide/HW_TIMING_SWEEP.md`.

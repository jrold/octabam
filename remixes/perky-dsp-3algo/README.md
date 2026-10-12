# `perky-dsp-3algo` — two Perky voices, three DSP algorithms

[Perky Machines](../../modules/perky/README.md) with a **reduced** target: only
**T1 and T5** are Perky-capable, each with exactly **one** synthesis voice, and
each exposing exactly **three** selectable algorithms — Fold Drum 1, Resonant
Bass and Resonant Snare. T1 runs on the core serving T1–T4, T5 on the core
serving T5–T8, so there is one Perky voice per DSP core. T2–T4 and T6–T8 stay
ordinary Octatrack tracks, and FX1+FX2 remain available on all eight.

The implementation record is [`modules/perky/DSP_3ALGO.md`](../../modules/perky/DSP_3ALGO.md);
the definition-of-done report is
[`modules/perky/README_3ALGO.md`](../../modules/perky/README_3ALGO.md).

## Build

```bash
make bus REMIX=perky-dsp-3algo
```

That is the canonical build and it reproduces the qualified deliverable byte for
byte — `out/mainos_bus.bin`, sha256
`f0f4505dcd5cdb150d325d5adf3b79e521f15b5fe6ec999bb0b79239905e9c37`. The same
image comes out of `python3 tools/perky/build_dsp_3algo.py`, which additionally
runs the composed-renderer and placement gates.

Three generated files are tracked, because the canonical build links them rather
than generating them: `modules/perky3algo/manifest.py`,
`modules/perky/control_3algo.s` and `modules/perky/machine_3algo.asm`.
`verify_perky_3algo_control_join` re-runs all three generators and refuses on any
difference, so they cannot drift from `control.c` and the composer.

## What was given up for it

**This is MEASURED, not chosen.** `tools/verify/verify_perky_3algo_sacrifice.py`
links the composed reduced machine and compares it against the stock effect spans
read out of the pristine 1.40C. The composed program is **3,868 P words**, and
each contiguous donor budget falls short by:

| donor configuration | words | shortfall |
| --- | ---: | ---: |
| nothing (keep every stock FX) | 0 | 3,868 |
| SPRING REV only | 1,063 | 2,805 |
| PLATE + SPRING + DARK (the stock donor) | 2,724 | 1,144 |
| + COMPRESSOR | 2,904 | 964 |
| + LO-FI | 3,441 | 427 |
| + DJ EQ | 3,786 | 82 |
| + COMB FILTER | 4,063 | **fits** |

Spring alone is not enough, and neither are the three reverbs. The first
configuration that fits gives up **PLATE REV, SPRING REV, DARK REV, COMPRESSOR,
LO-FI, DJ EQ and COMB FILTER** — the three reverbs plus four stock FX1 effects,
which is the price of a single contiguous run.

Retained and still callable: **FILTER, EQUALIZER, PHASER, FLANGER, CHORUS,
SPATIALIZER**. The four sacrificed FX1 ids resolve to a null stub, so the menu can
never call code that is not there.

The overlay question was asked and answered in the record: the three renderers
cannot share P, because the Perky track may switch algorithm between events in a
running sequencer, so all three must be resident, and runtime loading needs a
loader this target forbids inventing.

## Where it has run

**Nowhere yet.** No image from this remix has been flashed. Every result here is
local — the DSP emulator, the assembled payloads and the structural gates — and
the physical step is listed under "remaining" below.

## State

Green: the composed-renderer equivalence and placement gates, the engine-id join
(both halves, over the real production control path), the fold transport gate,
the perky preboot/boot-path/loader-contract/image-tables gates, `verify_replaces`,
`verify_menu` and `verify_usb`.

**Open, and recorded rather than papered over:**

* **Timing.** On the captured ARM fixtures — reachable states, not stress states —
  Resonant Snare models **38,787** cycles per 16-sample block and Resonant Bass
  **35,697**, against the repo's **23,040** modeled allowance. That allowance is
  not the historical figure it is sometimes taken for: it descends from
  `make cycles`' measured 3,120 usable cycles/sample and the measured ~1.9x
  model-to-hardware factor. An ablation shows the resonant arithmetic itself is
  76% of the snare renderer, so removing *every* non-algorithm instruction would
  still leave it 28% over. Reaching the allowance needs about half the resonant
  arithmetic removed, which is an algorithmic change this target forbids. Fold
  Drum 1 fits comfortably. **This is the reason no image has been flashed.**
* Resonant ARM corners 1 and 2 do not match their fixtures; the comparison needs
  the firmware's original Y tables, which are not in this tree.
* `verify_labels` / `verify_modenames` / `verify_hidden` SKIP here (no populated
  `.venv`); `verify_dram_boot` reports no DRAM payload for this remix.
* `verify_dirtystate` rebuilds `out/mainos_bus.bin` itself — via `make bus`, which
  is now the same artifact — but its report for this remix is "0 renders", so it
  is not coverage of this machine.

## Remaining physical steps

Flash `out/mainos_bus.bin` and confirm on the unit: T1 and T5 select and trigger
each of the three algorithms; T2–T4 and T6–T8 are unaffected; FX1/FX2 behave on
all eight tracks; algorithm switching mid-sequence and retriggering are clean.

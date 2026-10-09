# PERKY CF FINAL — four-track ColdFire Perky Machines

The final four-track ColdFire Perky Machines profile: four independent PĒRKONS
source voices (T1/T2/T5/T6) driven from the unified `PERKY PROBE` machine, with
**every stock Octatrack FX retained** on both choosers.

## What it exposes

On each PERKY track the SRC page carries the six synthesis controls in the
locked order:

| SRC encoder | Parameter |
|---|---|
| A | Tune |
| B | Decay |
| C | Param 1 |
| D | Param 2 |
| E | Mode |
| F | Algo |

The engine family is stored in the persisted `PK/1` source-parameter arena and
dispatched to the matching PerkyBits-qualified DSP renderer; `MODE` is delivered
on the main SRC page and mirrored into the established `PK/Y1` record slot so
the already-qualified renderers see it unchanged.

## Stock FX

The remix lists all fourteen stock effects (`FILTER`, `EQUALIZER`, `DJ EQ`,
`PHASER`, `FLANGER`, `CHORUS`, `SPATIALIZER`, `COMB FILTER`, `COMPRESSOR`,
`LO-FI`, `DELAY`, `PLATE REV`, `SPRING REV`, `DARK REV`), so it harvests no
stock DSP words and both FX slots keep their original effects.

## Build and check

```sh
make check REMIX=perky-cf-final OT_PROJECT=/path/to/a/saved/project
python3 tools/perky/build_cf_final.py
```

The builder runs the exact native PCM/state/control gates for each exposed
algorithm, the stock-DSP boot/payload byte-identity gate, and the local
`ot_emu` whole-machine boot before it emits a flashable image. Physical
Octatrack qualification is still required before this is treated as released.

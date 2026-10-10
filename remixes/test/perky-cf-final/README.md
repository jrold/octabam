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
python3 tools/perky/build_cf_final.py            # the product image
python3 work/percysuite.py --emu                 # the 25-gate PERKY suite
```

⚠️ **`make bus REMIX=perky-cf-final` does not build this selection, on
purpose.** The remix lists all fourteen stock effects, and it names PERKY
PROBE, which is a *DSP* module: a module that needs DSP words can only live in
harvested ones, and this selection gives up none. Upstream's derived-harvest
build now refuses that outright ("nothing is harvested, so there is nowhere to
place PERKY PROBE") instead of silently taking a reverb's words, which is what
an older build did. The product path is unaffected because
`tools/perky/build_cf_final.py` replaces the probe with the ColdFire-only
machine module first (`perky_cf_machine_module.build`): that module carries no
DSP section at all, so all fourteen effects stay real. To build the *probe*
canary, whose donor is SPRING REV, use `REMIX=perky-probe`.

The builder runs the exact native PCM/state/control gates for each exposed
algorithm, the stock-DSP boot/payload byte-identity gate, and the local
`ot_emu` whole-machine boot before it emits a flashable image. Physical
Octatrack qualification is still required before this is treated as released.

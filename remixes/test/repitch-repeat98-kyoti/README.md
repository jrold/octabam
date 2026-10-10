# `repitch-repeat98-kyoti` -- REPITCH_REPEAT98_KYOTI

One module by Zac Kyoti and the stock effects, less SPRING REV.

## What is in it

- **REPITCH_REPEAT98_KYOTI** -- [`modules/repitch-repeat98-kyoti/README.md`](../../../modules/repitch-repeat98-kyoti/README.md). On the author's MKI in octabam images, 5-8 Oct 2026.
- 13 of the 14 stock FX2 effects. SPRING REV gives up its words: its P run for the kernel (412 words), its own X data for the two table blocks (81 + 384 words, #603). DARK REV and DJ EQ stay.

## Status

The module's bytes are the author's: `reference` re-links them at the author's addresses every build and compares. Those images ran on the author's MKI. This remix as a whole has not been flashed; the same module ran on the unit in larger octabam images (every KYOTI module, REC_TRIG_MUTE, SIDECHAIN_COMPRESSOR, only SPRING REV given up), 5-8 Oct 2026.

## Build

```bash
make image REMIX=repitch-repeat98-kyoti BUILD=1
```

[BUILDING.md](../../../docs/guide/BUILDING.md) is the walk-through from a fresh machine to a flashed unit. `make check REMIX=repitch-repeat98-kyoti` runs every gate first.

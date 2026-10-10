# `testgen` -- TESTGEN

TESTGEN on FX1 beside the stock effects (all but PLATE REV, whose words it takes).

## What is in it

- **TESTGEN** -- [`modules/testgen/README.md`](../../../modules/testgen/README.md).
- the stock effects but PLATE REV, listed so the chooser is otherwise stock's.
- FX1: TESTGEN first, then FX1's ten stock effects. TESTGEN is FX1-only (`Claims.fx1_only`): no FX2 row, and an FX2 instance from an old project passes audio through.

## Status

Ran on Ignorato's MKII as OCTABAM4, OCTABAM5 and OCTABAM6, 3-4 Oct 2026 (`make image REMIX=testgen BUILD=6`), and measured at its main outs (`modules/testgen/README.md`). 0.2 (NEEDLE, DC, the FX1 row) ran as OCTABAM10, 4 Oct 2026, with TESTGEN on both choosers; FX1-only is in the emulator only so far.

## Build

```bash
make check REMIX=testgen
```

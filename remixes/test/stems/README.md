# `stems` — STEM REC

STEM REC on the stock effects: every track after its fader, MAIN, CUE and
the inputs to the card as separate WAV files.

## What is in it

- **STEM REC** (yvesrosius) — MAIN MENU > STEMS records a take to
  `<set>/AUDIO/YYMMDD-HHMM/`, one file per source, 16 or 24 bits.
  [The module page](../../../modules/stems/README.md) says how to use it
  and what is open.
- **The 14 stock effects**, listed so the FX2 chooser is stock's.

## Status

On hardware: Yves's MKII, STEMS1 to STEMS3 (30 Sep to 6 Oct 2026). Under
the port: `tools/verify/verify_stems.py` and `verify_stems_menu.py`.

## Build

```bash
make image REMIX=stems BUILD=1
```

[BUILDING.md](../../../docs/guide/BUILDING.md) is the walk-through from a fresh machine to a flashed unit. `make check REMIX=stems` runs every gate first.

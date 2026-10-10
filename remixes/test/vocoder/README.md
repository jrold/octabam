# `vocoder` -- VOCODER

VOCODER beside the stock effects (all but PLATE REV, whose words it takes, and DJ EQ, so its tables sit in X memory). VOCODER runs on FX2 of tracks 2, 3, 6 and 7 only (two per DSP core, not a core's first track) and passes audio elsewhere.

## What is in it

- **VOCODER** -- [`modules/vocoder/README.md`](../../../modules/vocoder/README.md).
- the stock effects but PLATE REV and DJ EQ, listed so the chooser is otherwise stock's: PLATE REV gives up its words for VOCODER's code, and DJ EQ is left out on both menus so VOCODER's tables sit in the stock curve bank in X memory.

## Status

Renders in `dsp_host` (`tools/verify/verify_vocoder.py`); the per-track limit checked under the ColdFire port. On a MKII (OCTABAM7-9, 4 Oct 2026) two per core played and three stalled, which is why the limit is built in; with the limit built in, OCTABAM12 ran VOCODER on FX2 of all eight tracks, stable (two vocoding per core, the rest dry), at the earlier positions T1, T2, T5 and T6. The current positions (T2, T3, T6, T7) are not flashed on this build; they were heard clean on the 0.2 code (OCTABAM20, branch vocoder-0.2 at f83463c8).

## Build

```bash
make check REMIX=vocoder
```

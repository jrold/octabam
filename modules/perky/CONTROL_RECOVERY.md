# Recovering a family's control laws from the firmware

Every engine's *renderer* is qualified against the firmware's captured PCM and
state.  The *control* path — the arithmetic that turns the panel's four values
into the object fields the renderer reads — had to be recovered separately for
each family, and for four of the twelve it never was.

This is how to recover one without guessing.

## Why three control corners are not enough

`tools/harness/perky_cf/capture_engines.cpp` captures each family at three
control corners (0, 2048, 4095).  That is enough to *check* a recovered law.  It
is not enough to *find* one: for Complex Drum's amplitude-envelope rate, three
points left **268 different (offset, scale) pairs** that fit, and its
pitch-envelope law moves in the opposite direction to Simple Drum's, so the
shape had to be discovered rather than re-parameterised.

## The tool

`tools/harness/perky_cf/capture_control_sweep.cpp` dumps the engine's whole
wrapper window for

* `sweep` — every panel position 0..127 of each control in turn, with the other
  three held at mid.  That is the converged prepared word for every reachable
  setting.
* `traj` — the targets are written with `settleIterations = 0` and then the
  firmware's own update pass is stepped one at a time
  (`advanceControlSmoothing`), capturing the object after every step.  That is
  the law at *intermediate* smoothed words, which the converged sweep cannot
  see — and which is what actually happens when a knob moves or a p-lock lands.

Build it against the same PerkyBits/Unicorn objects the capture tool uses:

```
call "<VS>\VC\Auxiliary\Build\vcvars64.bat"
cl /nologo /std:c++20 /O2 /MD /EHsc /I <perkybits>/Source /I <unicorn-src>/include ^
   tools/harness/perky_cf/capture_control_sweep.cpp ^
   <obj>/FirmwareImage.obj <obj>/PerkonsM7.obj <obj>/PerkonsVoices.obj ^
   <obj>/NativeV121*.obj ^
   <unicorn-build>/unicorn.lib <unicorn-build>/arm-softmmu.lib <unicorn-build>/unicorn-common.lib ^
   /Fe:capture_control_sweep.exe
```

Then fit.  A rate is `0xFFFFF / den`, so each captured rate pins `den` to an
interval; intersecting the intervals over a few thousand points leaves a small
set of exact `(offset, scale, shift)` candidates, and the right helper shape
narrows it to one.

## What it recovered for Complex Drum (V2, algorithm 3)

Object at **wrapper + 0x1F8**, 0x140 bytes.  Prepared control words in the
object's own slots **0x1C / 0x20 / 0x24 / 0x28** (tune, decay, P1, P2), exactly
as Fold Drum keeps them.

| panel | object field | law |
|---|---|---|
| TUNE | raw pitch `0xBA` | `min(prepared_tune + 768, 4095)` |
| DECAY | amplitude env decay `0x96` | `0xFFFFF / (48*51 + (48*7279 * time_parameter(prepared_decay)) >> 12)` |
| P1 | pitch env decay `0x11A` | `0xFFFFF / ((43244160 - 9552*prepared_p1) >> 12)` |
| P2 | pitch amount `0x120` | `prepared_p2` |
| MODE | main wave target `0x3C` | M1 → `0x080222A0`, M2 → `0x080224A0`, M3 → `0x080228A0` |

Constants: amplitude and pitch attack rates `10922` / `21845`, both envelopes
`flag6` set and reset armed, main oscillator starts on `0x080222A0` and the
modulation oscillator is fixed on `0x080226A0`.

Both rate laws are **exact over all 3,584 captured points** (128 converged
positions × 4 controls, plus 128 × 24 intermediate smoothing steps), which spans
1,627 distinct prepared values per control.  `time_parameter` and the
`0xFFFFF / den` helper are the same ones `simple_drum_control.py` documents.

Note `prepared_p1` here is the *raw* smoothed word, not `time_parameter` of it,
and the pitch law's denominator is *smaller* for larger controls — the opposite
of the amplitude law and of Simple Drum's pitch law.  That asymmetry is why
guessing from the three-corner captures was not an option.

## Slap (V3, algorithm 2) — renderer done, two laws still open

**Object at wrapper + 0xC4, 0x2670 bytes** (it embeds a 4,805-word delay ring at
0xE0).  `slap_compact.py` is **exact against the firmware** — PCM, the full
0x2670 state *and* the RNG for the continuation and active-retrigger blocks, all
three modes and all three corners.  So the renderer can be ported the same way
as Simple and Complex Drum; it needs the shared RNG (already in the engine), the
two filter stages per sample, the counter/tap ring and one envelope.

Sweeping each control identifies exactly which object fields move:

| panel | object fields that move |
|---|---|
| TUNE | `0xBA`, `0xAA` (filter coefficient), `0x34` (derived increment) |
| DECAY | `0x96`, `0x7A`, `0xBC` |
| P1 | `0xBE`, `0x266C` (MIX) |
| P2 | `0xA8` (filter damping), `0xC0` |

Five are recovered exactly from the 128-point sweep:

| field | law |
|---|---|
| `0xBA` raw pitch | `min(prepared_tune + 768, 4095)` (same bias as Complex Drum) |
| `0x266C` MIX | `prepared_p1 >> 1` |
| `0xA8` filter damping | `2048 - (prepared_p2 >> 1)` |
| `0xC0` | `prepared_p2` |
| `0x7B` sustain gate | `prepared_decay >= 0x0FF0` (the common `obj+8 <= decay` rule) |

Two are **not yet recovered**, and they are deliberately left rather than
fitted:

* `0x96`, the amplitude-envelope rate.  Its denominator at prepared-decay 0 is
  exactly **912 = 48*19**, so the usual `48*(off+1) + (48*(scale-1)*x) >> 12`
  helper is in play with offset 18 — but neither `x = prepared` nor
  `x = time_parameter(prepared)` satisfies the rest of the curve, and the
  denominators (912, 1474, 2035, 3157, 4279, 6514, 8811, 13273, 17772) grow
  far faster than linearly.  The family is using a *different* conversion from
  the smoothed control to that helper's argument.
* `0xAA`, the filter coefficient: 6588 at prepared 0 rising ~8.58 per step and
  clamping at **35127**.  No `(A + B*x) >> s` form fits all 128 unclamped
  points, so the clamp is not the only nonlinearity.

Both want the ARM update routine read directly (the disassembly tooling in
`work/`: `fwdis.py`, `fwscan.py`, `fwimm.py`), or a finer trajectory capture —
the two remaining unknowns are a single helper's argument conversion, not the
shape of the engine.

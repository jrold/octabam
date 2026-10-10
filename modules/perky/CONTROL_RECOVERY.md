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

Six are recovered exactly from the 128-point sweep, and the amplitude rate was
solved against all 3,584 points (sweep + trajectory):

| field | law |
|---|---|
| `0xBA` raw pitch | `min(prepared_tune + 768, 4095)` (same bias as Complex Drum) |
| `0x266C` MIX | `prepared_p1 >> 1` |
| `0xA8` filter damping | `2048 - (prepared_p2 >> 1)` |
| `0xC0` | `prepared_p2` |
| `0x7B` sustain gate | `prepared_decay >= 0x0FF0` (the common `obj+8 <= decay` rule) |
| `0x96` amplitude env rate | `0xFFFFF / (912 + (48*749 * time_parameter(prepared_decay)) >> 12)` |

The amplitude rate is the standard helper with **offset 18, scale 750 and no
rounding bias** — every other family's helper form, with this family's
constants.  Note the near miss that cost the most time: scale 751 (48\*750) fits
the coarse sweep but fails 747 of the trajectory points, so the intermediate
smoothing data is what actually pins it.

One is **not yet recovered**:

* `0xAA`, the filter coefficient: 6588 at prepared 0, rising ~8.58 per unit and
  clamping at **35127**.  It is not affine in `prepared`, not affine in
  `time_parameter(prepared)`, not pitch-table-derived, and no
  `(A + B*x) >> s`, `A + ((B*x + E) >> s)` or `(A + B*x + E) >> s` form fits the
  unclamped points.  Its local step pattern is 8,9,8,9 while its long-range
  slope is 8.578, so its argument is non-linear in a way the other families did
  not show.

That one wants the ARM update routine read directly — the disassembly tooling
is in `work/` (`fwdis.py`, `fwscan.py`, `fwimm.py`) — or a capture that steps
the control through *single* update passes at a finer target grid.  It is a
single coefficient, not the shape of the engine: the Slap renderer is already
exact against the firmware (PCM, the full 0x2670 object including the 4,805-word
delay ring, and the RNG).

### Where Slap's update routine is (mapped by disassembling the M7 image)

The image's M7 segment loads at **0x08020000**, ends at 0x080d17e8, and
disassembles with capstone in Thumb mode with `skipdata = True` (without it,
decoding stops after ~4.5 k instructions at the first data region).

The envelope-rate helper that `simple_drum_control.py` documents —
**0x08028784** — has exactly **seven** callers in the whole image:

```
0x08024a3a  0x08024ad2  0x08024dcc  0x08025108  0x080262be  0x08026322  0x08027114
```

one per family update.  Landmarks already identified:

* **0x0802775c** — the shared voice-defaults pass ("strh 0x0FF0 at engine+8"),
  and the *only* `strh [rN, #0xaa]` in the image, which is where the filter
  coefficient is initialised to 0.  Slap's *update* writes 0xAA through a
  computed base, which is why an offset search does not find it.
* **0x08024714** — the common update; **0x080246ac** — common init.
* The four family init/update pairs seen so far sit at 0x08024a04/0x08024a8c,
  0x08026288/0x080262fc, and one of the two unread call sites
  (0x08024dcc, 0x08025108) is Slap's.

So the remaining job is bounded: disassemble those two call sites, find the
coefficient computation, and read off its two constants.

## The last three engines are a different class of work

Measured after Slap landed (9 of 12 shipping):

**Wavetable V1 / V2.**  The host model `wavetable_drum_compact.py` says of
itself "an oracle candidate, not an Octatrack DSP renderer", and it shows: the
engine-2 and engine-5 captures place the object at **wrapper + 0xC4** (the
0x0802819D simple-oscillator entry sits at object +0x58, i.e. wrapper +0x11C,
exactly as the other engines' geometry), with the primary oscillator's
current/next wave pointers at object +0x38/+0x3C holding **0x080222A0** — but
the model's *secondary*-oscillator and crossfade fields (object +0xF4, +0xF8,
+0x100, +0x104) hold no valid wave address in either capture.  So the ARM
layout for the two-oscillator crossfade has to be recovered before a port can
be verified; rendering the model at the right offset does not reproduce the
firmware PCM.  Its wavetable assets may also be its own bank rather than the
four shared waves.

**Acoustic Hats.**  Its render is single-precision float, not fixed point: the
one-pole filter does `decayed = previous * DECAY`, `summed = input + previous`
with IEEE754 singles stored in the object (object +0x100 int, +0x104 float bits,
+0x108 dirty flag), then truncates to int.  The ColdFire build is freestanding
`-msoft-float` with no libgcc float helpers linked, so this needs either an
exact integer soft-float FMUL/FADD for those two operations or a different
approach; it also plays *sample assets* (object +0xF8 address, +0xFC length)
that the asset extractor does not currently carry.

Neither is blocked on method — both are blocked on work that is larger than the
sweep-and-fit pass that closed Complex Drum and Slap.

### Wavetable: what the sweeps settled

Correcting the first read: the object is **not** at 0xC4.  Sweeping each
control and clustering the four prepared words gives the real bases:

* **Wavetable V1 (engine 2): wrapper + 0x2E8** (plus a second prepared-word
  cluster at +0x3F8, the secondary oscillator's own block)
* **Wavetable V2 (engine 5): wrapper + 0x31C**

At those bases the layout is the usual one — envelope at +0x74, rate at +0x96,
raw pitch at +0xBA — and the moving-field map is:

| panel | object fields that move |
|---|---|
| TUNE | `+0x34`, `+0xBA`, `+0x12C` |
| DECAY | `+0x7A`, `+0x96`, `+0xBC`, `+0x130` |
| P1 | `+0xBE`, `+0x104`, `+0x106`, `+0x10C`, `+0x10E`, `+0x114`, `+0x134` |
| P2 | `+0xC0`, `+0xEC`, `+0x138` |

**Wavetable V1 is already exact against the firmware at the corner where it
uses the shared waves** — 3 of 3 modes, PCM first block + continuation + full
object state, at base 0x2E8 with the four existing wave assets.  What it needs
beyond that is its **own wavetable bank**: the secondary oscillator's current
wave pointer (object +0x104) walks to addresses the extractor does not carry —
measured across the nine cases, mode 1 corners 0/1/2 give
`0x080417CC / 0x0803A7CC / 0x080337CC`, mode 2 gives
`0x080517CC / 0x0804A7CC / 0x080437CC`, mode 3 gives
`0x080617CC / 0x0805A7CC / 0x080537CC`.  Those are 4,096-byte tables on a
0x2000 stride in the 0x0803xxxx–0x0806xxxx region, so the asset extractor has to
take that bank (and the crossfade walks through it, not just to one table).

So Wavetable is: extract the bank, read the P1-driven crossfade fields
(+0x104/+0x10C/+0x114 are the walk), then port the renderer — whose arithmetic
the host model already gets right at corner 0.

### Wavetable: the bank measured, and where the host model stops matching

Walking every one of the 4096 twelve-bit targets gives the bank exactly:
object +0x104 (the secondary oscillator's current table) takes **15 values**,
`0x080337CC .. 0x080427CC` on a **0x1000 stride**, and +0x10C takes
`0x080327CC .. 0x080417CC` — so the bank is **16 tables of 4,096 bytes starting
at 0x080327CC**.  Object +0x100 and +0x108 stay on 0x080222A0.

Two things that follow, both measured:

* The tables are 4,096 bytes (2048 s16), not the 512 bytes the extractor takes
  for the Simple Drum waves — those are the *first 256 entries of the same
  tables*, which is all Simple Drum indexes (`(phase >> 12) & 0xFF`).  Extending
  the shared wave assets to 4,096 bytes is required for Wavetable.
* With 4,096-byte tables the host model still asks for an address the firmware
  never puts in those fields — it requested **0x08048C4C**, which is outside the
  0x080327CC + 0x1000k grid entirely.  So `wavetable_drum_compact.py`'s
  *secondary-oscillator pointer* offsets (its words 34/36, raw +0x108/+0x10C)
  are not the firmware's; its arithmetic is right at one corner but its layout
  is a reconstruction.  The real crossfade fields are the ones the P1 sweep
  moves: **+0x104, +0x106, +0x10C, +0x10E, +0x114, +0x134**.

So the remaining Wavetable work is precisely: read those six fields' law from
the sweep (the walk is visible there), fix the host model's offsets to the real
ones, re-verify against the nine captures, then port.

### Wavetable: the crossfade law, measured

Sweeping P1 alone (object base 0x2E8, all other controls at mid) gives the whole
crossfade in one table:

| P1 (object +0x134) | +0x104 (current table) | +0x10C (next table) | +0x114 (mix) |
|---|---|---|---|
| 0 | 0x080417CC | 0x080407CC | 0 |
| 254 | 0x080417CC | 0x080407CC | 246 |
| 510 | 0x080407CC | 0x0803F7CC | 229 |
| 1022 | 0x0803E7CC | 0x0803D7CC | 195 |
| 1534 | 0x0803C7CC | 0x0803B7CC | 161 |
| 2046 | 0x0803A7CC | 0x080397CC | 127 |
| 2557 | 0x080387CC | 0x080377CC | 92 |
| 3069 | 0x080367CC | 0x080357CC | 58 |
| 3581 | 0x080347CC | 0x080337CC | 24 |
| 3836 | 0x080337CC | 0x080327CC | 6 |
| 4091 | 0x080337CC | 0x080327CC | 255 |

Reading it: **+0x134 is P1 verbatim**, the secondary oscillator's current table
(+0x104) walks *down* the 16-table bank as P1 rises — one table per ~512 of P1 —
its next table (+0x10C) is always exactly one step lower, and **+0x114 is the
crossfade fraction**, counting down 246 → 6 as P1 rises within a table and
snapping to 255 only at the very top.  Object +0x100 and +0x108 stay on
0x080222A0 (the primary table), and +0x112 is 0 in every captured state.

That replaces the host model's secondary-pointer fields (`raw +0x108 / +0x10C`)
with the firmware's own `+0x104 / +0x10C`, and gives the walk and the mix law
directly rather than by fitting.  With the tables extracted at their real 4,096
bytes, Wavetable V1 becomes the same kind of port as Simple and Complex Drum:
point the model at the real fields, re-verify the nine captures, translate.

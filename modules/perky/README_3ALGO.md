# Reduced Perky DSP machine — implementation report

> **This report has been corrected.** An earlier revision quoted an
> "OVER by 2,003 / 8,210 cycles against the physical deadline" column that
> compared MODELED cycles against a HARDWARE deadline -- a category error, now
> removed and retracted in `DSP_3ALGO.md`. It also carried the pre-fix footprint
> (3,936) and described the composed execution as unproven. All three are
> corrected below; the numbers here are the measured ones.

**Branch** `perky-dsp-2voice-3algo` (from `perky-optimize`; `perky-optimize` is untouched)
**Scope** the reduced target: **two Perky voices total, one per DSP core, three
algorithms each**, six normal Octatrack tracks remaining.
**Headline artifact**

```
out/mainos_bus.bin   1,116,588 bytes
sha256               b18e202c0406a6ac20de4fccdaf332c3be3332b0b118e61af2be8f709d313342
```

Reproduce everything with one command:

```bash
python3 tools/perky/build_dsp_3algo.py
```

It runs, in order: the composed-renderer equivalence gate, the measured
sacrifice gate, composition, the full Octabam build, and image validation.

---

## 1. Final architecture

| Track | Core (payload) | Perky? | Algorithms |
| --- | --- | --- | --- |
| T1 | **B** (`P:0x0dc0`) | yes | Fold Drum 1, Resonant Bass, Resonant Snare |
| T2–T4 | B | no — ordinary Octatrack tracks | — |
| T5 | **A** (`P:0x1000`) | yes | Fold Drum 1, Resonant Bass, Resonant Snare |
| T6–T8 | A | no — ordinary Octatrack tracks | — |

The track↔core mapping is the repository's measured one (payload A serves
tracks 5–8, payload B serves 1–4; AGENTS.md, established via the MrkVerb32
marker flash). Because T1 and T5 are on **different** cores, exactly one Perky
voice can execute per core, which the composed seam enforces itself: it reads
the per-core track slot at `x:$418` and returns without rendering unless it
holds the admitted value.

Wavetable is not used. Simple Drum, Fold Drum 2, Complex Drum, Slap, Karplus,
Noise Hat, Noise/Tone and Acoustic Hats are not included. Synthesis is on the
DSP, not ColdFire.

## 2. Included algorithms and how they were composed

Fold Drum 1, Resonant Bass and Resonant Snare are composed into **one** source
by `tools/perky/build_dsp_3algo_source.py`, which deduplicates their shared
low32/RNG/envelope helper block rather than emitting each renderer's copy.

| | P words |
| --- | ---: |
| Fold Drum 1 standalone | 1,312 |
| Resonant Bass standalone | 2,447 |
| Resonant Snare standalone | 2,329 |
| Naive standalone sum | 6,088 |
| **Composed shipping source** | **3,868** |
| Deduplicated | **2,152** |

This is the measured composition, not a sum of standalone sizes.

## 3. Memory ledger

### Program memory

```
payload A: region P:0x01000..0x01fdf (4063 words)  used 3868  FREE 195
payload B: region P:0x00dc0..0x01d9f (4063 words)  used 3868  FREE 195
```

### Stock FX sacrifice — measured, and it is more than Spring

`verify_perky_3algo_sacrifice.py` reads the stock effect spans out of the
pristine 1.40C MAIN OS and compares them with the composed requirement. The
placer can only harvest **contiguous** runs, so the budgets are prefix sums:

| Configuration sacrificed | A | B | Result |
| --- | ---: | ---: | --- |
| nothing (preserve all) | 0 | 0 | short 3,868 |
| **SPRING REV only** | 1,063 | 1,063 | short **2,873** |
| PLATE + SPRING + DARK (the stock donor) | 2,724 | 2,724 | short 1,212 |
| + COMPRESSOR | 2,904 | 2,904 | short 1,032 |
| + LO-FI | 3,441 | 3,441 | short 495 |
| + DJ EQ | 3,786 | 3,786 | short 150 |
| **+ COMB FILTER** | **4,063** | **4,063** | **FITS** |

**Spring Reverb alone is demonstrably not sufficient.** The first configuration
that fits sacrifices seven of the thirteen stock effects: the three reverbs
plus COMPRESSOR, LO-FI, DJ EQ and COMB FILTER. LO-FI and DJ EQ cannot be split
out of that set because they are interior members of the run.

A second, non-obvious constraint applies: `stock.fx1_ids()` is read from the
image's **FX1 chooser**, and the DSP dispatch table is indexed by the raw id and
shared by both menus, so an effect on FX1 cannot have its code harvested unless
it is taken off FX1 as well. Naming `fx1` explicitly in the remix is what
replaces that auto-add rule; with it in force the harvest collapses to the three
reverbs (2,724 < 3,868 — the reason the first attempt at this remix overran).

### Retained and removed

**Retained, still selectable and still callable:** FILTER, EQUALIZER, PHASER,
FLANGER, CHORUS, SPATIALIZER.

**Removed:** PLATE REV, SPRING REV, DARK REV, COMPRESSOR, LO-FI, DJ EQ,
COMB FILTER — explicitly confirmed by the sacrifice and image gates.

### X / Y

The composed X/Y ledger is in `modules/perky/DSP_3ALGO.md`: voice block
`0x3800`, RNG `0x38e8`, scratch `0x3900` (188 words), and the Y regions
`Y_WAVES 0x07a5`, `Y_ENV1 0x2000`, `Y_ENV2 0x2280`, `Y_INTERP_A 0x2500`,
`Y_INTERP_B 0x2600`. No Wavetable allocation exists in this target, so no
stock FX data/state was displaced for Y.

## 4. Tests run and results

| Gate | Result |
| --- | --- |
| DSP assembler / link | PASS — composed source assembles, 3,868 words |
| Composed-renderer equivalence | **PASS** — every renderer instruction identical to the qualified standalone builds apart from relocated `DO`/`JSR`/branch targets |
| Measured FX sacrifice | **PASS** — names the minimum sacrifice, fails if nothing fits |
| Image placement and admission | **PASS** — 4,063/4,063 words present in both payloads, top exact, 4/4 ordered admission fingerprints at the region entry |
| Fold Drum 1 (standalone) | PASS — 15 original ARM blocks + 400 randomized blocks, PCM/state/RNG |
| Resonant Bass (standalone) | PASS — 1,024 blocks, exact stereo PCM/state/RNG |
| Resonant Snare (standalone) | PASS — 1,024 blocks, exact stereo PCM/state/RNG |
| Full build (`make bus`) | PASS |
| Composed **Fold** execution parity | **PASS** — 640 blocks, 400 native randomized; 15/15 captured ARM cases exact |
| Composed **Resonant** execution parity | **oracle unusable** — see section 6 |

## 5. Timing

Measured on the composed production path by
`tools/verify/verify_perky_3algo_timing.py` (report at
`out/perky/dsp-3algo/timing.json`). **Two figures are reported and they are not
interchangeable:**

```
algorithm   stress/16  REACHABLE/16   2x+stock  vs window verdict  bound
fold            25393         25393      73346       +834    OVER  arm-fixtures
bass            74511         35713      93986     +21474    OVER  arm-fixtures
snare           80718         38737     100034     +27522    OVER  arm-fixtures
```

* **REACHABLE** comes from the captured ARM fixtures — states the production
  control path actually produced on hardware — and is the **production bound**.
  `timing.json` keys its verdict on it.
* **stress** comes from `resonant_state()`, whose own docstring says it covers
  "both sides of every bounded-path guard": 24-bit decay fields, `DECAY_COUNT` up
  to `0xffffffff`, random coefficients. Those are states the control path cannot
  produce, and quoting them as the production cost is an error this split exists
  to prevent.

**The budget model.** `make cycles` prints the split directly: whole core 4,532
cycles/sample (hardware, 199.9 MHz measured), stock's own share ~1,415, usable by
us 3,120. The host's cycle model undercounts hardware by ~2x — measured against
CHIP.md's own hardware instruction table (1.89x for `move x0,a`, 1.94x for a
one-word displaced move, 1.97x for a two-word one) — so the production test is
`2 x modeled + stock <= 72,512`, i.e. **modeled <= 23,040** with the repo's ~7.7%
margin held back. 23,040 is therefore *not* a stale historical number: it
descends from those two measurements. Because load is the MAXIMUM of the selected
algorithm per core, only one of the three runs on a core at a time.

## 6. The blocker, restated on the reachable domain

**Resonant Bass and Resonant Snare do not fit the frame at one voice per core.**
On the reachable figures, with the measured dispatcher wrapper of **547** modeled
cycles/block added:

| engine | reachable | + wrapper 547 | vs 23,040 | hardware window |
| --- | ---: | ---: | --- | --- |
| Fold Drum 1 | 25,393 | 25,940 | 11.2% over | **+2.7%** |
| Resonant Bass | 35,713 | 36,260 | needs **36.5%** | +31.1% |
| Resonant Snare | 38,737 | 39,284 | needs **41.4%** | +39.5% |

**Fold Drum 1 is not part of the blocker** -- 2.7% over the hardware window is
inside what bit-exact work could reach.

**The optimisation ceiling is measured, not argued.** Ablating one routine at a
time in the composed source and diffing executed instructions:

```
snare baseline 27,538 instructions/16
  pk_resonant_decay   -10,928 (39.7%)   pk_u32_mul_low  -4,372 (15.9%)
  pk_resonant_core     -5,974 (21.7%)   pk_resonant_noise -1,524 (5.5%)
all five stubbed -> 6,572; the ALGORITHM is 76.1% of the renderer (bass 69.7%)
```

So the non-algorithm share — register setup, the 32-bit pack/unpack motifs, loop
control — is only **23.9% for snare**. **Removing every non-algorithm instruction
in the renderer still leaves the snare 28% over the allowance.** The reduction
required is larger than the entire non-algorithm content of the code.

Avenues from the brief's list were attempted and measured, not skipped:

* **native-width multiply**: the DSP's multiply is 24x24, so `pk_u32_mul_low`
  would collapse to one `mpyuu` if its operands were <= 24 bits. Reading every
  32-bit word out of the captured ARM fixtures, the widest is **32 bits** — the
  precondition fails on reachable data.
* **dead code**: a fallthrough-aware reachability walk finds 51 unreachable
  instructions = **67 P words** (verified bit-exact, 15/15 Fold ARM). It does not
  reach the 82-word breakpoint that would keep SPATIALIZER, and it is deliberately
  not shipped.
* **redundant reloads**: 5 composition-wide under a call-clobber-aware scan.

## 7. Safe algorithm switching (fixed on this branch)

The three engines share `X:0x3800` with DIFFERENT layouts -- word 34 is `MODE` for
Fold, `DECAY_A` for Resonant Bass and inside `RES2` for Resonant Snare -- so a
switch handed the new engine the old engine's fields as if they were its own.
**Measured, before the fix:** switching Fold -> Resonant Bass produced `-8388608`
= `-2^23` exactly, railed at the 24-bit limit, on the first block after the
switch; Fold -> Snare rendered silence.

The dispatcher now keeps an **ENGINE LEDGER** at `x:$38ed` (the old admission
latch word, free since that was removed), compares the incoming engine id against
it, and **re-seeds the shared voice block when the engine changes**. The id is
tagged `0x8000` so a boot word of zero can never match. Cost: **+20 P words** and
**+13 modeled cycles** on the steady-state wrapper, plus **+129** on the single
block where a switch happens (the 108-word clear). It did not move the blocker:
36.4% -> 36.5% and 41.3% -> 41.4%.

`verify_perky_3algo_switch` drives all three engines in sequence through
`pk3d_source` and asserts **no block rails**; a silent block after a switch is the
re-seed working, not a defect. There is **no oracle** for any switched block -- the
captured fixtures are per-engine and the dispatcher stages controls through
registers the stock caller owns -- and the gate says so rather than implying
coverage.

**What would unblock it** is a decision this branch is not authorised to take:
a deliberately smaller resonant algorithm (the target forbids this branch
choosing a redesign); or accepting a per-voice budget above the frame (which
contradicts "never exceed the physical full-core DSP deadline"); or reducing the
target to what fits — **Fold Drum 1 does**, at 34% of the frame.

## 7. What is not done, stated plainly

This image is **not yet ready to flash**, and the reasons are narrower and
better-evidenced than when this report was first written. Three of the four
original items are closed:

1. **Fold execution parity — CLOSED.** The composed Fold renderer is bit-exact
   against the captured ARM fixtures: 640 blocks, 400 native randomized, and
   **15/15 ARM cases exact** across every mode and corner, triggers AND
   continuation blocks. Two real composition bugs were found and fixed (an
   envelope table literal that made Fold decode WAVE DATA as its amplitude
   curve, and a scratch-convention mismatch that put the mode-2 noise path 64
   words off the qualified build). Both are in `DSP_3ALGO.md`.
2. **The control side — CLOSED.** `pk_render` now dispatches all three
   algorithms, `pk_resonant_prepare` exists, the family byte provably reaches the
   DSP word the dispatcher reads (`0x13`), and the reserved conflict with the
   module's old `DEFAULT_ENGINE 10` is handled by a build define rather than
   silently. Both halves of the join are gated end to end.
3. **Resonant execution parity — OPEN, and the ORACLE is the problem.** The
   composed resonant renderers match the captured ARM fixtures' PCM on corner 0
   (bit-exact) but not on corners 1–2, and five state words differ. Investigating
   that produced the finding that matters: **the reference Python model does not
   reproduce the captured ARM fixture either** — it fails BOTH transitions
   (`before`→`after` by 20-21 words, `after`→`continuation-after` by 10-13) on
   every corner. So the fixture<->model correspondence is unverified, and the
   state assertion derived from it is not a usable oracle in either direction.
   Settling it needs the standalone ARM gate, which needs the **stock 1.40C
   image** for the original Y tables — not in this tree.
4. **Timing — OPEN, and it is the blocker.** See sections 5 and 6.

## 7. Remaining physical-hardware validation

Once the resonant oracle and the timing question are settled: flash, then confirm
on the unit that T1 and T5 each select and trigger all three algorithms, that
algorithm changes between events are clean, that retriggering and sequencer
operation survive, that T2–T4 and T6–T8 remain ordinary tracks, and that the six
retained stock effects still run on FX1 and FX2. Nothing in this repository can
see audio quality, the panel, or the real unit's timing.

## 7. Remaining physical-hardware validation

Once (1) and (2) above are closed: flash, then confirm on the unit that T1 and
T5 each select and trigger all three algorithms, that algorithm changes between
events are clean, that retriggering and sequencer operation survive, that T2–T4
and T6–T8 remain ordinary tracks, and that the six retained stock effects still
run on FX1 and FX2. Nothing in this repository can see audio quality, the panel,
or the real unit's timing.

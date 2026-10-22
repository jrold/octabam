# Moving a voice family to a DSP: what it frees and what it costs — 21 October 2026

**No placement of V4 alone can meet the fixed budget.** With V4 removed from
the ColdFire entirely, the worst selection (Wavetable V1 and V2, Slap V3)
still measures 162.98 µs steady mean against the 158.21 µs ceiling, and its
p99.9 and peak are 13.0 and 8.0 µs over. Moving Noise/Tone to a DSP also
does not fit the DSP side without removing stock FX code, and its worst
measured DSP path exceeds the per-core source allowance. This is a study;
nothing was built or flashed. The [receipt](STRUCTURAL_PLACEMENT_STUDY.json)
binds every row.

## Method (measured)

The PKFM31 image, frozen observer, card fixtures, clocks and budget of the
[orchestration campaign](ORCHESTRATION_CF_QUALIFICATION.md), with one change
per run: `placement_mask` bits cleared
(`tools/harness/perky_cf/diagnostic/placement_mask_variant.py`). A cleared
voice's chunks go where `pk_render` sends them: T1/T5 to the original
DSP-voice control path (`pk_dsp_render_orig`), T2/T6 to the stock source
routine. This prices the ColdFire side of a voice leaving the ColdFire; the
DSPs in this image run no renderer for the moved voice, so its DSP cost is
taken from the existing DSP records below. All placed voices stayed exact
(zero PCM mismatches, full source frames). 32,768 blocks, all 14 FX.

| ColdFire placement (Slap worst rows) | Steady mean | p99 | p99.9 | Peak | Total CF | Ceilings passed |
|---|---:|---:|---:|---:|---:|---|
| Nothing placed (base) | 123.64 | 129.89 | 193.52 | 208.59 | 149.93 | all 7 |
| V4 Hat only | 140.03 | 148.40 | 221.96 | 230.81 | 166.31 | 6 (ACK peak 362.78) |
| V3 Slap + V4 Hat | 159.48 | 168.00 | 245.97 | 252.61 | 185.63 | 3 |
| V2 WT + V3 Slap | **154.04** | **161.73** | **236.23** | **246.02** | **180.10** | **all 7** |
| V1 WT + V2 WT + V3 Slap | 162.98 | 170.77 | 250.67 | 258.75 | 188.86 | 3 |
| V2 WT + V3 Slap + V4 Hat | 170.47 | 179.63 | 263.78 | 270.72 | 196.41 | 2 |
| V2 WT + V3 Slap + V4 Noise/Tone | 178.17 | 188.04 | 268.34 | 274.24 | 204.07 | 2 |
| All four, V4 Hat (PKFM31 row) | 179.39 | 188.62 | 278.33 | 284.82 | 205.26 | 2 |
| All four, V4 Noise/Tone (PKFM31 row) | 186.88 | 196.84 | 282.77 | 287.12 | 212.72 | 2 |
| **Ceiling** | **158.21** | **166.78** | **237.73** | **250.71** | **189.30** | |

The increments are additive to within 0.2 µs across independent pairs:

| ColdFire cost of | Steady mean |
|---|---:|
| V4 metallic Hat on DSP-A (its ColdFire transport: ring, taps, feedback, controls) | 16.4 µs (three pairs) |
| V4 Noise/Tone rendered on the ColdFire | 24.0 µs (two pairs) |
| V1 Wavetable, net of the DSP control path that replaces it | 8.7–8.9 µs |
| V2 Wavetable, net of the stock path | 11.0 µs |
| V3 Slap, net of the DSP control path | 19.5 µs |

Two findings were not expected. The resident Hat on DSP-A still costs the
ColdFire 16.4 µs, more than a Wavetable voice rendered on it, because its
4,805-sample delay ring, tap gathering and feedback commit live on the
ColdFire. And two ColdFire voices of the heaviest kinds (Wavetable + Slap)
with nothing else placed pass every ceiling, with 4.2 µs of mean margin.

## What moving Noise/Tone off the ColdFire would free (measured bound, inferred net)

At most **24.0 µs**: the cost of V4 Noise/Tone on the ColdFire. A
DSP-hosted voice still needs ColdFire transport. With the Hat's transport
(16.4 µs, measured) the net saving is ~7.5 µs and the worst row becomes the
Hat row, 179.39 µs. A Noise/Tone transport needs no delay ring, so it should
cost less than the Hat's; its size is not measured. Even at zero, the worst
selection stays at 162.98 µs (above).

## What it would cost on a DSP (existing records, not re-measured)

| Resource | Noise/Tone needs | DSP-A (T6's core, beside the Hat) | DSP-B |
|---|---|---|---|
| Program | 1,471 words shared-mode renderer; 1,222 for M1 (Waveform2); standalone sizes including probe/helpers ([DSP qualification](../DSP_QUALIFICATION.md)) | Shared P 92 free (PKFM31 ledger); A upper tail 33 words, unqualified | Shared P 92 free; B upper tail ~609 words, hardware-unqualified |
| Program, if two stock FX go | — | +774 private-P donor words | +774 private-P donor words |
| Low Y tables | Waves 683 + two envelope curves ≈ 1,975–2,135 of 2,139 ([memory plan](../MEMORY.md)) | 2,093/2,139 used; envelope, pitch and clock tables exist, but the retired wave storage now holds the Hat's state snapshot | Free; fits with ≤164 words spare |
| Source time per 16 samples | Worst test path 40,738 modeled cycles (M1 15,945); worst original capture 22,813 | Same allowance; the Hat's own worst test paths are 22,058–35,445, and an earlier resident-Hat prototype measured A's frame peak at 358.5–372.5 µs against 362.8 ([taps campaign](NOISE_HAT_TAPS.md)) | Allowance **23,040** (one voice per core): worst test path 77% over |
| Audio path | T6 is DSP-A's track | Renders into T6 directly | PCM must cross B → ColdFire → A: at least one more 16-sample block of source latency (inferred), which the brief keeps unchanged, plus ColdFire forwarding cost |

The private-P donors are the Plate Reverb and Compressor code that PERKY4S
removed and the full map restored; taking them back drops two of the fourteen
stock FX the brief requires.

## Other families (existing records)

Wavetable cannot run on a DSP as qualified: its exact renderer executed only
against a logical Y bank that is not mapped on Octatrack hardware. Slap's
delay ring (4,805 samples) does not fit a DSP, as with the Hat. Fold Drum 1/2,
Simple and Complex can (the [DSP-B experiment](DSP_B_FEASIBILITY.md) placed
three of them), but only one voice per core fits the allowance, and they are
not the worst-case selections.

## Conclusion and falsifiers

The worst selection keeps three heavy voices on the ColdFire whatever V4
does, and that floor (162.98 µs; p99.9 250.67) is already over the budget.
Closing the gap therefore needs at least one of:

1. **Taking Wavetable or Slap off the ColdFire**, which needs new DSP work
   the records say does not yet fit (Wavetable table storage, Slap's ring).
2. **Reducing the three ColdFire voices** by at least 4.8 µs mean, 4.0 µs
   p99, 12.9 µs p99.9 and 8.0 µs peak, plus whatever ColdFire cost the V4
   placement keeps; the kernels already run near one instruction per cycle.
3. **A hardware-justified budget.** The target is conservative: two-Wavetable
   rows fitted the working envelope in calibration, and the 154.04 µs
   two-voice shape passes it now.
4. **A product restriction** on which algorithm combinations can sound at
   once.

These conclusions would be overturned by a cheaper ColdFire implementation
of Wavetable or Slap, a DSP renderer meeting the allowance with memory to
spare, or hardware evidence for a different envelope. The study does not
measure DSP-side timing for a moved voice, and the ColdFire base includes
the DSP control path for T1/T5, which a real DSP voice would also use.

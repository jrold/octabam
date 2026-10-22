# Merged segments and assembly kernels: PKFM22–PKFM26 — 21 October 2026

> Superseded as the best candidate by PKFM31; see
> [the orchestration campaign](ORCHESTRATION_CF_QUALIFICATION.md). Correction
> (21 October 2026): the receipt's hash for `generate_cf_v4_merge.py` is the
> later PKFM27 revision, not PKFM26's input, and the committed tree does not
> rebuild PKFM26's image; that campaign's reproduction note has the details.
> This record is unchanged otherwise.

**PKFM26 is the best candidate and still fails the fixed performance budget.**
All eight sustained rows keep exact original-reference synth PCM, DSP Hat
state, side words, clocks and feedback. Steady ISR means fall 16.5–21.9 µs
against PKFM21 (the worst row goes from 214.98 to 193.10 µs). Five rows now meet
the ACK p99 ceiling and all eight meet ACK peak, but every row still fails the
steady mean, p99, p99.9, full peak and total-CF ceilings. The verdict is
`FAIL_HOLD / HOLD_FOR_PERFORMANCE_WORK`. No hardware flash was made or authorized.

The [machine-readable receipt](KERNEL_CF_QUALIFICATION.json) has every row,
image hash and gate. Times are modelled CF264/PIT132 microseconds under the
frozen observer (`f975b4d2…`) and the unchanged budget (`8608844b…`).

## Candidates

Each candidate is a new layer and a new work directory; earlier builders and
outputs are untouched. The arithmetic of every algorithm, the native clocks,
both DSP uploads (byte-identical to PKFM21), the packet formats and the stock
path are unchanged in all of them.

| Version | Change | Worst-row mean (µs) | Verdict |
|---|---|---:|---|
| PKFM21 | Baseline (stock/CF campaign) | 214.98 | admitted reference |
| PKFM22 | V1–V3 render a frame in one native segment when the event boundary is a rendering no-op | 205.23 | kept |
| PKFM23 | Direct dispatcher fast path | 204.59 | **rejected**: first form broke the oracle's seams; seam-keeping form raised p99.9/peak 4.3–4.5 µs |
| PKFM24 | Wavetable render in one assembly chunk | 199.57 | kept |
| PKFM25 | + Slap envelope through the shared assembly envelope block, Noise/Tone in one assembly chunk | 195.56 | kept |
| PKFM26 | + exact merged V4 Noise/Tone frame | **193.10** | **best** |
| PKFM27 | Leaner C dispatcher | 193.79 | **rejected**: slower |

**Merged segments (PKFM22).** The stock loop calls each PERKY track twice per
frame, `(0, split)` and `(split, 16)`, with only the stock per-track event
routine in between. In sustained playback the boundary's prepare almost always
takes its unchanged-control path (0.05 slow prepares per frame were counted),
so rendering both segments separately paid every per-call cost twice. The
first segment is now deferred to the second call. There, if the boundary is
provably a no-op (same generation, initialized, no trigger, same algorithm and
mode, unchanged controls, tracing off), the same `placement_prepare` runs and
then one `placement_segment(voice, 0, 16, 0)`; otherwise the deferred prefix
renders first and the original order is kept. The native clock adapter and
every renderer have an arbitrary block-length contract. The deferral marker is
loaded data, never BSS.

**Assembly kernels (PKFM24–25).** `modules/perky/cf_env_block.s` is the shared
PĒRKONS envelope (all states, flags, wrap-around arithmetic, linear and curve
output). `cf_wt_render.s` runs the whole Wavetable chunk (both envelopes, the
EMAC frequency pass, the two-oscillator block and the commit);
`cf_nt_render.s` runs the whole Noise/Tone chunk (envelope, RNG noise and
twice-stepped filter, two-oscillator mix). Each proves its preconditions before
touching state and otherwise tail-calls the original C, kept as
`pk_cf_wt_render_c` / `pk_cf_nt_shared_render_c`. Slap's per-sample
object-resident envelope runs through the shared block between precomputed
burst retriggers, applying `slap_retrigger`'s exact effects.

**Exact V4 merge (PKFM26).** V4's external CF source is packed in two halves,
each carrying the Hat hold pair and the voice RNG after that half. When V4 is
Noise/Tone (shared modes) on both halves, the boundary is a no-op, no Hat
snapshot is being built and the assembly fast path is provably taken, the
frame renders once at the start of `pk_nhr_frame`, the noise pass records the
RNG at the first half's native sample count, and half 0 publishes that RNG:
the DSP-A packets are byte-identical to two renders.

## Measured rows (32,768 blocks, WT/WT, four stock tracks, all 14 FX)

| T5 / T6 | PKFM21 mean | **PKFM26 mean** | p99 | p99.9 | peak | total CF | ACK p99 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Resonant Bass / metallic Hat | 196.44 | **179.91** | 190.13 | 288.08 | 293.26 | 205.77 | 328 ✓ |
| Resonant Bass / Noise/Tone | 208.14 | **187.45** | 199.10 | 294.26 | 298.68 | 213.24 | 326 ✓ |
| Resonant Snare / metallic Hat | 197.15 | **179.92** | 190.11 | 289.77 | 294.20 | 205.79 | 329 |
| Resonant Snare / Noise/Tone | 208.59 | **187.57** | 199.44 | 295.88 | 300.28 | 213.38 | 328 ✓ |
| Snare/Bass MODE locks / metallic Hat | 196.77 | **179.90** | 190.11 | 289.57 | 294.48 | 205.77 | 329 |
| Snare/Bass MODE locks / Noise/Tone | 208.32 | **187.48** | 199.24 | 295.71 | 300.72 | 213.28 | 327 ✓ |
| Slap / metallic Hat | 203.34 | **185.52** | 195.21 | 286.40 | 292.72 | 211.38 | 330 |
| Slap / Noise/Tone | 214.98 | **193.10** | 204.28 | 292.91 | 297.19 | 218.91 | 328 ✓ |
| **Ceiling** | | **158.21** | **166.78** | **237.73** | **250.71** | **189.30** | **328** |

ACK peak passes in every row (342.2–353.0 against 362.2). Every row reports
32,768 source frames per CF voice (32,766 for V4), zero PCM, DSP state/side/
clock and feedback mismatches, zero oracle errors and zero transport failures.

## Correctness evidence on PKFM26

- Captured-vector replays of each in-image kernel against the PKFM22 image's
  own function (`tools/verify/bench_perky_kernel.py`): Wavetable 3,441
  vectors / 52,242 native samples, Slap 581 / 8,715, Noise/Tone 1,153;
  PCM, object bytes, RNG and return values exact.
- `tools/verify/kernels/test_env_block.py`: 26,000 random envelope contexts
  (every state, flag set, wrapping rate, threshold, curve wrap, n = 0..20)
  against an independent model.
- `verify_perky_merged_segments.py`: 11,664 frames (8,253 merged) of the
  actual predicate, prepare and segment against the native two-segment oracle.
- `verify_perky_dispatch_differential.py` against PKFM21: 1,500 frames of the
  production `pk_render` with triggers, mode/algorithm changes and Part
  changes; every placement/production/Hat object, both packet pings (including
  366 merged V4 frames' side words) and the cleared cursor block byte-identical.
- Existing actual-image gates: direct source (81 layouts + 24 transitions,
  5,355 frames, tracing toggled), linked NT/AH/Slap kernels, Hat state handoff
  (800 frames) and DMA all pass. Lifecycle, selector matrix and scene results
  are in the receipt.

## What the campaign learned

1. **The frozen predictor model never credits a table hit for taken NE, CS,
   VS, MI or LT branches** ([trap](../../../docs/contributing/TRAPS.md#trap-predictor-condition)).
   Such branches cost 0 on a branch-cache hit and 8 otherwise. It inflates
   stock and PERKY code alike; it was not exploited.
2. **The observer's seams are `placement_prepare`, `placement_segment` and
   `pk_nhr_frame`** ([trap](../../../docs/contributing/TRAPS.md#trap-observer-seams)).
3. **Orchestration, not synthesis, is now the largest reducible pool.** The
   PKFM26 worst-row profile: stock ≈ 103.7 µs, synthesis kernels ≈ 50 µs,
   dispatch/prepare/segment/convert/pack/Hat transport ≈ 38 µs. GCC-level
   restructuring did not help (PKFM27); further gains need assembly bodies
   behind the seams. Estimated remaining: roughly 12–15 µs across dispatcher,
   prepare/segment, Slap noise/velocity, filter polish and V4 transport.
4. **The tails are dominated by stock work.** Frames above 250 µs spend about
   56% in stock code; the stock sequencer's per-step parameter-lock copy
   (`0x4000c400–0x4000c6ff`) is about 14% of such a frame. PERKY trigger-time
   control laws add about 15 µs. The p99.9 gap above the mean is about 100 µs
   against PERKY4S's 80 µs, so a mean at the 158 µs ceiling would still leave
   p99.9 near 258 µs.
5. **The diagnostic profiler costs about 2.3 µs per frame** (timer reads in
   every dispatch, per-frame begin/end bookkeeping) and is enabled by default
   (`PK_HYBRID_PROFILER_DEFAULT`). It was left enabled; turning it off is a
   product decision, not an optimization.

## Reproduction

All local, in this checkout, with the existing toolchains and inputs. Builds
also rewrite `out/mainos_bus.bin` and `out/platform`; restore the default with
`make bus REMIX=perky-machine` afterwards.

```sh
PERKY_KERNELS=wt,slap,nt,v4merge PERKY_KERNELS_CF_WORK=out/perky/hybrid/full-map-kernels-v3 \
PERKY_KERNELS_CF_VERSION=PKFM26 .venv/bin/python tools/perky/build_perky_kernels_cf.py
.venv/bin/python tools/verify/measure_perky_stock_cf.py --build out/perky/hybrid/full-map-kernels-v3 \
  --work out/perky/hybrid/kernels3-campaign/workload --frames 32768 --v3 slap-control --voice4 noise-tone
PERKY_FULL_MAP_WORK=out/perky/hybrid/full-map-kernels-v3 .venv/bin/python tools/verify/verify_perky_merged_segments.py
.venv/bin/python tools/verify/verify_perky_dispatch_differential.py --candidate out/perky/hybrid/full-map-kernels-v3
```

Kernel development uses `tools/harness/perky_cf/cf_cycle_bench.cpp` (the
observer's patched core plus an unmodified copy of ot_emu's `v4e.cpp`; build
recipe in its header), `tools/verify/capture_perky_kernel_vectors.py` and
`tools/verify/bench_perky_kernel.py`. Bench cycles compare candidates; only the
full-image workload under the frozen observer is admission evidence.

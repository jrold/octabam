# PERKY full voice layout continuation handoff

Updated 21 October 2026. Continue in `/Users/jrold/Downloads/octabam` on
**`perky-cf-dsp-hybrid`**. The user explicitly chose this branch repeatedly,
overriding the `perky-machines` default in `AGENTS.md` for this experiment.
Keep using this checkout. Read its instructions before editing.

**The complete voice map exists and passes substantial local correctness and
lifecycle checks. It still fails the fixed performance budget.** The latest
candidate is **PKFM31** (PKFM26's merged segments, assembly kernels and exact
V4 merge, plus assembly placement seams, Slap loops, dispatcher and merge
predicates), with verdict `FAIL_HOLD / HOLD_FOR_PERFORMANCE_WORK`; see
[the orchestration campaign](ORCHESTRATION_CF_QUALIFICATION.md) and, before
it, [the kernel campaign](KERNEL_CF_QUALIFICATION.md). PKFM21 remains the
earlier admitted reference for comparisons.
The next task is to close that performance gap without changing the sound,
algorithms, native clocks or retained stock functionality, then qualify a
deliverable on the actual Octatrack. This is not a hardware-ready release.

## User goal and working agreement

Deliver four simultaneous PĒRKONS-style voices on Octatrack tracks T1, T2, T5
and T6, with the hardware's three selectable algorithms per voice and three
modes per algorithm. Keep stock T3/T4/T7/T8, all fourteen stock FX, normal
AMP/LFO/sequencer/scene integration, event-split ALGO/MODE locks, saved settings
and coherent STOP/START and Part/Bank changes. Preserve the original algorithm
audio, histories, RNG and exact native 48 kHz to 44.1 kHz conversion.

The user's later exact family-layout brief supersedes older
`PERKY_MACHINES_TARGET.md` wording about every algorithm on every track. The
table below is the accepted family contract; do not expand it back into that
older unrestricted routing goal.

The user wants autonomous progress through the brief, not repeated requests
to run another small test. Use focused development checks, reject regressions
early, and batch the full admission suite after a worthwhile candidate is
fixed. Report measured progress honestly. The user specifically experienced
Resonant as a severe hardware burden; dedicated sustained Snare, Bass and
sequenced Snare/Bass tests are now required alongside Slap.

Use local verification and the existing toolchains. Do not create branches,
worktrees, clones or duplicate workspaces; stash someone else's work; use
GitHub CI; or automatically pull, merge or rebase upstream. Check branch and
status before editing. Pushes need a user request; the checkpoint containing
this handoff was explicitly requested. Preserve proprietary stock inputs and
local evidence. Never commit an Elektron image, slice, `.syx` or sample asset.
No hardware flash has been authorized by this handoff.

## Read these first

1. [Current module status](../README.md),
   [latest PKFM31 orchestration campaign](ORCHESTRATION_CF_QUALIFICATION.md)
   with its [receipt](ORCHESTRATION_CF_QUALIFICATION.json), the
   [PKFM26 kernel campaign](KERNEL_CF_QUALIFICATION.md) it builds on, and the
   [PKFM21 qualification](STOCK_CF_QUALIFICATION.md) it builds on.
2. [Frozen emulator budget](EMULATOR_BUDGET.md) and
   [exact ceilings and calibration inputs](EMULATOR_BUDGET.json).
3. [PKFM20 control](REMAINING_CF_QUALIFICATION.md) and
   [corrected sustained Resonant baseline](RESONANT_WORKLOAD_QUALIFICATION.md).
4. [Full map and saved-project contract](FULL_MAP_QUALIFICATION.md),
   [on-demand Hat state handoff](STATE_HANDOFF_QUALIFICATION.md),
   [DSP-B feasibility](DSP_B_FEASIBILITY.md) and
   [correct native-clock CF placement experiment](CF_PLACEMENT_FEASIBILITY.md).
5. [Placement record](../../../docs/contributing/PLACEMENT.md),
   [trap register](../../../docs/contributing/TRAPS.md),
   [testing contract](../../../docs/contributing/TESTING.md) and
   [PERKY4S physical release evidence](../PERKY4S_RELEASE.md).

Earlier reports describe earlier images. Their nominal deadline passes and
historical reserves do not override the latest calibrated-budget rejection.

## Current algorithms and placement

| Track | Logical voice | ALGO 1 | ALGO 2 | ALGO 3 | Current renderer |
|---|---|---|---|---|---|
| T1 | V1 | Fold Drum 1 | Wavetable V1 | Simple Drum | ColdFire |
| T2 | V2 | Fold Drum 2 | Wavetable V2 | Complex Drum | ColdFire |
| T5 | V3 | Resonant Drums | Slap | Karplus | ColdFire |
| T6 | V4 | Noise Hat | Noise/Tone | Acoustic Hats | Hat on DSP-A; alternatives on ColdFire |

These are twelve panel choices, each with three modes. The two Wavetable
choices share engine ID 9 and immutable tables but have independent voice
histories; eleven engine IDs do not mean a missing panel choice. Local mode
indices are zero-based; panel values are 1–3. Noise Hat's panel indices
`0,1,2` map to original modes `1,0,2`: white, metallic, pulse. Resonant includes
Snare, Bass and its Noise/Tone mode. Check the source mapping before assuming
that an internal mode number is a panel number.

DSP-A serves stock tracks 5–8; DSP-B serves 1–4. The current candidate uses
DSP-A for Noise Hat. DSP-B retains its stock source path; there is no second
full-map voice running there. WT/WT plus Resonant or Slap plus Hat therefore
means three CF voices and one DSP voice. Selecting Noise/Tone or Acoustic Hats
on T6 means four CF source voices.

Hat state, synthesis, delay arithmetic and resampling live on DSP-A. The
4,805-sample ring lives on CF. Scheduled stock DMA padding carries commands,
taps, feedback or CF PCM; feedback carriers are removed before stock readers.
The implementation adds no source-latency block, synchronous HI08 transaction
or audio IPL7 wait. Nonblocking state/clock handoff drains pending jobs before
ownership changes. The continuous duplicate CF Hat shadow has been removed;
do not restore it as a switching shortcut.

All algorithms retain separate history within a Part generation, with RNG
owned by the logical voice. Production generation changes retire old jobs and
reset/import coherent state. This took several campaigns to get right.

Acoustic Hats requires `/PERKYAH.DAT`, **452,124 bytes**, containing exact
original PCM and a version/length/CRC header. UI-task loading uses bounded
4,096-byte reads and publishes readiness only after validation; audio does no
file I/O. Missing or invalid data leaves Acoustic Hats silent. The file is
generated locally from user-owned assets and must not enter Git. **934,480
bytes is the historical PKFM6 firmware wrapper size, not this asset's size or
an admission of a new PKFM21 package.**

Saved projects use the **PK/2** signature. Legacy PK/1 bytes must not silently
acquire new meanings. Preserve the tested fresh/default and reselect behavior;
do not automatically rewrite user projects.

For the active mapping, inspect `tools/perky/build_perky_full_map.py`,
`tools/perky/full_map_project.py` and
`tools/harness/perky_cf/placement_cf_engine.c`. The generic `cf_perky4.h` still
has a two-choice V4 family; the full-map build extends it with Acoustic Hats,
engine ID 10. `tools/perky/perky_full_map.py` alone is only the DSP service
adapter and does not describe the whole dispatcher.

## The performance target remains unmet

The budget comes from same-instrument replays of PERKY4S and historical
reported-working/reported-failing configurations. It is a conservative
engineering envelope, not a universal emulator-to-hardware multiplier. The
historical physical failure lacks a complete recoverable control/card trace;
some modeled working/failing shapes overlap. Passing the budget will still
require actual hardware acceptance.

| Fixed metric | Ceiling in model microseconds |
|---|---:|
| Steady ISR mean | 158.21153326922013 |
| Steady ISR p99 | 166.78030303030303 |
| Steady ISR p99.9 | 237.7310606060606 |
| Full ISR peak, including startup | 250.71212121212122 |
| Total playback CF work per transport frame | 189.2978376908736 |
| ACK CPU-work p99 | 328.000 |
| ACK CPU-work peak | 362.212 |

Keep CF/PIT at **264/132 MHz**, with uniform startup, pre-roll and playback
cycle-clock x1.00. Do not alter the observer, oracle, workload, budget,
precision or algorithms to obtain a pass. The nominal sixteen-sample frame
deadline is about 362.812 us; zero nominal misses is a weaker result.

All eight current runs use WT V1/V2, four stock sample tracks, all fourteen FX,
64-step 120 BPM 1X patterns and **32,768 transport blocks**, about 11.889 seconds.
Steady ISR statistics exclude the first 512 completed interrupts; full peaks
include startup. Total CF mean includes background work over all blocks.

| T5 | T6 | PKFM21 ISR mean | PKFM26 ISR mean | **PKFM31 ISR mean** | PKFM31 p99.9 | PKFM31 peak | PKFM31 total CF |
|---|---|---:|---:|---:|---:|---:|---:|
| Resonant Bass | Metallic Hat | 196.443 | 179.91 | **176.25** | 283.75 | 289.13 | 202.14 |
| Resonant Bass | Noise/Tone | 208.141 | 187.45 | **183.86** | 288.49 | 292.81 | 209.70 |
| Resonant Snare | Metallic Hat | 197.150 | 179.92 | **176.41** | 285.68 | 290.54 | 202.31 |
| Resonant Snare | Noise/Tone | 208.588 | 187.57 | **184.06** | 290.30 | 294.64 | 209.92 |
| Snare/Bass MODE locks | Metallic Hat | 196.767 | 179.90 | **176.30** | 285.16 | 289.79 | 202.20 |
| Snare/Bass MODE locks | Noise/Tone | 208.325 | 187.48 | **183.93** | 290.01 | 294.47 | 209.78 |
| Slap | Metallic Hat | 203.338 | 185.52 | **179.39** | 278.33 | 284.82 | 205.26 |
| Slap | Noise/Tone | 214.982 | 193.10 | **186.88** | 282.77 | 287.12 | 212.72 |

All eight PKFM31 rows preserve exact synth audio and DSP Hat state/side/clock/
feedback. All eight now meet ACK p99 and ACK peak; all fail the steady mean,
p99, p99.9, full peak and total-CF ceilings. The worst mean still needs about
**28.7 µs (15%)** less ISR work, and the tails are worse than the mean
suggests: p99.9 sits about 96 µs above the mean (PERKY4S: 80), dominated by
stock step frames, so p99.9 needs roughly 45–53 µs.

## What the latest campaign retained (PKFM22–PKFM26)

Read [the kernel campaign](KERNEL_CF_QUALIFICATION.md) before changing these.

- **Merged segments:** V1–V3 defer the `(0, split)` render to the stock
  loop's second call and render one `0..16` segment when the boundary is a
  rendering no-op (`tools/perky/generate_cf_merged_segments.py`).
- **Assembly kernels** with the original C as fallback: Wavetable
  (`modules/perky/cf_wt_render.s`), Noise/Tone (`cf_nt_render.s`), the shared
  envelope (`cf_env_block.s`) and the Wavetable frequency pass
  (`cf_wt_frequency_block.s`); Slap's envelope uses the shared block between
  burst retriggers (`tools/perky/generate_cf_slap_env_asm.py`).
- **Exact V4 merge:** one Noise/Tone render per frame with the first half's
  RNG captured for its side words (`tools/perky/generate_cf_v4_merge.py`).
- Rejected and recorded: PKFM23 dispatcher fast paths (first broke the
  oracle's seams, second raised tails) and PKFM27 (lean C dispatcher, slower).

PKFM28–PKFM31 ([orchestration campaign](ORCHESTRATION_CF_QUALIFICATION.md))
add, each pinned by SHA-256 to the C it mirrors and falling back to that C:

- **Placement seams in assembly** (`modules/perky/cf_placement.s`): the
  unchanged-control `placement_prepare` and the common `placement_segment`,
  same symbols, arguments and call positions; layout from exported `offsetof`
  symbols (`tools/perky/generate_cf_placement_asm.py`).
- **Slap chunk loops** (`cf_slap_render.s`): noise/LCG, a run-at-a-time
  counter walk, envelope scale and velocity around the same callees.
- **`pk_render` dispatcher** (`cf_render.s`), deciding from reads alone; the
  control unit exports its statics (`tools/perky/generate_cf_render_asm.py`).
- **Boundary no-op and V4 merge predicates** (`cf_placement_predicates.s`).

The layered builder is `tools/perky/build_perky_kernels_cf.py`
(`PERKY_KERNELS=wt,slap,slaprender,nt,v4merge,placement,predicates,render`
for PKFM31), on top of PKFM22's `build_perky_merge_cf.py`, which wraps the
PKFM21 `build_perky_stock_cf.py`. It applies every selected transform of a
unit in that order; PKFM24–27 selected one per unit, so their builds are
unchanged.

## Where worthwhile work remains

Measured on the worst row (Slap/Noise-Tone) with read-only diagnostic
observers whose profiles reproduce the control rows exactly
(`tools/harness/perky_cf/diagnostic/`): **stock code is 96.9 µs per frame and
diffuse** (no 256-byte PC bin above 4.7 µs; DELAY 15.9, 0x40004000–0x40004eff
13.1, the LFO.md inline-engine region 8.5). **PERKY's own code is 90.2 µs at
PKFM30**: synthesis kernels ≈ 48 µs near one instruction per cycle, the native
converter 5.2, `pk_render` 8.5, `pk_nhr_frame` 5.2, placement 4.9, the earlier
stock replacements 6.8. Use `full_map_pcbin_observer.h` for per-instruction
costs under the real workload and `cf_cycle_bench` with captured vectors for
kernels.

The previous estimate for this round was ~5 µs from the assembly dispatcher
and placement bodies plus ~2–3 µs from Slap; the measured gains were 3.1 µs
(placement 1.85, dispatcher 0.74, predicates 0.54) and 3.1 µs (Slap). The
remaining micro-gains found are about 2 µs (converter phase table, 32-bit V4
packet tail copies, Noise/Tone shift idioms). **CF optimization of PERKY code
alone does not reach the budget.** EMAC opcodes cost zero cycles in the port;
moving multiplies onto EMAC would exploit that model artifact and must not be
used to pass.
Closing it needs at least one of: exact stock-side reductions (the sequencer
step and DSP frame builder dominate spikes), a different placement for a voice
family, a product decision on the default-on diagnostic profiler (~2.3 µs), or
physical evidence that justifies a different envelope. The predictor-model
quirk ([trap](../../../docs/contributing/TRAPS.md#trap-predictor-condition))
inflates every image alike and must not be exploited.

## Local artifacts and source identity

The committed source and report metadata are sufficient to understand the
campaign. **Git does not contain the stock image, original sample assets,
toolchains, generated firmware, or complete ignored measurement receipts.**
Continue in the existing directory to retain those inputs and controls.
Reconstructing a remote checkout requires the user's own inputs and local
build steps; do not fetch or publish proprietary images to make it portable.

| Local path under `out/perky/hybrid/` | Purpose |
|---|---|
| `full-map-kernels-v8/` | **PKFM31** BUILD, MAIN, ELF and every gate receipt (source, kernels, handoff, DMA, merged, differential, lifecycle, matrix, scenes) |
| `kernels8-campaign/workload/` | Eight PKFM31 sustained rows with budget assessments; `gates/`, `floors/` beside it |
| `full-map-kernels-v5/`–`v7/` | PKFM28–PKFM30 builds; worst row and differential in `kernels5-campaign/`–`kernels7-campaign/` (`kernels7-campaign/pcbin/` is the per-instruction profile) |
| `full-map-kernels-v3/` | PKFM26 BUILD, MAIN, ELF and every gate receipt |
| `kernels3-campaign/workload/` | Eight PKFM26 sustained rows; `gates/`, `floors/`, `profile/`, `spike/`, `track/`, `stockpc/` beside it |
| `diagnostic-*-observer/` | Diagnostic observer builds (count, spike, track, stockpc, pcbin) |
| `full-map-merge-v1/`, `full-map-kernels-v1/`, `full-map-kernels-v2/` | PKFM22, PKFM24, PKFM25 builds (`merge-campaign/`, `kernels-campaign/`, `kernels2-campaign/` rows) |
| `full-map-dispatch-v1/`, `full-map-kernels-v4/` | Rejected PKFM23 and PKFM27, with `REJECTED.txt` in their campaign directories |
| `pkfm22-investigation/vectors/` | Captured WT/Slap/NT kernel vectors (and the table regions they read) from the PKFM22 image |
| `cf-cycle-bench/` | `cf_cycle_bench` built by `tools/harness/perky_cf/build_cf_cycle_bench.sh` |
| `full-map-stock-cf-v1/` | Final PKFM21 BUILD, MAIN, ELF, linked proofs and source archive |
| `stock-cf-optimization/final-workload/` | Eight final matched rows and fixtures |
| `stock-cf-optimization/final-profile/` | Exact matched final profile |
| `stock-cf-optimization/EXCLUSIVE_PKFM20_PKFM21.json` | Raw exclusive group membership |
| `full-map-remaining-cf-mix-v1/` | Immediate PKFM20 image/control build |
| `resonant-cf-optimization/final-workload/` | Eight PKFM20 control rows |
| `resonant-feasibility-v1/` | Corrected PKFM17 Resonant/Slap baseline |
| `budget-calibration/observer/ot_emu_safety` | Frozen timing observer |
| `full-map-release/observer/full-map-oracle.dylib` | Independent original-source oracle |
| `stock-isr-next-profile-v1/` | PKFM20 stock address-bucket investigation |

PKFM31 MAIN SHA256 is
`77c70410327245324a30bf453dca0d5d092341bdd10ad31f382fac3b476982a9`;
ELF SHA256 is
`0d2261861e856404901df2d61f75ed81578c6044cd5043243fc52fcf2d9b4b3a`. Its CF
text is 586,460 bytes (+1,538 over PKFM26); data/BSS, both DSP uploads and
`PERKYAH.DAT` are byte-identical to PKFM26.

PKFM26 MAIN SHA256 is
`e9502d2c477ba4e7ecdcffb949d879e2784833b9eec5d879ea60df8914ad2f9f`;
ELF SHA256 is
`62befe69dc57fb647d17627fb35d5f5d6573fb25030f93ae6f8164d7ff2f4412`. Its CF
text is 584,922 bytes (+6,526 over PKFM21), data/BSS 620/1,612,676 bytes; both
DSP uploads and `PERKYAH.DAT` are byte-identical to PKFM21.

PKFM21 MAIN SHA256 is
`484a0b9380670e15b31a0c06589f88066a861b93482504adecffd9a49840dfc3`;
ELF SHA256 is
`7231cd51f9e54613c47aad0da7dd3f7df06e3022a2ffb9f7bd388cd53f7786a6`.
Observer SHA256 is
`f975b4d2c4b6a2d993d3158bc8e68c8a786b328e2902b58bdde418225287d022`;
budget JSON SHA256 is
`8608844b96c6f20daed514147dc6cadab7a2c82aae80d2ef7c9a875a22ccaec4`.

The executed build records source checkpoint
`4eeae750caf8ba98144dd9ad8ac3b68299e21982` plus **110 source hashes** from
the then-uncommitted work. This push commits that implementation. Keep the
historical `source_commit` fields intact: their dirty-source hashes supply
the additional identity. A new commit does not invalidate an unchanged image,
and it does not mean that a different rebuild has already been tested.

`OPTIMIZATION_PROOFS.json` indexes eighteen receipts, thirteen linked to the
final image and five supporting proofs. `FINAL_SOURCE.tar.gz`,
`FINAL_SOURCE_SNAPSHOT.json` and `FINAL_ARCHIVE_RECEIPT.json` preserve local
source/evidence metadata without firmware or audio assets. Keep them. Completed
bulk card/block captures were deliberately removed after hashes and activity
summaries were saved; the retained counts cannot recreate those waveforms.

## Efficient continuation workflow

Keep admitted builders, generators, verifiers and receipts immutable. Create a
new layered candidate, a new work directory and a new version, such as PKFM28.
Existing adapters use source-hash guards; editing their ancestors can break
reproduction of every later campaign. Add a new adapter when behavior changes.

**Serialize full firmware builds and all writers of global `out/` or platform
outputs**, including `make check` and `make bus`. The layered builders still
share those paths; a candidate/default-check collision already cost work.
Parallelize only private microbuilds or separately staged measurement rows
whose inputs and observer links are fixed.

PKFM26 is not reproducible from the committed tree: its v4-merge generator
revision was edited after that build and only the edited one was committed
([correction](ORCHESTRATION_CF_QUALIFICATION.md)); compare against its
retained outputs, not a rebuild. The current opt-in build entry reproduces
PKFM31 into a new directory; add a
new generator to `KERNELS` in `tools/perky/build_perky_kernels_cf.py` (or a new
layer on it) for the next change:

```sh
PERKY_KERNELS=wt,slap,slaprender,nt,v4merge,placement,predicates,render \
PERKY_KERNELS_CF_WORK=out/perky/hybrid/full-map-next-v1 \
PERKY_KERNELS_CF_VERSION=PKFM32 \
  .venv/bin/python tools/perky/build_perky_kernels_cf.py
```

Use that only after inspecting the layered build and adding the intended
change; changing the version alone adds no optimization. Builds rewrite
`out/mainos_bus.bin` and `out/platform`; `make bus REMIX=perky-machine`
restores the default shipping configuration, **not this experimental
full-map image**. Do not overwrite PKFM21, PKFM26 or PKFM31 outputs.

For a kernel change, first capture vectors from the current image
(`tools/verify/capture_perky_kernel_vectors.py --kernel wt|slap|nt`), then
replay them and compare cycles with `tools/verify/bench_perky_kernel.py
VECTORS --candidate-elf ... --candidate-symbol ...` before building an image.

First prove the changed primitive/state path against independent reference
code, including actual CF/DSP execution and relevant PCM/state/RNG/clock,
alias, ABI, CCR and raw EMAC behavior. Then run one matched worst full workload:

```sh
.venv/bin/python tools/verify/measure_perky_stock_cf.py \
  --build out/perky/hybrid/full-map-next-v1 \
  --work out/perky/hybrid/next-cf-campaign/final-workload \
  --frames 32768 --v3 slap-control --voice4 noise-tone
```

Precreate the candidate's `observer/full-map-oracle.dylib` link to the retained
original oracle and the campaign's `observer` link to the frozen calibration
observer before parallel runs; the older lazy creation has a race. Preserve
the exact bytes. The row runner accepts new candidate versions and refuses to
overwrite completed rows. Bind new sources transitively; inspect current
receipts and adapters rather than bypassing a failed source-hash guard.

Use `profile_perky_stock_cf_cost.py --candidate BUILD --work PROFILEWORK
--build-observer` to prepare symbol ranges, then repeat with `--control-row
ROW.json` for the matching completed row. Its name is historical: it reuses
the qualified observer binary. Profiled/unprofiled audio, target dumps,
transport, cycles, histograms and final fixture must match exactly before
trusting attribution. Include branch-predictor isolation and same-image
controls for paired target microbenchmarks.

If the change is worthwhile, fix the candidate and run all eight combinations
of `--v3 {snare,bass,alternate,slap-control}` and
`--voice4 {hat,noise-tone}` with the same 32,768-block setup. Also retain
coverage for all three Hat modes and Acoustic Hats; the eight sustained rows
alone cover metallic Hat and Noise/Tone. Use existing direct/mode/lifecycle
gates and add focused sustained rows if a changed path needs them.

The actual-image functional entry points are:

```sh
PERKY_FULL_MAP_WORK=BUILD .venv/bin/python tools/verify/verify_perky_stock_cf_sources.py
.venv/bin/python tools/verify/verify_hat_state_handoff.py --build BUILD
.venv/bin/python tools/verify/verify_perky_synthesis_kernels.py --build BUILD
.venv/bin/python tools/verify/verify_hat_state_dma.py --build BUILD
PERKY_FULL_MAP_WORK=BUILD .venv/bin/python tools/verify/qualify_hat_state_lifecycle.py
PERKY_FULL_MAP_WORK=BUILD .venv/bin/python tools/verify/qualify_hat_state_matrix.py
PERKY_FULL_MAP_WORK=BUILD .venv/bin/python tools/verify/qualify_perky_full_map_scenes.py
```

Here `BUILD` means the new candidate directory. Read each gate's observer/link
setup and source contract first. A changed DSP upload requires renewed DSP
fit/ownership/stock-FX evidence; prior DSP-only evidence transfers only through
verified byte identity. A new stock detour or assembly helper needs a proof of
the executed binary, linked ELF, packaged bytes and actual boot readback.

`qualify_perky_stock_cf.py` is the frozen PKFM21 admission checker against
PKFM20. Its current invocation is recorded in the campaign logs. Adapt it in
a new file for a new pass, bind final proofs and rows to the actual image, and
keep all seven ceilings. An exit code of one is expected only when the fresh
receipt explicitly proves a performance hold; arbitrary failures are not an
accepted result.

## Verification already completed

PKFM31 has these completed local checks (receipts in `full-map-kernels-v8/`,
logs in `kernels8-campaign/gates` and `floors`, indexed by
[the campaign receipt](ORCHESTRATION_CF_QUALIFICATION.json)); do not repeat them
merely because a documentation checkpoint was committed:

- Direct source: 5,355 frames, 81 layouts, every split, trace disabled/enabled;
  linked NT/AH/Slap kernels; Hat handoff (800 frames); DMA cases. All pass.
- Merged segments: 11,664 actual-image frames (8,253 merged). Dispatcher
  differential against PKFM21: 1,500 frames (543 trigs, 7 part changes),
  every placement/production/Hat object, both packet pings (366 merged V4
  frames) and the cursor block byte-identical; merge counts equal PKFM30's.
- Kernel vectors replayed against PKFM31's linked image: WT 3,441 / Slap 581 /
  NT 1,153 captured calls exact (PCM, object, RNG).
- Production lifecycle: 52,706 frames, peak 311.110 µs. Selector sweep: all 243
  tuples, 160,054 frames, none missing; peak 329.242 µs. Scenes/fader: 9,155
  frames; peak 282.580 µs. All exact and all still over the calibrated ceilings.
- All eight sustained rows: exact synth PCM and DSP Hat state/side/clock/
  feedback, 32,768 source frames per CF voice (32,766 for V4), no transport
  failures; results in the table above.
- `make check REMIX=perky-machine`, `scripts/refhash.sh check` (24
  configurations bit-identical) and `make bus REMIX=perky-machine`: see the
  receipt's `default_floors`.

PKFM26's checks are recorded in [its campaign](KERNEL_CF_QUALIFICATION.md).
PKFM21's own completed checks remain recorded in
[its qualification](STOCK_CF_QUALIFICATION.md). Local timing does not model
physical cache, SDRAM/card/bus contention, IRQ latency or UI responsiveness.

## What completion still requires

1. Reduce complete workload and lifecycle costs until **every fixed ceiling
   passes with useful margin**, preserving the full map and exact behavior.
   If the present placement cannot do that, establish and implement a better
   placement with measured resource and complete-frame costs.
2. Requalify the changed paths and final fixed image, including demanding
   sustained Resonant and Slap rows, backend transitions, production resets,
   saved ALGO/MODE, stock playback, all FX and scene/fader delivery.
3. Prepare a fresh versioned project, asset companion and validated install
   package for that exact image. Recheck wrapper size/checksum and both
   upgrade round trips; historical PKFM6 packaging does not qualify PKFM21.
4. Run controlled actual Octatrack acceptance with the user's authorization:
   sustained worst combinations, stock card activity/FX, controls/UI,
   STOP/START, Part/Bank and backend changes, and matched physical performance
   evidence. Compare against PERKY4S; record exact image/project/control
   identities and diagnostic overhead. A calibrated emulator pass alone cannot
   prove this stage.
5. Promote the admitted configuration into the normal module/remix workflow,
   finish user-facing build/asset/project instructions and record release
   evidence. Keep rollback to the hardware-confirmed PERKY4S image.

PERKY4S remains the physical baseline: source
`16a8de19a17ee4cba765cbdb30ca051f85af4e23`, MAIN SHA256
`be74504aadc747817c54dc1226944abfb062244d404408c46d6040744a9ae1d0`.
Do not call the overall goal complete until the full requested layout is
accepted on hardware.

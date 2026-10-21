# PERKY full voice layout continuation handoff

Updated 21 October 2026. Continue in `/Users/jrold/Downloads/octabam` on
**`perky-cf-dsp-hybrid`**. The user explicitly chose this branch repeatedly,
overriding the `perky-machines` default in `AGENTS.md` for this experiment.
Keep using this checkout. Read its instructions before editing.

**The complete voice map exists and passes substantial local correctness and
lifecycle checks. It still fails the fixed performance budget.** The latest
candidate is **PKFM21**, with verdict `FAIL_HOLD / HOLD_FOR_PERFORMANCE_WORK`.
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

1. [Current module status](../README.md) and
   [latest PKFM21 qualification](STOCK_CF_QUALIFICATION.md), with its
   [machine-readable verdict](STOCK_CF_QUALIFICATION.json).
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

| T5 | T6 | PKFM21 ISR mean | Full ISR peak | Total CF mean |
|---|---|---:|---:|---:|
| Resonant Bass | Metallic Hat | 196.443 | 298.102 | 222.218 |
| Resonant Bass | Noise/Tone | 208.141 | 304.042 | 233.851 |
| Resonant Snare | Metallic Hat | 197.150 | 298.818 | 222.939 |
| Resonant Snare | Noise/Tone | 208.588 | 305.186 | 234.298 |
| Snare/Bass MODE locks | Metallic Hat | 196.767 | 298.337 | 222.555 |
| Snare/Bass MODE locks | Noise/Tone | 208.325 | 305.148 | 234.038 |
| Slap | Metallic Hat | 203.338 | 298.803 | 229.112 |
| Slap | Noise/Tone | 214.982 | 303.652 | 240.727 |

All eight preserve exact synth audio and fail six of seven budget metrics;
only ACK peak passes. The worst mean still needs **26.4% less ISR work and
21.4% less total CF work**, about **56.8/51.4 us per frame** respectively.
Resonant has lower means than Slap in these local runs but some higher peaks.
That does not resolve the user's hardware observation.

## What the latest optimization retained

PKFM21 layers five changes onto the immutable PKFM20 generators:

- A stock DELAY zero-ramp mixer removes zero additions and loop overhead only
  when all four coefficient increments are exactly zero. The generic path and
  original memory/MAC operation order remain available.
- Signed rational interpolation removes redundant magnitude/complement work
  while retaining exact negative rounding, phases, carry and clocks.
- Bounded packet publish/clear assembly retains every read, write and clear in
  order, including alias behavior and the generic length fallback.
- Slap uses rolling pointers when its five dynamic tap spans and write span
  avoid wrapping. Dynamic metadata and the generic fallback remain intact.
- Cold diagnostic trace loops are outlined while the trace flag stays live.

Relative to PKFM20, Resonant ISR means improve 3.443–3.890 us and Slap improves
3.795–3.935 us. Every matched peak improves 3.670–4.803 us. CF text is 578,396
bytes, up 1,104; data/BSS stay 588/1,612,664 bytes. Both DSP uploads, DMA words,
algorithms, precision and source latency remain unchanged.

PKFM20's exact Resonant twenty-sample native chunks, unchanged-control prepare
path and full stock source-mixer assembly remain retained. Earlier WT assembly,
NT/AH block work, exact RNG/EMAC changes, packet reservation and Hat state
handoff also remain. Review the generators before proposing these again.

## Where worthwhile work remains

The matched final Slap/Noise-Tone profile gives these exclusive steady costs:

| Group | PKFM21 model us per frame |
|---|---:|
| Stock ISR including new DELAY helper, mixer and position | 104.201 |
| WT synthesis | 27.468 |
| Slap including span fast body, generic delay and filter | 24.530 |
| Noise/Tone synthesis | 17.450 |
| Rational conversion | 6.395 |
| Packet publish and clear | 3.011 |
| Segment handling | 6.146 |
| Other ISR | 25.740 |
| Background work, separate from ISR | 26.000 |

Use raw exclusive maps, not the printed top-32 functions. A new helper moves
cost out of a stock address bucket; count it back into the group. Slap's
`pk_cf_slap_delay_span_fast` body must also be included. Use the 32,256 steady
frame denominator and native clock. These are combined-image attributions,
not independent causal savings to add together.

**Suggested next direction:** seek a material reduction in stock/CF synthesis
or orchestration, especially complete WT work and avoidable common state or
memory traffic. Inspect actual CF assembly and mutable-state writers before
choosing a rewrite. Small sub-microsecond changes alone will not close this
gap. Reconsider DSP placement if CF reductions cannot close it, with explicit
code/data/DMA and complete-frame cost proofs. The paired DSP-B feasibility
experiment did not admit a complete two-voice solution. WT storage/service and
compressed rendering have already been investigated; they are not free space
or an untried obvious offload.

Several exact experiments were slower and are deliberately excluded: WT
envelope C blocks and linear-envelope assembly, Slap compiler unrolling and
envelope caching, fixed Slap delay, NT filter assembly, and stock DELAY loop
unrolling. Some source files remain for provenance; presence does not mean
enabled. Do not admit zero-product MAC shortcuts based on unproven MACSR/PAV
behavior. A failed earlier prepare-inlining experiment broke the observer's
`placement_prepare` event boundary; its abort was not a valid audio or timing
verdict. Preserve that seam until a replacement observer is independently
qualified.

## Local artifacts and source identity

The committed source and report metadata are sufficient to understand the
campaign. **Git does not contain the stock image, original sample assets,
toolchains, generated firmware, or complete ignored measurement receipts.**
Continue in the existing directory to retain those inputs and controls.
Reconstructing a remote checkout requires the user's own inputs and local
build steps; do not fetch or publish proprietary images to make it portable.

| Local path under `out/perky/hybrid/` | Purpose |
|---|---|
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
new layered candidate, a new work directory and a new version, such as PKFM22.
Existing adapters use source-hash guards; editing their ancestors can break
reproduction of every later campaign. Add a new adapter when behavior changes.

**Serialize full firmware builds and all writers of global `out/` or platform
outputs**, including `make check` and `make bus`. The layered builders still
share those paths; a candidate/default-check collision already cost work.
Parallelize only private microbuilds or separately staged measurement rows
whose inputs and observer links are fixed.

The current opt-in build entry is:

```sh
PERKY_STOCK_CF_WORK=out/perky/hybrid/full-map-next-v1 \
PERKY_STOCK_CF_VERSION=PKFM22 \
  .venv/bin/python tools/perky/build_perky_stock_cf.py
```

Use that only after inspecting the layered build and adding the intended
change; changing the version alone adds no optimization. `make bus
REMIX=perky-machine` produces the default shipping configuration, **not this
experimental full-map image**. Do not overwrite admitted PKFM21 outputs.

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

PKFM21 has these completed local checks; do not repeat them merely because a
documentation checkpoint was committed:

- Direct source: 5,355 frames, 81 layouts, 24 directed transitions, three mode
  rotations, every split 0–16, plus trace disabled/enabled comparisons.
- Handoff: 800 actual-image frames with both owners, pending work, poisoned
  startup and wraps. Linked NT/AH/Slap kernels and ten DMA cases pass.
- Production lifecycle: 52,572 entries and returns, 43 events, seven
  generations, 22 backend switches; zero reported source/ownership/transport/
  DMA/stack violations. Peak 323.814 us, still over the calibrated ceiling.
- Selector sweep: all 243 declared tuples across four patterns, 160,224
  entries and returns; peak 328.580 us. This is not every possible algorithm
  and mode combination. Private stack peak is 1,244/4,096 bytes.
- Scenes/fader: all eight outputs active, 9,043 entries/9,042 returns with one
  in-flight interrupt at quit; peak 297.568 us, still over the ceiling.
- All eight sustained rows: exact original-reference synth PCM and DSP Hat
  state/side/clock/feedback, active stock chains, continuing card reads and
  zero modeled nominal misses. Direct gates provide separate full-state
  evidence; sustained rows do not compare every raw CF object every block.
- `make check REMIX=perky-machine`: all runnable default gates passed, with
  fixture-dependent skips retained. `scripts/refhash.sh check`: all 24
  configurations bit-identical. `make bus REMIX=perky-machine`: default output
  restored. Tool compilation, documentation verification and diff checks pass.

Logs are under `stock-cf-optimization/`; the final build's
`DEFAULT_FLOORS.json` records the default checks. Stock activity counts prove
activity, not gap-free stock waveform identity. Local timing does not model
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

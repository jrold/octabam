# CF budget optimization — 21 October 2026

**PKFM11 still fails the frozen performance target. Do not promote it as a
hardware-qualified build.** These are measured local model costs at
CF264/PIT132, with the actual background worker enabled. The
[calibrated budget](EMULATOR_BUDGET.md) remains unchanged. The
[machine-readable combined receipt](CF_BUDGET_OPTIMIZATION.json) is authoritative
for this candidate; its final status is `FAIL_FROZEN_BUDGET`, with admission
`HOLD_FOR_PERFORMANCE_WORK`.

## Measured result

All rows run WT/WT + Slap + the listed fourth source, all eight track outputs,
streaming stock samples and all fourteen stock FX. Each requests 16,384
transport frames using the exact same measuring binary as calibration.
Every source PCM/state/shared-RNG comparison passes. No nominal model deadline
miss or transport error was observed in these five rows; that does not satisfy
the stricter calibrated performance gate.

| Fourth source | Steady ISR mean, us | ISR p99, us | Full ISR max, us | Total CF mean, us | Budget |
|---|---:|---:|---:|---:|---|
| **Fixed target** | **158.212** | **166.780** | **250.712** | **189.298** | All seven ceilings required |
| White Hat | 223.500 | 232.784 | 315.303 | 268.877 | FAIL |
| Metallic Hat | 222.407 | 231.826 | 314.765 | 281.344 | FAIL |
| Pulse Hat | 212.576 | 222.205 | 306.758 | 262.915 | FAIL |
| Noise/Tone | 231.375 | 240.871 | 318.818 | 257.893 | FAIL |
| Acoustic Hats | 228.543 | 253.799 | 329.133 | 255.366 | FAIL |

Metallic Hat falls from PKFM6's **232.879 to 222.407 us** steady ISR mean
(4.5% less) and **299.144 to 281.344 us** total CF work/frame (5.9% less).
It still requires approximately **28.9% less ISR work** and **32.7% less total
CF work** from this new cost to meet the target. Noise/Tone and Acoustic Hats
remain four-CF-source layouts and gain much less from Hat-specific changes.

## Retained implementation

- WT native blocks hold up to twenty samples, avoiding the repeated 16+1/2
  setup at the native/output sample-rate boundary.
- The background Hat shadow uses the existing exact transposed metallic
  renderer, with delay work removed because the CF ring already owns it.
  It retains ordinary interruptible integer arithmetic.
- A bounded CF assembly helper gathers the five fixed Hat delay taps directly
  into the existing DMA packet; the original C fallback remains.
- CF assembly advances the original Slap filter twice per noise sample,
  retaining its 32-bit wrapping, negative-product adjustment and clamps.
- A sparse Hat codec copies only controls and required trigger words, skips
  redundant patches and empty prefix work, and keeps native histories in
  their owners. Full-state CF imports invalidate the cache at DSP takeover;
  generation resets also invalidate it.

The new assembly uses no EMAC state, peripheral accesses, waits or interrupt
mask changes. No clocks, waveforms, source precision, sample-rate ratio,
latency or voice count were reduced. Both DSP uploads remain byte-identical to
PKFM6, including all original fourteen FX implementations and dispatches.

The compact O2/no-unroll placement/worker experiment (PKFM9) regressed the
short-run timing and was rejected. PKFM7–PKFM10 remain intermediate experiment
artifacts, not releases. PKFM10's partial lifecycle/matrix runs were deliberately
interrupted after the takeover-cache audit; their partial results are not passes.

## Evidence and scope

Candidate MAIN: `ade52581b99c919f89da0e3c94df3a07b2e46486f901942b58ac34bd223e8cff`.
Runtime ELF: `9de6d4254ce9b550172a37fe49e8636098ff35fb534e0ec699ba1dac4893c3e5`.
Generated sources, source snapshot, build receipts, native disassembly, workload
rows and test receipts are retained under
`out/perky/hybrid/full-map-budget-v5/`; no stock bytes are added to Git.
The original PKFM6 qualification and external handoff bundle are preserved.

Actual-image direct checks pass all **81 layouts + 24 directed transitions**,
three rotated mode tuples and every split 0–16: **5,355 exact source frames**.
The assembly gates pass **19,220 tap cases** (every ring cursor, wrapping,
packet/carry/sentinels) and **4,096 Slap filter cases** (original recurrence,
overflow/clamps, output/state/sentinels). Both check all callee-saved registers.
The real scene/fader campaign also passes with exact source audio.

The actual production lifecycle run passes **52,987 frames**,
**22 backend handoffs** and **seven generations**, including STOP/START,
Part/Bank changes, first CF Hat use after a generation started on another
algorithm, and every Hat mode. PCM, state, side/RNG, native clocks and old-generation
feedback retirement remain exact. Its maximum observed ISR is
**345.928 us**, with zero nominal model deadline misses.
This maximum still exceeds the calibrated 250.712 us peak target.
One IRQ is in flight at interactive shutdown; 52,986 completed
returns are checked, as recorded by the lifecycle observer.

## Remaining measured costs

A separate read-only attribution observer replays the same **16,384-frame**
metallic workload. Its full-ISR metrics, total CPU counts, source/stock target
dumps and audio hashes match the fixed measuring observer exactly. The control
receipt and its hash are required by the profiling tool; absence of a control
cannot produce a pass.

Exclusive cost per measured steady frame (first 512 IRQs excluded):

| Domain | Routine/group | Measured us/frame |
|---|---|---:|
| ISR | Stock instructions | 109.571 |
| ISR | Both WT renderers + frequency conversion | 29.637 |
| ISR | Slap renderer + filter + delay | 26.092 |
| ISR | Hat frame/emit/conversion/taps/DMA helpers | 27.372 |
| Background | Hat state synthesis + worker | 33.124 |
| Background | Stock tasks | 26.082 |

These are non-overlapping attribution groups, not physical time predictions or
immutable lower bounds. Other glue/control routines account for the remaining
ISR work. The profile's steady window and the playback-total denominator are
recorded separately; their statistics should not be treated as analytical bounds.

**[Inference] Small kernel optimizations have not closed this gap.** With the
measured stock ISR cost held fixed, nonstock ISR cost would need to fall from
about 112.8 to 48.6 us (approximately 57%). Deleting all measured Hat background
state maintenance, even if it were free to replace, would leave about 248.2 us
of total CF work versus the 189.3 us target. Moving ISR work into the background
therefore cannot by itself satisfy both gates. This does not prove that a larger
rewrite, stock-path optimization or different DSP placement cannot succeed.

The next architectural issue exposed by this profile is that DSP Hat ownership
still requires a CF synthesis shadow to make exact nonblocking takeover possible.
Avoiding that duplicate evolution requires another state-transfer design; simply
turning the worker off would invalidate audio/state handoffs. WT/Slap and the
stock ISR also need substantial reductions or different placement. None of
those unimplemented changes is included in this candidate's performance claim.

## Completed production and repository checks

The actual sequencer/panel sweep passes all **243 production
ALGO/MODE tuples**, with zero missing combinations over
**160,161 frames** (160,160 completed IRQs).
Its maximum observed ISR is **347.413 us**, with no nominal
deadline miss, ownership violation, clock error or transport overflow.
Independent original-reference PCM/state/RNG comparisons pass throughout.
The sweep's calibrated ISR ceilings still fail; the combined receipt records
separate ISR assessments for matrix, lifecycle and scene/fader runs.

Completed commands and results:

- `verify_perky_full_map_sources.py`: PASS, 5,355 direct source frames.
- `verify_perky_budget_taps.py --work out/perky/hybrid/full-map-budget-v5`:
  PASS, 19,220 cases, including callee-saved registers.
- `verify_perky_budget_filter.py --work out/perky/hybrid/full-map-budget-v5`:
  PASS, 4,096 cases, including callee-saved registers.
- `verify_perky_full_map_stock_fx.py`: PASS, all fourteen stock FX code/data
  and both dispatch tables, with unchanged B stock source.
- `measure_perky_budget_candidate.py`: five PASS exact-audio/scheduling rows,
  each 16,384 requested frames, using Hat modes 0/1/2, Noise/Tone and Acoustic.
  Each `qualify_perky_hybrid_budget.py --assess ROW.json` returns **1 / FAIL**
  against the unchanged calibrated budget.
- `qualify_perky_full_map_lifecycle.py`: PASS model correctness/nominal timing,
  52,987 frames, 22 handoffs and seven generations.
- `qualify_perky_full_map_matrix.py`: PASS model correctness/nominal timing,
  243 tuples and 160,161 frames.
- `qualify_perky_full_map_scenes.py`: PASS, 9,218 frames.
- `profile_perky_full_map_cost.py --candidate ... --control-row ... --frames 16384`:
  PASS, exact target dumps/audio and unchanged CPU/ISR counts versus the
  unprofiled metallic row.
- `REFHASH_LOCAL=1 scripts/refhash.sh check`: PASS, all 24 configurations
  bit-identical to the existing local baseline; baseline not re-saved.
- `make check REMIX=perky-machine`: all runnable checks PASS. Its existing
  multi-machine canary and CF-final odd-access fixtures are absent, and the
  stock project/set, fragmented-FX and probe-port gates skip without
  `OT_PROJECT`. The candidate's own sustained card/stock-FX and production
  lifecycle/matrix checks above ran independently; those skips are not passes.
- `qualify_perky_budget_optimized.py --build out/perky/hybrid/full-map-budget-v5`:
  **exit 1 / FAIL_FROZEN_BUDGET / HOLD_FOR_PERFORMANCE_WORK**, after verifying
  image/runtime/source identities, all correctness receipts and fixed-budget
  comparisons. This is the required outcome for the measured costs.
- Python syntax checks and `git diff --check`: PASS.

The full-map tools use
`PERKY_FULL_MAP_WORK=out/perky/hybrid/full-map-budget-v5`; the candidate builder
uses `PERKY_BUDGET_WORK` at that directory, `PERKY_BUDGET_VERSION=PKFM11`,
`PERKY_BUDGET_SLAP=1` and `PERKY_BUDGET_CONTROLS=1`. The original PKFM6 immutable
DSP import fixtures/oracle and fixed calibration observer are reused by hash;
no new target-state repair or alternate clock is introduced.

The common `out/mainos_bus.bin` and its `.remix` label were rebuilt by the
standard check as the default `perky-machine` build, rather than left pointing
at an experiment. Its resulting SHA256 is
`c9e292bec49f54820355c76dca904c5dc02d1378120f7a34042c10dfe1bbe1a4`.
Disposable test card images and block dumps were removed after their hashes
and summaries were saved. Candidate images and generated source inputs remain
local under ignored `out/` paths; no Elektron bytes enter the committed record.
No firmware was flashed, pushed, or packaged as a new hardware handoff.

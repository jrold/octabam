# PERKY — PĒRKONS-style source machines

For continuation of the current hybrid experiment, start with the
[Claude handoff](hybrid/CLAUDE_HANDOFF.md): branch authorization, complete voice
map, measured budget gap, local artifacts, next steps and completion criteria.

## Stock and CF candidate: PKFM21 (performance target still failed)

The [stock and CF campaign](hybrid/STOCK_CF_QUALIFICATION.md) adds a guarded
stock DELAY mixer, exact signed interpolation, bounded packet assembly and
Slap ring spans, and smaller diagnostic trace frames. Eight matched full
workloads retain WT/WT, Slap or Resonant Snare/Bass/MODE locks, Hat or Noise/Tone,
four stock sample tracks and all fourteen FX. Resonant ISR means improve
3.443–3.890 us and Slap means improve 3.795–3.935 us over PKFM20; every matched
peak improves by 3.670–4.803 us. Source, helper, handoff, kernel, DMA, lifecycle,
scene and the 243-tuple selector sweep pass, with exact synth audio.

All eight still fail six of seven fixed timing ceilings. The worst mean is
214.982 us ISR and 240.727 us total CF against 158.212/189.298 us targets:
another 26.4%/21.4% reduction is required in those means. The final verdict is
`FAIL_HOLD`. CF text grows 1,104 bytes; data/BSS, DSP uploads, algorithms,
precision, native clocks and source latency remain unchanged. PERKY4S remains
the hardware-confirmed release.

## Remaining CF candidate: PKFM20 (performance target still failed)

The [remaining CF campaign](hybrid/REMAINING_CF_QUALIFICATION.md) retains exact
Resonant twenty-sample blocks, an authoritative unchanged-control preparation
path and a proven stock source-mixer assembly loop. In eight matched sustained
four-voice runs, Resonant ISR means improve 4.526–5.600 us and Slap means improve
2.764–3.305 us over PKFM17. WT/WT, four stock sample tracks and all fourteen FX
remain active. Fixed Slap/Resonant, sequenced Snare/Bass locks, DSP-A metallic
Hat and CF Noise/Tone are all measured against identical fixture cards.

Every row retains exact synth PCM and fails six of seven unchanged budget
ceilings. The highest mean is Slap/Noise-Tone at 218.918 us ISR and 244.643 us
total CF, against 158.212/189.298 us targets; another 27.7%/22.6% reduction is
required in those means. Some individual peaks rise despite lower averages.
Source, handoff, linked-kernel, DMA, lifecycle and scene gates pass. The complete
243-tuple selector sweep passes over 159,827 frames, and the final profile and
all eight workloads are bound to PKFM20. The final verdict is `FAIL_HOLD` for
performance; nominal deadline passes do not meet the calibrated target.

CF text shrinks 4,084 bytes; data/BSS and both DSP uploads are unchanged.
No precision, algorithm or clock is relaxed. This remains an opt-in experiment
held for performance work; PERKY4S remains the hardware-confirmed release.

## Corrected sustained Resonant screen: PKFM17 (performance target failed)

The [Resonant workload campaign](hybrid/RESONANT_WORKLOAD_QUALIFICATION.md)
adds dedicated Snare, Bass and sequenced Snare/Bass MODE-lock runs, with matched
Slap controls. Each runs 32,768 blocks with WT/WT, four stock sample tracks and
all fourteen FX. Resonant ISR means are 205.566–205.612 us with DSP-A metallic
Hat, and 216.536–217.005 us with CF Noise/Tone, against the unchanged 158.212 us
ceiling. All eight rows retain exact original-reference synth PCM and fail six
of seven timing gates. The current placement remains held for performance work.

The previous five sustained rows below all used Slap; the selector matrix's
Resonant coverage did not supply separate sustained means. Current matched
Resonant means are slightly lower than Slap, with higher ISR peaks; this local
result does not settle the user's reported much greater Resonant cost on
hardware. Sustained Snare/Bass and MODE-lock cases are now required alongside
the existing alternatives and lifecycle evidence. Firmware and the calibrated
budget are unchanged; PERKY4S remains the hardware-confirmed release.

## CF synthesis/ISR candidate: PKFM17 (performance target still failed)

The [CF synthesis/ISR campaign](hybrid/CF_SYNTHESIS_QUALIFICATION.md) retains
all twelve algorithm choices and three modes each. Exact hot-path changes
reduce steady ISR means by 9.4–12.0 us across the five sustained full workloads,
with all eight track outputs and all fourteen stock FX active. Metallic Hat's
ISR/total CF means fall from 222.128/248.054 to 210.117/235.939 us.

All five still fail the unchanged fixed budget. The worst of these Slap-based
rows, with Noise/Tone on V4, is
221.328 us ISR and 247.122 us total CF, against 158.212/189.298 us targets;
another 28.5%/23.4% reduction is required in those respective means. This
remains an opt-in hybrid experiment held for performance work. PERKY4S remains
the hardware-confirmed release.

## State handoff candidate: PKFM15 (performance target still failed)

The [DSP state handoff campaign](hybrid/STATE_HANDOFF_QUALIFICATION.md) removes
continuous duplicate CF Hat synthesis. DSP-A keeps rendering while a requested
backend change transfers a frozen state through spare scheduled DMA words;
CF catches up only when needed. Metallic Hat's total CF work/frame falls from
281.344 to 248.054 us (11.8%), with exact source audio in all five sustained
full-workload rows. Its ISR mean is 222.128 us. Both means still exceed the
unchanged 158.212/189.298 us targets. This remains an opt-in hybrid experiment
held for performance work; PERKY4S remains the hardware-confirmed release.

The 243-layout sweep, five sustained workload rows, 53,229-frame production
lifecycle and scene/fader run pass their exact-audio checks. These nominal
deadline passes are recorded separately from the failed performance target.

## Earlier CF optimization candidate: PKFM11

The [CF optimization campaign](hybrid/CF_BUDGET_OPTIMIZATION.md) reduces metallic
Hat's steady ISR mean from 232.879 to 222.407 us and total CF work/frame from
299.144 to 281.344 us. All five sustained full-workload rows retain exact source
audio and fail the frozen 158.212/189.298 us mean targets. This is an opt-in
experiment on the hybrid branch; PERKY4S remains the hardware-confirmed release.
Further substantial performance work is required before physical admission.

## Complete-map candidate: PKFM6 (performance target failed)

The [hardware-informed replay](hybrid/EMULATOR_BUDGET.md) now rejects PKFM6's
performance. The working one-CF configuration and exact hardware-confirmed
PERKY4S image average about 189 us total modeled CF work per frame; PKFM6
metallic Hat averages 299 us. It needs approximately 32% less steady ISR work
and 37% less total CF work to reach the working configuration's envelope.
These are engineering targets, not a universal emulator-to-hardware multiplier.
The correctness results below remain valid; nominal deadline passes do not
admit this candidate for physical performance acceptance.

The [full-map campaign](hybrid/FULL_MAP_QUALIFICATION.md) integrates the requested
T1/T2/T5/T6 layout: all twelve algorithm choices, three modes each, production
selectors/generation resets, exact native clocks and a nonblocking Noise Hat
service on DSP-A. Other sources run on ColdFire. All fourteen stock effects are
restored. Exact Acoustic Hats samples load from the supplied `/PERKYAH.DAT`
companion file outside audio; the card upgrade is 934,480 bytes.

The full layout sweep (243 tuples), additional mode sweep (324 tuples), five
sustained stock/FX rows, lifecycle, scene/fader, cold-reload and packaging gates
pass locally with exact source audio and no deadline misses. The worst observed
ISR is 355.337 µs, leaving 7.475 µs; physical timing and UI acceptance remain open.

The linked [qualification receipt](hybrid/FULL_MAP_QUALIFICATION.json) records
completion, measured timing, source/artifact fingerprints and limitations for
the original local candidate and handoff. The subsequent performance
screen above fails; further performance work is required. It does not
supersede PERKY4S's hardware status, and no existing PK/1 project is silently
migrated to the PK/2 mapping. A fresh SET accompanies the handoff.

## Current release: PERKY4S (Phase 2)

**PERKY4S is the current working DSP-based build**, confirmed by the user on
an Octatrack MKII. This is **not** the earlier four-voice ColdFire prototype,
the Noise/Tone canary, or the three-algorithm DSP test remix.

- **Original hardware checkpoint:** `16a8de19a17ee4cba765cbdb30ca051f85af4e23`
- **Hardware-tested MAIN OS SHA256:** `be74504aadc747817c54dc1226944abfb062244d404408c46d6040744a9ae1d0`
- **Audio tracks:** T1 (DSP core B) and T5 (DSP core A), one PERKY synthesis
  voice per core. T2–T4 and T6–T8 remain normal Octatrack tracks.
- **ALGO 1–4:** Fold Drum 1, Fold Drum 2, Simple Drum, Complex Drum.
- **SRC A–F:** TUNE, DECAY, ALGO, PAR1, PAR2, MODE. All six support
  parameter locks, including per-step ALGO/MODE changes.
- **Integration:** native DSP56300-family source rendering through the
  Octatrack's normal AMP, FX, LFO, scene and sequencing paths.
- **Retained stock effects (12):** Filter, Spatializer, Equalizer, DJ EQ,
  Phaser, Flanger, Chorus, Comb, Delay, Spring Reverb, Dark Reverb and Lo-Fi.
  Plate Reverb and Compressor are not available in this release.

PERKY4S incorporates Complex Drum control corrections verified against the
installed PerkyBits AU 0.2.0 and a guarded shared-DSP-program placement that
resolved the preceding PERKY4R hardware sequencer stall. Its production MAIN
OS is byte-identical to the successful P4RPG6 hardware probe. The user has
also reported PERKY4S working on the MKII. The extent of prolonged physical
stress testing is not established; local emulator/qualification results
should not be mistaken for exhaustive silicon verification.

The 14 October 2026 upstream integration preserves that original checkpoint
in Git history. Its merged source and local qualification are recorded in
[the integration report](UPSTREAM_INTEGRATION_2026-10-14.md). The merged branch
has not been separately tested on an Octatrack or approved for pushing.

### Hybrid diagnostic candidate

The approved private audio-interrupt stack has a scoped local diagnostic
qualification, with derived private and three-small-task stack budgets and exact
new card/MIDI hashes: [private-stack qualification](hybrid/PRIVATE_STACK_QUALIFICATION.md).
The user subsequently tested PKHYB2P on an MKII: T1/T2/T5 playback worked,
while adding T6 caused UI sluggishness. Eight cumulative PRFs confirm the
increased processing load; the latest interval averages 317.35 µs per ISR.
The user reports mostly RES Snare on T2 and RES Bass on T6, including p-locks.
See the [decoded hardware evidence](hybrid/CF_OPTIMIZATION_HARDWARE.json).

The earlier [ColdFire optimization campaign](hybrid/CF_OPTIMIZATION.json) reached a
measured practical plateau, with PKH3O1 preserved as an intermediate build.
The locally qualified **PKH3O3** diagnostic and its exact artifact hashes are
recorded in [the final qualification report](hybrid/CF_OPTIMIZATION_QUALIFICATION.json).
Its firmware inputs are committed at `f87df2de`; two builds reproduce the same
MAIN, runtime ELF and raw runtime. The final card/MIDI wrap uses that tested MAIN.

PKH3O3 reaches 279.98 µs dense, 277.34 µs Snare/Bass and 289.87 µs with enabled
scenes and fader input, versus 324.10, 321.75 and 334.07 µs on the original image.
These are local executed full-ISR comparisons at CPU264/PIT132. All fifteen
60-second workload rows and the continuous ten-minute Snare/Snare row completed
with zero modeled deadline misses. Separate all-eight-track audio captures cover
eight matrix configurations; the 24,000-frame sequencer test also verifies late
MODE/ALGO locks and reversions. Exact PCM/state/RNG, original-author comparisons,
retained FX, lifecycle, saved-project and package checks pass at their stated scopes.

The desired 20% margin is met by the observed local spans; the scene maximum
clears that target by only 0.38 µs. Silicon cache, bus arbitration, startup audio
and UI responsiveness remain unqualified. Six initial DSP readback/mix differences
in the zero-pre-roll port capture remain explicitly recorded; all cold source
records and all initialized post-PLAY records are exact. Use fresh MKII PRFs for
the hardware A/B decision. Nothing was flashed or pushed during that qualification. PERKY4S remains the
hardware-tested release.

### Current hybrid campaign: PKH4O2 (16 October 2026)

The new MKII capture `PKH20000(2).PRF` reports a 300.372 µs mean ISR,
421.030 µs observed maximum and 479 deadline misses. Its source fingerprint
matches the locally preserved build whose 26 manifest sources match `02fa20ff`;
the current baseline rebuild reproduces that MAIN image exactly. The raw new
PRF was not found locally; those decoded hardware facts were supplied by the user.
Its workload is not a matched A/B comparison with the older captures above.

The [new optimization ledger](hybrid/CF_OPTIMIZATION_20261016.json) and
[readable report](hybrid/CF_OPTIMIZATION_20261016.txt) record the actual ColdFire
experiments and their accepted or rejected results. The retained implementation
restores GCC helper inlining across option scopes, uses ordered resonator clamps,
removes the wavetable frequency-cache branch and reuses exact fixed-point decay
steps. A readiness repair also restores decoded PCM after repeated boot
initialization. Original-author, target PCM/state/RNG and initialization checks
pass at their recorded scopes. DSP synthesis, track assignments and the twelve
retained stock effects are unchanged.

All fifteen matched 4,096-frame paired ISR/audio rows pass. Snare/Snare's
executed maximum is 325.386 µs before and 278.015 µs after; the selected
scene/fader test reaches 289.220 µs. All fifteen 60-second rows and the
continuous ten-minute Snare/Snare row also pass, with full CF/DSP activity,
continuing sequencer triggers and no timer-window misses or late DSP words.
The longer runs measure the firmware timer window, excluding entry-save and
footer work. Their largest ACK-to-ACK CPU-work window reaches 360.061 µs,
leaving only 2.751 µs below the frame period; it includes intervening stock
tasks and does not establish 20% whole-CPU headroom. All timing here is an
emulator observation at 264 MHz, with physical cache/bus/IRQ latency unbounded.

The [final local qualification](hybrid/CF_OPTIMIZATION_20261016_QUALIFICATION.json)
binds the exactness, cold boot, lifecycle, DSP/FX, package-corruption and scoped
private-stack gates to the actual PKH4O2 image. Raw cold and primed comparisons
match completely; the six pipeline differences above belong to PKH3O3's
historical capture. The clean rebuild at `bb14be08` reproduces the MAIN and
runtime ELF tested throughout this campaign; its production sources match
`69ecb4dd`. Card and MIDI diagnostic packages pass their local gates.

Verified source and tests are pushed to `perky-cf-dsp-hybrid` with `[skip ci]`.
PKH4O2 completed that local diagnostic qualification; it had not been flashed
at that checkpoint. Subsequent MKII tests below report overload and lockup, so
dual-CF hardware acceptance remains open. PERKY4S remains the hardware-tested
release; the larger unchanged stock-task call graphs remain outside the scoped
private-stack proof.

### Footprint and second-CF-voice campaign (locally qualified; MKII pending)

The user reports that **two DSP voices + one CF voice + five stock FLEX or
STATIC sequences works**, whereas **two DSP voices + two CF voices + three
stock sequences causes sluggish UI and eventual lockup**. This shifts the
investigation toward the incremental second CF voice; it does not establish
STATIC playback, a particular algorithm or cache contention as the root cause.
The newer PKH4O2 PRFs include a roughly 504 µs maximum and 723 deadline misses
in one capture, and a later 9,901-frame interval averaging roughly 331 µs.
These supplied observations and their limits are kept separately in the
[footprint hardware evidence](hybrid/CF_FOOTPRINT_20261016_HARDWARE.json).

The [footprint ledger](hybrid/CF_FOOTPRINT_20261016.json) and
[readable report](hybrid/CF_FOOTPRINT_20261016.txt) distinguish target CPU
cycles, architectural requests and executed code footprint from unmodeled
physical cache/SDRAM/card/DMA costs. All 25 ordered CF pairs have completed
short seven-track STATIC rows, including active stock source audio and actual
card reads. PKH4O2 also passes a 60-second streaming run in the model, which
does **not** reproduce its physical overload. Local passes cannot establish
a reliable silicon voice limit.

Selected second-voice mean IRQ increments range from about 19.79 µs
(Wavetable) to 24.80 µs (Snare), slightly below first-voice increments in
the same matched model. Production function text shrinks 120096 → 108932 bytes;
loaded runtime shrinks by 16384 bytes. Wavetable dense callback cycles rise
slightly, while stack requests and executed code footprint fall. The report
records that tradeoff and further compact-control alternatives.

The clean PKH5D1 diagnostic and PKH5P1 performance builds share firmware source
`2ba5e761`; every runtime byte except the initial profiler-enable word matches.
The 20-job safety/exactness suite and 64 short composed workload rows pass.
The 600-second simulated Snare/Snare plus three-STATIC run also passes.
The [final qualification](hybrid/CF_FOOTPRINT_20261016_QUALIFICATION.json) binds
all receipts to both actual builds and the complete 43-file source fingerprint.
The long ACK-to-ACK work maximum is 362.466 µs, only 0.346 µs below the
frame period; it includes stock tasks and establishes no 20% whole-CPU
headroom or hardware UI acceptance. The campaign retains two
unrestricted CF voices; stock machines/playback and the frozen DSP remain
unchanged. The [25-pair matrix](hybrid/CF_FOOTPRINT_20261016_FEASIBILITY.csv)
requires physical confirmation for every pairing. No new hardware acceptance
or algorithm restriction is asserted. The [MKII A/B procedure](hybrid/CF_FOOTPRINT_20261016_HARDWARE_AB.txt)
isolates T6 admission with T2 and the stock workload held fixed.

### Full PERKONS layout feasibility

The [20 October native-clock placement campaign](hybrid/CF_PLACEMENT_FEASIBILITY.md)
prices the existing CF oscillator fallbacks at 48 kHz with conversion and
combined synthesis. It passes 93,312 target/native frame comparisons, but
WT/WT + Slap + Noise Hat overruns the combined stock-workload ISR at
406.26 us (362.812 us deadline). No existing placement covers the full map.
The subsequent [Noise Hat DSP-A prototype](hybrid/NOISE_HAT_OFFLOAD.md)
fits all three modes and preserves exact voice behavior locally, but its
synchronous host exchange increases the combined ISR peak to 468.875 us.
Its pulse row also fails the stock-track audio gate. This prototype does
not close the full-layout deficit; hardware feasibility remains open. Earlier native
16-sample CF costs do not price the native-rate OT integration tested here.

The subsequent [same-frame cooperative offload](hybrid/NOISE_HAT_ASYNC.md)
overlaps both Noise Hat segments with WT/WT and Slap. All three 4,096-frame
rows pass exactness and all eight audio chains with zero cleanup waits, but
the worst combined ISR rises to 494.034 us. It remains a rejected timing
candidate. The pulse investigation traces dirty-start signal loss to stock
AMP; its initialization cause remains open. Passing the new schedule is not general startup or
hardware qualification.

The [resident-state DMA experiment](hybrid/NOISE_HAT_RESIDENT.md) removes live
Noise Hat history round-trips and the new CF IPL7 reservation. It uses stock
source/readback padding; all three 4,096-frame rows pass audio, source/state
and ownership gates. Peak CF cost remains 380.530 µs against 362.812 µs, and
the source has 48 samples of added delay. The original complete-renderer and
clock witness confirms that delayed stream. This remains a feasibility
prototype; AMP/FX event alignment and the full voice layout are unqualified.

The [current-source tap-DMA prototype](hybrid/NOISE_HAT_TAPS.md) also moves
Noise Hat delay arithmetic and exact resampling onto A, leaving its ring on
CF. It removes the 48-sample added queue and passes 12,320 current-source
frame comparisons with all eight tracks and twelve retained FX active.
Pulse meets the modeled 362.812 µs deadline at 358.504 µs with zero misses;
white and metallic still peak at 370.841/372.485 µs. The full all-mode layout
remains timing-unqualified; this opt-in result is not a hardware release.

The [profiled control-settling follow-up](hybrid/NOISE_HAT_CONTROLS.md) resolves
those remaining modeled deadline misses. It batches redundant Noise Hat
control derivations while preserving exact smoothing and the one-update
attack lag. All three 4,096-frame WT/WT + Slap + Hat rows pass with all eight
tracks and twelve retained FX: peaks **324.841 / 327.299 / 316.902 µs**, with
zero misses and zero full-control/source/state/ring differences. DSP uploads
remain identical to PKNHD1. This was local model admission of that workload;
physical timing and lifecycle qualification were still open at that checkpoint.

The earlier [PKNHE1 lifecycle campaign](hybrid/NOISE_HAT_LIFECYCLE.md) passes three
STOP/START cycles, Part 1→3→1, live Bank A→B→A and all six directed Noise Hat
mode pairs at their continuous-probe scopes. The panel run checks 49,565 exact
source frames and peaks at 327.943 µs with zero misses. Fresh fixed-mode rows
reproduce 324.841 / 327.299 / 316.902 µs with all eight tracks and twelve
retained FX. **That image fails live CF/DSP switching:** three round trips produce
six target transport errors despite a 354.000 µs peak and zero deadline misses.
The audio continuity proof stops at the first backend departure; native CF
arithmetic has a separate stateless proof. Product Part selector/generation
semantics and physical timing remain unqualified in that record.

The [PKNHF7 handoff experiment](hybrid/NOISE_HAT_HANDOFF.md) fixes F6's
backend-switching timing regression: **339.830→331.110 µs**, below F5's
334.356 µs. A guarded typed-int16 CF Hat delay path preserves original PCM,
state, ring and RNG; altered tap metadata uses the original C recurrence.
Slap's assembly kernel is byte-identical to F6. Eighteen live transitions and
both-backend STOP/START, Part and playing Bank changes pass. All three
16,384-frame WT/WT + Slap + Hat rows, with eight tracks and twelve FX, pass at
**320.379 / 324.890 / 312.102 µs**. The worst overall frame is **345.379 µs**,
28 cycles above F6's calibration peak, leaving **17.433 µs** modeled reserve.
There are no deadline misses or transport errors.
One persistent author oracle checks 115,446 Hat source frames and 115,456 Hat
control calls; the actual-call Slap differential checks 2,010,741 native
samples plus full raw state/ring and RNG. The candidate's read-only switching
and calibration profiles reproduce normal frame and cycle totals. The direct
CF gate covers 96,880 cases plus 13,824 renderer frames. DSP uploads remain
identical to PKNHF1. F7 adds 6,056 CF text bytes over F6, no data/BSS growth,
and lowers the private-stack peak to 1,716/4,096 bytes. The author-proven Yves
Rosius PIO fix remains included. All 88 runnable repository gates and 24 local
identity cases pass.
That F7 experiment does not qualify production Part/generation resets; G3
below supplies that local proof for WT/WT + Slap + Hat. Physical timing remains
unqualified; no flash release is produced.

The opt-in [G3 production reset qualification](hybrid/PRODUCTION_LIFECYCLE.md)
passes for WT/WT + Slap + Noise Hat in the local cycle model. Production
Part/Bank events reset resident DSP state, CF ring/control state and the
interruptible shadow coherently; late jobs are checked and retired by
generation. All three 16,384-frame stock/FX rows, both lifecycle runs and
encoder/SAVE PROJECT/cold reload have exact Hat/Slap audio and zero deadline
misses. A separate 18-handoff test with cycling MODE locks also passes.
The worst frame is 349.439 µs against 362.812 µs, leaving 13.372 µs,
versus G2's 4.903 µs (2.7× reserve). Boot-derived sparse restores cut later
reset restoration from about 18,660 to 7,700 cycles; exact packet/clear and
resampling assembly also reduce shared CF overhead. Both DSP uploads and
synthesis remain unchanged from G2. True reset profiles reproduce normal
frame counts and cycle totals exactly. G2's passing baseline, G1's failed
admission and F7's continuing-history evidence remain preserved. Physical timing and V4 alternative Noise Tone source
dispatch remain outside admission; G3 is not a flash release.

### Current DSP memory limit

The opt-in [20 October DSP-B specialization experiment](hybrid/DSP_B_FEASIBILITY.md)
assembles 557 oscillator words into B's candidate private-P tail and verifies
independent paired contexts locally. Its worst pair takes 39,661 modeled
cycles against the unchanged 23,040-cycle source allowance. It releases
program space but does not justify admitting a second production oscillator;
private-tail silicon qualification and the complete production voice map remain open.
The default PERKY4S allocation below is unchanged.

Both cores use **770/774 safe private P-words** (four free per core).
The shared executable tails hold **2,398 code words plus six uploaded NOP
guard words**, consuming **2,404/2,404 shared P-words** (none free).
These are the PERKY4S totals; earlier PERKY3R/PERKY4 memory tables describe
earlier images. Shared P/X/Y aliasing, stock-effect buffers, and the
end-of-window guard must be respected by future DSP work.

### Source, build and qualification

The release is assembled from this repository's sources by
`tools/perky/build_four_machine.py`, not by a generic
`make bus REMIX=perky-probe` or the obsolete `build_machine_canary.py`
release path. The registered `modules/perky/manifest.py` is still a
**diagnostic impulse probe**; the source for the shipping four-algorithm
profile is assembled by the dedicated four-machine builder.

Start with [PERKY4S release and reproducibility](PERKY4S_RELEASE.md),
[the AU authenticity repair](PERKY4R_AU_REPAIR.md), and
[the hardware placement investigation](PERKY4R_RUNTIME_REGRESSION.md).
Packaging requires the user's own original Octatrack OS, qualified
firmware-tool executable, reference assets, local toolchain and project
fixture. These inputs and generated firmware images are deliberately
not committed to this repository.

A local test and packaging procedure is documented in
[PERKY4S_RELEASE.md](PERKY4S_RELEASE.md). The resulting firmware must
match the MAIN OS SHA256 above before claiming byte-identity with the
hardware-tested version. Tests run locally; do not use GitHub CI.

## Future work versus current functionality

Wavetable Drum V1/V2, Resonant, Noise/Tone, Karplus, Slap and Noise Hat
have historical prototypes or qualification research, **but they are not
available as additional ALGO choices in PERKY4S**. The wider target in
[PERKY_MACHINES_TARGET.md](../../PERKY_MACHINES_TARGET.md) calls for four
simultaneous independent tracks with all stock FX preserved; **PERKY4S
is a tested Phase 2 milestone, not completion of that target**.

## Historical experiments (not the current release)

The early source-seam canary used Noise/Tone and a five-control page;
the four-voice ColdFire experiment rendered ten families into source
segments. Those experiments remain in the repository for reproducibility,
but should not be used as descriptions of the working MKII firmware.

- [Early architecture and checkpoints](HANDOFF.md) — historical material,
  including obsolete ColdFire and older hardware-status claims.
- [DSP family execution research](DSP_QUALIFICATION.md) — standalone
  candidates, not a shipping ALGO list.
- [PERKY4 source and MKII handoff](PERKY4_RELEASE.md) — predecessor release.
- [PERKY4 physical memory](PERKY4_MEMORY.md) — predecessor memory ledger;
  use PERKY4S_RELEASE.md for the current 0-free shared-P allocation.
- [P4R/P4S runtime investigation](PERKY4R_RUNTIME_REGRESSION.md) —
  hardware failure, controlled probes, and resolution.

PERKY follows the existing Octabam source-machine seam (also explored by
ANALOG BD); source-render hooks and machine-selection sites may collide
with independently enabled modules. Do not assume the modules can be
combined without a collision audit.

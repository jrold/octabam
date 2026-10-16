# PERKY — PĒRKONS-style source machines

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
PKH4O2 is a locally qualified diagnostic for review, with physical MKII A/B
acceptance pending. No firmware has been flashed and no new physical speedup
or flash-safe certification is established. PERKY4S remains the hardware-tested
release; the larger unchanged stock-task call graphs remain outside the scoped
private-stack proof.

### Current DSP memory limit

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

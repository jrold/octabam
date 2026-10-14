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

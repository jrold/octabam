# PERKY — PĒRKONS-style source machines (work in progress)

This directory is the development home for a native Octatrack source-machine
port of the PerkyBits / PĒRKONS HD-01 engine families.  Acoustic Hats was
removed: it is a PCM sample player whose ~450 KB of hat samples duplicate what
the Octatrack's own sampler already does.

**Status:** the ColdFire four-voice build renders ten engine families
(Fold 1/2, Wavetable, Simple/Complex Drum, Resonant Drums, Slap, Karplus,
Noise Hat, Noise/Tone) directly on the MCF54455 into ordinary stock source
segments, with Tune/Decay/Algo/Prm1/Prm2/Mode p-locked on SRC A–F.  The PCM,
control and state qualification passes bit-exactly against the pinned PerkyBits
native references; hardware qualification is still pending.

The tracked `manifest.py` is an impulse probe. The full audible machine is
composed by `tools/perky/build_machine_canary.py`; use the full builder to test
shipping behavior. See [HANDOFF.md](HANDOFF.md) for verified evidence, local
paths, build steps, known limits, and continuation toward all twelve families.

The first milestone targeted **Noise / Tone** (voice 4, panel algorithm 2).
It established the initial source-machine path:

1. a `PERKY` row in the stock machine chooser;
2. per-track signature and Part persistence without consuming a sample slot;
3. a custom source record delivered to both DSP cores;
4. a DSP56300 Noise / Tone voice that is triggered at the stock event offset;
5. stock AMP, FX1, FX2, LFO, scenes and p-lock plumbing after the synthesized
   source;
6. a local render gate against the PerkyBits native integer reference;
7. measured P/X/Y footprint and cycles before more engines are admitted.

The implementation follows the measured `modules/analog-bassdrum/` source
machine seam rather than creating a second machine framework. Until the common
machine plumbing is generalized, PERKY and ANALOG BD will be mutually
exclusive because they need the same sixth chooser row, FLEX-signature storage
and DSP source seam.

No Elektron firmware bytes, PĒRKONS firmware bytes, samples or extracted table
blobs belong in this repository. Reference fixtures must be generated from the
user's own inputs at development/test time.

See [PORT.md](PORT.md) for the implementation plan and engine map, and
[DSP_QUALIFICATION.md](DSP_QUALIFICATION.md) for current per-family evidence,
cycle limits and production blockers.

Noise Hat's three candidate DSP modes now have original ARM PCM/state execution
gates. See [NOISE_HAT.md](NOISE_HAT.md) for measured resources and the outstanding
classic timing and production-integration gates. Family 010 remains unavailable
in production images.

Phase 2 development candidate: [PERKY4 release and hardware handoff](PERKY4_RELEASE.md),
[exact memory ledger](PERKY4_MEMORY.md), and [Pickup feasibility audit](PICKUP_FEASIBILITY.md).
This four-algorithm profile has its own local release runner; the registered
probe manifest and preserved PERKY3R checkpoint remain unchanged.

Complex authenticity repair: [PERKY4R AU audit and capture procedure](PERKY4R_AU_REPAIR.md).
PERKY4's original renderer comparisons proved arithmetic, while direct installed-AU
qualification exposed its TUNE, modulation-frequency and maximum-DECAY control omissions.

Runtime stability repair: [PERKY4S guarded placement and release procedure](PERKY4S_RELEASE.md).
Its production MAIN OS is identical to P4RPG6, reported working on MKII T1/T5
across all algorithms with Dark Reverb used on both. Full qualification receipts
and physical test scope are recorded separately.

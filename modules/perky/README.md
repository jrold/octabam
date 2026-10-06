# PERKY — PĒRKONS-style source machines (work in progress)

This directory is the development home for a native Octatrack source-machine
port of the twelve PerkyBits / PĒRKONS HD-01 engine families.

**Status:** PERKY2 synthetic Noise/Tone audio works on the user's Octatrack
(user confirmation, 6 Oct 2026). The native renderer, boot, timing and full
sequencer gates pass. Authentic tables/control conversion and the other eleven
families remain to be ported and qualified. Current timing-qualified layout:
one PERKY per DSP core (T1–T4 / T5–T8), FX1/FX2 NONE on all tracks.

The tracked `manifest.py` is an impulse probe. The full audible machine is
composed by `tools/perky/build_machine_canary.py`; use the full builder to test
shipping behavior. See [HANDOFF.md](HANDOFF.md) for verified evidence, local
paths, build steps, known limits, and continuation toward all twelve families.

The first target is **Noise / Tone** (voice 4, panel algorithm 1). The goal of
milestone 1 is not to land all twelve engines at once; it is to prove one
complete source-machine path:

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

See [PORT.md](PORT.md) for the implementation plan and engine map.

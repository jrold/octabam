# PERKY — PĒRKONS-style source machines (work in progress)

This directory is the development home for a native Octatrack source-machine
port of the twelve PerkyBits / PĒRKONS HD-01 engine families.

**Status:** scaffolding only. This directory intentionally has no
`manifest.py` yet, so the registry does not expose an incomplete machine and
existing remixes remain unchanged.

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

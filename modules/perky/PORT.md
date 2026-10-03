# PERKY port architecture

## Reference/oracle

The sound oracle is the native integer implementation in the private PerkyBits
repository. The Octatrack implementation is a translation to DSP56300 fixed
point, not a copy of ARM machine code.

The first engine uses these PerkyBits reference paths:

- `Source/EngineCatalog.h` — engine family / mode catalog.
- `Source/NativeV121NoiseToneShared.cpp` — shared Noise / Tone renderer used by
  voice 4 modes 1 and 3 and the voice 3 resonant noise/tone path.
- `Source/NativeV121NoiseTone.cpp` — the separately validated waveform-2 path.
- `Source/PerkonsVoices.cpp` — firmware state selection, trigger/update behavior,
  wavetable requirements and global PRNG ownership.

A future render gate must compare deterministic fixtures produced by that
native reference with the DSP56300 port. Do not check in firmware-owned tables;
generate or supply fixtures outside the repository.

## Engine catalog

| # | PERKY family | Modes |
|---|---|---|
| 1 | Fold Drum 1 | no transient / noise transient / pulse transient |
| 2 | Wavetable Drum V1 | wavetable 1 / 2 / 3 |
| 3 | Simple Drum | waveform 1 / 2 / 3 |
| 4 | Fold Drum 2 | no transient / noise transient / pulse transient |
| 5 | Wavetable Drum V2 | wavetable 1 / 2 / 3 |
| 6 | Complex Drum | waveform 1 / 2 / 3 |
| 7 | Resonant Drums | bassdrum / snare / noise-tone |
| 8 | Slap | retrigger 1 / 2 / 3 |
| 9 | Karplus | transient 1 / 2 / 3 |
| 10 | Noise Hat | white / metallic / pulse-stack |
| 11 | Noise / Tone | waveform 1 / 2 / 3 |
| 12 | Acoustic Hats | closed / open / ride |

The intended final UI is twelve machine-family entries with a three-position
MODE parameter inside each family, rather than thirty-six top-level machine
entries. Milestone 1 may expose only Noise / Tone while the memory and cycle
budget is proven.

## Octatrack source seam

`ANALOG BD` already proves the complete source-machine route:

- ColdFire keeps the underlying stock track type as FLEX and marks a custom
  machine using otherwise-unused per-track Part bytes.
- The chooser presents a virtual sixth machine row.
- The stock FLEX renderer is intercepted only for a signed custom track and
  emits a small control record rather than sample audio.
- Both DSP payloads hook the stock source seam before AMP/FX.
- The custom DSP recognizes that record, synthesizes the source into the stock
  track buffer and jumps to the normal continuation.
- Stock AMP, FX1, FX2 and output packing then run unchanged.

PERKY should reuse that architecture. The first implementation should be a
small rename/generalization of the measured Analog BD plumbing, not an
independent set of guessed hook sites.

## Signatures and compatibility

PERKY must use its own Part signature and DSP-record magic; it must never treat
an Analog BD Part as PERKY or vice versa. Exact bytes are intentionally left
open until the ColdFire implementation is added so the verifier can own them in
one place.

Until the common source-machine infrastructure can register multiple virtual
rows safely, the active PERKY manifest will declare a conflict with key
`ANALOG BD` because both implementations currently need the same chooser row,
control hooks and DSP source seam.

## Milestone 1: Noise / Tone

### Control path

The first page layout is deliberately not frozen yet. The port must first
extract the PerkyBits control/update mapping for Noise / Tone so that Octatrack
knob bytes feed the same internal quantities as the native reference. Do not
invent a superficially similar parameter curve.

At minimum the family needs:

- pitch / note;
- decay/envelope timing;
- MODE (three waveform variants);
- envelope amount;
- noise/tone mix;
- velocity/accent behavior;
- trigger/retrigger state.

Remaining Octatrack source slots can stay blank until their original mapping is
proven.

### DSP state

The validated shared Noise / Tone renderer contains these major blocks:

1. amplitude envelope;
2. firmware-compatible PRNG / sample-and-hold noise source;
3. two passes through the resonant noise filter state;
4. two interpolated tonal oscillators;
5. noise/tone cross-mix;
6. envelope and velocity scaling;
7. signed saturation to the source sample.

The specialized waveform-2 path has a different oscillator/table geometry and
must remain a separate verified mode until equivalence can be proven.

### Arithmetic policy

The DSP56300 port must preserve the integer reference's wrap, signed shift,
clamp and interpolation behavior deliberately. Octabam's assembler has known
operand-order traps around multiply instructions, so every new multiply form
must be disassembled and at least one hand-computable signed arithmetic gate
must exercise positive and negative inputs.

Approximate floating-point rewrites are not acceptable as the first port. If a
Q-format differs from the ARM reference, the translation must document the
scale at each state boundary and prove the resulting PCM error.

## Memory plan

Do **not** assume all twelve engines fit in Analog BD's current harvested P
region. Analog BD uses one harvested SPRING REV region for glue + two engines
and private X for tables/voice state. PERKY will first measure:

- P words for glue + Noise / Tone;
- private X/Y words per track and for shared tables;
- worst-case cycles per sample/frame;
- table footprint and which data can be generated rather than stored.

Only after that measurement should the final multi-engine placement be chosen.
Possible later strategies include multiple harvested stock regions, loadable
engine overlays, or executable shared-window placement if its timing is
acceptable. None is assumed yet.

## Development gates

Before hardware, milestone 1 needs all of the following:

1. registry/build gate for the active module;
2. ColdFire port gate proving chooser, Part persistence and validator behavior;
3. record-layout gate proving trig offset and twelve control bytes arrive on
   both DSP payloads;
4. DSP arithmetic unit vectors for envelope, RNG, interpolation and saturation;
5. deterministic PCM comparison against PerkyBits reference fixtures;
6. cycle/footprint report;
7. stock-path regression proving unsigned FLEX/STATIC/etc. remain untouched.

`make check REMIX=<perky-test-remix>` is the minimum claim once the manifest is
activated. Hardware status must remain unclaimed until an Octatrack has actually
run the image.

## Immediate implementation order

1. Extract Noise / Tone parameter-to-state mapping from PerkyBits.
2. Add a host-side integer reference/golden-vector generator with no firmware
   blobs in the tree.
3. Split/generalize the reusable Analog BD ColdFire machine plumbing enough to
   register PERKY cleanly.
4. Add the PERKY control-record signature and one-engine browser.
5. Port Noise / Tone DSP to DSP56300 and run arithmetic/PCM gates.
6. Measure memory/cycles.
7. Activate `modules/perky/manifest.py` and a dedicated test remix only when
   the above path builds and boots under the port.

# PERKY engine qualification matrix

This is the continuation checklist for taking the working PERKY2 Noise/Tone
milestone to all twelve PerkyBits engine families. A family is not considered
ported merely because a renderer has been translated: panel MODE order,
trigger/retrigger behavior, velocity, live-control updates, renderer state,
tables/assets, DSP resources, runtime and physical Octatrack behavior all need
an explicit gate.

Reference revision used for this audit:
`jrold/perkybits@605cfd05d9dcdc0d0caa955297556a26ea257f82`.

## Mode mapping

`MODE` below is physical panel M1/M2/M3 -> raw firmware mode. Do not substitute
0/1/2 panel order directly.

| Family | Slot / panel algorithm | MODE -> firmware | Native reference | Reference state / major assets | Octabam qualification |
|---|---:|---:|---|---|---|
| Fold Drum 1 | V1 / A1 | `1,2,0` | `NativeV121FoldDrums::renderFold1` | `0x0f4`; pitch + 2 envelopes + 2x256 waves + RNG | Audit only |
| Wavetable Drum V1 | V1 / A2 | `1,0,2` | `NativeV121WavetableDrum` | `0x150`; pitch + 2 envelopes + up to 4x2048 waves | Audit only |
| Simple Drum | V1 / A3 | `1,0,2` | `NativeV121SimpleDrum` | `0x120`; pitch + 2 envelopes + 2x256 waves | **34-word live compact parity gate; DSP/control integration pending** |
| Fold Drum 2 | V2 / A1 | `1,2,0` | `NativeV121FoldDrums::renderFold2` | `0x134`; pitch + 2 envelopes + up to 4x256 waves + RNG | Audit only |
| Wavetable Drum V2 | V2 / A2 | `1,0,2` | `NativeV121WavetableDrum` | `0x150`; pitch + 2 envelopes + up to 4x2048 waves | Audit only |
| Complex Drum | V2 / A3 | `1,0,2` | `NativeV121ComplexDrum` | `0x140`; pitch + 2 envelopes + up to 4x256 waves | Audit only |
| Resonant Drums | V3 / A1 | `1,0,2` | `NativeV121ResonantBass` / `NativeV121ResonantSnare` mode paths | `0x178` / `0x1d4`; 2 envelopes + 257-entry interpolation tables + RNG | Audit only |
| Slap | V3 / A2 | `1,0,2` | `NativeV121Slap` | `0x2670`; 2 envelopes + large delay/state + RNG | Audit only; large-state family |
| Karplus | V3 / A3 | `1,0,2` | `NativeV121Karplus` | `0x10e0`; 2 envelopes + large delay/state + RNG | Audit only; large-state family |
| Noise Hat | V4 / A1 | `1,0,2` | `NativeV121NoiseHatClassic` / `NativeV121NoiseHatPulseStack` + wrapper modes | classic `0x2dd8`, pulse `0x160`; envelopes, filters/delays/pulse stack | Audit only; split renderer/wrapper family |
| Noise / Tone | V4 / A2 | `1,0,2` | `NativeV121NoiseTone*` | `0x120`; pitch/envelopes/waves/filter/noise + RNG | **PERKY2 physical audio works; synthetic controls/tables remain** |
| Acoustic Hats | V4 / A3 | `1,0,2` | `NativeV121AcousticHats` | `0x10c`; 2 envelopes + sample asset up to `0x40000` bytes | Audit only; external sample-data family |

## Shared-port clusters

### Cluster A — common pitch/envelope/oscillator family

Port first: **Simple Drum -> Fold Drum 1/2 -> Complex Drum -> Wavetable V1/V2**.
These families reuse the v1.2.1 pitch table at `0x080202a0`, envelope tables at
`0x08022ea0` / `0x080236a2`, and oscillator/wave-table style renderers. The
Simple Drum work is therefore the primitive qualification path for six browser
families, not a one-off engine.

Simple Drum currently proves:

- direct ARM-shaped renderer translation;
- 34 live DSP words preserve every renderer-owned field;
- PCM and renderer-owned final state match across 240 randomized renders;
- all valid 16-bit prepared-pitch inputs are exercised, including the extended
  pitch-table branch;
- a prepared base-frequency value is exact across a render block, so the
  4096-entry pitch table does not need to live in the per-sample DSP path.

Shipping resource target for Simple Drum is **34 live words + 2 derived base
frequency words** before optional table-decode cache. The existing one-voice /
DSP-core admission guard remains in force.

### Cluster B — resonant family

Port after Cluster A. The resonant native paths replace wave assets with two
257-entry interpolation tables and use RNG. Their state sizes are still modest
enough to compact before touching the large delay families.

### Cluster C — delay/buffer-heavy synthesis

**Slap, Karplus, classic Noise Hat** need explicit ring-buffer placement or
state compression; copying their ARM object sizes into Octatrack X/Y memory is
not viable. Noise Hat's pulse-stack path is much smaller but the family also
contains wrapper/mix behavior, so qualifying only that limb would not qualify
all three panel modes.

### Cluster D — sample playback

**Acoustic Hats** has small live state but references a large external sample
asset. It needs a separate asset-storage/streaming decision rather than a normal
wave-table packing pass.

## Per-family gates

Every family must clear these rows before it can be called hardware-qualified.

| Gate | Required evidence |
|---|---|
| Catalog | family, slot, panel algorithm, `panelModeToFirmware` captured from `EngineCatalog.h` |
| Render target | v1.2.1 object offset/function and any wrapper-only mode behavior identified |
| Controls | authentic `update()`/smoothing law for TUNE, DECAY, ENV, MIX and MODE; no synthetic substitutions |
| Trigger | trigger, retrigger and release behavior; v1.2.1 update-after-trigger included |
| Velocity/note | velocity and chromatic-note effects preserved where renderer/update path uses them |
| State | compact renderer-owned state round-trips to the ARM-shaped reference |
| RNG | exact shared/local RNG parity where used |
| Tables/assets | provenance, identity/address switching, packing/decoding and hashes qualified |
| PCM | generated DSP shipping candidate matches independent native oracle across modes/corners |
| P/X/Y | measured program/data footprint fits without colliding with stock or PERKY private ranges |
| Runtime | worst 16-sample block measured against the 72,512-cycle/core deadline with stock reserve |
| Full image | boot/upload/readback, source seam, sequencer trigs, AMP/FX continuation and rejection behavior pass |
| Hardware | physical Octatrack audio, mode changes, controls, retriggers and stress behavior reported |

## Current next milestone

Finish **Simple Drum** before emitting another hardware image:

1. capture authentic prepared state for panel M1/M2/M3 and control corners from
   the PerkyBits v1.2.1 runtime;
2. identify/hash its two required wave assets and common envelope/pitch data;
3. add DSP56300 executable gates for the 34-word state, prepared pitch,
   oscillator and two-envelope render path;
4. integrate it behind engine browser family 003 while preserving PERKY2
   Noise/Tone as a regression fixture;
5. run full timing/boot/sequencer gates and only then produce a new build number.

# PERKY Noise/Tone memory plan

The shared Noise/Tone renderer's first hard constraint is DSP data memory. This
note pins the current measured budget and separates three different things that
must not be conflated:

1. the 0x120-byte ARM-shaped qualification object;
2. the compact live DSP renderer state;
3. static wave/envelope tables and their realtime decode cache.

## Measured private budget

Octabam's current memory census leaves about **616 X words** and **2,155 Y
words** of genuinely usable private data memory per DSP core. Do not infer a
larger free range merely because the boot payload has no static record there;
runtime FX allocations and host behaviour are part of the usable-memory
boundary.

The relevant executable gates are:

- `tools/verify/verify_perky_runtime_memory.py` — renderer/cache allocation;
- `tools/perky/analyze_noise_tone_tables.py` — exact table fit for extracted data;
- `tools/verify/verify_perky_packed_tables.py` — packed-table runtime ABI;
- `tools/verify/verify_perky_envelope_cache.py` — exact cached envelope access.

## Live state + envelope cache: 236 X words/core

The validated ARM object is 0x120 bytes, but most of those bytes are irrelevant
to `NativeV121NoiseToneShared::renderBlock()`. `noise_tone_compact.py` keeps
only the fields the renderer actually touches, with each u32 represented as two
16-bit limbs:

| field group | words / voice |
| --- | ---: |
| velocity | 1 |
| envelope state | 11 |
| noise sample/hold | 3 |
| resonant filter | 8 |
| two oscillators | 16 |
| noise/tone mix | 2 |
| **compact state / voice** | **41** |

A raw block-delta envelope lookup can require up to 15 additions. The shipping
runtime therefore reserves a **17-word derived cache per voice**:

- one cached envelope block id;
- sixteen fully decoded u16 envelope values.

A same-block lookup is then O(1). Crossing a 16-sample table block decodes its
anchor + fifteen deltas once and reuses those values until the envelope enters a
different block. The cache is not PĒRKONS state and never needs to round-trip to
the ARM-shaped oracle.

Per core:

```text
4 voices × (41 state + 17 cache) + 4 shared RNG limbs
= 236 X words
```

Against the measured ~616-word private-X headroom that leaves about **380 X
words** for source-record staging, decoder scratch and later control-converter
state.

This is intentionally a direct-word live layout. The hot renderer gets cheap
field access; compression effort is spent on static tables.

## Waves: 683 Y words for four exact tables

Noise/Tone uses four 256-sample signed-16 wave references. Storing each sample
as one DSP word costs 1,024 Y words. `noise_tone_tables.py` concatenates all
four waves and packs the resulting 1,024 u16 values LSB-first into 24-bit DSP
words: **three 16-bit samples in two DSP words**.

That costs exactly **683 Y words**. `noise_tone_wave_unpack.asm` is the first
DSP implementation of this format, and `verify_perky_wave_unpack_exec.py`
walks all 1,024 synthetic samples through it.

Oscillator lookup remains O(1); there is no delta chain in the waveform hot
path.

## Envelope curves: exact 16-sample block delta

The two curves are each 2,048 unsigned-16 values. Raw u16 packing would cost
1,366 Y words per curve and cannot coexist with the waves.

The exact candidate format is:

1. split a curve into 16-sample blocks;
2. store the first value as a 16-bit absolute anchor;
3. store the next fifteen values as fixed-width signed first differences;
4. choose one delta width per curve.

The original random-access policy capped a lookup at 15 additions. The new
17-word cache makes the runtime better than that: those additions occur only
when the requested envelope index crosses into a different 16-sample block;
subsequent lookups from the same block are direct cached reads.

The synthetic development curves both happen to use 7-bit deltas:

```text
wave stream                       683 Y words
synthetic envelope 1              646 Y words
synthetic envelope 2              646 Y words
                                  ----
synthetic exact table total      1,975 Y words
measured private-Y budget        2,155 Y words
synthetic margin                   180 Y words
```

Those numbers are a **development stress fixture**, not a claim about the real
PĒRKONS curves. Real v1.2.1 table bytes are still required to determine their
actual delta widths and exact Y footprint.

For reference, with 16-sample blocks an 8-bit-delta curve costs 726 words. Two
8-bit curves plus the 683-word wave stream consume 2,135 Y words, leaving only
20 words. The real curves therefore still need to pass the table analyzer
before the packed format is admitted to a hardware image.

## Required real-data check

Once a prepared v1.2.1 Noise/Tone state and update image are available:

```bash
python3 tools/perky/extract_noise_tone_tables.py \
  /path/to/perkons_v1.2.1.img \
  --state /path/to/noise-tone-state.bin \
  --out out/perky/noise-tone-tables

python3 tools/perky/analyze_noise_tone_tables.py \
  out/perky/noise-tone-tables \
  --json out/perky/noise-tone-memory.json
```

The second command must report that the exact tables fit the measured private
X/Y budget under the realtime policy before the real table payload is wired
into the image.

## Current unresolved items

- Actual delta widths of the two v1.2.1 envelope curves. The private PerkyBits
  `octabam-control-probe` branch contains the probe/runtime code but **does not
  contain the firmware image or extracted table blobs**.
- Executed cycle/instruction cost of the composed complete voice and packed
  accessors on the Octabam DSP emulator/toolchain. The gates are committed but
  this ChatGPT container does not currently contain Octabam's built
  `dsp_asm`/`dsp56kEmu` artifacts.
- Translation of the original ARM `update()` control converter. Synthetic
  control captures exercise plumbing only; they are explicitly not treated as
  PĒRKONS knob laws.
- Final integration of the optimized renderer behind the live `PK/Y1` source
  record. The active `perky-probe` remix remains the impulse canary until these
  qualification steps are satisfied.

# PERKY Noise/Tone memory plan

The shared Noise/Tone renderer is no longer arithmetic-bound on paper; its
first hard constraint is DSP data memory.  This note pins the current measured
budget and refuses to confuse the 0x120-byte ARM oracle object with the state we
actually need to keep on the Octatrack.

## Measured private budget

Octabam's current memory census leaves about **616 X words** and **2,155 Y
words** of genuinely usable private data memory per DSP core.  Do not infer a
larger free Y range just because the boot payload has no static record there;
runtime FX allocations and host behaviour are part of the usable-memory
boundary.

`tools/perky/analyze_noise_tone_tables.py` is the executable source of truth for
all numbers below.  `tools/verify/verify_perky_memory_plan.py` round-trips its
packing formats and tests both fitting and non-fitting synthetic table sets.

## Live renderer state: 168 X words/core

The validated ARM object is 0x120 bytes, but most of those bytes are irrelevant
to `NativeV121NoiseToneShared::renderBlock()`.  A DSP-native state can keep only
the fields the renderer actually touches, with every u32 represented as two
16-bit limbs:

| field group | words / voice |
| --- | ---: |
| velocity | 1 |
| envelope state | 11 |
| noise sample/hold | 3 |
| resonant filter | 8 |
| two oscillators | 16 |
| noise/tone mix | 2 |
| **total / voice** | **41** |

Four tracks on one DSP core therefore need 164 X words.  The firmware-style
shared PRNG needs four more limbs, for **168 X words total**, leaving about 448
of the measured 616 X words for transport scratch and any state we discover
while integrating the control converter.

This is intentionally a direct-word layout rather than bit-packed state.  The
hot renderer gets cheap field access; compression effort is spent on static
tables instead.

## Waves: 683 Y words for four exact tables

Noise/Tone uses four 256-sample signed-16 wave references.  Storing each sample
as one DSP word would cost 1,024 Y words.  Treating all four tables as one
contiguous 16-bit stream packs 1,024 samples into **683 24-bit words** exactly.
The codec is equivalent to three 16-bit samples in two DSP words; no waveform
approximation is involved.

The final DSP accessor still needs a cycle measurement because one logical
sample can straddle two physical words.  The memory planner assumes this exact
packing, not delta compression, because oscillator lookup is random and occurs
in the per-sample hot path.

## Envelope curves: realtime block-delta policy

The two firmware curves are each 2,048 unsigned-16 values.  Raw 16-bit packing
would cost 1,366 Y words per curve and cannot fit with the waves.

The exact candidate is a random-access block-delta representation:

1. every block begins with a 16-bit absolute anchor;
2. the remaining values in the block are fixed-width signed first differences;
3. lookup starts at the block anchor and accumulates only the deltas inside
   that block.

The fit calculation **does not** accept arbitrarily large blocks just because
they compress better.  The current realtime policy is at most **15 delta adds
per lookup**, i.e. a maximum block size of 16.  More aggressive exact encodings
are reported by the analyzer but do not make the shipping-fit result pass.

With a 16-sample block:

- 8-bit deltas cost 726 words per curve;
- two such curves cost 1,452 words;
- 1,452 curve words + 683 wave words = **2,135 Y words**;
- measured Y budget is 2,155 words, leaving **20 words**.

So two 8-bit-delta curves fit, narrowly.  A 7-bit curve can offset a 9-bit
curve; in general the real extracted curves must be measured before claiming a
fit.  No table bytes are currently checked into this repository, and no
approximate curve is accepted as a substitute.

## Required real-data check

After the user extracts a prepared Noise/Tone state and tables:

```bash
python3 tools/perky/extract_noise_tone_tables.py \
  /path/to/perkons_v1.2.1.img \
  --state /path/to/noise-tone-state.bin \
  --out out/perky/noise-tone-tables

python3 tools/perky/analyze_noise_tone_tables.py \
  out/perky/noise-tone-tables \
  --json out/perky/noise-tone-memory.json
```

The second command must end with:

```text
RESULT: FITS measured private X/Y budget under realtime decode policy
```

before the compressed table format is wired into the hardware image.

## Still unresolved

- Actual delta widths of the two v1.2.1 envelope curves: firmware/table bytes
  are not present in this branch.
- Cycle cost of packed-wave access and block-delta envelope lookup on the
  DSP56300.
- Additional state, if any, required by the still-unported ARM `update()`
  control converter.  The per-sample renderer itself is covered by the 41-word
  live-state census above.

Until those are measured, the active `perky-probe` remix stays the impulse
canary; it does not advertise a completed Noise/Tone voice.

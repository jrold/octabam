# Current PERKY4 memory checkpoint

Locally linked and boot-readback verified: 2,680 P words of 2,724; 359 private X words of 616; 1,946 private Y words of 2,139. See [HANDOFF.md](HANDOFF.md) for actual ranges, provenance and qualification limits. Simple Drum uses a shared 17-word control-rate pitch cache, three direct packed waves and direct amplitude-envelope samples. Noise/Tone retains its reachable shape-1 analytic lookup and original synthetic waves. Fold Drum 1 is locally integrated. The user authorized fewer stock effects to fit all twelve voices. Large delay/sample families still need explicit stock-memory claims and executed resource gates.

## All-family memory work — approved, not yet shipped

The user selected all twelve voices with fewer stock effects. Candidate reclaimed local Y arena is `$1000..$BFFF` (45,056 words/core). The 64K shared window is aliased P/X/Y across cores; assets and code must not independently claim it. Full Wavetable SURF requires 48 tables plus the initial waveform (49 × 2,048 signed16 samples). Acoustic closed/open/ride captures contain 10,101 / 86,400 / 129,553 signed16 samples. Lossless first-difference64 blocks measure 94,089 total words for the hats, including descriptors and guards. No realtime DSP decode gate or actual allocation is implied by these storage figures.

Preserve shared bootstrap/upload staging: `$30000..$300AA`, `$31000..$31031`, `$32000..$32039`, `$38000..$38012`, and mailbox `$37F00..$37F0F`. The low 72 staging words remain live after boot. Stock core init clears local Y `$3F00..$BFFF` and shared `$30000..$3FFFF`; boot-loaded assets there will be destroyed unless initialization is changed or loading occurs afterward. Stock effects on every track must be prevented from reusing reclaimed arenas, including FX1/FX2 shared dispatch IDs. A proposed fit is not a final memory-map check.

Wavetable candidate currently uses a logical large Y bank solely for exact renderer execution. That address range is not mapped on physical Octatrack hardware. Its storage decoder, control transport, dispatch integration and complete shipping build remain pending.

The material below records earlier plans and constraints. “Current unresolved” entries there are historical and superseded by this checkpoint.

# PERKY Noise/Tone memory plan

The shared Noise/Tone renderer's first hard constraint is DSP data memory. This
note pins the current measured budget and separates three different things that
must not be conflated:

1. the 0x120-byte ARM-shaped qualification object;
2. the compact live DSP renderer state;
3. static wave/envelope tables and their realtime decode cache.

## Measured private budget

The hardware sweep bounds private Y below the FX1 arena. Stock upload records
end at `$0794` on A and `$07a4` on B (see `docs/firmware/DSP.md` section 5).
Use the intersection free on both cores:

```text
Y:$0200..$07a4   stock/static data ends here
Y:$07a5..$0fff   measured private gap: 2,139 words
Y:$1000..        FX1 instance arena begins here
```

PERKY therefore treats **Y:$07a5..$0FFF** as the only candidate table region;
it does not infer a larger hole from the boot payload's static records. Runtime
FX allocations and host behaviour are part of the usable-memory boundary.

The measured private-X headroom is about **616 words** per core. The relevant
gates are:

- `tools/verify/verify_perky_runtime_memory.py` — renderer/cache allocation;
- `tools/perky/analyze_noise_tone_tables.py` — exact table fit for extracted data;
- `tools/verify/verify_perky_packed_tables.py` — packed-table runtime ABI;
- `tools/verify/verify_perky_envelope_cache.py` — exact cached envelope access;
- `tools/verify/verify_perky_image_tables.py` — private-Y upload boundaries;
- `tools/verify/verify_perky_preboot_reserve.py` — ColdFire preboot scratch reserve.

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
measured private-Y budget        2,139 Y words
synthetic margin                   164 Y words
```

Placed at the measured base, that synthetic payload occupies exactly:

```text
Y:$07a5..$0f5b   1,975 packed table words
Y:$0f5c..$0fff     164 words left untouched
```

`tools/build/perky_image.py` appends that Y record to both finalized DSP
uploads only after checking that no existing Y record overlaps it.

Those numbers are a **development stress fixture**, not a claim about the real
PĒRKONS curves. Real v1.2.1 table bytes are still required to determine their
actual delta widths and exact Y footprint.

For reference, with 16-sample blocks an 8-bit-delta curve costs 726 words. Two
8-bit curves plus the 683-word wave stream consume 2,135 Y words, leaving only
4 words. The real curves therefore still need to pass the table analyzer
before the packed format is admitted to a hardware image.

## ColdFire preboot scratch: 242 audio pages

The extended DSP uploads cannot overwrite their stock image slots, so the
standard Octabam loader depacks each replacement upload to reserved SDRAM
before the stock DSP boot routine reads it. PERKY uses the same four 256 KiB
windows as the measured Analog-BD preboot path:

```text
cached destination A   0x40b00000..0x40b3ffff
cached destination B   0x40b40000..0x40b7ffff
cached stage A         0x40b80000..0x40bbffff
cached stage B         0x40bc0000..0x40bfffff
```

Stock's audio arena begins at `0x40a955e0`. **242 × 6144-byte pages** is the
smallest integral bottom reservation that contains all four windows:

```text
PERKY arena reserve    0x40a955e0..0x40c005df
size                   1,486,848 bytes = 1.418 MiB
```

241 pages do not contain the final stage slot. The module therefore declares
`ArenaReserve(pages=242, where="bottom")`; this is intentionally far smaller
than Octabam's 1,707-page platform-runtime reserve. `platform_build.py` now
supports a separate `preboot_reserve`, so the same single loader can carry
PERKY's DSP uploads either by themselves or alongside an unrelated DRAM runtime
without making the two regions overlap.

`tools/build/build_perky_tables.py` is the current isolated development build:
it verifies the normal `perky-probe` image already contains those arena-geometry
pokes, adds the two extended DSP uploads, installs the standard loader, and
writes `out/mainos_perky_tables.bin`. It does **not** change the active source
renderer from the impulse canary.

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

python3 tools/perky/build_noise_tone_payload.py \
  out/perky/noise-tone-tables \
  --out out/perky/noise-tone-packed
```

The analyzer must report that the exact tables fit Y:$07a5..$0FFF under the
realtime decode policy before the real table payload is admitted to a hardware
image.

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

## PERKY2 realtime admission

The synthetic native renderer reserves two words at X:$38EC..$38ED for the
event offset and a per-block admission latch. Combined with 236 live-state
words and 100 scratch words, total private X use is 338 of 616 words.
Only one PERKY voice per core is admitted each block. The synthetic linear
curve uses an exact analytic lookup; the second curve retains the packed cache.

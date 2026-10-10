# `wave` — WAVE

A 4-voice wavetable synth on FX2, on the DSP: a port of CHOMPI WAVE's voice
(wavetable oscillator, DJ filter, filter and pitch LFOs). It is played by
the track it sits on: the track plays a sine (the carrier), WAVE measures
the carrier's pitch and level, and its four voices follow them. So PTCH,
the CHROMATIC keys, [SCALE QUANTIZER](../quantizer/README.md), p-locks,
LFOs on PTCH and the AMP envelope all play it.

**An experiment**, built for fun as the DSP route after
[WAVE LOAD](../waveload/README.md) measured one 4-voice track as the
ColdFire's limit, and meant to be extended: the Open section lists where.

The voice is ported from
[CHOMPI-Club/CHOMPI](https://github.com/CHOMPI-Club/CHOMPI)'s WAVE firmware
(`a73d732`), MIT, Copyright (c) 2026 CHOMPI Club; the full notice is in
[LICENSE-CHOMPI](LICENSE-CHOMPI). Not affiliated with or endorsed by CHOMPI Club or Chase Bliss, and not an official CHOMPI Club release; CHOMPI is CHOMPI Club's trademark (their `TRADEMARKS.md`), used here only to say where the code comes from.

## Playing it

1. `python3 modules/wave/carrier.py WAVCAR.wav` writes the carrier: a C5
   sine, 2,093 whole cycles in 4 s, so it loops without a seam. Put it in
   the set's audio pool.
2. A FLEX track: WAVCAR.wav, loop on. FX2 = **Wave Synth**. The track's own
   audio is replaced by the synth.
3. Trigs, PTCH, the CHROMATIC keys: the voices play the carrier's note,
   OCT octaves down (default −2: PTCH 0 = C3). The AMP envelope is the
   synth's envelope.

The first 64 blocks (23 ms) after the effect starts are silent while it
writes its tables.

## Knobs

| page | slot | name | range | what it does |
|---|---|---|---|---|
| 1 | 0 | FRAM | 0–127, default 0 | table position: sine, triangle, saw, square, pulses 1/4 to 1/32; morphs between neighbours |
| 1 | 1 | CUT | 0–127, default 80 | the DJ filter: low-pass below the middle, high-pass above |
| 1 | 2 | RES | 0–127, default 40 | resonance |
| 1 | 3 | CHRD | UNI OCT 5TH MAJ MIN MAJ7 MIN7 SUS4 | the four voices' intervals over the note |
| 1 | 4 | OCT | −4 … 0, default −2 | octaves below the carrier |
| 1 | 5 | LEVL | 0–127, default 64 | output level |
| 2 | 6 | FDEP | 0–127, default 0 | filter LFO depth |
| 2 | 7 | FRAT | 16 steps, 0.14–65 Hz, default 5.6 Hz | filter LFO rate (the original's rate law) |
| 2 | 8 | VDEP | 0–127, default 0 | vibrato depth, up to ±2 semitones |
| 2 | 9 | VRAT | 16 steps, 0.14–65 Hz, default 5.6 Hz | vibrato rate |
| 2 | 10 | DETN | 0–127, default 0 | spreads the four voices, up to ±60 cents on the outer two |

## What it costs

- **DSP code:** 1,269 words. In remix [`wave`](../../remixes/wave/README.md)
  it lives in DARK REV's and SPRING REV's harvested words (768 left), so
  both reverbs are off the chooser there.
- **DSP memory:** one 16,384-word FX2 buffer per instance from the
  allocator, as a stock reverb or delay instance takes.
- **DSP time:** 576 instructions a sample per instance (peak 9,213 a
  16-sample block, `verify_wave`); four on one core 2,301 a sample. A core
  has about 3,120 cycles a sample usable and stock's own work is about
  1,410 (`docs/firmware/CHIP.md`), so two or three WAVE tracks a core fit
  beside light FX; four do not. `cycle_count` prices one instance at
  1,082 cycles a sample, a ceiling that charges a pitch measurement (two
  23-step normalisations) on every sample where the carrier crosses zero
  once a period. Instructions are not cycles; not measured on the unit.
- **The carrier track:** its audio is the synth's input and is replaced.

## How it differs from CHOMPI WAVE

- The tables are generated (eight 2,048-sample frames), not Serum files;
  FRAM morphs continuously between neighbours where CHOMPI steps a
  33-frame table with a 960-sample crossfade.
- One envelope for the four voices (the carrier's level, through two
  2.9 ms one-poles) where CHOMPI has an ADSR per voice; the chord is fixed
  intervals, not voices allocated per key.
- 24-bit fixed point at 44.1 kHz; the filter runs at 1/16 internal scale
  with the feedback product kept in the 56-bit accumulator. CHOMPI's
  delay, reverb, compressor and sequencer are not part of it.
- The chord shapes are fixed intervals: SCALE QUANTIZER snaps the played
  note, not the chord's other voices.

## Measured

`python3 tools/verify/verify_wave.py wave` (dsp_host, both payloads, 3 Oct
2026):

| gate | result |
|---|---|
| carrier 261.6 / 523.3 / 1046.5 Hz → OCT −2 | 65.416 / 130.824 / 261.634 Hz (+0.25 / +0.15 / +0.06 cents) |
| MAJ: four partials | 130.82, 164.81, 196.01, 261.62 Hz, within 0.89 dB |
| pitch step C5 → G5, 10 ms later | 196.221 Hz (+0.02 cents) |
| carrier −6.02 dB | output −6.04 dB |
| 60 ms / 0.5 s after the carrier stops | −240 dBFS / exactly zero |
| silent carrier | every output sample zero |
| eight instances (both cores) | each bit-identical to its solo render |
| instructions | peak 9,213 a block, one instance |

Every instruction form in `wave.asm` (97) has a site in a stock payload
(`out/dsp/payload_*.asm`).

## Design

- **Pitch:** the rising zero crossing, interpolated to 1/256 sample
  (`f = −prev / (cur − prev)`), gives the period; the increment is 2^32 /
  (period × 256). Both divisions are a reciprocal: normalise to [.5, 1),
  seed 1.4571 − x (halved), three Newton steps. A period above 4,096
  samples or a carrier below about −66 dBFS is not measured.
- **Silence:** an envelope at zero clears the filters and writes zero.
  `mpy` truncates toward −∞, so a filter with no input settles on a small
  offset (736 LSB of DC at the output before this, measured).
- **dsp_asm:** it encodes no backward branch and no long `jmp`/`jsr`, and
  `cycle_count` prices only straight-line code, counted DOs and forward
  skips (`; CYCLES_FORWARD_BRANCHES`), so the pitch measurement is inline
  behind a forward skip and every loop is a counted DO; labels are `wv`
  plus two digits so none is another's prefix. `generate.py` writes
  `wave.asm`; `verify_wave` refuses a stale one.

## On the unit

Image 93 (remix `wave` at `e90912d9`), Sam's MKII, 3 Oct 2026: WAVCAR.wav
on a FLEX track with loop on, FX2 = Wave Synth. It plays; PTCH and the
CHROMATIC keys move the pitch. With loop on and AMP REL at INF it holds
until the AMP envelope ends it, as the carrier does. Not measured on the
unit: DSP headroom, how many instances fit.


Knob words are masked with `and #>$7f0000` before any shift; OCT is clamped
to 0..4. An LFO leaves a non-zero byte in bits 8-15 of a modulated knob word
(`docs/firmware/LFO.md` section 5): unmasked, OCT came out one octave off
and at OCT 4 `do n3` ran with LC = 0xffff. `verify_wave` renders OCT words
`0x0400fe`, `0x0200fe`, `0x047f7f` and CHRD `0x0300fe` and requires the clean
word's output bit for bit.

## Open

- How many instances fit beside a project on the unit (CF METER cannot
  see DSP time; a DSP burn sweep can).
- Optimisation: the per-sample control path (LFOs, the cubes, slews,
  Newton steps, vibrato; ~200 instructions a sample) could run once a
  block.
- Extensions: the tables from a sample (a Serum table loaded as the
  carrier's companion, or written by the ColdFire into the buffer); an
  ADSR per voice; chords snapped to SCALE QUANTIZER's scale; CHOMPI's
  delay and reverb as their own effects.

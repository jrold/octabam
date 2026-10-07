# All-family DSP checkpoint — 7 October 2026

All twelve families now have executable DSP renderer candidates. The original
ARM captures and independent native/compact oracles cover their three panel
modes. This closes the missing-renderer milestone. **It does not close the
all-twelve Octatrack machine milestone.** PERKY4 still exposes Fold Drum 1,
Simple Drum and the preserved synthetic Noise/Tone path. Only the earlier
PERKY2 Noise/Tone image has physical audio confirmation.

The reference is PerkyBits `605cfd05d9dcdc0d0caa955297556a26ea257f82` with the
user's v1.2.1 image SHA256
`adcdbc4a2c660ffb6477f202211ae3cb70170bfe6ddfaecc3df0e4cb7db398c6`.
The refreshed corpus contains 108 mode/corner captures, each with triggered and
continuation PCM, wrapper state and RNG. Noise Hat and Acoustic Hats capture
their global held samples separately. Assets, captures, binaries and logs stay
under ignored `out/perky`; no firmware bytes or samples are committed.

## Renderer evidence

Standalone P sizes include the probe and common helpers. They are not additive
shipping allocations. All cycle figures below are emulator-modeled cycles for
16 samples unless explicitly stated otherwise. A reference-capture maximum is
a measurement of that corpus, **not a worst-case bound**.

| Family | Executed renderer evidence | Standalone P words | Largest measured 16-sample test path | Largest original-capture path |
|---|---|---:|---:|---:|
| Fold Drum 1 | 15 ARM + 400 native randomized blocks; PCM/state/RNG | 1,337 | 26,121; physical noise-hold subset 19,424 | See production seam gate |
| Wavetable Drum V1 | Shared V1/V2: 816 ARM/native blocks plus all 100,352 bank samples; mapped-address candidate, PCM/state | 871 including two probes | 19,861 | 19,773 |
| Simple Drum | 240 native blocks; PCM/34-word state, all waves, retriggers/wraps | 766 | 13,913 | Production transport/seam separately qualified |
| Fold Drum 2 | 15 ARM + 400 native randomized blocks; PCM/state/RNG, both deferred wave identities | 1,410 | 33,045 | 394,377 per **256** samples; no per-16 ceiling inferred |
| Wavetable Drum V2 | Same shared renderer/storage gate as V1 | 871 including two probes | 19,861 | 19,773 |
| Complex Drum | 288 consecutive DSP blocks from 18 ARM captures; PCM/42-word state | 833 | 33,007 | 33,007 |
| Resonant Drums | Snare/bass: 1,072 blocks each, PCM/state/RNG; M3 shared Noise/Tone gate | 2,338 / 2,456 / 1,471 | 82,263 / 76,319 / 40,738 | 39,475 / 36,520 / 22,813 |
| Slap | 336 blocks; PCM/state/every ring word/RNG after each block | 1,057 | 30,326 | 20,420 |
| Karplus | 528 blocks; PCM/state/every ring word/RNG after each block | 1,068 | 33,526 | 16,312 |
| Noise Hat | All three modes against original ARM, full ring/hold/RNG | 1,147 / 1,180 / 1,047 | 31,811 / 35,445 / 22,058 | 20,128 / 32,092 / 18,063 |
| Noise/Tone | Shared 656 blocks + Waveform2 304; PCM/state/RNG and original final-state agreement | 1,471 shared / 1,222 Waveform2 | 40,738 / 15,945 | 22,813 / 13,745 |
| Acoustic Hats | 400 blocks; PCM/35-word state/global hold/IEEE754 history; 874 separate float-kernel cases | 4,905 | 97,606 | 17,337 |

Noise/Tone physical M1 is the separate **Waveform2** renderer, not a sine alias.
Physical M2/M3 and Resonant M3 share the noise/tone renderer. The newly qualified
paths are separate from the preserved synthetic PERKY2 production path.
Acoustic Hats retains exact floating-point history, including dirty-history
conversion, signed zero, subnormals, rounding ties and cancellation. Its common
zero-history fast path preserves every stored IEEE754 bit.

The full-core frame deadline is 72,512 cycles. The existing development source
allowance is 23,040 cycles, with a stock continuation reserve and margin.
Several candidates exceed that allowance, including some original captures;
others exceed it under randomized states. Passing PCM parity never overrides
the admission/timing gate. No additional family is enabled by these tests.

## Reproducing this checkpoint

The six newly registered module gates use synthetic assets by default and run
under `make check REMIX=perky-machine OT_PROJECT=`. They build the worktree's
own DSP host, assemble the actual renderer and audit the disassembly. The floor
build remains the tracked impulse canary; it does not build a twelve-family
production image.

Generate the reference corpus from external inputs:

```bash
python3 tools/perky/capture_engine_fixtures.py /path/to/perkons.img \
  --source /path/to/perkybits --unicorn-build /path/to/unicorn-build
```

Then execute the new original-capture gates:

```bash
python3 tools/verify/verify_perky_slap_dsp_exec.py --firmware /path/to/perkons.img
python3 tools/verify/verify_perky_karplus_dsp_exec.py --firmware /path/to/perkons.img
python3 tools/verify/verify_perky_resonant_dsp_exec.py --firmware /path/to/perkons.img
python3 tools/verify/verify_perky_noise_tone_original_dsp_exec.py --firmware /path/to/perkons.img
python3 tools/verify/verify_perky_acoustic_compact.py /path/to/perkons.img
python3 tools/verify/verify_perky_acoustic_float_dsp_exec.py
python3 tools/verify/verify_perky_acoustic_dsp_exec.py --firmware /path/to/perkons.img
```

The gates check firmware/capture hashes when original inputs are used. Slap,
Karplus, Resonant, Noise/Tone and Acoustic tests compare every consecutive
16-sample block against the compact oracle, then compare the complete sequence
and final state against the independent captured ARM result. Ring gates compare
every word, not a checksum. Stereo equality is checked independently.
Existing Simple/Fold/Wavetable gates use the pinned native C++ oracle and
external generated assets. The strengthened Complex gate executes both the
initial and continuation blocks in all nine captured mode/corner cases.

## Changes that closed gaps

Fold Drum 2's former randomized test did not switch both oscillator identities.
The strengthened gate exposed a four-wave ordering error and an envelope bank
that overlapped the fourth wave. Those test-bank defects are now corrected.
The same separated four-wave/envelope layout closes Complex Drum's former
fourth-wave divergence. Complex's state round-trip also now copies its envelope
without constructing a mismatched Simple Drum object.

Slap and Karplus now have complete DSP implementations. Slap wraps the delay
sum to signed32 before shifting; Noise Hat's superficially similar delay narrows
its return to int16 instead. Karplus deliberately reads its feedback ring as
unsigned16, writes feedback before the transient, advances under mute and
freezes the transient age after its original endpoint.

The common generated low32 operations are in `dsp_u32.py`. Scratch layout
centering in `dsp_source_layout.py` places a 128-word block within the hardware
one-word X displacement range; logical field offsets are unchanged. The
candidate advances r5 by 64, so callers supply the ABI base at each invocation.
This source transformation is execution-gated, not a general build change.
Original Noise/Tone retains its full32 mixer fallback and separately tests the
faster authentic 0..4095 MIX path; the two-pass filter keeps its registers live.
The preserved production PERKY2 sources are unchanged.

## Remaining production work

1. Establish reachable control-state timing bounds and reduce over-budget
   paths. Resonant standalone code now fits the current 2,724-word donor
   region after sharing its cores; Acoustic still exceeds it. A complete
   multi-engine composition remains unqualified.
2. Allocate persistent state, scratch, rings, shared code and all assets in one
   physical P/X/Y ledger. The 4,805-word Slap/classic-hat rings and 2,048-word
   Karplus ring need actual stock-FX reclamation and initialization changes.
3. Install and boot-qualify the constant-time Wavetable bank described below.
   Acoustic assets occupy 94,089 compressed words and require an actual
   DRAM/streaming design. Its test sample bank still crosses addresses absent
   on the physical Octatrack.
4. Add authentic production update/trigger/control transport for the remaining
   families, including Waveform2 and replacement of synthetic Noise/Tone.
   Original reference captures prove the render states supplied to the tests;
   they do not prove production control conversion or live mode switching.
5. Compose the twelve-family image, then run boot/upload/readback, tagged source
   records, sequencer/retrigger/AMP/FX/admission and updater round-trip gates.
6. Verify physical audio, all modes/knobs and stress behavior on the Octatrack.

The user has already chosen all twelve voices with fewer stock effects. That
scope is retained; there is no new effect-removal approval request. The current
one-voice-per-core guard stays in force until a new measured admission policy
is qualified. See [MEMORY.md](MEMORY.md), [ENGINE_MATRIX.md](ENGINE_MATRIX.md)
and [HANDOFF.md](HANDOFF.md) for the integrated-image checkpoint and constraints.

## Wavetable storage continuation

`verify_perky_wavetable_storage_exec.py --codec direct` now executes the complete
Wavetable renderer through a per-asset physical-pointer directory. It compares
816 consecutive ARM/native DSP blocks and every one of the 100,352 original
asset samples. Exact stereo PCM/state passes; all tested 16-sample renderer
paths are at most **19,861 modeled cycles** (original corpus 19,773). The 871 P
words include a second sample-reader probe; the renderer-only probe was 850.
The backend performs at most two direct packed reads per sample and needs no
block cache.

The direct bank uses **67,130 words**, including its 196-word directory. Its
candidate map is Y:$07a5..$0868 for the directory, Y:$1000..$a011 for 27 assets
(36,882 words per core), and shared Y:$38013..$3f576 for 22 assets (30,052 words
loaded once). Allocation rejects overlap, absent memory and protected boot
ranges. Y:$a020..$bfff is excluded from this table bank for later ring/state
allocation. This is a mapped-address candidate, **not a firmware installation
or a complete all-family persistent-ring ledger**. Stock init still clears the
large bank; stock effects must be retired before those arenas are reusable.
External-memory hardware latency and initialization/load ordering still need
full-image/hardware gates.

The smaller 45,713-word second-difference bank is bit-exact with two caches,
but complete-renderer misses cost **74,893 original / 84,021 all-case cycles**.
That exceeds the 72,512-cycle core deadline before stock continuation and rules
out that backend for production at present. The prior 2,511-cycle sequential
single-asset decoder figure was structurally blind to those renderer misses.
The test also normalizes signed 24-bit shared-address cache tags before comparing
them; without that, shared-window cache hits become silent extra misses.

Reproduce both paths from the generated external assets/corpus:

```bash
python3 tools/verify/verify_perky_wavetable_storage_exec.py --codec direct
python3 tools/verify/verify_perky_wavetable_storage_exec.py --codec second-difference32
```

These are explicit external-reference gates, not synthetic module gates. The
second command verifies parity and reports timing; PASS does not mean realtime.

## Resonant size/runtime continuation

The exact decay and resonator bodies are now shared by every oscillator in a
family. Guarded native DSP paths handle bounded values, with the original
full32 two-limb path retained for every value outside those bounds. Both
paths pass 1,072 consecutive blocks per family, including 256 synthetic
initial states with boundary/fallback cases and all six original snare/bass
mode/corner captures. PCM, every live word and RNG match after each block.

Snare now occupies **2,338 P words / 176 scratch**, bass **2,456 P / 180
scratch**; both standalone candidates fit the existing donor region. Largest
original blocks fell from 62,429 / 55,080 to **39,475 / 36,520 modeled cycles**.
That is still above the 23,040 development source allowance. Wider synthetic
states reach 82,263 / 76,319 cycles; the fast path is not used to invent a
reachable-state bound or relax admission.

The resonator guard proves signed22 drive, signed16 position/velocity and
unsigned16 cached coefficients/modulation. Modulated coefficients still fit
signed24; every product explicitly wraps low32 before its signed shift. The
decay guard proves positive signed24 multiplier/value, signed22 sign, unsigned16
minimum and a representable countdown category. Its unsigned low32 product
shift is normalized after masking, so stale accumulator extension/fractional
bits cannot alter the next comparison. No original state, control law or
rounding behavior is changed by these shortcuts.

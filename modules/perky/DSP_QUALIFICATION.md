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
| Wavetable Drum V1 | Shared V1/V2: 18 ARM + 240 native blocks; all 49 assets, PCM/state | 841 | 19,435 | Not separately reported |
| Simple Drum | 240 native blocks; PCM/34-word state, all waves, retriggers/wraps | 766 | 13,913 | Production transport/seam separately qualified |
| Fold Drum 2 | 15 ARM + 400 native randomized blocks; PCM/state/RNG, both deferred wave identities | 1,410 | 33,045 | 394,377 per **256** samples; no per-16 ceiling inferred |
| Wavetable Drum V2 | Same shared renderer gate as V1 | 841 | 19,435 | Not separately reported |
| Complex Drum | 288 consecutive DSP blocks from 18 ARM captures; PCM/42-word state | 833 | 33,007 | 33,007 |
| Resonant Drums | Snare/bass: 176 blocks each, PCM/state/RNG; M3 shared Noise/Tone gate | 3,910 / 3,286 / 1,471 | 81,168 / 66,439 / 40,738 | 62,429 / 55,080 / 22,813 |
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
   paths. Resonant and Acoustic code also exceed the current 2,724-word donor
   program region before a multi-engine composition is attempted.
2. Allocate persistent state, scratch, rings, shared code and all assets in one
   physical P/X/Y ledger. The 4,805-word Slap/classic-hat rings and 2,048-word
   Karplus ring need actual stock-FX reclamation and initialization changes.
3. Integrate lossless Wavetable decoding into the renderer and measure cache
   misses. Its full bank occupies 45,713 DSP words. Acoustic assets occupy
   94,089 compressed words and require an actual DRAM/streaming design. Current
   test sample/wave banks cross addresses absent on the physical Octatrack.
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

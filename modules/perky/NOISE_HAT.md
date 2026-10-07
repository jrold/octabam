# Noise Hat DSP checkpoint — 7 October 2026

All three panel modes now execute on the local DSP56300 interpreter with exact
PCM and continuation state. This is a renderer checkpoint. Noise Hat is not in
the production machine chooser and has not been tested on the Octatrack.
The one-voice-per-core admission policy remains unchanged.

Reference: PerkyBits revision `605cfd05d9dcdc0d0caa955297556a26ea257f82`,
using the user's local v1.2.1 image. The fixture manifest hashes both the image
and capture sources. No reference firmware, tables, state or PCM enters Git.

## Executed evidence

| Gate | What it proves |
|---|---|
| `verify_perky_noise_hat_pulse_native_compact.py` | Independent ARM-shaped C++ vs 59-word Pulse Stack: 128,000 exact samples and 472,000 continuation words |
| `verify_noise_hat_compact.py` | Nine original ARM continuation captures: exact host PCM, compact state, full ring, hold and global RNG |
| `verify_perky_noise_hat_dsp_exec.py` | Same nine original ARM captures executed as 144 consecutive DSP blocks: 2,304 exact samples, both stereo channels, every block's state/ring/hold/RNG, and final original ARM state |
| `verify_perky_noise_hat_classic_synthetic_exec.py` | Both classic limbs, random coefficients/taps/mix/state, ring wrap and mute freezes; four consecutive blocks per case |
| `verify_perky_noise_hat_pulse_synthetic_exec.py` | All shapes, local LCG wraps and alias, signed interpolation, native overflow and saturation; four consecutive blocks per case |
| Filter / phase / envelope executable gates | 207 / 256 / 213 exact primitive states |

All DSP gates build the branch's interpreter harness locally. They refuse
label-prefix collisions and out-of-range literal LUA displacements, and compare
the assembler listing with disassembled bytes, including NOPs. There is no
implicit signed MPY to MPYSU exception.

Run after the DSP dependency toolchain has been built:

```bash
python3 tools/verify/verify_perky_noise_hat_pulse_native_compact.py
python3 tools/verify/verify_perky_noise_hat_classic_synthetic_exec.py
python3 tools/verify/verify_perky_noise_hat_pulse_synthetic_exec.py
```

For original ARM evidence, regenerate the fixtures with the updated capture
harness (including the four-byte global hold state), then run both gates:

```bash
python3 tools/perky/capture_engine_fixtures.py /path/to/perkons.img \
  --source /path/to/perkybits --unicorn-build /path/to/_deps/unicorn-build
python3 tools/perky/verify_noise_hat_compact.py /path/to/perkons.img
python3 tools/verify/verify_perky_noise_hat_dsp_exec.py /path/to/perkons.img
```

The original ARM gate requires a matching fixture manifest and checks its file
hashes. It deliberately does not become an automatic manifest gate requiring
the external proprietary image. The self-contained gates run in `make check`.

## Timing and memory

These are **observed interpreter-model costs**, not hardware timing or a
worst-case ceiling. Complete synthetic probe programs include helper routines;
their P footprints are standalone counts, not incremental shipping sizes.

| Panel mode | Raw mode | Standalone P words | Original ARM corpus max cycles / 16 samples |
|---|---:|---:|---:|
| M1 white noise | 1 | 1,147 | 20,128 |
| M2 metallic | 0 | 1,180 | 32,092 |
| M3 Pulse Stack | 2 | 1,047 | 18,063 |

The optimized delay rebases its hot scratch through r7 so raw A0 stores use
the one-word X-displacement form present in stock, rather than introducing a
new two-word A0 store. Stock also contains the displaced X-to-B0 load, signed
MPY and immediate accumulator shift forms used here. This is instruction-form
precedent, not hardware qualification of the algorithm.

Before optimizing the wrapper, original ARM corpus M1/M2 peaked at
58,232 / 61,820 modeled cycles. Exact native arithmetic replaces the expensive
generic limb sequence while retaining wrapping sums, intermediate clamps and
final int16 narrowing. M1's mix also retains its signed25 intermediate via two
partial products. Re-run the broader synthetic corpus before interpreting a
timing improvement as admission evidence.

The existing development allowance is 23,040 modeled cycles per block, with a
2x model margin and 22,560 stock cycles reserved against the 72,512 deadline.
M2 already fails on real captures. M1's broader synthetic stress corpus also
exceeds this allowance. Both classic paths remain pending cycle qualification.
Passing the M3 corpus does not establish its production seam or hardware cost.
Local JSON reports record corpus maxima and whether they fit the allowance;
they do not label a PCM pass as production qualification.

| Candidate allocation | Classic M1/M2 | Pulse Stack |
|---|---:|---:|
| Hot X words per instance | 121 | 59 |
| Scratch span used by test ABI | 119 | 100 |
| Persistent sideband within that scratch | 2 hold + 4 global RNG limbs | none; local RNG is in hot state |
| External Y ring | 4,805 signed16 samples | none |
| Required envelope entries | two packed 1,025-entry curves | same |

The extended synthetic corpus peaks at 31,811 / 35,445 / 22,058 modeled
cycles for M1/M2/M3 respectively (10,240 exact PCM samples and 640 consecutive
blocks across the two complete-voice gates). These stress inputs deliberately
include independent state/parameter extremes, beyond the captured control corners.
The classic synthetic gate stores 2,048 entries per test curve; only the first
1,025 are reachable by the clamped renderer.

The classic state retains both limbs for future live mode switching. M3 word
57 remains the RNG high-half / second-filter-input alias; do not add a mirror.
The test curves live at separate addresses to avoid overlapping the full Y ring.
No test address here constitutes a physical memory allocation. Production still
needs the common X/Y/P ledger, stock-FX reclamation, bootstrap/mailbox exclusions,
and protection from stock initialization clears described in [MEMORY.md](MEMORY.md).

## Next production work

Reduce classic worst-path cost and measure authentic prepared-control sweeps,
then compose the candidates into the retained engine set with a physical memory
ledger. Qualify authentic parameter updates, trigger/mode transitions and the
real dispatcher seam before enabling family 010. Repeat full image boot,
sequencer, transport and retained-stock regressions, preserving PERKY2 as the
physical reference. Hardware qualification remains a separate step.

## Regression floor for this checkpoint

`make check REMIX=perky-machine OT_PROJECT=` passed all runnable checks on this
worktree, including 59 shared module gates and the existing Noise/Tone oracle.
The project-dependent `verify_set` and `verify_perky_probe_port` gates were
explicitly skipped. `verify_perky_shipping_voice_exec.py` separately passed the
actual generated PERKY2 renderer's 36 exact PCM/state/RNG blocks. This floor
builds the tracked probe/remix; it does not integrate Noise Hat into a full
production image. No new hardware updater was emitted.

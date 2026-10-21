# Remaining ColdFire optimization — 21 October 2026

**PKFM20 improves all eight matched sustained workloads but remains held for
performance.** Resonant steady ISR means fall by 4.526–5.600 us and Slap means
by 2.764–3.305 us against the unchanged PKFM17 fixtures. Every row still fails
six of the seven frozen budget ceilings. Exact synth PCM and zero nominal
deadline misses do not establish hardware headroom. The final
[machine-readable qualification](REMAINING_CF_QUALIFICATION.json) binds all
eight workloads and the completed source, handoff, lifecycle, selector,
scene, DMA, kernel and profile receipts to the actual PKFM20 image. Its verdict
is `FAIL_HOLD / HOLD_FOR_PERFORMANCE_WORK`; functional qualification passes.

## Retained changes

Resonant now renders up to twenty native samples per internal chunk, avoiding
another load/store/setup pass for common 17–19-sample requests. Recurrence
order, rounding, RNG, arbitrary-length handling and malformed-state behavior
remain exact. The isolated linked proof checks 3,360 native-clock frames and
4,320 directed full-state/PCM/guard/ABI cases per variant against the original
source; recompiled baseline assembly matches the actual PKFM17 bodies. Its
Resonant object text shrinks from 13,544 to 9,422 bytes.

An unchanged-control preparation path reads authoritative engine/control state
after production generation/event observation. Initialized, valid, untriggered
controls with matching raw values and MODE avoid the large slow frame. It
retains active ALGO/MODE updates and algorithm-change clock resets; dirty,
triggered, fresh and Acoustic Hat events use the original preparation body.
A native differential gate checks 6,000 events, including 858 poisoned events.
Actual-image source and lifecycle gates separately qualify real generations.

The stock source mixer uses an assembly loop for its original sixteen groups
and alternating six/nine fields. All original loads, stores and MAC operations
retain their order. Its 4,096-case proof compares complete aliased memory,
all registers, full CCR and raw EMAC across eight MAC modes, with independent
same-image predictor controls. The isolated saving is 329 model cycles per
whole mixer block, approximately 1.246 us per audio frame. The 558-byte helper,
eight-byte packaged detour, unchanged stock remainder and real loader readback
are bound to the executed standalone binary through an independent replay.
Integrated savings below are measured, rather than sums of isolated gains.

The first development image, PKFM18, let GCC inline the smaller public
`placement_prepare` into some callers. Its direct 5,355-frame source gate
passed, but the frozen observer aborted because its event boundary was
bypassed. Those captures have no timing qualification. Their exact sources
and failure evidence remain in `full-map-remaining-cf-v1`; the explicit public
`noinline` boundary is retained in PKFM19/20 without changing the instrument.

## Matched four-voice measurements

Every row runs 32,768 sixteen-sample transport blocks, 11.889 seconds at
44.1 kHz, using a 64-step 120 BPM 1X sequence. T1/T2 run WT V1/V2 on CF,
T5 runs the stated Slap or Resonant selection on CF, and T6 runs metallic
Noise Hat on DSP-A or Noise/Tone mode 1 on CF. Four stock sample tracks and
all fourteen FX are active. Selecting Noise/Tone puts all four source voices
on CF. Final card bytes and all sixteen banks' Part/pattern locks match the
corresponding PKFM17 controls exactly.

Values are model microseconds. Steady ISR means exclude the first 512
completions; peaks include the complete capture. Total CF divides exact
playback cycles by 32,768 and 264 MHz and includes background work.

| T5 | T6 | ISR mean, PKFM17 → PKFM20 | Full ISR peak, PKFM17 → PKFM20 | Total-CF mean, PKFM17 → PKFM20 |
|---|---|---:|---:|---:|
| **Fixed ceiling** | — | **158.212** | **250.712** | **189.298** |
| Slap | Metallic Hat | 210.437 → 207.132 | 300.667 → 302.473 | 236.154 → 232.863 |
| Snare | Metallic Hat | 205.582 → 200.593 | 303.083 → 303.621 | 231.353 → 226.353 |
| Bass | Metallic Hat | 205.612 → 200.012 | 301.947 → 302.322 | 231.386 → 225.738 |
| Snare/Bass MODE locks | Metallic Hat | 205.566 → 200.292 | 303.004 → 302.769 | 231.338 → 226.037 |
| Slap | Noise/Tone | 221.681 → 218.918 | 307.125 → 308.352 | 247.371 → 244.643 |
| Snare | Noise/Tone | 217.005 → 212.479 | 310.947 → 309.614 | 242.744 → 238.200 |
| Bass | Noise/Tone | 216.536 → 211.950 | 309.330 → 308.019 | 242.251 → 237.659 |
| Snare/Bass MODE locks | Noise/Tone | 216.772 → 212.190 | 310.867 → 309.417 | 242.505 → 237.905 |

Mean improvements do not imply uniform peak improvements. Slap peaks rise
1.227–1.807 us; fixed Snare/Bass peaks with Hat rise 0.375–0.538 us. Other
matched peaks fall 0.235–1.451 us. The worst sustained peak among these eight
rows falls from 310.947 to 309.614 us, but individual regressions remain
explicit. All rows fail ISR mean, p99, p99.9 and peak, total-CF mean and ACK
p99; only ACK peak passes. The highest mean remains Slap with CF Noise/Tone:
218.918 us ISR and 244.643 us total CF. Reaching the fixed 158.212/189.298 us
means still requires another 27.7% ISR reduction and 22.6% total-CF reduction.

Alternating fixtures select both Snare and Bass through real triggered-step
MODE locks. Each 45-trigger pattern alternates within the pattern and repeats
MODE 0 across its loop boundary. Runtime tuples independently confirm both
modes rendered; aggregate counts do not establish exact transition timestamps.
No algorithm, precision or native 48 kHz synthesis/44.1 kHz output clock was
relaxed.

## Remaining measured costs

The final Slap/Noise-Tone profile passes paired equality of exact source audio,
raw target dumps, transport, ISR histograms, total CPU cycles and final-card
selection witnesses against its unprofiled run. Exclusive steady costs below
use the same grouping for PKFM17 and PKFM20; stock work includes the new named
mixer and existing stock-position helper rather than treating moved symbol
attribution as a saving.

| Exclusive cost, us/frame | PKFM17 | PKFM20 |
|---|---:|---:|
| Stock ISR, mixer and stock position | 107.624 | 106.832 |
| Control preparation | 6.072 | 2.981 |
| WT render, oscillator and frequency | 27.019 | 27.327 |
| Slap render, delay and filter | 24.626 | 24.774 |
| Noise/Tone render, filter and envelope | 17.253 | 17.146 |
| Common render, conversion and transport | 31.464 | 32.115 |
| Background total | 25.939 | 25.982 |

The measured control saving is 3.090 us/frame; the grouped stock ISR saving is
0.792 us/frame. Layout and scheduling changes also affect other buckets, so
their isolated savings must not be added to the integrated 2.764 us ISR saving
for this case. Stock background alone remains 25.769 us/frame. The costs show
why these local changes cannot close the remaining 27.7% ISR / 22.6% total-CF
gap. The profile is local model evidence, not a hardware cost breakdown.

## Correctness and lifecycle evidence

The new actual image passes 5,355 direct source frames across 81 layouts,
three mode rotations, all splits 0–16 and 24 directed transitions, comparing
PCM, raw CF objects and shared RNG with separate original-source histories.
An 800-frame actual-image gate covers CF/DSP handoff, pending jobs, coherent
snapshots, delayed feedback and full sequence/ring wraps. Linked NT/AH/Slap
kernel gates pass 528/792/792 calls including edge lengths, full state, PCM
guards and RNG/hold. Scheduled-DMA startup, both banks, wrap and carrier
clearing also pass on this image.

The production lifecycle passes 52,934 ISR entries / 52,933 completed returns,
seven generations, STOP/START, Part/Bank changes, all modes and 22 backend
switches. Eleven snapshots, 730 replay frames and 741 completed jobs exercise
the real handoff path with exact source audio and no transport/safety/nominal
deadline violations. Its peak is 328.966 us. Scene/fader delivery passes
9,147 frames with all eight track outputs active and a 302.292 us peak.
These peaks still fail the separate 250.712 us calibrated ceiling. A final
entered-but-not-returned ISR is recorded explicitly where the interactive
capture stops; it is not relabeled a completed return.

The complete production matrix passes all 243 observed tuples, with none
missing, across four actual sequencer patterns and 159,827 ISR entries /
159,826 returns. Its peak is 333.004 us, with no nominal deadline misses,
source mismatches, transport errors or ownership/stack/DMA violations.
It still fails the fixed 250.712 us peak ceiling. Both DSP uploads remain byte-identical to PKFM17, so
the earlier DSP-only snapshot/stock-FX proofs are reused by byte identity;
CF source, handoff, transport and lifecycle evidence is newly executed.

Sustained source observations compare original-reference synth PCM and DSP
Hat state, side, clock and feedback. They do not byte-compare every raw CF
state on every sustained block; the new direct source gate supplies separate
raw-state evidence. Aggregate significant source/post-FX counts and continuing
card reads prove activity on all eight tracks, not uninterrupted stock PCM on
every frame. The calibrated adapter removes bulk audio after recording its
hash/counts, so these receipts cannot replay the stock capture.

## Excluded experiments

Slap compiler loop changes worsened held costs by roughly 193–237 cycles.
Slap envelope caching was exact and slightly faster in solo tests but slower
in the combined layout. WT envelope-block C and linear-envelope assembly
prototypes also stayed exact, including malformed-wave partial-failure
behavior, but worsened WT/WT costs by 369–373 and 417–420 cycles respectively.
None is included or credited with integrated savings.

An exact stock background envelope fusion saved about 0.727 us per
768-sample invocation. Its low inferred invocation rate made the amortized
opportunity too small to justify integration; that inference is not a measured
full-workload saving. An inner-only six/nine-field mixer unroll lost its gain
to dispatch/detour overhead. The separately proven complete sixteen-group
replacement is the retained mixer. Previously rejected fixed Slap delay,
NT filter assembly and stock DELAY unrolling remain excluded.

## Provenance and fixed limits

MAIN SHA256 is `9bae33446c3206e200edabee5b8e1ee4eb1e40f950e2de2e5157cea6a59d6935`;
ELF SHA256 is `ff1ea42382eb39d64db8a581c373502c011dd5d16dc3ef2df4f2d5f49468f8e2`.
CF text is 577,292 bytes, 4,084 smaller than PKFM17; data/BSS remain
588/1,612,664 bytes. DSP allocation, transfer word counts and source latency
are unchanged. The existing hybrid branch and checkout were used.

The source checkpoint is `4eeae750caf8ba98144dd9ad8ac3b68299e21982`
plus the dirty source hashes in the candidate's `BUILD.json`. Local evidence
is under `out/perky/hybrid/full-map-remaining-cf-mix-v1/`; its
`OPTIMIZATION_PROOFS.json` indexes the bound proofs. Sustained rows are under
`out/perky/hybrid/resonant-cf-optimization/final-workload/` and the final
profile under `resonant-cf-optimization/final-profile/`. The source-only
`FINAL_SOURCE_SNAPSHOT.json` and `FINAL_SOURCE.tar.gz` retain the build inputs,
new campaign tools, report and final qualification without firmware bytes.

Local verification completed:

- New-image source, handoff, linked synthesis, DMA, lifecycle, selector-matrix
  and scene commands all returned zero; their detailed receipts are indexed.
- Eight matched measurement commands each returned zero. The final qualifier
  returned one with a fresh `FAIL_HOLD` receipt because the fixed budget fails;
  all functional and provenance checks passed.
- `make check REMIX=perky-machine` returned zero: all runnable checks passed;
  fixture-dependent skips are preserved in `DEFAULT_FLOORS.json`.
- `scripts/refhash.sh check` returned zero: all 24 cases remained bit-identical.
- `make bus REMIX=perky-machine` returned zero and restored the standard output
  image, SHA256 `c9e292bec49f54820355c76dca904c5dc02d1378120f7a34042c10dfe1bbe1a4`.

The observer remains
`f975b4d2c4b6a2d993d3158bc8e68c8a786b328e2902b58bdde418225287d022`;
the budget remains
`8608844b96c6f20daed514147dc6cadab7a2c82aae80d2ef7c9a875a22ccaec4`.
CF/PIT clocks remain 264/132 MHz with uniform startup/pre-roll/playback
cycle-clock x1.00. Seven ceilings are unchanged: ISR mean/p99/p99.9/peak
158.212/166.780/237.731/250.712 us, total-CF mean 189.298 us, and ACK
p99/peak 328.000/362.212 us.

This is a local engineering screen, not a universal emulator/hardware
multiplier. It does not establish hardware cache, SDRAM/card/bus contention,
IRQ timing or UI acceptance. The user's earlier greater Resonant burden on
hardware is not settled by these fixtures. PERKY4S remains the hardware-tested
release. No flash, package, push or release commit was made.

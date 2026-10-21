# Native-clock ColdFire placement — 20 October 2026

**No existing placement establishes the complete PERKONS voice layout.** The
existing CF oscillators are usable fallbacks in the local correctness model,
but the four-CF escape route required by WT/WT already overruns the audio ISR
with active stock tracks and effects. The previous
[paired DSP-B experiment](DSP_B_FEASIBILITY.md) also exceeds its unchanged
source allowance. Neither failure is repaired by recovering program memory.

This opt-in experiment runs on the user-authorized `perky-cf-dsp-hybrid`
checkout, source checkpoint `4eeae750caf8ba98144dd9ad8ac3b68299e21982` plus
the source hashes in the [compact receipt](CF_PLACEMENT_FEASIBILITY.json).
PERKY4S remains the physical reference. There are no new flash wrappers or
hardware acceptance claims.

## Contract and implementation

The measured logical map is T1/V1 = Fold1, WT V1, Simple; T2/V2 = Fold2,
WT V2, Complex; T5/V3 = Resonant, Slap, Karplus; T6/V4 = Noise Hat,
Noise/Tone, Acoustic Hats. Algorithm identifiers in the raw receipts are
the generic CF identifiers, not new panel indices.

The existing CF renderer bodies are reused. `cf_native_clock.h` advances
synthesis at 48 kHz and produces 44.1 kHz source PCM with the same exact
x32 gain as the qualified DSP adapter and rational floor-rounded interpolation.
It retains independent phase/carry state, resets it on trigger or algorithm
switch, and renders old/new portions around the event boundary. This prices
the extra native samples and conversion, rather than treating 16 native
samples as one OT block. Existing control-preparation cadence is retained;
this is not a new qualification of every control law or panel-mode mapping.
The DSP uses quantized Q23 interpolation coefficients; its existing clock
gate permits one source LSB against this rational oracle. The CF comparison
is exact against that oracle, not a claim of bit-identical interpolated PCM
between processors. Native renderer state and sample evolution remain exact.

Acoustic Hats C, header, soft-float helper and independent ARM differential
were restored from `1b64a62db5544b414e46845e72ccc02e6bd780a0`.
Its sample assets are extracted locally from the user's hash-pinned
original firmware. The historical 8,192-byte control-rate table is recovered
only into ignored output. No sample/table/firmware bytes are added to git.
The restored source is not enabled in the default release generator.

The generic four-instance engine retains each family's history; it is not
an SRAM compaction or overlapping-state experiment. The integrated probe
uses approximately 330 KiB of CF BSS including decoded WT assets, with a
512 KiB startup-clear bound inside the existing platform reservation.
Private interrupt-stack and DMA-buffer ownership mechanisms are retained.

## Measured source cost and correctness

The target runs actual MCF54455 instructions with the corrected alignment
and per-instance predictor model at **264 MHz**. Timing excludes host
diagnostic sample traces: those run in the native shadow. The measured
function includes control preparation, event splitting, native synthesis,
resampling and source-record packing.

| Existing fallback | Maximum modeled cycles | Maximum microseconds |
|---|---:|---:|
| Fold1 | 10,007 | 37.91 |
| Fold2 | 11,575 | 43.84 |
| Simple | 8,220 | 31.14 |
| Complex | 9,388 | 35.56 |

Each solo family exercises three modes and three control corners, sustained
and dense-trigger blocks. These are measured maxima in that corpus, not
analytical bounds.

The combined matrix covers all **81 algorithm layouts**, six mode tuples
(`0000`, `1111`, `2222`, `0120`, `1201`, `2012`), all event offsets and
each possible single-oscillator-on-B choice. It records **93,312 target/native
frame comparisons, 9,072 complete canonical state/RNG/clock comparisons and
3,314,484 independently checked generated native samples**. PCM, source
packets, native counts and sampled full state all match. A separate C versus
rational-oracle check passes **19,108** cases covering every phase and segment
length 0..16, carried/fresh states, extreme samples and resets.

These checks also price conditional DSP-A removals:

| CF work measured together | Largest observed CF source cost |
|---|---:|
| Existing placement: at most one B oscillator, WT/WT entirely CF | 208.20 us |
| Remove V3 from CF | 163.88 us |
| Remove V4 from CF | 97.99 us |
| Remove both V3 and V4 from CF | 53.89 us |

The maxima come from different rows. Do not subtract these maxima or add
solo peaks to claim end-to-end headroom. The latter three rows contain no
replacement DSP code, transfer protocol or stock-ISR cost. When both
oscillators are present, choosing V2 for DSP often saves more CF time than
choosing V1, but production T2 DSP routing is not installed by this probe.

## Measured combined workload

The integrated image is MAIN OS SHA256
`e5d2e686e6368e71d3e3b888ee3e540a54c3a952ab9112f759e7c62c47dc1cbe`.
Its DSP payloads retain PERKY4S identity and the twelve retained effects.
The probe changes generated CF control code only; diagnostic selectors
choose algorithms/modes while actual sequencer locks, LFOs and scene/raw
control delivery feed the source seam. Existing menus are not remapped.

Each combined row runs 4,096 transport frames with four stock STATIC tracks
on T3/T4/T7/T8 and active effects across all eight tracks. The receipt binds
image, runtime, observer, fixture and driver hashes. The CPU cycle clock is
active during startup, pre-roll and playback; PIT is **132 MHz**. Reports
measure executed ISR entry through return, including the private-stack
switch, rather than accepting pending-IRQ observation as execution.

The frame deadline is **362.812 us**. Results are tabulated in the compact
receipt. WT/WT + Slap + Noise Hat reaches **406.26 us / 10 misses**;
WT/WT + Resonant + Noise Hat reaches **403.15 us / 10 misses**.
WT/WT + Resonant + Acoustic Hats reaches **334.52 us / zero misses** in
its tested row. Mean times do not determine acceptance.

| Actual selection, V1 / V2 / V3 / V4 | CF voices | Maximum ISR us | Misses |
|---|---:|---:|---:|
| WT V1 / WT V2 / Slap / Noise Hat | 4 | 406.26 | 10 |
| WT V1 / WT V2 / Resonant / Noise Hat | 4 | 403.15 | 10 |
| WT V1 / WT V2 / Resonant / Acoustic Hats | 4 | 334.52 | 0 |
| WT V1 / WT V2 / Karplus / Noise-Tone | 4 | 318.76 | 0 |
| DSP Fold1 / CF Fold2 / Slap / Noise Hat | 3 | 399.36 | 10 |
| DSP Fold1 / CF Complex / Resonant / Noise-Tone | 3 | 311.16 | 0 |
| CF Fold1 / CF Fold2 / Resonant / Noise-Tone | 4 | 346.84 | 0 |

The legacy fixture's DSP algorithm locks were pinned for the two DSP rows;
captured DSP control records prove only Fold1/Mode 0 ran there. Earlier
receipts using the fixture's four-oscillator stress sequence are superseded
for these named comparisons. The initial all-track source-PCM assertion
also falsely rejected an active DSP row; its replacement checks control
records plus post-FX audio. Neither correction changes the all-CF rows.

All completed rows require active source PCM for CF/sample tracks and active
post-FX audio on every track (DSP source records carry controls),
continued STATIC card reads after PLAY, balanced executed ISR/private-stack
returns, no DMA overlap, no write after dispatch, and no stack/fence or
ownership violations. CF call/native-sample counters prove selected engines
actually ran at the native rate. Large reproducible cards/block captures
are removed after hashing and audio analysis; raw counters/reports remain.

The integrated cases use fixed algorithm/mode selectors; they do not qualify
algorithm/mode locks, saved-Part migration, backend migration or full UI
lifecycle. Six mode tuples in the source matrix are not all 81 mode tuples,
and continuous controls are not exhaustively bounded. The model omits
physical cache/SDRAM/card arbitration costs and already passes arrangements
that failed on the user's hardware. Local passes cannot certify hardware.

## Placement decision

1. **Two unchanged oscillators on B:** rejected against the existing
   23,040-cycle source allowance; previous worst pair is 39,661 cycles.
2. **One B oscillator plus CF fallback, with CF WT/WT:** does not cover the
   full layout. Both WT selections leave the existing oscillators unused,
   force V3/V4 onto CF and expose the measured ISR overruns above. Choosing
   a different oscillator fallback cannot fix this counterexample.
3. **CF WT/WT and V3, DSP-A V4:** the strongest measured next candidate.
   Its CF remainder is materially smaller than moving V3 alone. This is a
   research placement, not a demonstrated solution: all three V4 families
   need a real code/data/cycle ledger and a measured exchange path. Existing
   Noise Hat delay storage and mode-dependent DSP execution are unresolved.
   A V3-only offload or a cross-core service remains conditional as well.

The removal experiment is not a requirement to move every V4 family to DSP.
The first useful offload target is **Noise Hat**. With V4 left on CF, the
largest source-only costs are 208.20 us for Noise Hat, 130.90 us for
Noise/Tone, and 145.05 us for Acoustic Hats. These separate maxima are not
combined-ISR bounds. The existing standalone DSP portfolio also is not a
drop-in solution: original Noise Hat M2 reaches 32,092 cycles/16 native
samples, the classic hat ring needs 4,805 words, and Acoustic Hats needs
4,905 program words plus a real asset placement. See
[DSP qualification limits](../DSP_QUALIFICATION.md). Selective V4 offload
with Acoustic Hats retained on CF avoids crediting an unsupported complete
V4 DSP portfolio; the remaining combinations still need combined bounds.

Thus **none can currently be claimed to meet the full map**. To reverse
that conclusion, an optimized CF arrangement must pass the same combined
counterexamples with margin, or a real DSP offload must preserve the original
PCM/state/control behavior, fit the memory ledger and pass combined timing.
After that, matched physical captures with stock workload and UI activity
are still required. SRAM placement, ring transfers and renderer optimization
were not implemented or credited by this measurement campaign.

## Reproduction and gates

Run from the existing checkout with its local toolchain, stock OS, original
PERKONS image and pinned PerkyBits checkout available:

```sh
python3 tools/verify/verify_perky_cf_placement_author.py
python3 tools/verify/verify_perky_cf_simple_drum_dsp.py
python3 tools/verify/verify_perky_cf_complex_drum_dsp.py
python3 tools/verify/measure_perky_cf_placement.py
python3 tools/verify/verify_perky_cf_acoustic_hats_dsp.py --rate-include out/perky/hybrid/cf-placement
python3 tools/verify/verify_perky_cf_native_clock.py
python3 tools/perky/build_cf_placement_probe.py
python3 tools/verify/verify_perky_hybrid_private_stack.py --work out/perky/hybrid/cf-placement-integrated --build-observer
python3 tools/verify/measure_perky_cf_placement_integrated.py
make check REMIX=perky-machine
REFHASH_LOCAL=1 REFHASH_JOBS=1 scripts/refhash.sh check
```

The original-core state/control/PCM/stress/long-tail differentials pass;
Simple, Complex and restored Acoustic Hats each match original ARM PCM and
object state for 6,912 samples. The historical complete CF release runner
was also attempted and **fails its older static no-division guard on the
already-existing `cf_resonant.c`**. The narrower differential pass is not
a pass or waiver for that complete runner. Default build gate and refhash
results are recorded separately in the compact receipt.

Full local evidence is under `out/perky/hybrid/cf-placement/` and
`out/perky/hybrid/cf-placement-integrated/`.

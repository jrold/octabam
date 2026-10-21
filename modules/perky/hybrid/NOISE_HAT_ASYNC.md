# Noise Hat: pulse investigation and cooperative offload — 20 October 2026

**Same-frame CF overlap works in the tested model, but this placement still
fails timing.** All three 4,096-frame rows pass eight-track audio, exact Noise
Hat state/PCM and loaded-program ownership with **zero cleanup waits**.
The worst complete ISR is **494.034 µs**, versus **362.812 µs** available.
This is an opt-in prototype on the user-authorized `perky-cf-dsp-hybrid`
branch, not a production admission or flash candidate.

Source checkpoint is `4eeae750caf8ba98144dd9ad8ac3b68299e21982` plus the
uncommitted sources fingerprinted in the [receipt](NOISE_HAT_ASYNC.json).
Full local evidence is under `out/perky/hybrid/noise-hat-async/` and
`out/perky/hybrid/noise-hat-irq-audit/`. PERKY4S remains the physical reference.

## What the pulse investigation establishes

The [blocking prototype](NOISE_HAT_OFFLOAD.md) lost T4/T7 post-FX audio and
nearly all of T8 with DSP RAM dirtied using seed 123. The investigation uses
that same image and CF runtime, with a separate read-only DSP witness.

* In 145 live host interrupts, A/B, X/Y, R/N/M, resolved SR, OMR, LA/LC,
  PC, SP and SC compare without changes. The observed service stack pointer
  peaks at seven. The earlier apparent N-flag changes were **retracted**:
  comparing the emulator's raw SR field missed its deferred condition-code
  calculation. The corrected witness resolves SR before comparison.
* Writes observed outside the service's X allocation are confined to
  `X:0x8100..0x83ff`, the ongoing ESAI DMA rings. No write to stock AMP/FX
  state or executable storage is observed inside these service calls.
* Source PCM is already active in the DSP before AMP. T4/T7/T8 lose their
  signal **before FX1**, not inside DJ EQ/Chorus/Comb. Every stock FX init
  runs once, and the expected process targets are selected.
* An unchanged blocking image passes all eight audio chains with zero-filled
  DSP RAM. Dirty and clean runs have identical captured current AMP control
  records; their persistent AMP histories differ.
* Dirty histories at `X:0x6600` and `X:0x6900` on both cores retain invalid
  AMP phase values and old envelope/control history. Clearing only the four
  phase words before boot restores T8 but leaves T4/T7 silent. **The phase
  word alone is not a sufficient repair.**
* Clearing the four complete 32-word AMP blocks before boot also leaves
  T4/T7 silent. This falsifies the stronger hypothesis that these four AMP
  histories alone explain the failure. Other dirty startup state or its
  delivery/lifecycle still needs to be traced.

This locates the observed loss in AMP and establishes dirty-start sensitivity;
the underlying initialization/transition cause remains open. It does not justify
changing stock initialization in a release. Diagnostic RAM counterfactuals
are applied only in the isolated observer; the default emulator and firmware
are unchanged. Passing audio under the new schedule must not be described as
general lifecycle or hardware qualification.

## Cooperative transport and event order

The new CF coordinator queues T1, T2 and T5 source work with each track's
captured controls and split offset. At T6 it submits the old Noise Hat
segment, then executes the queued WT/WT and Slap renderers. Readiness-guarded
polls inside their sample loops move available HI08 words and return to CF
work when the port is not ready. A poll has a fixed word budget.

Completion commits the returned raw state, hold/RNG and original classic
delay, converts that segment with the unchanged native clock, applies the
event/control update, and submits the second segment. The next request can
progress during the remaining CF work. Both segments and all deferred PCM
are published before the ordinary source DMA. No previous-frame PCM or
one-block event delay is substituted.

The explicit final cleanup path is counted and must remain unused for a
nonblocking row to pass. Every measured full row reports zero cleanup waits,
zero transport failures and a completed T6 frame. CF continues rendering
while DSP work is pending. **HI08 remains reserved at IPL7 for each active
transaction**, and the DSP still executes the long-interrupt service. This
prototype does not establish unrestricted interrupt latency or a fully
independent background transport. Selector/ICR and pending stock HOTX
ownership follow the earlier wire protocol.

The same image supplies the CF control: `pk_nha_enabled=0` invokes the original
complete renderer through the same coordinator and sample-loop hooks. The
controls include the poll-call overhead but move no HI08 payload.

## Fit and exactness

Both DSP uploads are **byte-identical to the earlier exact prototype**.
The three-mode service remains 1,453 P words; shared occupancy remains
1,820/2,404 with 584 free, A private X 320/616 and A low Y 2,093/2,139.
The complete 4,805-sample classic ring stays in CF RAM. B retains one admitted
oscillator; its private-tail and guard remain physically unqualified.

New CF storage is 324 bytes of transaction state, 80 bytes of coordinator
state and 24 bytes of queue/split state, excluding counters. The measured
private-stack peak is **1,596/4,096 bytes**, versus 1,128 for this image's CF
control. All twelve retained FX code/dispatch bytes remain exact, and loaded
private/shared P is checked after PLAY with only known stock mask updates
allowed.

The independent native shadow observes **submit and commit**, rather than
mistaking submit's RTS for completion. Across the offload matrix it checks
**23,734 calls / 215,661 native samples**, with no PCM, full raw-state/ring,
hold or RNG mismatch and no pending unchecked call. Including CF controls:
**47,384 calls / 430,591 native samples**. The earlier original-ARM/IRQ-wire
corpus remains applicable through byte-identical DSP uploads and unchanged
codec/delay/kernel sources; it is not counted as a newly executed corpus.

Each offload row's transferred-word counter also matches its exact request
sizes: `calls × (18 + 2 × compact_words) + native_samples`, where compact
words are 28 for panel M1, 81 for M2 and 59 for M3. This distinguishes actual
payload progress from a silent fallback to CF.

## Combined workload

Every row requests 4,096 transport frames: WT V1 on T1, WT V2 on T2, Slap on
T5, Noise Hat on T6, four streaming stock STATIC tracks on T3/T4/T7/T8,
all twelve retained FX and real p-lock/LFO/scene control delivery. Startup,
pre-roll and playback use the checked native CF 264 MHz / PIT 132 MHz clock.
Counts below include pre-PLAY ISR work; differing row maxima are not aligned
per-frame deltas or a hardware lower bound.

| Panel mode | Offload peak µs | Same-image CF peak µs | Offload misses | CF misses | All eight audio chains |
|---|---:|---:|---:|---:|---|
| M1 white noise | 430.034 | 398.750 | 10 | 10 | Pass |
| M2 metallic | **494.034** | 417.030 | **587** | 10 | Pass |
| M3 pulse stack | 447.951 | 384.121 | 84 | 10 | Pass |

Offload ISR counts are 4,112 / 4,157 / 4,114; controls are
4,113 / 4,117 / 4,111. All have balanced ISR/private-stack returns, no DMA
source overlap, fence or ownership violation, sustained post-PLAY card reads
and correct native sample counts. A separate 1,024-frame pulse row with dirty
seed **456** also passes eight-track audio and 1,740 exact calls / 18,148
native samples, with zero cleanup waits or transport failures.

The protocol makes progress during useful CF computation, but packing,
unpacking, polling and the CF-owned delay still cost CPU time. The measured
result rejects this implementation as a timing solution; it does not rule
out a resident-state or different transport design. No saving is credited
from adding isolated renderer costs or subtracting the earlier different
image's maximum.

## Limits and reproduction

The isolated long-interrupt peripheral-clock correction from the first
prototype is still required. The integrated DSP scheduler uses its existing
4,532 **instructions** per sample, not cycle-accurate silicon timing. The
model cannot certify caches, SDRAM/card arbitration, interrupt/UI latency,
private-P prefetch boundaries or real HI08 timing. Fixed diagnostic family
selectors do not qualify ALGO/MODE migration, saved Parts or the complete
81-layout product map.

```sh
python3 tools/verify/build_perky_noise_hat_irq_audit.py
python3 tools/verify/measure_perky_noise_hat_irq_audit.py --dirty 123 --expect-audio-failure
python3 tools/verify/measure_perky_noise_hat_irq_audit.py --dirty 0
python3 tools/verify/measure_perky_noise_hat_irq_audit.py --dirty 123 --clear-amp-block --expect-audio-failure
python3 tools/perky/build_noise_hat_async_probe.py
python3 tools/verify/build_perky_noise_hat_async_observer.py
python3 tools/verify/measure_perky_noise_hat_async.py --reference
python3 tools/verify/measure_perky_noise_hat_async.py
make check REMIX=perky-machine
REFHASH_LOCAL=1 REFHASH_JOBS=1 scripts/refhash.sh check
```

The combined driver exits successfully for exactness, active audio, ownership
and nonblocking progress; the timing table still rejects admission. Normal
remix checks pass (84 shared gates and four image gates, with the stated
project-dependent skips). All 24 pre-edit local refhash artifacts/reports
remain identical; the baseline was not re-saved. No flash, push, default
emulator modification or hardware acceptance occurred.

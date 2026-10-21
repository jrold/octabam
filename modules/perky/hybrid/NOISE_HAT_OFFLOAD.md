# Split Noise Hat on DSP-A — 20 October 2026

**The prototype fits and reproduces the tested Noise Hat behavior exactly,
but fails the combined workload.** Synchronous HI08 exchange increases every
measured full-ISR peak over the same-image CF control. The pulse-stack row
also fails retained stock-track audio. This implementation does not enable
the full PERKONS voice layout and is not a flash candidate.

This is an opt-in experiment on the user-authorized `perky-cf-dsp-hybrid`
branch in the existing checkout. Source checkpoint:
`4eeae750caf8ba98144dd9ad8ac3b68299e21982`, plus the uncommitted sources
fingerprinted in the [compact receipt](NOISE_HAT_OFFLOAD.json). Full local
logs and generated evidence are under `out/perky/hybrid/noise-hat-offload/`.
PERKY4S remains the physically tested release.

## Implementation and ownership

The prototype executes the existing Noise Hat envelope, phase, filter and
three synthesis kernels on DSP-A at their placed PCs. It reuses the shared
exact RNG helper from the specialized B portfolio; A has no call into B's
private P. B retains one admitted oscillator, with its three relocated kernels
in the experimental private tail. There is no second B context exchange.

CF keeps the complete raw objects, control preparation, sample/hold and RNG
ownership, original five-tap delay body and **4,805-sample / 9,610-byte ring**.
It also keeps the existing rational 48 kHz to 44.1 kHz clock adapter. Classic
Noise Hat's delay/feedback arithmetic still runs on CF; this prototype moves
the inner synthesis only. Pulse stack has no wrapper delay pass.

For each native segment, CF packs only the active compact limb: 81 words for
metallic, 28 for white noise or 59 for pulse stack, plus six hold/RNG words.
The blocking request invokes DSP-A host vector `P:0x2c`, renders the segment,
and returns updated state, sideband and mono PCM. CF restores raw state and
applies the unchanged classic delay. No previous-block PCM is substituted.
The tested maximum request size is 19 samples; allocated capacity is 20.

The service preserves A/B, X/Y, R/N/M0–7 and LA/LC; RTI restores PC/SR.
CF preserves the GPIO selector and ICR, masks competing level-6 transfers
with IPL7, and preserves an already pending stock HOTX word across the
exchange. These are scoped protocol checks, not a claim that all stock
scheduling invariants are established: the pulse workload fails below.

## Measured code/data placement

The builder assembles and disassembles the actual relocated service, checks
all declared ranges, preserves all twelve retained FX code and dispatch
bytes, and verifies runtime/uploads by boot read-back. Each combined row
also reads loaded private/shared P after PLAY; only known stock packer-mask
self modifications are allowed.

| Resource | Prototype occupancy | Limit / remainder |
|---|---:|---:|
| DSP-A service and synthesis code | 1,453 P words | Distributed across A donors and shared gaps |
| A private P, including startup clear | 762 | 774 donor words; 12 free |
| B private P, including experimental tail/guard | 1,333 | Includes the previously measured 557-word relocation |
| Physically shared executable P, both portfolios and guard | 1,820 | 2,404; **584 free** |
| A private X allocations | 320 | 616; 296 unallocated |
| A low-Y tables | 2,093 | 2,139; 46 free |
| Classic ring on DSP | 0 | Complete ring remains in CF RAM |

A X allocations are `0x3800..0x3879` active state,
`0x3900..0x3977` scratch/sideband, `0x3980..0x39a8` stereo temporary PCM,
`0x39b0..0x39b4` request/pending word and `0x39c0..0x39e4` saved registers
(exclusive ends). Shared P/X/Y alias storage is counted once. Unused gaps
are not silently credited as a new contiguous allocation.

This is a local address/upload fit. B's private upper boundary and guard,
the new vector and context-save instruction forms remain physically
unqualified. No additional stock donor or effect was removed.

## Exactness evidence

The IRQ-wire gate executes the placed DSP instructions through actual HDI08
RX/TX and RTI, using the production CF codec and original delay body. Nine
original-author ARM capture cases cover all three modes and three control
corners: **2,304 native samples in 207 requests**, split into irregular sizes
1, 18, 7, 17, 16, 3 and 19. Each segment compares PCM, full raw state/ring,
RNG and hold to the independently qualified complete CF renderer. Final
PCM/state/RNG also match the ARM captures exactly. Receive destinations are
poisoned, nontrivial hardware-visible registers are seeded, and both pending
and empty stock-reply cases are exercised. Register/framing checks pass.

The live target observer runs the original complete CF renderer in a host
shadow using each actual CF call's input. This adds no target instructions.
Across the three offload rows it checks **23,730 calls / 215,627 native
samples**, with zero PCM, full raw-state, hold or RNG mismatches and no
unchecked pending call. Including the three controls: **47,370 calls /
430,470 native samples**. These counts include startup calls. They prove
the captured voice behavior, not exhaustive algorithm/mode switching or
saved-Part/backend migration.

## Combined measurement and rejection

Each row requests 4,096 transport frames with WT V1 on T1, WT V2 on T2,
Slap on T5 and Noise Hat on T6, four stock STATIC tracks on T3/T4/T7/T8,
all twelve retained FX, and real sequencer p-lock/LFO/scene control delivery.
Clock activation is checked in stdout: CF 264 MHz, PIT 132 MHz, with the
same cycle clock through startup, pre-roll and transport. Native render
counts confirm conversion is active. The control uses the **same image**
and changes only `pk_nha_enabled` to zero, invoking the original CF renderer.

| Panel mode (firmware mode) | Offload peak ISR µs | CF control peak µs | Offload misses | CF misses | Offload stock audio |
|---|---:|---:|---:|---:|---|
| M1 white noise (1) | 413.246 | 387.458 | 10 | 10 | Pass |
| M2 metallic (0) | **468.875** | 409.595 | **98** | 10 | Pass |
| M3 pulse stack (2) | 423.439 | 378.201 | 10 | 10 | **Fail** |

Deadline: **362.811791 µs**. Executed ISR counts, including pre-PLAY work,
are respectively 4,111 / 4,157 / 4,113 for offload and 4,111 / 4,115 / 4,110
for controls. These are observed row maxima, not aligned per-frame cost
differences or a hardware lower bound. The heaviest mode is panel M2;
the engine maps panel indices to firmware modes `{1, 0, 2}`.

All rows have balanced ISR/private-stack returns, no DMA overlap, fence or
ownership violations, and sustained post-PLAY card reads. Offload RPC reports
zero transport failures. The native shadow and P read-back pass in every row.
However, pulse stack has **zero post-FX significant samples on T4 and T7**;
T8 has only 61 and fails the same >64 gate. Their source PCM is active.
An unchanged repeat produces the same timing, exactness counts and audio
failure. The CF pulse control passes all eight tracks. The failing run exits
nonzero and retains `AUDIO_GATE_FAILED` in its structured row; its timing is
diagnostic evidence, not a qualified functional workload result. The cause
of this stock-audio regression is unresolved.

The [cooperative follow-up investigation](NOISE_HAT_ASYNC.md) subsequently
localized this failure to dirty stock AMP history before FX1. The same image
passes with clean DSP RAM. Live IRQ registers/stack are preserved, while the
tested nonblocking schedule passes all eight audio chains with dirty seed
123. The follow-up records the startup counterfactuals and their limits;
the original failed rows above remain failures.

The earlier all-CF 406.26 µs result used a different image and is not the
matched control here. It must not be subtracted to claim an offload saving.

## Instrument limits

The first live attempt stalled because the vendored DSP interpreter stops
its normal peripheral callback during a long interrupt. An isolated observer
continues the existing timed peripheral service inside that interrupt;
the default emulator/vendor implementation is untouched. A same-request
negative control disables the correction and must stall, while the corrected
request passes. Host observation does not advance the target clock.

The integrated DSP scheduler still uses its existing **4,532 instructions per
sample** schedule; this is not a DSP cycle-accurate hardware budget. The
standalone wire meter separately prices modeled instruction cycles and
excludes CF execution/host pacing. Its maxima vary with request length and
must not be presented as 16-sample source costs. Physical caches, SDRAM/card
contention, HI08 latency and UI response remain outside acceptance here.

## Decision, falsifiers and reproduction

**Reject this blocking, per-segment state-exchange design as a solution for
the requested full layout.** Code/data fit alone does not yield a CF saving,
and exact source synthesis does not establish preserved stock audio. A
different scheduling/transfer design or further CF reduction would require
fresh combined evidence. This result does not rule out every DSP-A offload.

The decision could be superseded by an exact implementation that passes all
eight audio chains and meets the unchanged combined deadline across an equal
or broader workload. Local fit/exactness claims would be falsified by upload
drift, unexpected writes, an original-author mismatch or physical boundary
failure. Full menus, interior ALGO/MODE locks, backend migration, saved-Part
lifecycle and the complete 81-layout map are not qualified by this prototype.

Use the existing local toolchains, original firmware assets and prior
placement-observer build. No firmware bytes or flash wrappers are checked in.

```sh
python3 tools/perky/build_noise_hat_offload_probe.py
python3 tools/verify/verify_perky_noise_hat_offload.py --wire
python3 tools/verify/build_perky_noise_hat_observer.py
python3 tools/verify/measure_perky_noise_hat_offload.py --reference
python3 tools/verify/measure_perky_noise_hat_offload.py
# Expected nonzero: pulse stock-audio failure; all rows retain measurements.
python3 tools/verify/measure_perky_noise_hat_offload.py --mode 2
make check REMIX=perky-machine
REFHASH_LOCAL=1 REFHASH_JOBS=1 scripts/refhash.sh check
```

The default remix floor passes (84 shared gates and four image gates; its
project-dependent skips do not qualify this candidate). All 24 local
pre-edit refhash configurations' artifacts and reports remain bit-identical;
the baseline was not re-saved. A final rebuild reproduces the measured MAIN
and runtime ELF hashes. The ordinary bus output is restored afterward.
No hardware acceptance, flash or push occurred.

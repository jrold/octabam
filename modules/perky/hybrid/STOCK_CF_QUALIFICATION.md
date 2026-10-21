# Stock and ColdFire optimization — 21 October 2026

**PKFM21 improves every matched sustained mean and peak, but remains held for
performance.** Resonant ISR means fall by 3.443–3.890 us and Slap means by
3.795–3.935 us relative to PKFM20. All eight cases preserve exact synth audio
and still fail six of seven unchanged budget ceilings. The final
[machine-readable qualification](STOCK_CF_QUALIFICATION.json) binds eighteen
proof receipts to this image: functional qualification passes, while the
verdict is `FAIL_HOLD / HOLD_FOR_PERFORMANCE_WORK`.

## Changes and proof

The starting stock profile reuses the proven observer with external 256-byte
address buckets. It exactly matches the 32,768-frame PKFM20 Slap/Noise-Tone
control's audio, target dumps, timing and final-card fixture. The residual
stock ISR bucket is 102.449 us/frame. Address aggregates suggest approximately
20.6 us in DELAY, 22.3 us in sample dispatch/render and 33.9 us in the frame
body, including 8.5 us in LFO/control buckets. These aggregates cross function
boundaries; the LFO subtotal overlaps the frame-body estimate. They are not
independent exact function timings.

The stock DELAY mixer now recognizes four exactly zero coefficient increments.
For that fixed sixteen-sample block it omits zero additions and repeated loop
control, retaining every source/ring access and MAC operation in its original
order. Other increments use the original loop. Its independent target proof
passes 4,096 cases: 2,458 fast and 1,638 fallback, with nine alias layouts,
eight MAC modes, complete registers/CCR/raw MAC state and 64 KiB of memory.
The isolated fast path saves 72.413 cycles/call; fallback dispatch costs
16.485 cycles/call. Eight eligible calls would save about 2.19 us/frame in that
isolated average. This does not establish the full workload's hit rate or
isolate the contribution to its measured gain.

CF interpolation now multiplies the signed sample difference directly, with
an exact coefficient adjustment for negative differences. The final linked
gate passes 19,267,437 exhaustive rational quotient cases and 9,996 actual CF
calls, including every phase, output length 0–16, extreme/random samples,
clock/carry state, PCM guards, MAC state and callee-saved registers. Native
48 kHz synthesis, 44.1 kHz output and exact rounding remain unchanged.

Bounded packet publish/clear paths use computed entries into unrolled loops.
Every read and write remains in its original order; clears are retained.
An 8,192-case target proof checks aliased memory, output guards, C ABI, SR mask
and raw MAC state, with independent same-image predictor controls. Separate
binding reconstructs the executed binary from its ELF, privately replays it,
and checks both ordinary helper bodies after the packaged image really boots.

Slap uses rolling ring pointers only when all five dynamic tap spans and the
write span avoid wrapping. Tap/gain metadata stays dynamic and every rejected
span uses the original generic helper. Its separate proof checks 2,880 native
PCM/state/RNG/clock frames and 76,880 full-ring/metadata/guard/ABI cases per
variant. A fresh private replay binds the loaded binary/symbols to the pinned
ELF, verifies the sole generic-fallback relocation and final source relink,
then checks helper, caller and actual loader readbacks. These wide standalone
cases are separate from actual-image source and linked-kernel qualification.

Diagnostic trace loops are outlined from the normal segment register frame,
reducing that frame from 100 to 80 bytes. The flag remains live. The new
source gate checks trace contents for CF voices 1–3 with tracing disabled for
2,686 frames and enabled for 2,669. No isolated timing saving is credited to
this change; the combined profile's segment cost rises slightly.

## Matched full workloads

Each case runs 32,768 sixteen-sample transport blocks, 11.889 seconds at
44.1 kHz. T1/T2 run WT V1/V2, T5 runs Slap, Resonant Snare, Resonant Bass or
sequenced Snare/Bass MODE locks, and T6 runs DSP-A metallic Hat or CF Noise/Tone
mode 1. Four stock sample tracks and all fourteen FX remain active. Noise/Tone
on T6 puts all four source voices on CF. Cards, all sixteen banks' Part/pattern
bytes and MODE locks match the immediate PKFM20 controls. PKFM17 evidence
remains preserved ancestry.

Steady means exclude the first 512 completed ISRs; peaks include the complete
capture. Total CF uses exact playback cycles over all 32,768 blocks, including
background work. All values below are local model microseconds.

| T5 | T6 | ISR mean, PKFM20 → PKFM21 | Full ISR peak, PKFM20 → PKFM21 | Total CF mean, PKFM20 → PKFM21 |
|---|---|---:|---:|---:|
| **Fixed ceiling** | — | **158.212** | **250.712** | **189.298** |
| Slap | Metallic Hat | 207.132 → 203.338 | 302.473 → 298.803 | 232.863 → 229.112 |
| Snare | Metallic Hat | 200.593 → 197.150 | 303.621 → 298.818 | 226.353 → 222.939 |
| Bass | Metallic Hat | 200.012 → 196.443 | 302.322 → 298.102 | 225.738 → 222.218 |
| Snare/Bass MODE locks | Metallic Hat | 200.292 → 196.767 | 302.769 → 298.337 | 226.037 → 222.555 |
| Slap | Noise/Tone | 218.918 → 214.982 | 308.352 → 303.652 | 244.643 → 240.727 |
| Snare | Noise/Tone | 212.479 → 208.588 | 309.614 → 305.186 | 238.200 → 234.298 |
| Bass | Noise/Tone | 211.950 → 208.141 | 308.019 → 304.042 | 237.659 → 233.851 |
| Snare/Bass MODE locks | Noise/Tone | 212.190 → 208.325 | 309.417 → 305.148 | 237.905 → 234.038 |

Every matched sustained peak falls by 3.670–4.803 us. The highest peak among
the eight cases falls from 309.614 to 305.186 us. Only the ACK peak ceiling
passes; ISR mean/p99/p99.9/peak, total CF mean and ACK p99 still fail.
The worst-mean case, Slap/Noise-Tone, is 214.982 us ISR and
240.727 us total CF, against frozen ceilings of 158.212/189.298 us. That case
still needs 26.4% less ISR work and 21.4% less total CF work. The fixed budget
has not been relaxed. Zero nominal deadline misses does not satisfy it.

## Remaining costs

The final Slap/Noise-Tone cost run exactly matches its unprofiled run's source
audio, target dumps, transport, ISR histograms, CPU cycles and final-card
witness. The raw exclusive maps give these consistent groups:

| Exclusive steady cost, us/frame | PKFM20 | PKFM21 |
|---|---:|---:|
| Stock ISR, DELAY helper, mixer and stock position | 106.832 | 104.201 |
| WT synthesis | 27.327 | 27.468 |
| Slap, including span fast body, generic delay and filter | 24.774 | 24.530 |
| Noise/Tone synthesis | 17.146 | 17.450 |
| Rational conversion | 7.118 | 6.395 |
| Packet publish and clear | 4.139 | 3.011 |
| Segment handling | 6.118 | 6.146 |
| Background total | 25.982 | 26.000 |

Moving stock instructions into a named helper does not count as a saving:
the stock group includes that helper. Likewise Slap includes its separately
named fast body. Stock falls 2.631 us/frame, conversion 0.723 us and publication
1.128 us in this combined profile. Some other groups rise. These are image-level
attribution differences, not independently isolated causal savings to sum.
The raw memberships are retained in `EXCLUSIVE_PKFM20_PKFM21.json`.

Further stock DELAY filter and LFO review did not find another substantial
shortcut with equally strong proof. Those paths already pair assembly MACs
with loads. No zero-product shortcut that depends on unproven MACSR/PAV
behavior is admitted. Stock background remains about 25.785 us/frame; the
large remaining mean gap requires more than these bounded local changes.

## Functional and lifecycle scope

The new image passes 5,355 direct source frames across 81 algorithm layouts,
24 directed transitions, three mode rotations and every split 0–16, comparing
PCM and raw CF objects with independent original-source histories and checking
T6 shared RNG and DSP state separately.
Handoff passes 800 actual-image frames, both owners, pending jobs, delayed
feedback, startup poison and full transport/ring wraps. Linked NT/AH/Slap
gates pass 528/792/792 calls, including edge lengths, full state, guards,
RNG/hold and invalid-table returns. Ten scheduled-DMA cases pass.

Production lifecycle passes 52,572 entries and completed returns, 43 events,
seven generations, STOP/START, Part/Bank changes and 22 backend switches.
Eleven snapshots, 770 replay frames and 781 completed handoff jobs exercise
the real path without source, transport, ownership, stack or DMA errors.
The observed full ISR peak is 323.814 us. Scene/fader delivery passes 9,043
entries / 9,042 returns with all eight outputs active and a 297.568 us peak.
These interactive captures have their own durations and are not matched
32,768-block peak benchmarks. An in-flight ISR at quit is recorded explicitly.
Both observed peaks still fail the separate 250.712 us ceiling.

The selector sweep passes all 243 tested tuples across four sequencer
patterns, with none missing, over 160,224 entries and completed returns.
Its peak is 328.580 us, with no nominal deadline misses or source, transport,
ownership, stack or DMA violations. It still fails the calibrated peak
ceiling. The observed private stack peak is 1,244 bytes within 4,096 bytes.
These 243 tuples cover the declared sweep, not every possible cross-product
of all algorithm and mode choices.

Sustained observations compare original-reference synth PCM and DSP Hat
state/side/clock/feedback. They do not compare every raw CF object on every
sustained block; the direct gate supplies separate full-state evidence.
Significant source/post-FX counts and continuing card reads establish activity
on eight audio chains. They do not establish uninterrupted stock PCM on every
frame, and deliberately removed bulk dumps cannot be replayed from aggregate
counts. DSP-only snapshot and stock-FX evidence is reused only after actual
A/B upload bytes match PKFM20 and PKFM17; changed CF paths are newly exercised.

## Artifact and budget identity

MAIN SHA256: `484a0b9380670e15b31a0c06589f88066a861b93482504adecffd9a49840dfc3`.
ELF SHA256: `7231cd51f9e54613c47aad0da7dd3f7df06e3022a2ffb9f7bd388cd53f7786a6`.
CF text is 578,396 bytes, 1,104 more than PKFM20; data/BSS remain
588/1,612,664 bytes. DSP allocations, uploads, DMA words and source latency
are unchanged. Slap's bounded helper uses 44 more private stack bytes on its
own call; final actual-image stack gates enforce the existing 4,096-byte
capacity rather than assuming standalone stack costs add to a whole ISR.

The existing `perky-cf-dsp-hybrid` checkout and source checkpoint
`4eeae750caf8ba98144dd9ad8ac3b68299e21982` plus 110 dirty source hashes were
used. New evidence is under `out/perky/hybrid/full-map-stock-cf-v1/`;
measurements and matched profiles are under
`out/perky/hybrid/stock-cf-optimization/`. The profile used to locate stock
work remains under `out/perky/hybrid/stock-isr-next-profile-v1/`.
The build's `OPTIMIZATION_PROOFS.json` indexes the final receipts. Its
`FINAL_SOURCE_SNAPSHOT.json` and `FINAL_SOURCE.tar.gz` retain the exact source
and JSON/text receipts without firmware, uploads, card images or audio assets.

The timing observer remains
`f975b4d2c4b6a2d993d3158bc8e68c8a786b328e2902b58bdde418225287d022`;
the budget remains
`8608844b96c6f20daed514147dc6cadab7a2c82aae80d2ef7c9a875a22ccaec4`.
CF/PIT clocks remain 264/132 MHz with uniform startup/pre-roll/transport
cycle-clock x1.00. Seven ceilings remain ISR mean/p99/p99.9/peak
158.212/166.780/237.731/250.712 us, total CF mean 189.298 us and ACK
p99/peak 328.000/362.212 us.

`make check REMIX=perky-machine`, `scripts/refhash.sh check` and
`make bus REMIX=perky-machine` all returned zero. All runnable default checks
passed with fixture-dependent skips retained, all 24 reference configurations
were bit-identical, and the standard output was restored to SHA256
`c9e292bec49f54820355c76dca904c5dc02d1378120f7a34042c10dfe1bbe1a4`.
All eight measurement commands and the actual-image functional gates returned
zero. The final qualifier returned one with a fresh `FAIL_HOLD` receipt because
the performance budget fails; all functional and provenance checks passed.

This calibrated model screen does not establish physical cache, SDRAM/card/bus
contention, IRQ timing or UI acceptance. It does not settle the user's earlier
greater Resonant burden on hardware. PERKY4S remains the hardware-tested release.
No flash, package, push or release commit was made.

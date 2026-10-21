# Resident Hat state handoff — 21 October 2026

PKFM15 replaces the continuously executed CF Hat synthesis shadow with an
on-demand, nonblocking DSP state handoff. The hardware-informed
[performance budget](EMULATOR_BUDGET.md), CF264/PIT132 clocks and measuring
binary remain unchanged. All five sustained rows fail the frozen performance
gate despite exact audio and removal of duplicate work. This experiment remains
held for performance work; it is not a hardware release.

## Ownership and transport

DSP-A keeps producing current-frame Hat audio while a requested fallback is
prepared. At a source-frame boundary it freezes all 180 compact state words,
six hold/RNG words and three native-clock words, with the request's sequence.
The 190-word payload and cursor occupy Y:07a5..0863, reclaimed from retired A
oscillator wave data within the existing PERKY allocation. The live envelope
and clock tables begin at 09a5, 0c51 and 0f3f and remain unchanged.

The existing 24-halfword feedback mailbox keeps its normal ring-write count
and ring words. An offset in its fourth word identifies snapshot chunks placed
only after the normal ring payload. A frame carrying 17/18 ring writes has
three/two spare halfwords. No extra DMA transaction, word count, source packet
latency, host-port polling or interrupt-mask hold is introduced.

CF logs only the tail after a requested snapshot. While bytes are still arriving
it publishes no runnable catch-up jobs, so the ordinary idle path can remain
idle. After receiving a complete sequence/generation-bound snapshot, main
imports it and replays the logged tail with interrupts enabled. DSP continues
rendering until main has caught up exactly; audio changes owner only at a
callback boundary. CF ring storage and the lightweight shared-RNG/control
maintenance remain necessary for exact sample timing and other algorithms.

Normal DSP ownership performs no CF Hat inner synthesis, no replay and no
snapshot requests. CF fallback uses its original renderer once. Returning to
DSP drains old work and exports changed limbs through the existing scheduled
import path. All original source precision, sample-rate conversion, controls,
shared RNG and algorithm histories are retained.

Cancellation invalidates the request without overwriting a live worker's raw
state. IRQ and main completion have separate writers, and a new request cannot
start until pending jobs have retired. Boot initializes the epoch explicitly;
production generation changes invalidate it without resetting the worker under
an interrupt. The [publication trap](../../../docs/contributing/TRAPS.md#trap-epoch-publication)
records the source audit and the rejected CF counter probe.

## Direct proofs and memory

- DSP snapshot proof: **400 frames**, four coherent captures, three complete
  streams and one generation-cancelled stream, with **5,403 ring-feedback words**
  unchanged versus PKFM11. Every PCM sample, compact state, side/RNG and clock
  comparison passes, with significant positive and negative audio in each mode.
- The retired Y payload is poisoned before execution. A positively calibrated
  actual-DSP read watch sees no synthesis reads or writes there before the first
  request. Frozen payload words change only on capture and stay immutable while
  ordinary rendering continues.
- Actual CF/DSP handoff proof: **800 frames**, six complete backend changes,
  sequence wrap, cancelled requests and a poisoned pre-audio epoch reset.
  Independent original PCM/full compact state/RNG/hold/native-clock comparisons
  pass. Its 166 inner-renderer calls and 129 replay frames occur only during
  requested catch-up; initial and final steady intervals have zero such work.
- Full 32-bit transport and native ring-counter wraps, exact-zero takeover and
  repeated-zero feedback pass through the actual source entry. A separate
  ten-case actual-DMA gate checks cold startup, active sequence zero, both ping
  banks, exact mailbox extraction and all carrier/neighboring bytes.
- Shared custom P: **2,312/2,404 words**, 92 free. No private-P donor/tail or
  extra private-X allocation. Reusing 191 existing low-Y words leaves the
  reservation and its 2,093/2,139-word overall occupancy unchanged.
- All fourteen stock FX implementations, both dispatch tables and all original
  stock P/X/Y words remain exact. B's private program/data are identical to
  PKFM11. A's private changes are limited to its relocated callback targets and
  the declared retired-wave initializer.

Candidate MAIN:
`a472d1ac1ce6d6f919f00eed84cda99b67bacf98ed237b4a7640e7c3733f2fe1`.
Runtime ELF:
`a871cf07d98882f22b71e28e7889f38b4d607637d0612102b5450e3973e3a573`.
Source checkpoint: `4eeae750caf8ba98144dd9ad8ac3b68299e21982` plus the
captured uncommitted implementation hashes; this is not a release commit.
Actual uploads, source snapshot, direct fixtures, generated C/assembly and
receipts remain local at `out/perky/hybrid/full-map-state-v4/`.

PKFM12's partial campaign stopped for the deterministic boot-epoch correction.
PKFM13 completed its original gates, then failed the added full-sequence-wrap
ownership test; PKFM14 failed the repeated-zero return test. Their sources and
receipts remain preserved locally. PKFM15 includes the three startup/zero-return
repairs described below and reruns qualification on its own image. The earlier
PKFM6/PKFM11 receipts and external hardware handoff remain unchanged.

## Startup and sequence wrap

An explicit transport-started latch replaces sequence zero as a startup test
in both ownership selection and actual DMA extraction. It is reset before
audio and published with real source packets, including the first packet after
CF-owned startup. Last-consumed validity has its own reset flag; a valid wrapped
zero return can be deduplicated normally. Reset also invalidates stale mailbox
magic. These repairs are candidate-only; historical prototype sources remain
unchanged.

The directed source trajectory starts near `0xffffff80`, crosses full transport
wrap during snapshot collection, then requests CF at exact sequence zero.
DSP must keep rendering while a fresh snapshot arms. Repeating the consumed
zero mailbox advances neither consumption, ring writes nor snapshot position.
An empty issued/committed ring starts near `0xfffffff0` and wraps through real
native writes. These are pre-trajectory counter fixtures; no synthesis state is
repaired during the audio comparison. PKFM13 fails the ownership assertion at
frame 128; PKFM14 passes that assertion and fails repeated-zero feedback at
frame 131. Their separate negative-control logs preserve those falsifiers.

## Fixed-budget result

Every row requests **16,384 transport frames**, with WT/WT + Slap and the listed
fourth source, streaming stock samples, all eight track outputs and all fourteen
stock FX active. All independent original-reference PCM/state/RNG/clock and
normal feedback comparisons pass. Every no-shadow counter is zero, and actual
DSP transport issue/consumption remains positive. The same-image directed
handoff receipt is bound to each row; positive worker activity there makes the
steady zero count meaningful.

| Fourth source | ISR mean, us | ISR p99, us | Full ISR max, us | Total CF mean, PKFM11 → PKFM15, us | Budget |
|---|---:|---:|---:|---:|---|
| **Fixed target** | **158.212** | **166.780** | **250.712** | **189.298** | All seven ceilings required |
| White Hat | 223.287 | 232.674 | 315.784 | 268.877 → **249.200** | FAIL |
| Metallic Hat | 222.128 | 231.686 | 315.265 | 281.344 → **248.054** | FAIL |
| Pulse Hat | 212.159 | 221.852 | 306.519 | 262.915 → **238.074** | FAIL |
| Noise/Tone | 232.366 | 241.886 | 319.178 | 257.893 → **258.174** | FAIL |
| Acoustic Hats | 228.840 | 254.367 | 329.000 | 255.366 → **254.924** | FAIL |

Metallic Hat saves **33.290 us/frame of total CF work** (11.8% from PKFM11),
while its ISR falls only 0.279 us. The duplicate background synthesis is gone;
lightweight CF controls/RNG, the CF ring and regular stock background work
remain. White and pulse also improve; Noise/Tone and Acoustic were already
CF alternatives and change by less than 0.5 us in total mean. Noise/Tone
regresses 0.281 us. Small individual timing
variations accompany the changed code placement and instruction history;
no claim is made that every metric improved.

The remaining metallic gap is **63.917 us in ISR mean** and **58.756 us in total
CF mean**. Reaching the target requires about **28.8% less ISR work** from this
cost. Removing the background Hat shadow by itself does not admit the current
voice placement. The budget was neither recalibrated nor replaced with a
nominal 362.812 us deadline check.

## Completed workload and lifecycle qualification

The [machine-readable receipt](STATE_HANDOFF_QUALIFICATION.json) binds the
actual image, runtime, generated program, source hashes, fixed observer and
unchanged budget to the completed campaign. Its functional verdict is
`PASS_EXACT_AUDIO_AND_NONBLOCKING_STATE_HANDOFF_MODEL_SCOPE`; its overall
verdict is **`FAIL_HOLD / HOLD_FOR_PERFORMANCE_WORK`**.

| Executed check | Coverage | Result |
|---|---|---|
| Independent source gate | 5,355 frames; 81 layouts plus 24 transitions, three rotated modes and 17 split points | Exact PCM, compact state, shared RNG and native clock |
| Actual DMA helper | Ten startup/active cases, full sequence wrap and both ping banks | Exact mail, all 48 carrier clears, surrounding bytes and counters |
| Sustained combined workload | Five rows × 16,384 requested frames; WT/WT, Slap, all stock tracks and fourteen FX | Exact source and feedback; all eight outputs active; zero continuous CF Hat work; all five budget failures |
| Production layout sweep | 243 tuples, four patterns, 160,034 frames | No missing tuples or audio/state differences; no continuous CF Hat synthesis, requests or worker jobs |
| Production lifecycle | 53,229 frames, 22 backend changes and seven generations, including STOP/START, Part/Bank and mode/backend changes | Exact PCM/state/RNG/clock/feedback; 11 complete snapshots and 824 replay frames |
| Scene/fader workload | 9,126 frames | Exact source and active workload |

There are no nominal deadline misses in these port runs. The lifecycle,
layout and scene/fader full-ISR peaks are **345.674**, **346.697** and
**314.246 us** respectively. Each exceeds the fixed **250.712 us** full-ISR
ceiling; all four assessed ISR ceilings fail for each interactive run.
Each sustained row fails six of seven ceilings; only its whole-CPU ACK peak
passes. Interactive whole-CPU
ACK statistics were not captured, so no whole-CPU interactive claim is made.
Snapshot collection leaves runnable job counts at zero until a complete state
arrives; the lifecycle's 835 actual jobs include 11 imports and 824 replays.

The standard repository floor also passes: `make check REMIX=perky-machine`
reports **all runnable checks passed**, and `REFHASH_LOCAL=1 scripts/refhash.sh
check` reports **all 24 configurations bit-identical** against the existing
local baseline, which was not re-saved. The default floor retains its recorded
missing-canary/odd-access/optional-project skips. The candidate's actual full
card, source, stock-FX, lifecycle and layout runs above provide their separately
stated coverage; they do not turn those default skips into passes.

The final campaign binding command is:

```sh
.venv/bin/python tools/verify/qualify_hat_state_campaign.py \
  --build out/perky/hybrid/full-map-state-v4
```

It exits **1 deliberately**, after validating all functional receipts and
writing the failed performance admission. The measuring observer SHA256 is
`f975b4d2c4b6a2d993d3158bc8e68c8a786b328e2902b58bdde418225287d022`;
the frozen budget SHA256 is
`8608844b96c6f20daed514147dc6cadab7a2c82aae80d2ef7c9a875a22ccaec4`.
Prebuild sources and final verification sources are preserved alongside the
local receipts. PKFM12's interrupted generated cards and temporary project
copies were removed after recording cleanup; source inputs and its failed
instrument experiment remain preserved.

No candidate was flashed, pushed or packaged for hardware acceptance. The
ordinary output image was restored with `make bus REMIX=perky-machine` after
the candidate build; the experimental
candidate remains under its own work directory. PERKY4S retains its physical
release status. The removed duplicate work is measured; safe Octatrack
performance for this placement is still unproven and the fixed local target
is still unmet.

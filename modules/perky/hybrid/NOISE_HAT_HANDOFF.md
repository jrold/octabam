# Noise Hat: nonblocking backend handoff

**Pass with timing headroom in the local model; hardware unqualified.**
PKNHF7 fixes the PKNHF6 backend-switching regression while keeping the Slap
assembly kernel and exact original synthesis behavior. The switching maximum
falls from **89,715 to 87,413 cycles / 331.109848 µs**, below PKNHF5's 88,270.
All workload and lifecycle tests pass. The tightest result is continuous CF
calibration at **345.378788 µs** against **362.811791 µs**, leaving
**4,602.313 modeled CF cycles / 17.433004 µs**. That calibration peak is 28
cycles / 0.106061 µs above F6; panel, switching, white and metallic maxima
improve. Pulse rises by 63 cycles / 0.238636 µs. The overall reserve remains 564 cycles above
F5. These are local model measurements; no flash release is produced.

The admitted measured placement is CF WT/WT on T1/T2 and Slap on T5, with
resident Noise Hat on DSP-A/T6. T3/T4/T7/T8 carry the stock fixture, with all
eight tracks active and twelve retained FX across sixteen slots. This result
does not admit every family combination or a second B oscillator.

Machine-readable receipts: [NOISE_HAT_HANDOFF.json](NOISE_HAT_HANDOFF.json).
Source checkpoint and every implementation/input hash are recorded there;
there is no release commit. MAIN OS SHA256:
`3e3699637ca27e9c6a3908ce4859419ffe2fa974a907bb5a33f8e37d27607bab`.

| Run | Returned ISRs | Exact Hat source frames | Peak full ISR (µs) | Misses |
|---|---:|---:|---:|---:|
| Continuous CF calibration, all modes | 4,897 | 4,897 | 345.379 | 0 |
| 18 live backend transitions | 9,666 | 9,664 | 331.110 | 0 |
| Both-backend STOP/START, Part 1→3→1, playing Bank A→B→A | 51,703 | 51,701 | 336.489 | 0 |
| WT/WT + Slap + white Hat | 16,397 | 16,395 | 320.379 | 0 |
| WT/WT + Slap + metallic Hat | 16,397 | 16,395 | 324.890 | 0 |
| WT/WT + Slap + pulse Hat | 16,396 | 16,394 | 312.102 | 0 |

Across these runs **115,446 emitted Hat source frames** and **115,456 original
Hat control calls** have zero mismatches. Source PCM, compact dynamics,
RNG/hold, phase/carry, feedback and committed ring checks all pass. The Slap
witness checks **223,683 actual renderer calls / 2,010,741 native samples**,
with zero PCM, full raw-state/ring or RNG differences. Two DSP source jobs may
still be queued at capture end; all lifecycle ISRs returned in this rerun.
The receipts retain these tails instead of counting them as observed audio.

The backend run drains 18 old feedback jobs after CF takeover; the panel run
drains six more. Maximum feedback age is three source frames, with at most
52 pending classic writes. No old blocking RPC executes. Transport, worker
clock, queue overflow, DMA overlap/restart, stack/guard and private-ownership
error counts are zero. The steady DSP rows finish with **0 / 12 / 2** shadow
jobs outstanding after over 16,384 frames each; publication occupancy peaks
are **126 / 156 / 103** including the just-published job, against 1,024 slots.
The switching peak publication occupancy is 217; the panel peak is 172.
The panel performs 117 successful card-sector writes and executes the pinned
PIO first-sector fix 15 times, with zero card write errors.

The unchanged repository floor passes **84 shared + 4 image gates**. The
current local refhash check reports **all 24 configurations bit-identical**,
and restores the default bus image to SHA256
`354bdac8f2fe79696b3156a034894b1bd0d5f757ce76657ca608851089268a58`.

The previous [PKNHE1 lifecycle campaign](NOISE_HAT_LIFECYCLE.md) rejected live
switching: six transport errors, stale CF histories/clock, and no continuous
audio proof after departure. Those historical results remain valid for that
image.

## Ownership and transport

`pk_nhr_enabled` is a request. `pk_nhb_owner` identifies the renderer that will
produce a frame. A callback never waits for a request to become eligible.

While A renders, main's interruptible idle loop advances a private copy of the
original **inner** Noise Hat renderer. A bounded publication queue carries the
actual two segments, control patches and five taps for the retained sample.
The shadow needs the final rational phase and carry, not sixteen interpolated
outputs. Its clock update is the closed form of the existing converter. The
single retained classic sample uses the original five delay stages, signed
shifts, saturation and int16 wrap. Ring writes remain the scheduled DSP DMA
replies; the shadow does not recompute a second delay line.

A DSP→CF request becomes eligible only when the inner shadow has caught up.
The callback copies compact dynamics, hold/RNG and phase/carry, and advances
the logical CF ring cursor to the next native sample. Outstanding DSP replies
continue to fill their original ring positions. They do not move the new CF
cursor. The first CF tap is 573 native samples behind that cursor; the pending
span plus CF advancement during retirement is checked against that bound.
There is no audio queue and no wait for those replies in the callback.

While CF renders, ordinary PCM occupies the first 80 source halfwords. Up to
86 of the remaining 88 halfwords carry one complete active limb, phase and
signed carry; the white limb also carries global hold/RNG. Frozen inactive
limbs are sent first after a mode change. A CF→DSP request waits until every
changed limb has been sent, the shadow has caught up, and every old DSP job
has actually drained. The next source packet renders on A. Ordered stock
source DMA places the imports before that render packet.

All three CF-entry and subsequent 80 ms CF dwell snapshots show sequence and
consumed counters equal. The continuous witness also checks the old jobs that
retire before those snapshots. Takeover remains nonblocking; the qualification
bound permits up to three source frames of feedback age.

The DMA reader keeps collecting and stripping the 24-word return carrier
regardless of the requested backend. Repeated sequence tags are idempotent;
unknown tags still fail. Neither sequence nor consumed-job counters are
reset to hide outstanding work. Queue overflow or a shadow clock fault
latches the migration state invalid and leaves the current renderer active.

No new HI08 transaction, DMA word, IPL7 hold or source-audio latency is added.
The old blocking RPC remains linked in the experiment; the live witness counts
entries to it explicitly and qualification requires zero.

## PKNHF5 profile-guided ColdFire changes

The preserved PKNHF1 profile reproduces the 95,780-cycle worst frame. That
frame is already owned by CF after takeover. Hat rendering costs 11,973 cycles,
source-segment work 6,641, stock work 46,598 and state codec only 596. This
measured attribution redirected the work from the handoff codec to the render
path. A codec-only experiment remained exact but missed three deadlines and
was withdrawn. Exact C division alone still left a 95,720-cycle peak.

PKNHF5 keeps the original C synthesis arithmetic. For metallic mode, six
independent oscillator blocks and then four serial filter blocks run across
the short native block. Each recurrence and the oscillator summation order are
preserved; fewer histories compete for CF registers. Calls above 20 samples
retain the original body. White and pulse synthesis are unchanged. A generated
source hash pins the original renderer, and complete raw-state, ring, RNG,
hold and PCM comparisons cover all nine captured ARM continuations.

Only the rational sample converter becomes a small CF assembly helper. A
4,672-entry table splits exact division by 147 into high/low parts. The
remaining bounded multiply and shift preserve signed floor rounding. The
shared original C converter remains the independent oracle. Exhaustive audio
numerators plus general-u32 checks cover 306,279,667 division cases; 145,504
complete clock/conversion cases cover phase, carry, chunking and resets.
The actual CF assembly passes 39,984 converter cases over all 147 phases,
with callee-save register canaries, plus 3,456 combined renderer frames.

Empty CF prefixes no longer publish an unchanged state snapshot. Snapshot
coalescing was tried in an intermediate image and is absent from PKNHF5.
Neither DSP upload changes from PKNHF1. There is no new DMA format, audio queue,
transport latency or IPL7 hold.

An intermediate PKNHF3 panel run froze twice in stock PIO card handling on the
third STOP/START, at `0x40015524`. The observed wait and pending IRQ match the
previously established first-sector race in
[STEM_REC.md section 11.7](../../../docs/firmware/STEM_REC.md); the exact new
preemption window is inferred from that prior proof. This is separate from
the passing audio comparisons. PKNHF5 explicitly includes Yves Rosius's
existing `stems_ata_first` fix. The author's own `REMIX=stems` build runs first;
the relocated 52-byte function and the 54-byte reference unit including its
preceding RTS must match that build exactly. No full STEMS recorder is added.
The panel witness records actual fix entries, successful card writes and PIO
mode (the stock unsupported-UDMA sentinel is 255), with no quiet retry of a
failed START. See the [retiming trap](../../../docs/contributing/TRAPS.md#trap-pio-retiming).

## PKNHF6 CF synthesis assembly (historical measurements)

A fresh read-only PKNHF5 CF-calibration profile reproduces every normal
completed-ISR cycle total, including the 91,744-cycle maximum. On that maximum,
metallic Hat costs 10,492 cycles, Slap 7,773 and WT rendering 7,209 plus 1,064
for WT pitch conversion. Stock work remains 46,747 cycles. This identifies
synthesis costs without treating all non-synthesis time as recoverable.

The follow-up keeps the five-stage delay recurrence and uses two small CF
assembly entries for the existing Hat and Slap compact state layouts. The ring
stays little-endian int16; temporary input/output samples are native int32.
Each tap uses the exact modulo-32-bit identity
`gain*(stage + delayed) - (stage << 4)` before the original signed shift and
clamp. Signed mix arithmetic, index wrap and final int16 writes retain their
original order. No EMAC accumulator, MACSR or interrupt mask is touched.
Ring-independent inner samples are generated first, followed by the original
serial delay recurrence in the same renderer call. Blocks above 20 samples
retain the original C body. No source queue or latency is added.

A register-resident filter-block prototype remained exact but did not improve
the combined workload, so it was withdrawn. Early delay versions also showed
that converting compact metadata to a wider temporary structure can erase
assembly gains. The retained kernel reads each renderer's existing native
compact structure directly. White and metallic Hat use it; pulse synthesis
and WT synthesis remain unchanged.

The actual target assembly passes 72,660 direct cases across native-wide,
Hat-compact and Slap-compact layouts, all ring indices, counts 0..20, overflow
inputs and signed mix values. Every case compares the complete ring plus its
guard, PCM, metadata and callee-save registers. The renderer differential
adds 13,824 actual CF frames, 9,288 complete raw-state snapshots and 482,040
native samples against the unchanged original C. The paired microbenchmark
measures these aggregate costs in its solo rows:

| Path | C mean cycles | Assembly mean cycles | Reduction |
|---|---:|---:|---:|
| Slap, mode 1 sweep | 9,688.6 | 9,058.5 | 6.5% |
| Metallic Hat sweep | 15,049.0 | 14,694.2 | 2.4% |
| White Hat sweep | 18,602.7 | 18,327.9 | 1.5% |

Those are isolated synthesis measurements, not complete-ISR savings. All
WT/WT + Slap + Hat layout means in that campaign improve. A new read-only
full-workload witness also compares each actual Slap native-render call with
the unchanged original C, including the complete raw object/ring and RNG.
It uses the actual entry state for this pure-renderer differential. The
Noise Hat migration witness remains a separately evolving persistent stream.
The campaign binder compares both linked delay function bodies directly with
the target assembly exercised by the standalone gate. At the two CF-calibration
maxima, Slap's render-plus-delay buckets total 7,773 cycles in F5 and 7,163 in
F6; Hat's equivalent total is 10,709 and 10,688. WT plus pitch conversion is
8,273 in both. These are observed worst-frame attributions, not a claim that
the two maxima have identical inputs. The complete ISR improves by 592 cycles;
all frame, peak and cycle-sum observations reproduce without profiling.

| Complete run peak (µs) | PKNHF5 | PKNHF6 |
|---|---:|---:|
| CF calibration | 347.515 | 345.273 |
| Backend switching | 334.356 | 339.830 |
| STOP/START, Part and Bank changes | 341.492 | 336.754 |
| White full workload | 324.720 | 320.723 |
| Metallic full workload | 328.818 | 325.739 |
| Pulse full workload | 315.742 | 311.864 |

The source data and control schedule are the same, but faster callbacks change
which events coincide within a frame. The switching peak's regression is
retained explicitly; the worst across the complete suite still improves.

## PKNHF7 switching regression fix

A fresh F6 profile places its 89,715-cycle peak at frame 8,958, already owned
by CF before and after the callback. It follows a rapid white-to-metallic
change: source split 13, trigger 1, phase 125. Metallic rendering and delay
consume 10,890 cycles, Slap 7,206, WT plus pitch 8,266 and stock work 46,178;
the state codec costs 596. This identifies synthesis overlap as a worthwhile
optimization target. It does not attribute the whole regression to copying
ownership state. Different callback costs also change handoff eligibility and
which source events share a frame.

The original classic-Hat velocity scaler already returns signed int16. The
new short-block path keeps those native samples in the destination buffer,
avoiding the int32 temporary and final copy. A guarded assembly specialization
uses the actual five taps (573/1201/1538/3139/4804) and gains (1/1/3/5/7).
Every call checks all ten metadata words and the ring cursor; altered metadata
uses the original C recurrence. No initialization value is assumed invariant.
Blocks above 20 samples retain the original C body.

For signed int16 stage and delayed sample, each gain product fits int32.
The exact identity `(gain*(stage+delayed)>>4)-stage` bounds each next stage to
-32768..32767. Only -32768 needs the original clamp to -32767. The kernel
preserves signed floor shifts, modulo-32-bit mix arithmetic, little-endian ring
writes, native int16 output wrap and callee-save registers. It touches no EMAC,
MACSR or interrupt mask. Slap's linked delay body is byte-identical to F6;
WT, pulse and both DSP uploads are unchanged. No queue, DMA or latency changes.
An exact five-pointer/shift-add prototype was slower and was withdrawn before
qualification; the native CF model's register multiply throughput is one cycle.

The target gate now passes **96,880 direct cases**, adding typed-int16 inputs,
extreme clamp vectors and near-matching metadata changes that force the C
fallback. It compares every ring word and guard, PCM, state and callee-save
registers. The fast-entry counter is nonzero (16,495 entries across the gate),
so a passing fallback alone cannot qualify the specialization. The independent
renderer proof still covers 13,824 frames, 9,288 raw-state snapshots and 482,040
native samples. Current paired C→candidate solo means are Slap 9,598.5→9,009.8,
metallic Hat 15,085.4→14,795.1 and white Hat 18,604.4→18,548.1 cycles. These
retain gains over original C, with different branch/layout costs from F6.

The old worst frame 8,958 now takes 87,049 cycles with the same recorded mode,
split, trigger and phase. Its Hat render-plus-delay buckets total 8,696 cycles.
Those fields do not establish identical complete inputs. Frame 5,513 now sets
the 87,413-cycle switching maximum. The candidate's switching and CF-calibration
profiles reproduce their normal frame counts, maxima and total cycles exactly.

The preserved F6 image also passes a fresh unprofiled replay with the same
newly built observer binary. Its normal/profile pair matches at 9,661 returns,
89,715 peak cycles and 591,117,012 total cycles. The older F6 receipt has the
same count and peak but 591,113,212 total cycles, a 3,800-cycle difference with
one different backend-eligibility frame. The cause of that replay difference
is unresolved; the historical receipt remains recorded rather than silently
replaced. No candidate profiling comparison relies on matching that old sum.

| Complete run peak (µs) | PKNHF5 | PKNHF6 | PKNHF7 |
|---|---:|---:|---:|
| CF calibration | 347.515 | 345.273 | 345.379 |
| Backend switching | 334.356 | 339.830 | 331.110 |
| STOP/START, Part and Bank changes | 341.492 | 336.754 | 336.489 |
| White full workload | 324.720 | 320.723 | 320.379 |
| Metallic full workload | 328.818 | 325.739 | 324.890 |
| Pulse full workload | 315.742 | 311.864 | 312.102 |

## Independent audio witness

The new witness seeds one original-author stream from the target's complete
initial Noise Hat object, control history, RNG/hold and clock before the first
source frame. It then evolves independently and is never reseeded at a backend
change. It renders the prefix at source entry and observes actual controls at
`prepare_nh`, the real event boundary. This matters when diagnostic selector
pokes arrive during an in-flight callback.

Every CF or DSP source frame is compared exactly with that stream. Compact
dynamics, phase/carry, RNG/hold and feedback are checked too. The CF ring
comparison follows actual commits: original DSP feedback fills old positions,
while CF frames add their new writes. This proves the retirement holes are
filled correctly without pretending they were synchronously copied at takeover.

The earlier stateless CF arithmetic witness could accept stale input state.
It remains historical evidence for arithmetic only. A frame-entry-only control
snapshot also produced false errors at live mode changes; those intermediate
results are withdrawn. The event-boundary witness must first pass continuous
CF-only calibration before it is used to qualify migration.

One intermediate panel run incorrectly demanded that the editor bank match
the playing bank. The corrected test checks both `0x800065bd` and the actual
frame-ISR bank latch `0x46c7ff40`, as documented in
[PARTS.md](../../../docs/firmware/PARTS.md#3-pattern-changes). Editor and per-track
bank bytes remain recorded observations.

## Fit and validation

| Resource | Used / capacity | Bound |
|---|---:|---|
| A program | 2,023 words | 83 more than PKNHE1 |
| Shared P, both cores combined | 2,381 / 2,404 | 23 free |
| A private P, including startup clear | 771 / 774 | 3 free |
| A declared private X | 513 / 616 | unchanged; unclaimed words are fragmented |
| A low Y | 2,093 / 2,139 | unchanged |
| B qualified program | 2,414 words | every word unchanged from PKNHE1 |
| CF linked text / data / BSS | 1,059,870 / 580 / 997,584 bytes | +53,404 / +16 / +650,812 from PKNHE1 |

The 1,024-frame CF queue occupies 638,976 bytes; the raw inner-shadow object is
11,768 bytes. BSS remains below the explicit 2 MiB initialization bound. The
observed main-stack peak is 1,424/4,096 bytes; the private frame stack peaks at
1,716/4,096. B's private-tail silicon boundary remains unqualified.

The 18,688-byte exact-division table is included in linked text. Relative to
PKNHF1, text grows by 38,664 bytes; PKNHF7 adds 6,056 text bytes over F6
and 15,132 over F5.
Data and BSS do not grow. The typed short-block buffer lowers the observed private stack peak from
F6's 1,844 to 1,716 bytes, within its 4,096-byte bound.

The scheduled DMA formats and DSP X/Y residency are unchanged. The DSP
import parser is split into relocatable shards; exact packing, final-address
disassembly and boot readback cover the resulting image. All twelve retained
stock FX retain their code and dispatch bytes. B's qualified oscillator words
are compared directly with PKNHE1.

The CF shadow and bounded queue have an explicit DRAM cost, recorded with the
actual linked ELF. A loaded nonzero cookie prevents idle work before its
initialization. No readiness decision relies on an uncleared BSS flag.

The standalone gates cover 720 persistent DSP source frames, 2,560 DSP delay
vectors, 768 poisoned-wire imports, 9,996 final clock-state cases, the original
ARM native continuations, and 8,192 additional retained-carry vectors.
The campaign binder requires real STOP/START, Part/Bank changes, eighteen live
ownership transitions, zero transport/worker faults, a bounded sustained
worker backlog, and three 16,384-frame full-workload rows. It also requires
at least 10 µs modeled reserve in every run. The read-only profile must reproduce
the normal switching witness's exact full-ISR count, peak and cycle sum. The
qualified and normal switching runs match: 9,666 returned ISRs and an
87,413-cycle peak. A second CF-calibration profile also reproduces every
completed-ISR cycle total and its 91,180-cycle peak.

The full workload is WT/WT, Slap and Noise Hat, all eight tracks active, all
twelve retained stock FX across sixteen slots, locks, LFOs, scenes and sustained
card reads. Exactness means the persistent Noise Hat source/state/clock/feedback
stream plus every Slap native renderer call given its actual entry state.
Whole-project post-FX PCM equivalence is not asserted. Part/Bank tests retain the
diagnostic algorithm placement, and do not qualify production generation reset
or ALGO/MODE persistence. DSP timing uses the instruction scheduler; physical
cache/card arbitration and B's private-tail boundary still need the unit.

## Reproduction

Run builds that share `out/` serially. Keep the candidate image and observer
unchanged while runtime campaigns execute. These commands reuse this checkout’s
existing hybrid baseline, preserved PKNHF1/F5/F6 comparison proofs, author fixtures,
asset tables and integrated-observer build; the prototype is not a standalone
release build. The builder first proves the original STEMS PIO fix against
the shared stock image and caches that source-bound author reference.

```sh
make emu-cf
env -u NHB_REUSE_CF .venv/bin/python tools/perky/build_noise_hat_handoff_probe.py
.venv/bin/python tools/verify/build_perky_noise_hat_handoff_observer.py
.venv/bin/python tools/verify/verify_perky_noise_hat_handoff_clock.py
.venv/bin/python tools/verify/verify_perky_noise_hat_handoff_inner.py
.venv/bin/python tools/verify/verify_perky_noise_hat_handoff_dsp.py
.venv/bin/python tools/verify/verify_perky_noise_hat_handoff_import.py
.venv/bin/python tools/verify/verify_perky_noise_hat_handoff_resample.py
.venv/bin/python tools/verify/verify_perky_noise_hat_handoff_renderer.py
.venv/bin/python tools/verify/verify_perky_noise_hat_handoff_asm.py
.venv/bin/python tools/verify/verify_perky_cf_synthesis_asm.py
.venv/bin/python tools/verify/qualify_perky_noise_hat_handoff.py --case backend --case cf-calibration --case panel
.venv/bin/python tools/verify/measure_perky_noise_hat_handoff.py --frames 16384
.venv/bin/python tools/verify/profile_perky_noise_hat_handoff.py --work out/perky/hybrid/noise-hat-switch-before --source out/perky/hybrid/noise-hat-handoff-f6
# Replay F6 without attribution, using the same observer binary as its profile.
.venv/bin/python - <<'PY_F6'
import sys, shutil
from pathlib import Path
sys.path.insert(0, 'tools/verify')
import qualify_perky_noise_hat_handoff as q
q.WORK = Path('out/perky/hybrid/noise-hat-switch-before-normal').resolve()
q.SOURCE = Path('out/perky/hybrid/noise-hat-handoff-f6').resolve()
q.WORK.mkdir(exist_ok=True)
shutil.copytree(Path('out/perky/hybrid/noise-hat-switch-before/observer'),
                q.WORK/'observer', dirs_exist_ok=True)
q.run('backend')
PY_F6
.venv/bin/python tools/verify/profile_perky_noise_hat_handoff.py --work out/perky/hybrid/noise-hat-switch-qualified
.venv/bin/python tools/verify/profile_perky_noise_hat_handoff.py --work out/perky/hybrid/noise-hat-switch-cf-qualified --case cf-calibration
make check REMIX=perky-machine
REFHASH_LOCAL=1 REFHASH_JOBS=1 scripts/refhash.sh check
.venv/bin/python tools/verify/verify_perky_noise_hat_handoff_campaign.py
```

The later [production lifecycle integration](PRODUCTION_LIFECYCLE.md) passes
its saved-selector subscopes but fails production reset audio/timing admission.
It is a separate opt-in image; the F7 continuing-history result above remains
valid only within its declared scope.

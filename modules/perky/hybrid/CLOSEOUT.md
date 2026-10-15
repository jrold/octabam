# Goal 2 engineering closeout — 14 October 2026

> Historical Goal 2 closeout. The later bounded software safety investigation is
> [SAFETY_QUALIFICATION.md](SAFETY_QUALIFICATION.md). Its current decision is
> **BLOCKED — COMBINED STACK BOUND NOT ESTABLISHED**. The subsequently authorized
> IPL2→3 operand guard passes its bounded local IRQ and producer tests. Real
> chooser/Part/playing-bank, guarded saved-card reload, dense trigger/lock/UI/DMA
> accounting and paired timing checks have scoped passes. No guard regression,
> corruption or ownership race was reproduced. The interrupted-stock-task plus
> nested-ISR ceiling is still UNVERIFIED; missing evidence is not a firmware bug.
> The new dense modeled maximum is 324.004 µs in both original and guarded images
> at CPU 264/PIT 132 MHz, with 38.808 µs headroom. The previous 323.765 µs was the
> earlier workload maximum. Physical timing and the unwaived missed 20% margin
> are separate from the software stack gate. No guarded installable set is
> qualified and no flash is recommended. Goal 2 stays closed;
> the historical timings and missing-test descriptions below are preserved as history.

**CLOSED — UNQUALIFIED. Assessment complete; implementation qualification incomplete.**
All further Goal 2 performance experiments are stopped. The proposed 20% margin
is not waived. No Goal 3 work, hardware run, packaging, flashing or push occurs.
Rejected iteration 3 remains archived and is not reapplied.

**Functional verdict, independent of timing margin: not fully qualified.**
The source dispatcher, bounded PCM/state/RNG behavior, positive boot/readback,
static placement and short mixed audio paths have substantial local evidence.
No reproduced retained-image synthesis/DSP-identity failure was found in those
executed checks. That does not establish the required complete lifecycle,
sustained integration, stack/backlog, all-effect active processing or package
safety. Removing the 80% gate would still leave qualification incomplete.

## Identity and evidence policy

Existing branch: `perky-cf-dsp-hybrid`; assessment starts at
`9b8039491631dfcb88f71e5c83662638a44f2820`. Compiled inputs are committed at
`19d1810429765d4a1c4e18bd24d92b9fa2c6f1f3` and match current source bytes.
Only reports change during closeout. The commit containing this document is the
closeout commit; its exact final HEAD and working-tree state are also saved in
`out/perky/hybrid/closeout/FINAL_GIT.json` after committing, and reported to the user.

Retained **simulation-input MAIN**, 1,483,674 bytes:
`out/perky/hybrid/probe/mainos_PKHYB2P.bin`, SHA256
`46bd31dba62651500de6c672ec0e3e50c38533f8edbe39cd12e200318c93ca2a`.
ELF SHA256 `290b82c30c0f813df159a555a01f5f81cb43b2cb93ebe9571196491a07fad0e6`.
Source identity `71e6b1ed98a9874b0e58aad61ed31f71eefe901818fca69a2d2a54628997c743`.
**No legitimately qualified diagnostic firmware set exists.** Matching current
ELEK/card/MIDI files are absent. Old archived wrappers are not substitutes.
The raw MAIN size neither proves nor disproves compliance with the encrypted
1 MiB payload cap. No flash hash or installation recommendation is issued.

The audit verifies actual artifact/source/tool hashes, historical frozen inputs,
ancestry, log hashes, the unchanged rejected/restored evidence and the preserved
branch. `CLOSEOUT.json` contains the exact commands, identities, gate statuses
and source citations. Baseline/CF-only/PERKY4S successes are labeled as such;
they are not silently promoted to integrated-hybrid qualification. The baseline
execution's only source deltas are profiler-switch setup/assertions in the
workload helper and decoder trailing whitespace; CF synthesis inputs are exact.

## Local test disposition

| Gate | Exact observed result | Qualification limit |
|---|---|---|
| Corrected emulator | Fresh closeout CTest **9/9 PASS**, including timing, EMAC, divide and HDI08 tests | Instruction/model regression tests; no silicon calibration |
| Foundation | `verify_perky_hybrid.py --stage baseline --work out/perky/hybrid/resume-fixes`: **18/18 PASS_FOR_PROBE_BUILD** | Prerequisite; cached completed-release gates concern PERKY4S, not hybrid |
| Original CF oracle | **19 sections, 22,098 cases, 325,277 state checks, 3,046,272 PCM samples, 0 failures; 138 release calls** | Engine/control conformance on matching CF source |
| Retained hybrid runtime | **1,024 frames / 2,048 exact source records**, full two-voice state/RNG, 16 splits, **8** corrupt-smoother fallback cases: PASS | Bounded callback execution, not complete lifecycle |
| Mixed dispatcher/transport | Single owner; **192** original native record comparisons, **288** CF split cases; cursor/tail/independence: PASS | Stock delegation and direct-call behavior; not every stock UI path |
| UI/control adapter | ALGO bounds and PMTR formatter stubs, six-slot/order mapping: PASS | Complete all-six-control scene/crossfader/LFO/persistence workflow **not established** |
| Positive boot | Loader once/no fatal, RTOS handoff; loaded runtime exact except three expected READY cookies; A/B uploads/pointers/append exact: PASS | Stops at RTOS handoff; not project/lifecycle/output qualification |
| Dirty state/readiness | **5,922 B** voice/template poisoning, callback asset-write watch, UI-no-live-reset fixture: PASS | Not a full hybrid BSS/native-global poison or all-load boot-fault proof |
| Frozen DSP | All identity checks PASS; exact source/tables/layout/bootstrap and ordered A/B uploads | Private P **770/774** each; shared P **2,398+6=2,404**, four private spare words unused |
| Stock FX identity/readback | Both startup-register sets and retained FX programs/dispatch exact; **4 configurations × 600 frames**, all 12 assigned, both-core P/X/Y/table readback: PASS | Does not independently assert nonzero processing by every effect |
| Real project/sequencer/audio | **22,450-frame** T2/T6 split drift; **1,000-frame** mixed snare smoke; separate **2,400-frame** eight-track source/post-FX capture: PASS | Short, specific fixtures. Historical T3 failure does not reproduce; no assertions weakened |
| Static memory | Actual ELF/layout, cached/uncached normalization, reserve containment and mutual extent nonoverlap: PASS | Physical cache/DMA/recorder interference not exhaustively modeled/tested |
| Profiler logic/export | One count/ISR; 32-bit wrap fixture **64 ticks**; snapshot collision/no-spin; UI ABI and actual stock-FS **1,864 B PRF** export after STOP: PASS locally | Silicon timer/read cost/export and release-to-entry coverage **unverified** |
| Negative evidence/profile tests | Fresh **9/9** evidence-refusal tests; **6/6** malformed profile files rejected; generic release guards PASS | Not current-image package/loader corruption coverage |
| Reproducibility/restoration | MAIN, fragmented normal, ELF and raw runtime bit-identical to retained pre-iteration-3 image: PASS | No rejected runtime change remains |
| Current package | Wrapper command **exit 1: missing ELEK**; combined negative gate **exit 1: missing card** | Current cap/header/checksum/decrypt/roundtrip/corruption tests **not executed**; no proven malformed package/overflow |
| Full integration/lifecycle | **NOT EXECUTED to contract** | Seven >=60 s pairings, extra/reversed/heavier pairings, worst >=600 s, complete stock Bank/Part, long transition/tail/reversion stress, per-effect active audio, UI/event backlog and independent per-core completion |
| Stack/memory stress | **UNVERIFIED** | Declared 4,096 B stack reserve is not a measured nested call/interrupt ceiling; full sampler/recorder/streaming/DMA and all-runtime-state lifecycle scope missing |
| Aggregate probe qualification | **BLOCKED**, remains blocked independently of 80% gate | Missing safety/integration/package evidence and failed proposed margin |

The retained smoke and readback results are for the hybrid image, not merely
an old CF-only build. Candidate iteration-3 tests remain separate historical
evidence: **4,096** callback boundaries, including **242** empty callbacks and
all **17** splits, exact slots/state/RNG/cursor/counters, PASS before rejection.
No all-tests functional PASS is inferred from the component/reference passes.

Memory detail: linked `.text` 349,728 B, `.rodata` 348 B, `.data` 548 B,
`.bss` 218,560 B; raw loaded span 351,300 B includes link alignment. Waveforms
occupy 200,704 B BSS; two live CF states 3,948 B plus 1,974 B pristine template.
Runtime reservation `0x40c005e0..0x41600de0`; BSS ends `0x40c8b7e4`, packed
stage `0x40c8c000..0x40cc29da`; 2,076 B gap before stage and 9,692,166 B after
stage inside the reserve. These unused bytes do not prove stack or DMA safety.
The 1 MiB cap is **encrypted payload**, with 12 B outer overhead assessed
separately; `MEMORY.json.wrappers` is empty for this retained build.

## Consolidated performance evidence

A frame is 16/44,100 s = **362.811791 us**. The proposed advancement ceiling
is **290.249433 us**. Recorded CPU conversions use **266 MHz**.

| Artifact/case | Window | Frames | Maximum | Observed duration misses |
|---|---|---:|---:|---:|
| Fixed initialization/profiler, before optimization; delayed-trigger/Part-index pokes | Runtime late timer stamp |4,000|368.167 us|2|
| Same pre-optimization build, STOP/export case | Runtime late timer stamp |4,000|374.538 us|4|
| Iteration 1, same delayed-trigger case | Runtime late timer stamp |4,000|349.598 us|0|
| Iteration 2, same delayed-trigger case | Runtime late timer stamp |4,000|315.871 us|0|
| Retained final snare/snare, profiler on | Complete ISR service-code window |4,000|**319.860902 us**|**0**|
| Retained, profiler off / CF disarmed comparisons | Complete service-code window |4,000 each|317.593985 /222.221805 us|0 /0|
| Rejected zero-render candidate | Complete service-code window |4,000|320.011278 us|0|

**Current retained image: no observed ISR-duration miss in the accepted short
measurements. Historical true pre-optimization overruns did occur.** Those
older images cannot be used to assert a current miss; current short passes
cannot establish all workloads fit. The latest rejected image was restored
bit-identically, so 319.860902 us remains the retained maximum. Retained p99
is 213.917293 us and mean 196.577683 us in the matched-PC run.

The retained measurement has **42.950889 us** nominal headroom: 11.838% of the
frame, equivalent to only 13.428% slowdown relative to measured service. It is
**29.611469 us above** the unwaived engineering ceiling. The deadline and
engineering-margin statements are separate; this result proves neither
infeasibility nor physical safety.

PC watches match all 4,000 frames, from the instruction after the hook's first
LEA to just before RTE; adding the model's LEA 1 + RTE 10 cycles gives 85,083
cycles. This is the whole **ISR service-code window**, including stock CF work,
source callbacks, waits and probe bookkeeping. It does **not** bound pending
interrupt latency, exception-entry/vector costs before that hook, or total
release-to-completion/backlog under arbitrary task/interrupt traffic. Runtime
late-stamp maxima exclude a small entry/footer and are not directly interchangeable
with the complete PC spans. No concurrent DSP execution times are added to CF time.

Mean conditional instrumentation delta is 3.194657 us; common hooks remain in
the off image path. Difference of maxima is not a worst-overhead bound. Two
HC polling sites are not proof of two independent DSP completion times.
Accepted short exchange counters reported 0 words-not-in-time, not a calibrated
hardware underrun/overrun proof. No independent calibrated per-core maxima exist.

Retractions preserved: recovery's 98,632 cycles / 370.797 us and one over-budget
count measured **ACK-to-ACK task-inclusive CPU work**, not ISR latency. Final
retained ACK-window peak 350.500 us likewise is not an ISR maximum or a quantity
to add to 319.861 us. The inherited 88 MHz/callback-grouping profiler and invalid
one-byte off/disarmed pokes are excluded. Prior 115.2 us / 66 us CF-headroom claims
in CONTRACT.md are retracted. Rejecting iteration 3 is permanent historical
evidence, not permission to repeat optimization.

## What the emulator establishes and what remains a hardware risk

The corrected core executes the actual linked CF instructions and both DSP
payloads, and pins important instruction arithmetic/timing regressions. With
`--cf-cycles-clock 1.0`, audio timing follows modeled cycles rather than a fitted
instruction-rate shortcut. The results are useful repeatable model observations.
They are **not** a physical worst-case execution-time bound:

- `vendor/mc68k/Musashi/m68kcfcycles.h` explicitly assumes cache hits and zero-wait
  operands, mixes MCF5206E table costs with V4e adjustments, and retains inherited
  estimates for uncovered instructions/exceptions. It does not model the physical
  cache hierarchy, SDRAM/FlexBus waits, all DMA contention or all pipeline effects.
- There is a concrete clock-basis discrepancy: CHIP.md documents stock PCR
  `0x16777731`, stored CPU 264 MHz and bus 132 MHz; the workload/cycle clock uses
  266 MHz. Purely rescaling the same 85,083 cycles by 264 gives **322.284091 us**
  and 40.527700 us nominal headroom. This is sensitivity arithmetic, **not** a
  rerun or corrected system prediction; clock-dependent scheduling can change.
- Real cache misses/bus contention and pending higher-priority/interrupt-masked
  work could consume the nominal 43 us; their bound is unknown. Known earlier
  CF timing discrepancies prevent treating the present estimate as conservative.
- Stock source delivery, two-core handshakes and deadlines depend on physical
  concurrency. Exact DSP bytes preserve semantics/placement; they do not establish
  mixed-load completion time. A late frame can produce stale/dropout/clicking audio
  or stalled playback; a wait-loop stall can also prevent UI STOP/export.
- The maximum is the first measured frame. A very short run still encounters
  cold activation and event work. The probe counts misses but does not implement
  an automatic probe-specific disarm/abort. `pk_hybrid_cf_arm` defaults to 1.
- The timer is a stock hardware register, supported by existing cfmeter source:
  DTMR3=0x000b, bus/1, 132 MHz. Hybrid silicon read overhead, wrap/capture coverage
  and STOP export are not measured. Its boot calibration returning 0 is not zero
  physical cost. File export is outside the callback but still depends on a
  responsive UI/card and may contend with audio that continues after STOP.
- Static placement and callback tests do not close stack/nested-interrupt,
  original native-global BSS, lifecycle or physical recorder/DMA safety gaps.
  No corruption has been demonstrated by those missing tests; safety is unproven.

## Restricted diagnostic hardware probe assessment

A diagnostic probe can in principle be justified to discover physical timing
before production qualification. Requiring all physical timing answers before
any measurement would be circular. That does not waive **independent safety**
gates, nor make a short requested duration a containment mechanism.

**The existing candidate is not sufficiently qualified for such a recommendation
now.** Essential gaps are clock/timer/read-cost and measurement-scope reconciliation;
boot/BSS/lifecycle and stack/nesting safety; bounded representative mixed integration,
retained effect activity and core completion/backlog evidence; and exact current
package/cap/roundtrip/corruption checks. Existing bytes default fully CF-armed
and provide no probe-specific automatic abort. There is no qualified installable
set or approved restricted activation/stop/failure/capture protocol. No image is
packaged here, and the unwaived margin remains a separate failed gate.

A future **separately authorized** review would need those independent gates,
known rollback identity, a deliberately bounded activation/stop/capture plan and
an explicit decision about the failed engineering margin before installation.
Automatic STOP-to-card `.PRF` extraction can avoid CF METER readings; a frozen-DSP
meter insert is not proposed. Nothing in this closeout authorizes that future run.

## Final recommendation and stop

**Recommendation: targeted, non-optimization investigation of the demonstrated
clock/timer-basis discrepancy and missing lifecycle/stack/package safety evidence,
before considering a controlled hardware probe.** No hardware probe now. There
is insufficient evidence to label the design infeasible, and insufficient evidence
to label it functionally or physically qualified. Goal 2 investigation ends here.
No further optimization, new runtime change, package, flash, push, new branch,
worktree or Goal 3 was performed during closeout.

The preserved `perky-machines` ref remains
`4ff6aa4456502424bff5bea62e7b55aa36d7b4a4`. The only unrelated untracked file is
`PERKY_Hybrid_Goal2_Gemini_Argon4.txt`, SHA256
`285b0b0dbf5cf90bb65da481e97cf740858148c9c4e0377d4ebbe8320263766a`;
it was neither edited nor staged. Prior refhash helper checkouts were already
removed and the compliant single-checkout 24-case run passed; this closeout
creates none. All previously verified code/tests remain locally committed.
